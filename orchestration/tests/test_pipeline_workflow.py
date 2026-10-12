"""AgentPipelineWorkflow's plan-review loop — the narrow architect-agent
Temporal-wiring slice of specs/005-pipeline-mode-signals-escalation.

Runs against a real local Temporal server (`make up`), like every other
Temporal-facing test in this repo (no WorkflowEnvironment/time-skipping
usage exists anywhere here — see webhook_bridge/tests/test_integration.py).
Every stage activity is stubbed by name, so no real git/gh/e2b/model call
ever happens: this test is about the workflow's own CO-1/CO-2/CO-3/CO-4
budget-charging and signal-gating logic, and (specs/009) its credential-pool
seat leasing/handoff, not about run_architect_stage() or
run_swe_agent_activity() themselves (each has its own test suite). The seat
activities and CredentialPoolWorkflow are the real ones, against a per-test
pool. `_harness` terminates the pool and the pipeline workflow in a `finally`,
and both carry TEST_WORKFLOW_TIMEOUT, so a killed run leaves nothing running
for long (specs/014).
"""
import asyncio
import contextlib
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from temporalio import activity
from temporalio.api.enums.v1 import EventType
from temporalio.client import Client, WorkflowExecutionStatus, WorkflowFailureError
from temporalio.exceptions import ApplicationError, CancelledError
from temporalio.worker import Worker

from activities import (
    acquire_seat_activity,
    release_seat_activity,
    report_seat_failure_activity,
)
from tests._workflow_limits import TEST_WORKFLOW_TIMEOUT, recorded_limit
from workflows.credential_pool import CredentialPoolWorkflow
from workflows.pipeline_workflow import AgentPipelineWorkflow

pytestmark = pytest.mark.temporal

TASK_QUEUE = "agent-factory-pipeline-test"
BUILD_READING_RESETS_AT = "2099-01-01T05:00:00+00:00"  # specs/011 F2
REPO = "owner/repo"


def _pool(*seat_ids: str, max_concurrent: int = 1) -> dict:
    """A pool whose seats all serve every agent, in the given order."""
    seat_ids = seat_ids or ("seat-a",)
    return {
        "seats": {
            s: {"token_env": "CLAUDE_OAUTH_SEAT_A", "max_concurrent": max_concurrent,
                "token_expires_on": None}
            for s in seat_ids
        },
        "assignments": {a: list(seat_ids) for a in ("swe-agent", "architect-agent")},
    }


def _pipeline_id(run_id: str) -> str:
    return f"pipeline-workflow-test-{run_id}"


async def _start(client, run_id):
    return await client.start_workflow(
        AgentPipelineWorkflow.run,
        args=[REPO, f"branch-{run_id}", f"agent-{run_id}", "1"],
        id=_pipeline_id(run_id),
        task_queue=f"{TASK_QUEUE}-{run_id}",
        execution_timeout=TEST_WORKFLOW_TIMEOUT,
    )


@contextlib.asynccontextmanager
async def _harness(
    client: Client, run_id: str, activities: list, pool: dict | None = None,
    seat_overrides: list | None = None,
):
    """Worker for the pipeline + a real CredentialPoolWorkflow (specs/009),
    with the real seat activities pointed at that per-test pool.
    `seat_overrides` replaces real seat activities by registered name."""
    overridden = {a.__temporal_activity_definition.name for a in seat_overrides or []}
    seat_activities = [
        a for a in (acquire_seat_activity, release_seat_activity, report_seat_failure_activity)
        if a.__name__ not in overridden
    ] + list(seat_overrides or [])
    task_queue = f"{TASK_QUEUE}-{run_id}"
    pool_id = f"credential-pool-test-{run_id}"
    previous = os.environ.get("CREDENTIAL_POOL_ID")
    os.environ["CREDENTIAL_POOL_ID"] = pool_id
    try:
        async with Worker(
            client, task_queue=task_queue,
            workflows=[AgentPipelineWorkflow, CredentialPoolWorkflow],
            activities=[*activities, *seat_activities],
        ):
            pool_handle = await client.start_workflow(
                CredentialPoolWorkflow.run, pool or _pool(), id=pool_id, task_queue=task_queue,
                execution_timeout=TEST_WORKFLOW_TIMEOUT,
            )
            try:
                yield pool_handle
            finally:
                # specs/014: the pipeline workflow too, which a failed test leaves parked.
                with contextlib.suppress(Exception):  # best-effort cleanup only
                    await client.get_workflow_handle(_pipeline_id(run_id)).terminate()
                with contextlib.suppress(Exception):  # best-effort cleanup only
                    await pool_handle.terminate()
    finally:
        if previous is None:
            os.environ.pop("CREDENTIAL_POOL_ID", None)
        else:
            os.environ["CREDENTIAL_POOL_ID"] = previous


