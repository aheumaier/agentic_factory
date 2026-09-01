"""Durable pipeline workflow (§2 process flow, §3.5).

Spec Intake -> Build -> Sandbox Test -> Eval/Gate -> (loop to Build on fail)
  -> Harness Integration -> Deploy -> Monitor -> Retire or Version

This pass wires only Build (the SWE agent, §3.2) against a branch whose
Spec Intake (§3.1) already happened manually — see
`harness/swe-agent/SKILL.md` for what's deferred (Sandbox Test/§3.3,
Eval-Gate/§3.6, Deploy/§3.7 are not yet activities here).
"""
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from activities import run_swe_agent_activity


@workflow.defn
class AgentPipelineWorkflow:
    @workflow.run
    async def run(self, repo: str, branch: str) -> str:
        return await workflow.execute_activity(
            run_swe_agent_activity,
            args=[repo, branch],
            start_to_close_timeout=timedelta(minutes=20),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
