"""One real-Temporal test (research.md/H6): every other Temporal-facing test
(test_temporal_client.py) runs against a mock, so a wrong kwarg name, a wrong
import path, or a renamed exception class would pass every mocked test and
fail only on first real use. This confirms the actual SDK surface round-trips
against a live `make up` Temporal instance.
"""
import asyncio
import uuid

import pytest
from temporalio import workflow
from temporalio.client import Client
from temporalio.worker import Worker

from webhook_bridge import temporal_client

TASK_QUEUE = "webhook-bridge-integration-test"


@workflow.defn(name="_IntegrationProbeWorkflow")
class _IntegrationProbeWorkflow:
    def __init__(self) -> None:
        self._decision: str | None = None

    @workflow.signal
    def pm_approved(self) -> None:
        self._decision = "pm_approved"

    @workflow.run
    async def run(self) -> str:
        await workflow.wait_condition(lambda: self._decision is not None)
        assert self._decision is not None
        return self._decision


async def _connect_or_skip() -> Client:
    try:
        return await Client.connect("localhost:7233")
    except Exception as exc:  # noqa: BLE001 - environment-dependent skip
        pytest.skip(f"Temporal not reachable at localhost:7233: {exc}")


async def test_real_temporal_start_resolve_and_signal_round_trip() -> None:
    client = await _connect_or_skip()

    # Unique per run (not just agent_name) so a leftover workflow from a
    # prior/interrupted test run can never collide with this run's query.
    run_id = uuid.uuid4().hex[:8]
    repo = f"owner/integration-test-repo-{run_id}"
    pr_number = uuid.uuid4().int % 1_000_000
    agent_name = f"probe-{run_id}"
    version = "1"
    wf_id = temporal_client.workflow_id(repo, agent_name, version)

    async with Worker(
        client, task_queue=TASK_QUEUE, workflows=[_IntegrationProbeWorkflow]
    ):
        handle = await client.start_workflow(
            "_IntegrationProbeWorkflow",
            id=wf_id,
            task_queue=TASK_QUEUE,
            search_attributes={"TargetRepo": [repo], "PRNumber": [pr_number]},
        )
        assert handle.id == wf_id

        try:
            # Visibility indexing (search attributes) is eventually
            # consistent — poll briefly rather than assuming the write is
            # visible immediately.
            resolution = None
            for _ in range(25):
                resolution = await temporal_client.resolve_gate_target(client, repo, pr_number)
                if resolution.handle is not None:
                    break
                await asyncio.sleep(0.2)
            assert resolution is not None and resolution.handle is not None, (
                resolution.reason if resolution else None
            )
            assert resolution.handle.id == wf_id

            await resolution.handle.signal("pm_approved")
            result = await resolution.handle.result()
            assert result == "pm_approved"
        finally:
            try:
                await handle.terminate()
            except Exception:  # noqa: BLE001 - best-effort cleanup only
                pass