async def _connect_or_skip() -> Client:
    try:
        return await Client.connect("localhost:7233")
    except Exception as exc:  # noqa: BLE001 - environment-dependent skip
        pytest.skip(f"Temporal not reachable at localhost:7233: {exc}")


async def _wait_until(predicate, timeout: float = 10.0) -> None:
    for _ in range(int(timeout / 0.05)):
        if predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"condition not met within {timeout}s")


async def _wait_plan_parked(handle, n_results: int, timeout: float = 10.0) -> None:
    """Wait until the workflow has recorded `n_results` architect activity
    results (completed or failed) AND finished the workflow task after the
    last one — i.e. it is parked in the plan-decision wait_condition.

    Signalling as soon as the stub merely *records* the Nth call races the
    workflow: if the signal lands in the same activation as the activity's
    completion, the SDK applies the signal first, and the workflow's
    deliberate post-activity reset of `_plan_decision` (stale-signal guard,
    FR-016) then drops it — the run waits forever. On seats (specs/009) the
    stage's lease release runs after the architect result, so "parked" also
    needs no activity still pending.
    """
    done = {EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED, EventType.EVENT_TYPE_ACTIVITY_TASK_FAILED}
    for _ in range(int(timeout / 0.05)):
        events = [e async for e in handle.fetch_history_events()]
        architect_scheduled = {
            e.event_id for e in events
            if e.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED
            and e.activity_task_scheduled_event_attributes.activity_type.name
            == "architect_stage_activity"
        }
        results = [
            e for e in events if e.event_type in done
            and (e.activity_task_completed_event_attributes.scheduled_event_id
                 if e.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED
                 else e.activity_task_failed_event_attributes.scheduled_event_id)
            in architect_scheduled
        ]
        if (len(results) >= n_results
                and events[-1].event_type == EventType.EVENT_TYPE_WORKFLOW_TASK_COMPLETED
                and not (await handle.describe()).raw_description.pending_activities):
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"workflow not parked after {n_results} architect result(s) in {timeout}s")


def _stub_activities(calls: list, plan_outcomes: list, build_outcomes: list | None = None):
    """plan_outcomes: consumed in order by architect_stage_activity, one
    per call — either a result dict, or an ApplicationError to raise
    (already typed/non_retryable, exactly as the real activities.py
    ::architect_stage_activity would map a RuntimeError/ValueError before
    it ever reaches the workflow — this test is about the workflow's
    handling of that mapped error, not the mapping itself).

    build_outcomes: same, for run_swe_agent_activity (specs/009) — an
    ApplicationError (e.g. type="SeatExhausted") to raise, or None for the
    default success result; once exhausted, every call succeeds."""
    plan_iter = iter(plan_outcomes)
    build_iter = iter(build_outcomes or [])

    @activity.defn(name="ensure_target_pr_activity")
    async def ensure_target_pr_activity(repo: str, branch: str) -> str:
        calls.append(("ensure_target_pr_activity", repo, branch))
        return "https://github.com/owner/repo/pull/1"

    @activity.defn(name="architect_stage_activity")
    async def architect_stage_activity(
        repo: str, branch: str, pr_url: str, attempt: int, feedback: str | None = None,
        seat_id: str | None = None,
    ) -> dict:
        calls.append(("architect_stage_activity", attempt, feedback))
        calls.append(("architect_seat", seat_id))
        outcome = next(plan_iter)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    @activity.defn(name="run_swe_agent_activity")
    async def run_swe_agent_activity(
        repo: str, branch: str, feedback: str | None, seat_id: str, handoff: int = 0,
    ) -> dict:
        calls.append(("run_swe_agent_activity", feedback, seat_id, handoff))
        outcome = next(build_iter, None)
        if isinstance(outcome, Exception):
            raise outcome
        return {"pr_url": "https://github.com/owner/repo/pull/1", "seat_id": seat_id,
                "utilization": 0.25, "rate_limit_type": "five_hour",
                "utilization_resets_at": BUILD_READING_RESETS_AT}

    @activity.defn(name="eval_gate_activity")
    async def eval_gate_activity(repo: str, branch: str, sandbox_trace: dict) -> dict:
        calls.append(("eval_gate_activity",))
        return {"passed": True, "criteria": ["SC-001"], "reason": ""}

    @activity.defn(name="register_activity")
    async def register_activity(
        repo: str, agent_name: str, version: str, eval_result: dict
    ) -> str:
        calls.append(("register_activity",))
        return "https://github.com/factory/repo/pull/2"

    return [
        ensure_target_pr_activity,
        architect_stage_activity,
        run_swe_agent_activity,
        eval_gate_activity,
        register_activity,
    ]


