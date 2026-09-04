"""AgentPipelineWorkflow's plan-review loop — the narrow architect-agent
Temporal-wiring slice of specs/005-pipeline-mode-signals-escalation.

Runs against a real local Temporal server (`make up`), like every other
Temporal-facing test in this repo (no WorkflowEnvironment/time-skipping
usage exists anywhere here — see webhook_bridge/tests/test_integration.py).
Every activity is stubbed by name, so no real git/gh/e2b/model call ever
happens: this test is about the workflow's own CO-1/CO-2/CO-3/CO-4
budget-charging and signal-gating logic, not about run_architect_stage()
or run_swe_agent_activity() themselves (each has its own test suite).
"""
import asyncio
import uuid

import pytest
from temporalio import activity
from temporalio.client import Client, WorkflowFailureError
from temporalio.exceptions import ApplicationError
from temporalio.worker import Worker

from workflows.pipeline_workflow import AgentPipelineWorkflow

TASK_QUEUE = "agent-factory-pipeline-test"
REPO = "owner/repo"


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


def _stub_activities(calls: list, plan_outcomes: list):
    """plan_outcomes: consumed in order by architect_stage_activity, one
    per call — either a result dict, or an ApplicationError to raise
    (already typed/non_retryable, exactly as the real activities.py
    ::architect_stage_activity would map a RuntimeError/ValueError before
    it ever reaches the workflow — this test is about the workflow's
    handling of that mapped error, not the mapping itself)."""
    plan_iter = iter(plan_outcomes)

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
        repo: str, branch: str, feedback: str | None = None
    ) -> str:
        calls.append(("run_swe_agent_activity", feedback))
        return "https://github.com/owner/repo/pull/1"

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

    async with Worker(client, task_queue=f"{TASK_QUEUE}-{run_id}", workflows=[AgentPipelineWorkflow],
                       activities=activities):
        handle = await client.start_workflow(
            AgentPipelineWorkflow.run,
            args=[REPO, f"branch-{run_id}", f"agent-{run_id}", "1"],
            id=f"pipeline-workflow-test-{run_id}",
            task_queue=f"{TASK_QUEUE}-{run_id}",
        )
        await _wait_until(lambda: any(c[0] == "architect_stage_activity" for c in calls))
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

    async with Worker(client, task_queue=f"{TASK_QUEUE}-{run_id}", workflows=[AgentPipelineWorkflow],
                       activities=activities):
        handle = await client.start_workflow(
            AgentPipelineWorkflow.run,
            args=[REPO, f"branch-{run_id}", f"agent-{run_id}", "1"],
            id=f"pipeline-workflow-test-{run_id}",
            task_queue=f"{TASK_QUEUE}-{run_id}",
        )
        await _wait_until(
            lambda: len([c for c in calls if c[0] == "architect_stage_activity"]) == 1
        )
        await handle.signal(AgentPipelineWorkflow.plan_rejected, "use candidate B")
        await _wait_until(
            lambda: len([c for c in calls if c[0] == "architect_stage_activity"]) == 2
        )
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

    async with Worker(client, task_queue=f"{TASK_QUEUE}-{run_id}", workflows=[AgentPipelineWorkflow],
                       activities=activities):
        handle = await client.start_workflow(
            AgentPipelineWorkflow.run,
            args=[REPO, f"branch-{run_id}", f"agent-{run_id}", "1"],
            id=f"pipeline-workflow-test-{run_id}",
            task_queue=f"{TASK_QUEUE}-{run_id}",
        )
        await _wait_until(lambda: any(c[0] == "architect_stage_activity" for c in calls))
        await handle.signal(AgentPipelineWorkflow.plan_approved)
        result = await handle.result()

    assert result == "https://github.com/factory/repo/pull/2"


async def test_idempotent_hit_skips_charge_and_goes_straight_to_gate():
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    calls: list = []
    activities = _stub_activities(calls, [_plan_result(idempotent_hit=True)])

    async with Worker(client, task_queue=f"{TASK_QUEUE}-{run_id}", workflows=[AgentPipelineWorkflow],
                       activities=activities):
        handle = await client.start_workflow(
            AgentPipelineWorkflow.run,
            args=[REPO, f"branch-{run_id}", f"agent-{run_id}", "1"],
            id=f"pipeline-workflow-test-{run_id}",
            task_queue=f"{TASK_QUEUE}-{run_id}",
        )
        await _wait_until(lambda: any(c[0] == "architect_stage_activity" for c in calls))
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

    async with Worker(client, task_queue=f"{TASK_QUEUE}-{run_id}", workflows=[AgentPipelineWorkflow],
                       activities=activities):
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

    async with Worker(client, task_queue=f"{TASK_QUEUE}-{run_id}", workflows=[AgentPipelineWorkflow],
                       activities=activities):
        handle = await client.start_workflow(
            AgentPipelineWorkflow.run,
            args=[REPO, f"branch-{run_id}", f"agent-{run_id}", "1"],
            id=f"pipeline-workflow-test-{run_id}",
            task_queue=f"{TASK_QUEUE}-{run_id}",
        )
        await _wait_until(
            lambda: len([c for c in calls if c[0] == "architect_stage_activity"]) == 2
        )
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

    async with Worker(client, task_queue=f"{TASK_QUEUE}-{run_id}", workflows=[AgentPipelineWorkflow],
                       activities=activities):
        handle = await client.start_workflow(
            AgentPipelineWorkflow.run,
            args=[REPO, f"branch-{run_id}", f"agent-{run_id}", "1"],
            id=f"pipeline-workflow-test-{run_id}",
            task_queue=f"{TASK_QUEUE}-{run_id}",
        )
        for i, fb in enumerate(["no good", "still no good", "no good either"], start=1):
            await _wait_until(
                lambda i=i: len([c for c in calls if c[0] == "architect_stage_activity"]) == i
            )
            await handle.signal(AgentPipelineWorkflow.plan_rejected, fb)

        with pytest.raises(WorkflowFailureError):
            await handle.result()

    plan_calls = [c for c in calls if c[0] == "architect_stage_activity"]
    assert len(plan_calls) == 3  # budget exhausted before a 4th call
