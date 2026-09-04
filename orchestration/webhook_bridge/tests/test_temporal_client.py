from unittest.mock import AsyncMock, MagicMock

import pytest
from temporalio.common import WorkflowIDConflictPolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from webhook_bridge import temporal_client


def _async_iter(items):
    async def _gen():
        for item in items:
            yield item

    return _gen()


async def test_start_run_call_shape() -> None:
    client = MagicMock()
    client.start_workflow = AsyncMock()

    result = await temporal_client.start_run(
        client, "owner/repo", 42, "feature-branch", "widget-export", "3"
    )

    client.start_workflow.assert_awaited_once_with(
        "AgentPipelineWorkflow",
        args=["owner/repo", "feature-branch", "widget-export", "3"],
        id="pipeline/owner/repo/widget-export/v3",
        task_queue="agent-factory-pipeline",
        id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
        search_attributes={"TargetRepo": ["owner/repo"], "PRNumber": [42]},
    )
    assert result.started is True
    assert result.workflow_id == "pipeline/owner/repo/widget-export/v3"


async def test_start_run_already_started_is_noop() -> None:
    client = MagicMock()
    client.start_workflow = AsyncMock(
        side_effect=WorkflowAlreadyStartedError(
            workflow_id="pipeline/owner/repo/widget-export/v3", workflow_type="AgentPipelineWorkflow"
        )
    )

    result = await temporal_client.start_run(
        client, "owner/repo", 42, "feature-branch", "widget-export", "3"
    )

    assert result.started is False
    assert result.workflow_id == "pipeline/owner/repo/widget-export/v3"


async def test_resolve_gate_target_zero_matches() -> None:
    client = MagicMock()
    client.list_workflows = MagicMock(return_value=_async_iter([]))

    resolution = await temporal_client.resolve_gate_target(client, "owner/repo", 42)

    assert resolution.handle is None
    assert "no in-flight run" in resolution.reason


async def test_resolve_gate_target_multiple_matches() -> None:
    client = MagicMock()
    wf1 = MagicMock(id="pipeline/owner/repo/a/v1")
    wf2 = MagicMock(id="pipeline/owner/repo/b/v1")
    client.list_workflows = MagicMock(return_value=_async_iter([wf1, wf2]))

    resolution = await temporal_client.resolve_gate_target(client, "owner/repo", 42)

    assert resolution.handle is None
    assert "multiple in-flight runs" in resolution.reason


async def test_resolve_gate_target_single_match_uses_search_attribute_query() -> None:
    client = MagicMock()
    wf = MagicMock(id="pipeline/owner/repo/widget-export/v3")
    client.list_workflows = MagicMock(return_value=_async_iter([wf]))
    handle = MagicMock()
    client.get_workflow_handle = MagicMock(return_value=handle)

    resolution = await temporal_client.resolve_gate_target(client, "owner/repo", 42)

    client.list_workflows.assert_called_once_with(
        query="TargetRepo = 'owner/repo' AND PRNumber = 42 AND ExecutionStatus = 'Running'"
    )
    client.get_workflow_handle.assert_called_once_with("pipeline/owner/repo/widget-export/v3")
    assert resolution.handle is handle


@pytest.mark.parametrize(
    "gate,decision,feedback,signal_name",
    [
        ("pm", "approved", None, "pm_approved"),
        ("pm", "rejected", "needs work", "pm_rejected"),
        ("plan", "approved", None, "plan_approved"),
        ("plan", "rejected", "use candidate C", "plan_rejected"),
        ("security", "approved", None, "security_cleared"),
        ("security", "rejected", "found a CVE", "security_rejected"),
    ],
)
async def test_signal_gate_call_shape(gate, decision, feedback, signal_name) -> None:
    client = MagicMock()
    wf = MagicMock(id="pipeline/owner/repo/widget-export/v3")
    client.list_workflows = MagicMock(return_value=_async_iter([wf]))
    handle = MagicMock()
    handle.signal = AsyncMock()
    client.get_workflow_handle = MagicMock(return_value=handle)
    github_client = MagicMock()
    github_client.post_reaction = AsyncMock()

    await temporal_client.signal_gate(
        client, "owner/repo", 42, gate, decision, feedback, 999, "alice", "comment body", github_client
    )

    if feedback is None:
        handle.signal.assert_awaited_once_with(signal_name)
    else:
        handle.signal.assert_awaited_once_with(signal_name, feedback)
    github_client.post_reaction.assert_awaited_once_with("owner/repo", 999, "eyes")


async def test_signal_gate_no_match_posts_confused_reaction() -> None:
    client = MagicMock()
    client.list_workflows = MagicMock(return_value=_async_iter([]))
    github_client = MagicMock()
    github_client.post_reaction = AsyncMock()

    await temporal_client.signal_gate(
        client, "owner/repo", 42, "pm", "approved", None, 999, "alice", "pm_approved", github_client
    )

    github_client.post_reaction.assert_awaited_once_with("owner/repo", 999, "confused")


async def test_signal_gate_signal_error_does_not_raise() -> None:
    client = MagicMock()
    wf = MagicMock(id="pipeline/owner/repo/widget-export/v3")
    client.list_workflows = MagicMock(return_value=_async_iter([wf]))
    handle = MagicMock()
    handle.signal = AsyncMock(side_effect=RuntimeError("not found"))
    client.get_workflow_handle = MagicMock(return_value=handle)
    github_client = MagicMock()
    github_client.post_reaction = AsyncMock()

    await temporal_client.signal_gate(
        client, "owner/repo", 42, "pm", "approved", None, 999, "alice", "pm_approved", github_client
    )

    github_client.post_reaction.assert_awaited_once_with("owner/repo", 999, "confused")


async def test_signal_gate_reaction_post_failure_does_not_raise() -> None:
    client = MagicMock()
    wf = MagicMock(id="pipeline/owner/repo/widget-export/v3")
    client.list_workflows = MagicMock(return_value=_async_iter([wf]))
    handle = MagicMock()
    handle.signal = AsyncMock()
    client.get_workflow_handle = MagicMock(return_value=handle)
    github_client = MagicMock()
    github_client.post_reaction = AsyncMock(side_effect=RuntimeError("rate limited"))

    await temporal_client.signal_gate(
        client, "owner/repo", 42, "pm", "approved", None, 999, "alice", "pm_approved", github_client
    )  # must not raise
