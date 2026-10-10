"""Durable pipeline workflow (§2 process flow, §3.5).

Spec Intake -> Build+Sandbox Test -> Eval/Gate -> (loop to Build on fail)
  -> Register -> Deploy (separate long-lived workflow, see
  registry_promotion_waiter.py) -> Monitor -> Retire or Version

Spec Intake (§3.1) already happened manually — see `harness/swe-agent/SKILL.md`
for what's deferred. Build (§3.2) and Sandbox Test (§3.3) are collapsed into
one activity (`run_swe_agent_activity`) that runs the SWE agent inside a real
E2B sandbox. Eval-Gate (§3.6) and Register (§3.7) are real activities below.
Deploy (§3.7) is intentionally NOT part of this workflow — its SLA (days to
weeks, waiting on a human to merge the registry PR) is wildly different from
Build/Gate's minutes, so it runs in its own long-lived workflow instead of
sharing this execution's history.
"""
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError, is_cancelled_exception

# activities.py loads eval/braintrust/eval.config.py via importlib at module
# import time (Path.resolve(), exec_module) — real filesystem/non-
# deterministic work the workflow sandbox otherwise refuses to run during
# workflow validation. It's never executed as workflow code (only referenced
# by name for execute_activity), so pass it through, along with the e2b SDK
# activities.py uses to run the SWE agent.
with workflow.unsafe.imports_passed_through():
    from activities import (
        acquire_seat_activity,
        architect_stage_activity,
        ensure_target_pr_activity,
        eval_gate_activity,
        register_activity,
        release_seat_activity,
        report_seat_failure_activity,
        run_swe_agent_activity,
    )

MAX_BUILD_ATTEMPTS = 3

# Shared budget for the architect/plan-review loop (004's fan-out/judge
# stage, gated by a human plan_approved/plan_rejected signal). Charged per
# specs/004-architect-fanout-judge/contracts/architect-agent-interface.md's
# CO-1/CO-2/CO-3 consumer obligations — see the plan-review loop below.
MAX_PLAN_ATTEMPTS = 3

# Activities with side effects (pushing a branch, opening a PR) are not
# idempotent, so Temporal must not re-run them on its own — the Build->Gate
# loop below is the only retry they get.
_NO_AUTO_RETRY = RetryPolicy(maximum_attempts=1)

# The Eval-Gate is read-only, and its only expected failure mode is a
# transient Braintrust API error, so let Temporal back off and retry it.
_TRANSIENT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    maximum_interval=timedelta(seconds=60),
    backoff_coefficient=2.0,
    maximum_attempts=4,
)

# Credential-pool seat handoffs (specs/009) per stage invocation — a budget of
# its own: a seat running out is neither a Build failure nor a plan failure,
# so it never charges MAX_BUILD_ATTEMPTS / MAX_PLAN_ATTEMPTS (FR-019).
MAX_SEAT_HANDOFFS = 4

# The seat activities only call updates on CredentialPoolWorkflow and are
# idempotent per lease key, so transient-retry them freely.
_SEAT_ACTIVITY_OPTS = {
    "start_to_close_timeout": timedelta(seconds=30),
    "retry_policy": _TRANSIENT_RETRY,
}
_SEAT_OUTCOMES = {"SeatExhausted": "exhausted", "SeatInvalid": "invalid"}
# Raised by _with_seat itself (workflow code, not an activity): the pool, not
# the stage, failed — never charged to a stage's own retry budget.
_POOL_FAILURES = {"CredentialPoolExhausted", "SeatHandoffsExhausted", "CredentialPoolUnavailable"}


