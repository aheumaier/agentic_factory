"""Durable pipeline workflow (§2 process flow, §3.5).

Spec Intake -> Build -> Sandbox Test -> Eval/Gate -> (loop to Build on fail)
  -> Harness Integration -> Deploy -> Monitor -> Retire or Version
"""
from datetime import timedelta

from temporalio import workflow


@workflow.defn
class AgentPipelineWorkflow:
    @workflow.run
    async def run(self, spec_path: str) -> str:
        # TODO: each step below is an activity backed by the corresponding
        # layer directory (spec/, harness/, sandbox/, eval/, registry/).
        # A failing Eval/Gate activity should raise so Temporal retries
        # Build with the failure trace attached, per architecture doc §2.
        del spec_path
        raise NotImplementedError("wire activities per layer before running")