def _plan_result(*, gap_round_ran: bool = False, idempotent_hit: bool = False) -> dict:
    if idempotent_hit:
        return {"attempt": 1, "comment_body": "existing", "idempotent_hit": True}
    return {
        "attempt": 1,
        "plan_md": "plan", "tasks_md": "tasks", "adrs": [],
        "winner_index": 0, "grafted_from": None, "rationale": "r",
        "scores": {}, "completeness": {"gap_found": False},
        "gap_round_ran": gap_round_ran, "invalid_candidates": [],
        "malformed_retries_used": 0, "commit_sha": "abc123",
        "comment_body": "posted",
    }


async def test_approve_first_pass_no_gap_round_charges_nothing():
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    activities = _stub_activities(calls, [_plan_result()])

    async with _harness(client, run_id, activities):
        handle = await _start(client, run_id)
        await _wait_plan_parked(handle, 1)
        await handle.signal(AgentPipelineWorkflow.plan_approved)
        result = await handle.result()

    assert result == "https://github.com/factory/repo/pull/2"
    plan_calls = [c for c in calls if c[0] == "architect_stage_activity"]
    assert plan_calls == [("architect_stage_activity", 1, None)]


async def test_reject_once_then_approve_charges_one_and_carries_feedback():
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    activities = _stub_activities(calls, [_plan_result(), _plan_result()])

    async with _harness(client, run_id, activities):
        handle = await _start(client, run_id)
        await _wait_plan_parked(handle, 1)
        await handle.signal(AgentPipelineWorkflow.plan_rejected, "use candidate B")
        await _wait_plan_parked(handle, 2)
        await handle.signal(AgentPipelineWorkflow.plan_approved)
        result = await handle.result()

    assert result == "https://github.com/factory/repo/pull/2"
    plan_calls = [c for c in calls if c[0] == "architect_stage_activity"]
    assert plan_calls[0] == ("architect_stage_activity", 1, None)
    assert plan_calls[1][0:2] == ("architect_stage_activity", 2)
    assert "use candidate B" in plan_calls[1][2]


async def test_gap_round_ran_charges_budget_even_when_approved():
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    # A gap round on attempt 1 charges the budget (CO-1); two more human
    # rejections after that would exhaust MAX_PLAN_ATTEMPTS=3 — approve
    # immediately instead, to isolate the gap-round charge in this test.
    activities = _stub_activities(calls, [_plan_result(gap_round_ran=True)])

    async with _harness(client, run_id, activities):
        handle = await _start(client, run_id)
        await _wait_plan_parked(handle, 1)
        await handle.signal(AgentPipelineWorkflow.plan_approved)
        result = await handle.result()

    assert result == "https://github.com/factory/repo/pull/2"


async def test_idempotent_hit_skips_charge_and_goes_straight_to_gate():
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    activities = _stub_activities(calls, [_plan_result(idempotent_hit=True)])

    async with _harness(client, run_id, activities):
        handle = await _start(client, run_id)
        await _wait_plan_parked(handle, 1)
        await handle.signal(AgentPipelineWorkflow.plan_approved)
        result = await handle.result()

    assert result == "https://github.com/factory/repo/pull/2"


