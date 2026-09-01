"""Temporal worker (§3.5). Sequences the pipeline itself — intake -> build ->
sandbox test -> gate -> register -> deploy -> monitor -- with crash-safe,
replayable state, per architecture doc §2.
"""
import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from workflows.pipeline_workflow import AgentPipelineWorkflow

TASK_QUEUE = "agent-factory-pipeline"


async def main() -> None:
    client = await Client.connect("localhost:7233")
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[AgentPipelineWorkflow],
        # TODO: register activities for build/sandbox-test/gate/register/deploy
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
