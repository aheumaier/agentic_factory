"""Deploy (§3.7) — a second, independent, long-lived workflow, deliberately
separate from AgentPipelineWorkflow: it waits on a human merging the
registry PR opened by `register_activity`, an SLA of days to weeks, vs.
Build/Gate's minutes. Started at a deterministic workflow ID
(`registry-promotion-{agent_name}-v{version}`) so the GH Actions step that
signals it doesn't need any workflow-to-workflow correlation machinery.

Not a child workflow of AgentPipelineWorkflow — avoids ParentClosePolicy
complications for two executions with wildly different SLAs.
"""
from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from activities import promote_agent_activity


@workflow.defn
class RegistryPromotionWaiterWorkflow:
    def __init__(self) -> None:
        self._merged = False

    @workflow.signal
    def pr_merged(self) -> None:
        self._merged = True

    @workflow.run
    async def run(self, agent_name: str, version: str) -> None:
        await workflow.wait_condition(lambda: self._merged)
        await workflow.execute_activity(
            promote_agent_activity,
            args=[agent_name, version],
            start_to_close_timeout=timedelta(minutes=5),
        )