async def test_malformed_retries_exhausted_fails_immediately_no_charge():
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    activities = _stub_activities(
        calls,
        [
            ApplicationError(
                "All 3 candidates were malformed after 1 retries",
                type="MalformedRetriesExhausted",
                non_retryable=True,
            )
        ],
    )

    async with _harness(client, run_id, activities):
        handle = await _start(client, run_id)
        with pytest.raises(WorkflowFailureError):
            await handle.result()

    plan_calls = [c for c in calls if c[0] == "architect_stage_activity"]
    assert len(plan_calls) == 1  # no re-attempt: CO-3 fails the run outright


async def test_deterministic_failure_charges_budget_and_retries():
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    activities = _stub_activities(
        calls,
        [
            ApplicationError(
                "No SC-NNN success criteria found",
                type="PlanDeterministicFailure",
                non_retryable=True,
            ),
            _plan_result(),
        ],
    )

    async with _harness(client, run_id, activities):
        handle = await _start(client, run_id)
        await _wait_plan_parked(handle, 2)
        await handle.signal(AgentPipelineWorkflow.plan_approved)
        result = await handle.result()

    assert result == "https://github.com/factory/repo/pull/2"
    plan_calls = [c for c in calls if c[0] == "architect_stage_activity"]
    assert plan_calls[1][2] is not None  # attempt 2 got derived feedback


async def test_budget_exhaustion_after_repeated_rejection_raises():
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    # MAX_PLAN_ATTEMPTS=3: three rejections charge attempts 1, 2, and 3 —
    # the third rejection exhausts the budget, with no fourth call ever
    # made.
    activities = _stub_activities(calls, [_plan_result(), _plan_result(), _plan_result()])

    async with _harness(client, run_id, activities):
        handle = await _start(client, run_id)
        for i, fb in enumerate(["no good", "still no good", "no good either"], start=1):
            await _wait_plan_parked(handle, i)
            await handle.signal(AgentPipelineWorkflow.plan_rejected, fb)

        with pytest.raises(WorkflowFailureError):
            await handle.result()

    plan_calls = [c for c in calls if c[0] == "architect_stage_activity"]
    assert len(plan_calls) == 3  # budget exhausted before a 4th call


async def test_harness_ends_a_parked_pipeline_and_both_workflows_carry_the_limit():
    """specs/014 FR-003/FR-008: a test that fails while its pipeline workflow
    is parked leaves nothing running, and both workflows carry the limit."""
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    activities = _stub_activities(calls, [_plan_result()])

    class _Sentinel(Exception):
        pass

    with pytest.raises(_Sentinel):
        async with _harness(client, run_id, activities) as pool_handle:
            handle = await _start(client, run_id)
            await _wait_plan_parked(handle, 1)
            assert await recorded_limit(handle) == TEST_WORKFLOW_TIMEOUT
            assert await recorded_limit(pool_handle) == TEST_WORKFLOW_TIMEOUT
            raise _Sentinel

    assert (await handle.describe()).status == WorkflowExecutionStatus.TERMINATED
    assert (await pool_handle.describe()).status == WorkflowExecutionStatus.TERMINATED


# --- Credential-pool seats (specs/009) -----------------------------------------

async def _approve_and_result(client, run_id, handle):
    await _wait_plan_parked(handle, 1)
    await handle.signal(AgentPipelineWorkflow.plan_approved)
    return await handle.result()


def _seat_error(kind: str, seat_id: str, resets_at: str | None = None) -> ApplicationError:
    if kind == "SeatExhausted":
        return ApplicationError("seat exhausted", seat_id, resets_at,
                                type="SeatExhausted", non_retryable=True)
    return ApplicationError("seat invalid", seat_id, type="SeatInvalid", non_retryable=True)


def _build_calls(calls):
    return [c for c in calls if c[0] == "run_swe_agent_activity"]


async def test_build_runs_on_leased_seat_and_releases_usage():
    """US1 / SC-001: one-seat pool, Build leases seat-a, releases it with usage."""
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    activities = _stub_activities(calls, [_plan_result()])

    async with _harness(client, run_id, activities) as pool:
        result = await _approve_and_result(client, run_id, await _start(client, run_id))
        table = await pool.query(CredentialPoolWorkflow.seats)

    assert result == "https://github.com/factory/repo/pull/2"
    assert [c[2] for c in _build_calls(calls)] == ["seat-a"]
    assert table["seat-a"]["active_leases"] == 0
    assert table["seat-a"]["last_utilization"] == 0.25
    assert table["seat-a"]["last_rate_limit_type"] == "five_hour"


