"""Test-only stand-in for specs/005-pipeline-mode-signals-escalation's
not-yet-built AgentPipelineWorkflow signal handlers. Kept in its own
module (no filesystem/sys.path setup at import time) because Temporal's
sandboxed workflow runner reimports the module that defines a workflow
under restricted globals — sharing this file with test_e2e_pipeline_gate's
agent-import/sys.path bootstrap trips that sandbox (e.g. restricted
pathlib.Path.resolve).
"""
from temporalio import workflow


@workflow.defn(name="AgentPipelineWorkflow")
class AgentPipelineWorkflow:
    def __init__(self) -> None:
        self._stage = "pm"
        self._rejected: dict[str, str] = {}
        self._done = False

    def _advance_if_ready(self) -> None:
        order = ["pm", "plan", "security", "done"]
        idx = order.index(self._stage)
        self._stage = order[idx + 1]
        if self._stage == "done":
            self._done = True

    @workflow.signal
    def pm_approved(self) -> None:
        if self._stage == "pm":
            self._advance_if_ready()

    @workflow.signal
    def pm_rejected(self, feedback: str) -> None:
        # Deliberate divergence from a simpler demo stand-in: a PM
        # rejection means "stay at this gate" rather than advancing, since
        # a real rejection should let a caller decide whether to loop back.
        self._rejected["pm"] = feedback

    @workflow.signal
    def plan_approved(self) -> None:
        if self._stage == "plan":
            self._advance_if_ready()

    @workflow.signal
    def plan_rejected(self, feedback: str) -> None:
        self._rejected["plan"] = feedback

    @workflow.signal
    def security_cleared(self) -> None:
        if self._stage == "security":
            self._advance_if_ready()

    @workflow.signal
    def security_rejected(self, feedback: str) -> None:
        self._rejected["security"] = feedback

    @workflow.query
    def stage(self) -> str:
        return self._stage

    @workflow.query
    def state(self) -> dict:
        return {"stage": self._stage, "rejected": dict(self._rejected)}

    @workflow.run
    async def run(self) -> str:
        await workflow.wait_condition(lambda: self._done)
        return self._stage