@workflow.defn
class AgentPipelineWorkflow:
    def __init__(self) -> None:
        self._plan_decision: str | None = None  # None | "approved" | "rejected"
        self._plan_feedback: str | None = None

    @workflow.signal
    def plan_approved(self) -> None:
        self._plan_decision = "approved"

    @workflow.signal
    def plan_rejected(self, feedback: str) -> None:
        self._plan_decision = "rejected"
        self._plan_feedback = feedback

    async def _with_seat(
        self, agent: str, stage: str, invocation: int, activity_fn, args: list, **opts,
    ) -> dict:
        """Run one seat-backed stage invocation on a credential-pool seat
        (specs/009, contracts/credential-pool-interface.md): lease a seat,
        run `activity_fn(*args, seat_id)`, release the seat with the usage
        the stage reported. On SeatExhausted/SeatInvalid the seat is reported
        to the pool (which drops the lease) and the stage re-runs on another
        seat — the stage resumes from its own pushed checkpoints."""
        workflow_id = workflow.info().workflow_id
        for handoff in range(MAX_SEAT_HANDOFFS + 1):
            lease_key = f"{workflow_id}/{stage}/{invocation}/{handoff}"
            lease = await self._pool_call(acquire_seat_activity, [agent, lease_key])
            seat_id = lease["seat_id"]
            if seat_id is None:
                raise ApplicationError(
                    f"No credential-pool seat available for {agent} ({stage})",
                    lease["earliest_reset"],
                    type="CredentialPoolExhausted",
                    non_retryable=True,
                )
            try:
                result = await workflow.execute_activity(
                    activity_fn, args=[*args, seat_id], **opts
                )
            except ActivityError as e:
                kind = _SEAT_OUTCOMES.get(getattr(e.cause, "type", None))
                if kind is None:
                    await self._release_seat(seat_id, lease_key, None, None)
                    raise
                details = list(getattr(e.cause, "details", None) or [])
                resets_at = details[1] if kind == "exhausted" and len(details) > 1 else None
                await self._pool_call(
                    report_seat_failure_activity, [seat_id, lease_key, kind, resets_at],
                )
                continue
            # Not BaseException: a workflow cancel (CancelledError) must
            # propagate untouched; a leaked lease ages out via LEASE_TTL.
            except Exception:
                await self._release_seat(seat_id, lease_key, None, None)
                raise
            await self._release_seat(
                seat_id, lease_key, result.get("utilization"), result.get("rate_limit_type")
            )
            return result
        raise ApplicationError(
            f"Seat handoff budget ({MAX_SEAT_HANDOFFS}) exhausted for {stage}",
            stage,
            MAX_SEAT_HANDOFFS,
            type="SeatHandoffsExhausted",
            non_retryable=True,
        )

    async def _pool_call(self, activity_fn, args: list):
        """A seat activity, its failure (after _TRANSIENT_RETRY) typed as the
        pool's own: a stage's retry budget must never be charged for it
        (FR-019) — callers re-raise anything in _POOL_FAILURES."""
        try:
            return await workflow.execute_activity(activity_fn, args=args, **_SEAT_ACTIVITY_OPTS)
        except ActivityError as e:
            # A workflow cancel arrives as ActivityError(cause=CancelledError);
            # re-typing it would turn Cancelled into Failed, or let
            # _release_seat swallow it.
            if is_cancelled_exception(e):
                raise
            raise ApplicationError(
                f"Credential pool unavailable: {e.cause or e}",
                type="CredentialPoolUnavailable",
                non_retryable=True,
            ) from e

    async def _release_seat(
        self, seat_id: str, lease_key: str,
        utilization: float | None, rate_limit_type: str | None,
    ) -> None:
        """Best effort: a failed release must neither mask the stage's own
        outcome (its result, or its error) nor discard a finished stage. The
        lease then ages out via LEASE_TTL; only the usage figure is lost."""
        try:
            await self._pool_call(
                release_seat_activity, [seat_id, lease_key, utilization, rate_limit_type],
            )
        except ApplicationError as e:
            workflow.logger.warning("Seat %s release failed: %s", seat_id, e)

    @workflow.run
    async def run(self, repo: str, branch: str, agent_name: str, version: str) -> str:
        pr_url: str | None = None

        # Architect fan-out/judge stage (004) ahead of Build, gated by a
        # human plan_approved/plan_rejected signal. Patched so a workflow
        # started before this change (none exist today, but the marker is
        # cheap) replays deterministically without it.
        if workflow.patched("architect-stage-v1"):
            pr_url = await workflow.execute_activity(
                ensure_target_pr_activity,
                args=[repo, branch],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=_TRANSIENT_RETRY,
            )

            plan_feedback: str | None = None
            plan_attempt = 0
            charged = 0
            # Its own patch id, not the Build loop's "seat-pool-v1": patched()
            # is memoized per id, so sharing one would make this earlier call
            # decide the Build loop's branch on replay of older histories.
            on_seats = workflow.patched("architect-seat-pool-v1")
            while True:
                plan_attempt += 1
                try:
                    if on_seats:
                        # specs/009: on a credential-pool seat; seat handoffs
                        # happen inside _with_seat and never charge the budget.
                        result = await self._with_seat(
                            "architect-agent", "architect", plan_attempt,
                            architect_stage_activity,
                            [repo, branch, pr_url, plan_attempt, plan_feedback],
                            start_to_close_timeout=timedelta(minutes=30),
                            retry_policy=_TRANSIENT_RETRY,
                        )
                    else:
                        result = await workflow.execute_activity(
                            architect_stage_activity,
                            args=[repo, branch, pr_url, plan_attempt, plan_feedback],
                            start_to_close_timeout=timedelta(minutes=30),
                            retry_policy=_TRANSIENT_RETRY,
                        )
                except Exception as e:  # noqa: BLE001 — ActivityError wraps the ApplicationError cause
                    # specs/009: no seat to run on (or the handoff budget is
                    # spent) says nothing about the plan — fail the run
                    # without charging, like CO-3 below.
                    if isinstance(e, ApplicationError) and e.type in _POOL_FAILURES:
                        raise
                    cause = getattr(e, "cause", None)
                    # A cancel is the operator's, not a plan failure; and a
                    # pool failure raised activity-side (e.g. a seat's token
                    # env var unset) is the pool's — neither is charged.
                    if is_cancelled_exception(e) or getattr(cause, "type", None) in _POOL_FAILURES:
                        raise
                    if getattr(cause, "type", None) == "MalformedRetriesExhausted":
                        # CO-3: not a budget-charging failure — fail the run.
                        raise ApplicationError(
                            f"Architect stage failed: {cause}"
                        ) from e
                    # CO-2: any other stage failure is deterministic — charge.
                    charged += 1
                    if charged >= MAX_PLAN_ATTEMPTS:
                        raise ApplicationError(
                            f"Plan attempt budget ({MAX_PLAN_ATTEMPTS}) exhausted: {cause or e}"
                        ) from e
                    plan_feedback = (
                        f"Architect stage failed (charged {charged}/{MAX_PLAN_ATTEMPTS}): "
                        f"{cause or e}"
                    )
                    continue

                # CO-4: idempotent_hit results carry no other key — branch
                # on it before reading gap_round_ran.
                if not result.get("idempotent_hit") and result.get("gap_round_ran"):
                    # CO-1: a gap round charges the budget even if the
                    # resulting plan is later approved.
                    charged += 1
                    if charged >= MAX_PLAN_ATTEMPTS:
                        raise ApplicationError(
                            f"Plan attempt budget ({MAX_PLAN_ATTEMPTS}) exhausted after gap round"
                        )

                # Reset immediately before waiting, not before the activity
                # call above: the stage's PR comment for this attempt is
                # posted at the end of run_architect_stage, so any signal
                # received during the activity call is necessarily a stale
                # reply to a prior attempt's comment (FR-016).
                self._plan_decision = None
                self._plan_feedback = None
                await workflow.wait_condition(lambda: self._plan_decision is not None)

                if self._plan_decision == "approved":
                    break
                charged += 1
                if charged >= MAX_PLAN_ATTEMPTS:
                    raise ApplicationError(
                        f"Plan attempt budget ({MAX_PLAN_ATTEMPTS}) exhausted after human rejection"
                    )
                plan_feedback = self._plan_feedback

        feedback: str | None = None
        eval_result: dict = {}

        for attempt in range(1, MAX_BUILD_ATTEMPTS + 1):
            if workflow.patched("seat-pool-v1"):
                # Build on a credential-pool seat (specs/009); seat handoffs
                # happen inside _with_seat and never charge this loop.
                build = await self._with_seat(
                    "swe-agent", "build", attempt, run_swe_agent_activity,
                    [repo, branch, feedback],
                    start_to_close_timeout=timedelta(minutes=60),
                    retry_policy=_NO_AUTO_RETRY,
                )
                pr_url = build["pr_url"]
            else:
                pr_url = await workflow.execute_activity(
                    run_swe_agent_activity,
                    args=[repo, branch, feedback],
                    start_to_close_timeout=timedelta(minutes=20),
                    retry_policy=_NO_AUTO_RETRY,
                )
            eval_result = await workflow.execute_activity(
                eval_gate_activity,
                args=[repo, branch, {"pr_url": pr_url, "exit_code": 0}],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=_TRANSIENT_RETRY,
            )
            if eval_result["passed"]:
                return await workflow.execute_activity(
                    register_activity,
                    args=[repo, agent_name, version, eval_result],
                    start_to_close_timeout=timedelta(minutes=5),
                    retry_policy=_NO_AUTO_RETRY,
                )
            # Feed the gate's verdict back into the next Build attempt.
            feedback = f"Eval-Gate failed (attempt {attempt}): {eval_result['reason']}"

        raise ApplicationError(
            f"Eval-Gate did not pass after {MAX_BUILD_ATTEMPTS} attempts: "
            f"{eval_result['reason']}"
        )
