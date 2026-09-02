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
from temporalio.exceptions import ApplicationError

# activities.py loads eval/braintrust/eval.config.py via importlib at module
# import time (Path.resolve(), exec_module) — real filesystem/non-
# deterministic work the workflow sandbox otherwise refuses to run during
# workflow validation. It's never executed as workflow code (only referenced
# by name for execute_activity), so pass it through, along with the e2b SDK
# activities.py uses to run the SWE agent.
with workflow.unsafe.imports_passed_through():
    from activities import eval_gate_activity, register_activity, run_swe_agent_activity

MAX_BUILD_ATTEMPTS = 3

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


@workflow.defn
class AgentPipelineWorkflow:
    @workflow.run
    async def run(self, repo: str, branch: str, agent_name: str, version: str) -> str:
        feedback: str | None = None
        eval_result: dict = {}

        for attempt in range(1, MAX_BUILD_ATTEMPTS + 1):
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
