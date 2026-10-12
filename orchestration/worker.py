"""Temporal worker (§3.5). Sequences the pipeline itself — intake -> build ->
sandbox test -> gate -> register -> deploy -> monitor -- with crash-safe,
replayable state, per architecture doc §2.
"""
import asyncio
import logging
import os
from datetime import date
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
from credentials.pool import expiring_seats, load_pool
from workflows.credential_pool import CredentialPoolWorkflow
from workflows.pipeline_workflow import AgentPipelineWorkflow
from workflows.registry_promotion_waiter import RegistryPromotionWaiterWorkflow

TASK_QUEUE = "agent-factory-pipeline"

logger = logging.getLogger(__name__)


def warn_expiring_seats(pool: dict, today: date) -> None:
    """specs/011 F4: one warning per seat whose credential expires within
    EXPIRY_WARN_DAYS or already has — seat ID and date only, never a token."""
    for seat_id, expires_on, days in expiring_seats(pool, today):
        logger.warning(
            "seat %s: credential expires on %s (%d days) - renew it with "
            "`claude setup-token`, then update .env and token_expires_on in pool.yaml",
            seat_id, expires_on, days,
        )


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
    pool = load_pool()
    warn_expiring_seats(pool, date.today())
    await client.start_workflow(
        CredentialPoolWorkflow.run,
        pool,
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
    # Without a handler Python prints WARNING and up only, so activity.logger
    # INFO lines (specs/013's "sandbox token minted" grant line) never reached
    # the worker log. INFO is opened for our activities' logger alone, not for
    # third-party libraries.
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("temporalio.activity").setLevel(logging.INFO)
    asyncio.run(main())