async def test_seat_exhausted_hands_off_without_charging_budgets():
    """US2 / SC-004: seat-a runs out mid-Build -> successor on seat-b; one
    Build attempt (same feedback), one Eval-Gate call, no plan charge."""
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    activities = _stub_activities(
        calls, [_plan_result()],
        build_outcomes=[_seat_error("SeatExhausted", "seat-a", "2099-01-01T00:00:00+00:00")],
    )

    async with _harness(client, run_id, activities, _pool("seat-a", "seat-b")) as pool:
        result = await _approve_and_result(client, run_id, await _start(client, run_id))
        table = await pool.query(CredentialPoolWorkflow.seats)

    assert result == "https://github.com/factory/repo/pull/2"
    builds = _build_calls(calls)
    assert [c[2] for c in builds] == ["seat-a", "seat-b"]
    assert [c[1] for c in builds] == [None, None]  # same Build attempt, not a gate retry
    assert len([c for c in calls if c[0] == "eval_gate_activity"]) == 1
    assert len([c for c in calls if c[0] == "architect_stage_activity"]) == 1
    assert table["seat-a"]["exhausted_until"] == "2099-01-01T00:00:00+00:00"
    assert table["seat-a"]["active_leases"] == 0
    assert table["seat-b"]["active_leases"] == 0
    assert table["seat-b"]["last_utilization"] == 0.25


async def test_seat_invalid_marks_seat_and_hands_off():
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    activities = _stub_activities(
        calls, [_plan_result()], build_outcomes=[_seat_error("SeatInvalid", "seat-a")],
    )

    async with _harness(client, run_id, activities, _pool("seat-a", "seat-b")) as pool:
        await _approve_and_result(client, run_id, await _start(client, run_id))
        table = await pool.query(CredentialPoolWorkflow.seats)

    assert [c[2] for c in _build_calls(calls)] == ["seat-a", "seat-b"]
    assert table["seat-a"]["invalid"] is True


async def test_seat_handoff_budget_exhaustion_fails_distinctly():
    """FR-019: an exhaustion whose reset is already past keeps the seat
    eligible, so the stage ping-pongs until MAX_SEAT_HANDOFFS is spent."""
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    past = "2000-01-01T00:00:00+00:00"
    activities = _stub_activities(
        calls, [_plan_result()],
        build_outcomes=[_seat_error("SeatExhausted", "seat-a", past)] * 20,
    )

    async with _harness(client, run_id, activities):
        handle = await _start(client, run_id)
        with pytest.raises(WorkflowFailureError) as exc:
            await _approve_and_result(client, run_id, handle)

    assert exc.value.cause.type == "SeatHandoffsExhausted"
    assert len(_build_calls(calls)) == 5  # 1 + MAX_SEAT_HANDOFFS
    assert not [c for c in calls if c[0] == "eval_gate_activity"]


async def test_pool_exhausted_fails_with_earliest_reset_and_no_charge():
    """US4 / SC-008: one-seat pool, seat runs out -> CredentialPoolExhausted
    carrying the reset time; Eval-Gate never reached, no plan re-run."""
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    resets = "2099-01-01T00:00:00+00:00"
    activities = _stub_activities(
        calls, [_plan_result()],
        build_outcomes=[_seat_error("SeatExhausted", "seat-a", resets)],
    )

    async with _harness(client, run_id, activities):
        handle = await _start(client, run_id)
        with pytest.raises(WorkflowFailureError) as exc:
            await _approve_and_result(client, run_id, handle)

    assert exc.value.cause.type == "CredentialPoolExhausted"
    assert list(exc.value.cause.details) == [resets]
    assert len(_build_calls(calls)) == 1
    assert not [c for c in calls if c[0] == "eval_gate_activity"]
    assert len([c for c in calls if c[0] == "architect_stage_activity"]) == 1


