"""bridge -> Temporal call shapes (contracts/temporal-call-contract.md).

The target workflow is referenced by its registered name string,
"AgentPipelineWorkflow", not by importing the class — importing
orchestration/workflows/pipeline_workflow.py would also import
activities.py, which has module-level side effects (e2b/braintrust/
importlib setup) this standalone process has no reason to trigger
(research.md).
"""
import logging
from dataclasses import dataclass
from typing import Any, Literal

from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from . import audit

TASK_QUEUE = "agent-factory-pipeline"
WORKFLOW_TYPE = "AgentPipelineWorkflow"

_logger = logging.getLogger("webhook_bridge.temporal_client")

_SIGNAL_NAMES: dict[tuple[str, str], str] = {
    ("pm", "approved"): "pm_approved",
    ("pm", "rejected"): "pm_rejected",
    ("plan", "approved"): "plan_approved",
    ("plan", "rejected"): "plan_rejected",
    ("security", "approved"): "security_cleared",
    ("security", "rejected"): "security_rejected",
}


async def connect() -> Client:
    """Connect to Temporal exactly as orchestration/worker.py does."""
    return await Client.connect("localhost:7233")


def workflow_id(repo: str, agent_name: str, version: str) -> str:
    """f"pipeline/{repo}/{agent_name}/v{version}" — repo used as-is (its one
    '/' can't collide with a field boundary since agent_name/version are
    slug-validated '/'-free before this is ever called (data-model.md
    PipelineRunIdentity, research.md).
    """
    return f"pipeline/{repo}/{agent_name}/v{version}"


@dataclass
class StartRunResult:
    started: bool
    workflow_id: str


async def start_run(
    client: Client, repo: str, pr_number: int, branch: str, agent_name: str, version: str
) -> StartRunResult:
    wf_id = workflow_id(repo, agent_name, version)
    try:
        await client.start_workflow(
            WORKFLOW_TYPE,
            args=[repo, branch, agent_name, version],
            id=wf_id,
            task_queue=TASK_QUEUE,
            id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
            search_attributes={
                "TargetRepo": [repo],
                "PRNumber": [pr_number],
            },
        )
        return StartRunResult(started=True, workflow_id=wf_id)
    except WorkflowAlreadyStartedError:
        return StartRunResult(started=False, workflow_id=wf_id)


@dataclass
class GateTargetResolution:
    handle: Any | None = None
    reason: str | None = None

    @property
    def resolved(self) -> bool:
        return self.handle is not None


async def resolve_gate_target(client: Client, repo: str, pr_number: int) -> GateTargetResolution:
    query = f"TargetRepo = '{repo}' AND PRNumber = {pr_number} AND ExecutionStatus = 'Running'"
    matches = [wf async for wf in client.list_workflows(query=query)]
    if len(matches) == 0:
        return GateTargetResolution(reason="no in-flight run for this PR")
    if len(matches) > 1:
        return GateTargetResolution(reason="multiple in-flight runs for this PR")
    return GateTargetResolution(handle=client.get_workflow_handle(matches[0].id))


async def signal_gate(
    client: Client,
    repo: str,
    pr_number: int,
    gate: Literal["pm", "plan", "security"],
    decision: Literal["approved", "rejected"],
    feedback: str | None,
    comment_id: int,
    author: str,
    comment_body: str,
    github_client,
) -> None:
    """Resolve the target run, signal it, and log/react to the outcome.

    Every failure mode (target not found/ambiguous, or the signal call
    itself raising) is caught here and turned into outcome="signal_failed"
    plus a 😕 reaction — never allowed to crash the request handler
    (contracts/temporal-call-contract.md's failure-handling section).
    """
    resolution = await resolve_gate_target(client, repo, pr_number)
    handle = resolution.handle
    if handle is None:
        audit.log_entry(
            author=author,
            comment=comment_body,
            reason=f"signal target not found: {resolution.reason}",
            outcome="signal_failed",
        )
        await _react(github_client, repo, comment_id, "confused")
        return

    signal_name = _SIGNAL_NAMES[(gate, decision)]
    try:
        if feedback is None:
            await handle.signal(signal_name)
        else:
            await handle.signal(signal_name, feedback)
    except Exception as exc:  # noqa: BLE001 - any signal failure must not crash the handler
        audit.log_entry(
            author=author,
            comment=comment_body,
            reason=f"signal call failed: {exc}",
            outcome="signal_failed",
        )
        await _react(github_client, repo, comment_id, "confused")
        return

    audit.log_entry(
        author=author,
        comment=comment_body,
        reason=f"signal issued: {signal_name} (no @workflow.signal handler until 005 lands)",
        outcome="signal_issued_no_handler",
    )
    await _react(github_client, repo, comment_id, "eyes")


async def _react(github_client, repo: str, comment_id: int, content: str) -> None:
    try:
        await github_client.post_reaction(repo, comment_id, content)
    except Exception:  # noqa: BLE001 - a reaction failure must never mask the outcome above
        _logger.warning("reaction POST failed for comment_id=%s content=%s", comment_id, content)
