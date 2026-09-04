"""Test harness support for tests/test_pm_agent.py.

`harness/pm-agent/agent.py` declares its own runtime deps
(`claude-agent-sdk`, `braintrust`) in its own `pyproject.toml`, per
`CLAUDE.md`'s "don't conflate" rule for harness vs. root deps — the root
venv (`pytest`/`pyyaml` only, per root `pyproject.toml`) never installs
them. Stub both modules here so `import agent` succeeds under
`uv run pytest` from repo root with no real network or model access;
tests monkeypatch `agent.query` per-test to control model output.
"""
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PM_AGENT_DIR = REPO_ROOT / "harness" / "pm-agent"
if str(PM_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(PM_AGENT_DIR))

if "claude_agent_sdk" not in sys.modules:
    _sdk_stub = types.ModuleType("claude_agent_sdk")

    class ClaudeAgentOptions:
        def __init__(self, **kwargs):
            self.tools = kwargs.get("tools")
            self.allowed_tools = kwargs.get("allowed_tools", [])
            self.permission_mode = kwargs.get("permission_mode")
            self.setting_sources = kwargs.get("setting_sources")
            self.cwd = kwargs.get("cwd")
            self.env = kwargs.get("env", {})

    async def query(*, prompt, options=None):
        raise RuntimeError(
            "claude_agent_sdk.query stub called directly — tests must "
            "monkeypatch agent.query"
        )
        yield  # pragma: no cover - keeps this an async generator

    _sdk_stub.ClaudeAgentOptions = ClaudeAgentOptions
    _sdk_stub.query = query
    sys.modules["claude_agent_sdk"] = _sdk_stub

if "dotenv" not in sys.modules:
    _dotenv_stub = types.ModuleType("dotenv")

    def load_dotenv(*args, **kwargs):
        return False

    _dotenv_stub.load_dotenv = load_dotenv
    sys.modules["dotenv"] = _dotenv_stub

if "braintrust" not in sys.modules:
    _bt_stub = types.ModuleType("braintrust")

    class _StubLogger:
        def flush(self):
            pass

    def init_logger(project=None):
        return _StubLogger()

    def auto_instrument():
        pass

    _bt_stub.init_logger = init_logger
    _bt_stub.auto_instrument = auto_instrument
    sys.modules["braintrust"] = _bt_stub


def _load_agent(name: str, path: Path) -> types.ModuleType:
    """Load a second harness/<agent>/agent.py under its own module name.

    `import agent` (above) puts harness/pm-agent/ on sys.path so
    tests/test_pm_agent.py can `import agent` — a second
    harness/<agent>/agent.py would collide on that same module name if
    loaded the same way. Loading by explicit file path under a distinct
    name avoids the collision without touching the existing path shim or
    test_pm_agent.py.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


architect_agent = _load_agent(
    "architect_agent", REPO_ROOT / "harness" / "architect-agent" / "agent.py"
)