async def test_non_seat_build_failure_releases_lease():
    """A non-seat Build failure must not strand the seat's lease."""
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    activities = _stub_activities(
        calls, [_plan_result()],
        build_outcomes=[ApplicationError("sandbox run failed (1)", non_retryable=True)],
    )

    async with _harness(client, run_id, activities) as pool:
        handle = await _start(client, run_id)
        with pytest.raises(WorkflowFailureError):
            await _approve_and_result(client, run_id, handle)
        table = await pool.query(CredentialPoolWorkflow.seats)

    assert table["seat-a"]["active_leases"] == 0
    assert table["seat-a"]["exhausted_until"] is None


def _architect_seats(calls):
    return [c[1] for c in calls if c[0] == "architect_seat"]


async def test_architect_seat_exhausted_hands_off_without_charging_plan_budget():
    """US5: seat-a runs out mid-architect -> the same plan attempt re-runs on
    seat-b; MAX_PLAN_ATTEMPTS is not charged (no failure feedback carried)."""
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    resets = "2099-01-01T00:00:00+00:00"
    activities = _stub_activities(
        calls, [_seat_error("SeatExhausted", "seat-a", resets), _plan_result()],
    )

    async with _harness(client, run_id, activities, _pool("seat-a", "seat-b")) as pool:
        handle = await _start(client, run_id)
        await _wait_plan_parked(handle, 2)
        await handle.signal(AgentPipelineWorkflow.plan_approved)
        result = await handle.result()
        table = await pool.query(CredentialPoolWorkflow.seats)

    assert result == "https://github.com/factory/repo/pull/2"
    plan_calls = [c for c in calls if c[0] == "architect_stage_activity"]
    assert plan_calls == [("architect_stage_activity", 1, None)] * 2
    assert _architect_seats(calls) == ["seat-a", "seat-b"]
    assert table["seat-a"]["exhausted_until"] == resets
    assert table["seat-a"]["active_leases"] == 0
    assert table["seat-b"]["active_leases"] == 0


async def test_architect_pool_exhausted_fails_without_charging_plan_budget():
    """US5 / FR-018: one-seat pool runs out during the architect stage ->
    CredentialPoolExhausted fails the run as-is; no CO-2 charge, no retry."""
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    resets = "2099-01-01T00:00:00+00:00"
    activities = _stub_activities(
        calls, [_seat_error("SeatExhausted", "seat-a", resets), _plan_result()],
    )

    async with _harness(client, run_id, activities):
        handle = await _start(client, run_id)
        with pytest.raises(WorkflowFailureError) as exc:
            await handle.result()

    assert exc.value.cause.type == "CredentialPoolExhausted"
    assert list(exc.value.cause.details) == [resets]
    assert [c for c in calls if c[0] == "architect_stage_activity"] == [
        ("architect_stage_activity", 1, None)
    ]
    assert not _build_calls(calls)


def _failing_seat_activity(name: str):
    @activity.defn(name=name)
    async def failing(*args) -> None:
        raise ApplicationError(f"{name}: pool unreachable", non_retryable=True)
    return failing


async def test_pool_unavailable_at_acquire_fails_without_charging_plan_budget():
    """FR-019: the pool's own failure is typed CredentialPoolUnavailable and
    re-raised by the plan loop, not charged as a CO-2 plan failure."""
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    activities = _stub_activities(calls, [_plan_result()])

    async with _harness(client, run_id, activities,
                        seat_overrides=[_failing_seat_activity("acquire_seat_activity")]):
        handle = await _start(client, run_id)
        with pytest.raises(WorkflowFailureError) as exc:
            await handle.result()

    assert exc.value.cause.type == "CredentialPoolUnavailable"
    assert not [c for c in calls if c[0] == "architect_stage_activity"]


async def test_failed_release_neither_masks_nor_discards_a_finished_stage():
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    activities = _stub_activities(calls, [_plan_result()])

    # The unreleased plan lease stays held until LEASE_TTL, so Build needs a
    # second slot on the seat (the real seat-a has max_concurrent: 2).
    async with _harness(client, run_id, activities, _pool("seat-a", max_concurrent=2),
                        seat_overrides=[_failing_seat_activity("release_seat_activity")]):
        result = await _approve_and_result(client, run_id, await _start(client, run_id))

    assert result == "https://github.com/factory/repo/pull/2"
    assert len([c for c in calls if c[0] == "architect_stage_activity"]) == 1
    assert len(_build_calls(calls)) == 1


