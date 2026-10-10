"""run_swe_agent_activity's seat protocol (specs/009-credential-pool-handoff,
contracts/seat-guard-and-agent-protocol.md): sandbox env, seat_status
parsing, and the exit-code -> typed ApplicationError mapping.

AsyncSandbox is replaced with a fake, so no E2B call happens; the fake
raises e2b's real CommandExitException exactly as `commands.run` does on a
non-zero exit (research R8).
"""
import json

import pytest
from e2b import CommandExitException
from temporalio.exceptions import ApplicationError

import activities

TOKEN = "sk-ant-oat01-test-only-not-a-real-token"


class _FakeSandbox:
    def __init__(self, outcome):
        self.outcome = outcome
        self.created_with: dict = {}
        self.run_kwargs: dict = {}
        self.killed = False
        self.commands = self

    async def run(self, cmd, **kwargs):
        self.run_kwargs = {"cmd": cmd, **kwargs}
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome

    async def kill(self):
        self.killed = True


class _Result:
    def __init__(self, stdout: str):
        self.stdout = stdout
        self.stderr = ""
        self.exit_code = 0


@pytest.fixture
def sandbox(monkeypatch):
    holder: dict = {}

    class _FakeAsyncSandbox:
        @staticmethod
        async def create(**kwargs):
            box = holder["box"]
            box.created_with = kwargs
            return box

    monkeypatch.setattr(activities, "AsyncSandbox", _FakeAsyncSandbox)
    monkeypatch.setenv("CLAUDE_OAUTH_SEAT_A", TOKEN)
    monkeypatch.setenv("GH_TOKEN", "ghs_test")
    monkeypatch.delenv("CREDENTIAL_POOL_CONFIG", raising=False)
    monkeypatch.delenv("SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS", raising=False)
    monkeypatch.delenv("SEAT_GUARD_FORCE_EXHAUST_SEAT", raising=False)

    def use(outcome) -> _FakeSandbox:
        holder["box"] = _FakeSandbox(outcome)
        return holder["box"]

    return use


def _ok_stdout(utilization=0.37, rate_limit_type="seven_day"):
    status = {"seat_status": "ok", "utilization": utilization,
              "rate_limit_type": rate_limit_type}
    return f"working...\n{json.dumps(status)}\nhttps://github.com/o/r/pull/7\n"


def _exit(code: int, stdout: str = "", stderr: str = "") -> CommandExitException:
    return CommandExitException(stderr=stderr, stdout=stdout, exit_code=code, error=None)


# --- _parse_seat_status (T020) -------------------------------------------------

def test_parse_seat_status_ok_line():
    assert activities._parse_seat_status(_ok_stdout()) == {
        "seat_status": "ok", "utilization": 0.37, "rate_limit_type": "seven_day",
    }


def test_parse_seat_status_missing_or_malformed():
    assert activities._parse_seat_status("just\nhttps://x/pull/1") == {}
    assert activities._parse_seat_status('{"seat_status": oops}\nurl') == {}
    assert activities._parse_seat_status("") == {}


# --- success path (T020) -------------------------------------------------------

async def test_success_returns_dict_with_usage(sandbox):
    box = sandbox(_Result(_ok_stdout()))
    result = await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-a")
    assert result == {
        "pr_url": "https://github.com/o/r/pull/7", "seat_id": "seat-a",
        "utilization": 0.37, "rate_limit_type": "seven_day",
    }
    assert box.killed


async def test_sandbox_env_carries_seat_token_not_api_key(sandbox):
    box = sandbox(_Result(_ok_stdout()))
    await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-a")
    envs = box.created_with["envs"]
    assert envs["CLAUDE_CODE_OAUTH_TOKEN"] == TOKEN
    assert envs["GH_TOKEN"] == "ghs_test"
    assert "ANTHROPIC_PLATFORM_API_KEY" not in envs
    assert "SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS" not in envs


async def test_timeouts_command_budget_inside_sandbox_lifetime(sandbox):
    box = sandbox(_Result(_ok_stdout()))
    await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-a")
    command_timeout = box.run_kwargs["timeout"]
    sandbox_timeout = box.created_with["timeout"]
    assert command_timeout == activities._COMMAND_TIMEOUT_SECONDS > 60  # not e2b's 60s default
    assert sandbox_timeout >= command_timeout + 120
    assert sandbox_timeout < 60 * 60  # under the Build activity's 60-min timeout


# --- exit-code mapping (T027) --------------------------------------------------

async def test_exit_75_raises_seat_exhausted_with_reset_iso(sandbox):
    status = {"seat_status": "exhausted", "resets_at": 1791655200,
              "utilization": 1.0, "rate_limit_type": "five_hour"}
    box = sandbox(_exit(75, stdout=json.dumps(status)))
    with pytest.raises(ApplicationError) as exc:
        await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-a")
    assert exc.value.type == "SeatExhausted"
    assert exc.value.non_retryable
    assert list(exc.value.details) == ["seat-a", "2026-10-10T18:00:00+00:00"]
    assert box.killed


async def test_exit_75_without_reset_carries_none(sandbox):
    sandbox(_exit(75, stdout='{"seat_status": "exhausted", "resets_at": null}'))
    with pytest.raises(ApplicationError) as exc:
        await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-a")
    assert list(exc.value.details) == ["seat-a", None]


async def test_exit_77_raises_seat_invalid(sandbox):
    sandbox(_exit(77, stdout='{"seat_status": "invalid"}'))
    with pytest.raises(ApplicationError) as exc:
        await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-a")
    assert exc.value.type == "SeatInvalid"
    assert list(exc.value.details) == ["seat-a"]


async def test_other_exit_raises_runtime_error_without_token(sandbox):
    sandbox(_exit(1, stderr="Traceback: boom"))
    with pytest.raises(RuntimeError, match=r"sandbox run failed \(1\): Traceback: boom") as exc:
        await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-a")
    assert TOKEN not in str(exc.value)


async def test_force_hook_forwarded_only_for_named_seat(sandbox, monkeypatch):
    monkeypatch.setenv("SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS", "1")
    monkeypatch.setenv("SEAT_GUARD_FORCE_EXHAUST_SEAT", "seat-a")
    box = sandbox(_Result(_ok_stdout()))
    await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-a")
    assert box.created_with["envs"]["SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS"] == "1"

    monkeypatch.setenv("SEAT_GUARD_FORCE_EXHAUST_SEAT", "seat-b")
    box = sandbox(_Result(_ok_stdout()))
    await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-a")
    assert "SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS" not in box.created_with["envs"]


async def test_unknown_seat_fails_before_any_sandbox(sandbox):
    box = sandbox(_Result(_ok_stdout()))
    with pytest.raises(KeyError, match="unknown seat"):
        await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-z")
    assert box.created_with == {}
