"""Shared limit for every workflow a test starts on the live Temporal server (specs/014)."""
from datetime import timedelta

from temporalio.client import WorkflowHandle

# Longer than pytest-timeout's 60 s, so it never ends a workflow whose test may
# still run; execution_timeout (not run_timeout) spans continue-as-new.
# It also bounds a debugger session (pytest-timeout turns off under --pdb); raise it locally to debug.
TEST_WORKFLOW_TIMEOUT = timedelta(minutes=2)


async def recorded_limit(handle: WorkflowHandle) -> timedelta:
    """The execution limit the server recorded for this workflow (0 = none).

    The raw value is a protobuf Duration, which never equals a timedelta."""
    config = (await handle.describe()).raw_description.execution_config
    return config.workflow_execution_timeout.ToTimedelta()