async def test_cancel_during_seat_backed_architect_stage_cancels_the_run():
    """A workflow cancel must end the run Cancelled — not be charged as a
    CO-2 plan failure (and retried), nor re-typed as a pool failure."""
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    started = asyncio.Event()

    @activity.defn(name="architect_stage_activity")
    async def blocking_architect(repo, branch, pr_url, attempt, feedback=None, seat_id=None):
        calls.append(("architect_stage_activity", attempt, feedback))
        started.set()
        await asyncio.sleep(3600)

    activities = [blocking_architect if a.__temporal_activity_definition.name
                  == "architect_stage_activity" else a
                  for a in _stub_activities(calls, [])]

    async with _harness(client, run_id, activities) as pool:
        handle = await _start(client, run_id)
        await asyncio.wait_for(started.wait(), 10)
        await handle.cancel()
        with pytest.raises(WorkflowFailureError) as exc:
            await handle.result()
        table = await pool.query(CredentialPoolWorkflow.seats)

    assert isinstance(exc.value.cause, CancelledError)
    assert len([c for c in calls if c[0] == "architect_stage_activity"]) == 1
    assert table["seat-a"]["active_leases"] == 0


async def test_cancel_during_seat_release_is_not_swallowed():
    """A cancel landing while the lease release runs must not be re-typed as
    a pool failure and swallowed by the best-effort release (the run would
    otherwise carry on to Build)."""
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    releasing = asyncio.Event()

    @activity.defn(name="release_seat_activity")
    async def blocking_release(*args) -> None:
        releasing.set()
        await asyncio.sleep(3600)

    activities = _stub_activities(calls, [_plan_result()])
    async with _harness(client, run_id, activities, seat_overrides=[blocking_release]):
        handle = await _start(client, run_id)
        await asyncio.wait_for(releasing.wait(), 10)
        await handle.cancel()
        with pytest.raises(WorkflowFailureError) as exc:
            await handle.result()

    assert isinstance(exc.value.cause, CancelledError)
    assert not _build_calls(calls)


# --- specs/011-seat-pool-hardening ---------------------------------------------

async def test_build_receives_handoff_index_but_architect_does_not():
    """F5/F6: the Build activity gets its handoff index (0, then 1 for the
    successor); the architect stage's signature is unchanged."""
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    activities = _stub_activities(
        calls, [_plan_result()],
        build_outcomes=[_seat_error("SeatExhausted", "seat-a", "2099-01-01T00:00:00+00:00")],
    )

    async with _harness(client, run_id, activities, _pool("seat-a", "seat-b")):
        await _approve_and_result(client, run_id, await _start(client, run_id))

    assert [(c[2], c[3]) for c in _build_calls(calls)] == [("seat-a", 0), ("seat-b", 1)]
    assert ("architect_seat", "seat-a") in calls


async def test_build_release_stores_the_readings_reset_time():
    """F2: the Build result's utilization_resets_at reaches the pool's release."""
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    activities = _stub_activities(calls, [_plan_result()])

    async with _harness(client, run_id, activities) as pool:
        await _approve_and_result(client, run_id, await _start(client, run_id))
        table = await pool.query(CredentialPoolWorkflow.seats)

    assert table["seat-a"]["last_utilization"] == 0.25
    assert table["seat-a"]["utilization_resets_at"] == BUILD_READING_RESETS_AT


def _acquire_stub(build_answers: list, build_calls: list):
    """acquire_seat_activity stand-in: the architect stage always gets
    seat-a; Build's acquires are answered from `build_answers` in order
    (each a callable returning earliest_reset, or a seat id), the last one
    repeating."""
    @activity.defn(name="acquire_seat_activity")
    async def acquire(agent: str, lease_key: str) -> dict:
        if "/build/" not in lease_key:
            return {"seat_id": "seat-a", "earliest_reset": None}
        build_calls.append(lease_key)
        answer = build_answers[min(len(build_calls), len(build_answers)) - 1]
        if callable(answer):
            return {"seat_id": None, "earliest_reset": answer()}
        return {"seat_id": answer, "earliest_reset": None}
    return acquire


