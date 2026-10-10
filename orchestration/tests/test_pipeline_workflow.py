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
pool that is terminated in a `finally`.
"""
import asyncio
import contextlib
import os
import uuid

import pytest
from temporalio import activity
from temporalio.api.enums.v1 import EventType
from temporalio.client import Client, WorkflowFailureError
from temporalio.exceptions import ApplicationError
from temporalio.worker import Worker

from activities import (
    acquire_seat_activity,
    release_seat_activity,
    report_seat_failure_activity,
)
from workflows.credential_pool import CredentialPoolWorkflow
from workflows.pipeline_workflow import AgentPipelineWorkflow

TASK_QUEUE = "agent-factory-pipeline-test"
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


@contextlib.asynccontextmanager
async def _harness(client: Client, run_id: str, activities: list, pool: dict | None = None):
    """Worker for the pipeline + a real CredentialPoolWorkflow (specs/009),
    with the real seat activities pointed at that per-test pool."""
    task_queue = f"{TASK_QUEUE}-{run_id}"
    pool_id = f"credential-pool-test-{run_id}"
    previous = os.environ.get("CREDENTIAL_POOL_ID")
    os.environ["CREDENTIAL_POOL_ID"] = pool_id
    try:
        async with Worker(
            client, task_queue=task_queue,
            workflows=[AgentPipelineWorkflow, CredentialPoolWorkflow],
            activities=[*activities, acquire_seat_activity, release_seat_activity,
                        report_seat_failure_activity],
        ):
            pool_handle = await client.start_workflow(
                CredentialPoolWorkflow.run, pool or _pool(), id=pool_id, task_queue=task_queue,
            )
            try:
                yield pool_handle
            finally:
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
    FR-016) then drops it — the run waits forever.
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
                and events[-1].event_type == EventType.EVENT_TYPE_WORKFLOW_TASK_COMPLETED):
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
        repo: str, branch: str, pr_url: str, attempt: int, feedback: str | None = None
    ) -> dict:
        calls.append(("architect_stage_activity", attempt, feedback))
        outcome = next(plan_iter)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    @activity.defn(name="run_swe_agent_activity")
    async def run_swe_agent_activity(
        repo: str, branch: str, feedback: str | None, seat_id: str
    ) -> dict:
        calls.append(("run_swe_agent_activity", feedback, seat_id))
        outcome = next(build_iter, None)
        if isinstance(outcome, Exception):
            raise outcome
        return {"pr_url": "https://github.com/owner/repo/pull/1", "seat_id": seat_id,
                "utilization": 0.25, "rate_limit_type": "five_hour"}

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
        handle = await client.start_workflow(
            AgentPipelineWorkflow.run,
            args=[REPO, f"branch-{run_id}", f"agent-{run_id}", "1"],
            id=f"pipeline-workflow-test-{run_id}",
            task_queue=f"{TASK_QUEUE}-{run_id}",
        )
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
        handle = await client.start_workflow(
            AgentPipelineWorkflow.run,
            args=[REPO, f"branch-{run_id}", f"agent-{run_id}", "1"],
            id=f"pipeline-workflow-test-{run_id}",
            task_queue=f"{TASK_QUEUE}-{run_id}",
        )
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
        handle = await client.start_workflow(
            AgentPipelineWorkflow.run,
            args=[REPO, f"branch-{run_id}", f"agent-{run_id}", "1"],
            id=f"pipeline-workflow-test-{run_id}",
            task_queue=f"{TASK_QUEUE}-{run_id}",
        )
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
        handle = await client.start_workflow(
            AgentPipelineWorkflow.run,
            args=[REPO, f"branch-{run_id}", f"agent-{run_id}", "1"],
            id=f"pipeline-workflow-test-{run_id}",
            task_queue=f"{TASK_QUEUE}-{run_id}",
        )
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
        handle = await client.start_workflow(
            AgentPipelineWorkflow.run,
            args=[REPO, f"branch-{run_id}", f"agent-{run_id}", "1"],
            id=f"pipeline-workflow-test-{run_id}",
            task_queue=f"{TASK_QUEUE}-{run_id}",
        )
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
        handle = await client.start_workflow(
            AgentPipelineWorkflow.run,
            args=[REPO, f"branch-{run_id}", f"agent-{run_id}", "1"],
            id=f"pipeline-workflow-test-{run_id}",
            task_queue=f"{TASK_QUEUE}-{run_id}",
        )
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
        handle = await client.start_workflow(
            AgentPipelineWorkflow.run,
            args=[REPO, f"branch-{run_id}", f"agent-{run_id}", "1"],
            id=f"pipeline-workflow-test-{run_id}",
            task_queue=f"{TASK_QUEUE}-{run_id}",
        )
        for i, fb in enumerate(["no good", "still no good", "no good either"], start=1):
            await _wait_plan_parked(handle, i)
            await handle.signal(AgentPipelineWorkflow.plan_rejected, fb)

        with pytest.raises(WorkflowFailureError):
            await handle.result()

    plan_calls = [c for c in calls if c[0] == "architect_stage_activity"]
    assert len(plan_calls) == 3  # budget exhausted before a 4th call


# --- Credential-pool seats (specs/009) -----------------------------------------

async def _approve_and_result(client, run_id, handle):
    await _wait_plan_parked(handle, 1)
    await handle.signal(AgentPipelineWorkflow.plan_approved)
    return await handle.result()


async def _start(client, run_id):
    return await client.start_workflow(
        AgentPipelineWorkflow.run,
        args=[REPO, f"branch-{run_id}", f"agent-{run_id}", "1"],
        id=f"pipeline-workflow-test-{run_id}",
        task_queue=f"{TASK_QUEUE}-{run_id}",
    )


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
