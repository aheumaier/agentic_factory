"""Temporal worker (§3.5). Sequences the pipeline itself — intake -> build ->
sandbox test -> gate -> register -> deploy -> monitor -- with crash-safe,
replayable state, per architecture doc §2.
"""
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy
from temporalio.worker import Worker

from activities import (
    acquire_seat_activity,
    architect_stage_activity,
    ensure_target_pr_activity,
    eval_gate_activity,
    promote_agent_activity,
    register_activity,
    release_seat_activity,
    report_seat_failure_activity,
    run_swe_agent_activity,
)
from credentials.pool import load_pool
from workflows.credential_pool import CredentialPoolWorkflow
from workflows.pipeline_workflow import AgentPipelineWorkflow
from workflows.registry_promotion_waiter import RegistryPromotionWaiterWorkflow

TASK_QUEUE = "agent-factory-pipeline"


async def main() -> None:
    # Explicit, not a side effect of activities.py loading the architect
    # agent: the seat tokens (CLAUDE_OAUTH_SEAT_*, specs/009) live only in
    # the repo .env, and `make worker` exports nothing. Never overrides a
    # value already in the process env.
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    client = await Client.connect("localhost:7233")

    # The long-lived seat pool (specs/009). USE_EXISTING makes this idempotent
    # across worker restarts: a running pool keeps its state; pool.yaml edits
    # are applied via its reload_config update, not by restarting it.
    await client.start_workflow(
        CredentialPoolWorkflow.run,
        load_pool(),
        id=os.environ.get("CREDENTIAL_POOL_ID", "credential-pool"),
        task_queue=TASK_QUEUE,
        id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
    )

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[
            AgentPipelineWorkflow,
            RegistryPromotionWaiterWorkflow,
            CredentialPoolWorkflow,
        ],
        activities=[
            ensure_target_pr_activity,
            architect_stage_activity,
            run_swe_agent_activity,
            eval_gate_activity,
            register_activity,
            promote_agent_activity,
            acquire_seat_activity,
            release_seat_activity,
            report_seat_failure_activity,
        ],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