def _in(seconds: float):
    return lambda: (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()


async def test_empty_pool_waits_for_a_near_reset_then_builds():
    """F3 / SC-004: no seat, reset in 2 s -> durable timer, same lease key,
    then Build runs once on the seat; no Build attempt or plan charged."""
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    build_acquires: list = []
    activities = _stub_activities(calls, [_plan_result()])
    acquire = _acquire_stub([_in(2), "seat-a"], build_acquires)

    async with _harness(client, run_id, activities, seat_overrides=[acquire]):
        handle = await _start(client, run_id)
        result = await _approve_and_result(client, run_id, handle)
        events = [e async for e in handle.fetch_history_events()]

    assert result == "https://github.com/factory/repo/pull/2"
    assert len(build_acquires) == 2 and len(set(build_acquires)) == 1  # same key, no handoff
    assert [(c[1], c[2], c[3]) for c in _build_calls(calls)] == [(None, "seat-a", 0)]
    assert len([c for c in calls if c[0] == "architect_stage_activity"]) == 1
    assert any(e.event_type == EventType.EVENT_TYPE_TIMER_STARTED for e in events)


async def test_empty_pool_without_known_reset_fails_at_once():
    """F3: e.g. every seat invalid -> no reset time -> fail fast, no timer."""
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    build_acquires: list = []
    activities = _stub_activities(calls, [_plan_result()])
    acquire = _acquire_stub([lambda: None], build_acquires)

    async with _harness(client, run_id, activities, seat_overrides=[acquire]):
        handle = await _start(client, run_id)
        with pytest.raises(WorkflowFailureError) as exc:
            await _approve_and_result(client, run_id, handle)
        events = [e async for e in handle.fetch_history_events()]

    assert exc.value.cause.type == "CredentialPoolExhausted"
    assert list(exc.value.cause.details) == [None]
    assert len(build_acquires) == 1
    assert not any(e.event_type == EventType.EVENT_TYPE_TIMER_STARTED for e in events)


async def test_empty_pool_with_a_far_reset_fails_at_once():
    """F3: a reset beyond the 6 h horizon (e.g. a seven-day window) is not waited for."""
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    build_acquires: list = []
    activities = _stub_activities(calls, [_plan_result()])
    acquire = _acquire_stub([_in(7 * 3600)], build_acquires)

    async with _harness(client, run_id, activities, seat_overrides=[acquire]):
        handle = await _start(client, run_id)
        with pytest.raises(WorkflowFailureError) as exc:
            await _approve_and_result(client, run_id, handle)

    assert exc.value.cause.type == "CredentialPoolExhausted"
    assert len(build_acquires) == 1


async def test_empty_pool_fails_after_two_waits():
    """F3: MAX_POOL_WAITS (2) spent -> CredentialPoolExhausted; Build never ran."""
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    build_acquires: list = []
    activities = _stub_activities(calls, [_plan_result()])
    acquire = _acquire_stub([_in(1)], build_acquires)

    async with _harness(client, run_id, activities, seat_overrides=[acquire]):
        handle = await _start(client, run_id)
        with pytest.raises(WorkflowFailureError) as exc:
            await _approve_and_result(client, run_id, handle)

    assert exc.value.cause.type == "CredentialPoolExhausted"
    assert len(build_acquires) == 3  # first ask + one per wait
    assert not _build_calls(calls)


async def test_empty_pool_with_a_past_reset_asks_again_at_once_as_one_wait():
    """F3 edge case: a reset already past still counts as a wait (bounded),
    and the stage asks again after the 1 s margin, not later."""
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    build_acquires: list = []
    activities = _stub_activities(calls, [_plan_result()])
    acquire = _acquire_stub([_in(-5), _in(-5), "seat-a"], build_acquires)

    async with _harness(client, run_id, activities, seat_overrides=[acquire]):
        handle = await _start(client, run_id)
        result = await _approve_and_result(client, run_id, handle)

    assert result == "https://github.com/factory/repo/pull/2"
    assert len(build_acquires) == 3  # 2 waits, then the seat
    assert [c[2] for c in _build_calls(calls)] == ["seat-a"]
