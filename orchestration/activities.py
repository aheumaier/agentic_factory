"""Temporal activities (§3.5) wrapping the SWE agent (Harness/Runtime, §3.2).

Loaded via `importlib` because `harness/swe-agent/` is a hyphenated
directory name and isn't importable as a normal Python package.
"""
import importlib.util
import tempfile
from pathlib import Path

from temporalio import activity

_AGENT_PATH = (
    Path(__file__).resolve().parent.parent / "harness" / "swe-agent" / "agent.py"
)
_spec = importlib.util.spec_from_file_location("swe_agent", _AGENT_PATH)
_swe_agent = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_swe_agent)


@activity.defn
async def run_swe_agent_activity(repo: str, branch: str) -> str:
    """Not idempotent — may already have pushed on partial failure.
    Workflow sets maximum_attempts=1."""
    with tempfile.TemporaryDirectory() as td:
        return await _swe_agent.run(repo, branch, Path(td))
