"""Temporal worker (§3.5). Sequences the pipeline itself — intake -> build ->
sandbox test -> gate -> register -> deploy -> monitor -- with crash-safe,
replayable state, per architecture doc §2.
"""
import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from activities import (
    architect_stage_activity,
    ensure_target_pr_activity,
    eval_gate_activity,
    promote_agent_activity,
    register_activity,
    run_swe_agent_activity,
)
from workflows.pipeline_workflow import AgentPipelineWorkflow
from workflows.registry_promotion_waiter import RegistryPromotionWaiterWorkflow

TASK_QUEUE = "agent-factory-pipeline"


async def main() -> None:
    client = await Client.connect("localhost:7233")
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[AgentPipelineWorkflow, RegistryPromotionWaiterWorkflow],
        activities=[
            ensure_target_pr_activity,
            architect_stage_activity,
            run_swe_agent_activity,
            eval_gate_activity,
            register_activity,
            promote_agent_activity,
        ],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
