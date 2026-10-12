"""run_swe_agent_activity's seat protocol (specs/009-credential-pool-handoff,
contracts/seat-guard-and-agent-protocol.md): sandbox env, seat_status
parsing, and the exit-code -> typed ApplicationError mapping.

AsyncSandbox is replaced with a fake, so no E2B call happens; the fake
raises e2b's real CommandExitException exactly as `commands.run` does on a
non-zero exit (research R8).
"""
import json
import logging

import aiohttp
import pytest
from e2b import CommandExitException
from temporalio.exceptions import ApplicationError

import activities
from webhook_bridge.github_app import MintedToken

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


PAT = "github_pat_TESTONLY000000000000000000"  # the worker's own GH_TOKEN


class _Minter:
    """Stands in for GitHubAppClient: records each mint, and answers from
    `outcomes` (an exception or a MintedToken) in order, then with a fresh
    well-formed token per call."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.outcomes: list = []
        self.issued: list[str] = []

    def client(self, app_id, private_key_b64, session):
        minter = self

        class _Client:
            async def mint_repo_token(self, repo, permissions):
                minter.calls.append((repo, dict(permissions)))
                outcome = minter.outcomes.pop(0) if minter.outcomes else minter.token_for(repo)
                if isinstance(outcome, Exception):
                    raise outcome
                minter.issued.append(outcome.token)
                return outcome

        return _Client()

    def token_for(self, repo, permissions=None, repositories=None):
        return MintedToken(
            token=f"ghs_MINTEDTESTONLY00000000000000{len(self.calls)}",
            repositories=repositories or [repo.split("/", 1)[1]],
            permissions=permissions or dict(activities._SANDBOX_TOKEN_PERMISSIONS),
            expires_at="2026-10-11T13:00:00Z",
        )


@pytest.fixture
def minter(monkeypatch):
    m = _Minter()
    monkeypatch.setattr(activities, "GitHubAppClient", m.client)
    monkeypatch.setattr(activities, "_MINT_RETRY_WAIT_SECONDS", 0)
    monkeypatch.setenv("SWE_AGENT_APP_ID", "1")
    monkeypatch.setenv("SWE_AGENT_APP_PRIVATE_KEY", "dummy")
    return m


@pytest.fixture
def sandbox(monkeypatch, minter):
    holder: dict = {}

    class _FakeAsyncSandbox:
        @staticmethod
        async def create(**kwargs):
            box = holder["box"]
            box.created_with = kwargs
            return box

    monkeypatch.setattr(activities, "AsyncSandbox", _FakeAsyncSandbox)
    monkeypatch.setenv("CLAUDE_OAUTH_SEAT_A", TOKEN)
    monkeypatch.setenv("GH_TOKEN", PAT)
    monkeypatch.delenv("CREDENTIAL_POOL_CONFIG", raising=False)
    monkeypatch.delenv("SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS", raising=False)
    monkeypatch.delenv("SEAT_GUARD_FORCE_EXHAUST_SEAT", raising=False)
    monkeypatch.delenv("SEAT_GUARD_FORCE_EXHAUST_HANDOFF", raising=False)

    def use(outcome) -> _FakeSandbox:
        holder["box"] = _FakeSandbox(outcome)
        return holder["box"]

    return use


def _ok_stdout(utilization=0.37, rate_limit_type="seven_day", utilization_resets_at=None):
    status = {"seat_status": "ok", "utilization": utilization,
              "rate_limit_type": rate_limit_type}
    if utilization_resets_at is not None:
        status["utilization_resets_at"] = utilization_resets_at
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
        "utilization_resets_at": None,
    }
    assert box.killed


async def test_sandbox_env_carries_seat_token_not_api_key(sandbox, minter):
    box = sandbox(_Result(_ok_stdout()))
    await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-a")
    envs = box.created_with["envs"]
    assert envs["CLAUDE_CODE_OAUTH_TOKEN"] == TOKEN
    assert envs["GH_TOKEN"] == minter.issued[0]  # specs/013: the minted App token
    assert not any("github_pat_" in v for v in envs.values())
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


async def test_unknown_seat_fails_before_any_sandbox(sandbox, minter):
    box = sandbox(_Result(_ok_stdout()))
    with pytest.raises(KeyError, match="unknown seat"):
        await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-z")
    assert box.created_with == {}
    assert minter.calls == []  # specs/013: no token is minted for a run that can't start


# --- specs/013: per-run GitHub App token for the Build sandbox ----------------

async def test_mint_asks_for_target_repo_and_sandbox_rights(sandbox, minter):
    sandbox(_Result(_ok_stdout()))
    await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-a")
    assert minter.calls == [("o/r", {"contents": "write", "pull_requests": "write",
                                     "metadata": "read"})]


async def test_each_call_mints_its_own_token(sandbox, minter):
    first = sandbox(_Result(_ok_stdout()))
    await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-a")
    second = sandbox(_Result(_ok_stdout()))
    await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-a", 1)
    assert len(minter.calls) == 2
    assert first.created_with["envs"]["GH_TOKEN"] != second.created_with["envs"]["GH_TOKEN"]


async def _mint_failure(sandbox, minter, *outcomes) -> ApplicationError:
    box = sandbox(_Result(_ok_stdout()))
    minter.outcomes = list(outcomes)
    with pytest.raises(ApplicationError) as exc:
        await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-a")
    assert box.created_with == {}  # no sandbox, so no fallback to the worker's token
    assert exc.value.type == "SandboxTokenMintFailed"
    assert exc.value.non_retryable
    assert list(exc.value.details) == []
    # `from None` where raised inside `except`: no chained exception reaches the history
    assert exc.value.__cause__ is None
    assert exc.value.__context__ is None or exc.value.__suppress_context__
    return exc.value


@pytest.mark.parametrize("error, reason", [
    (aiohttp.ClientResponseError(None, (), status=502), "HTTP 502"),
    (aiohttp.ClientConnectionError(), "ClientConnectionError"),
    (TimeoutError(), "TimeoutError"),
])
async def test_transient_mint_error_is_retried_then_fails(sandbox, minter, error, reason):
    err = await _mint_failure(sandbox, minter, error, error, error)
    assert err.message == f"could not mint a GitHub App token for o/r: {reason}"
    assert len(minter.calls) == activities._MINT_TRIES == 3


async def test_transient_mint_error_then_success_runs(sandbox, minter):
    box = sandbox(_Result(_ok_stdout()))
    minter.outcomes = [aiohttp.ClientResponseError(None, (), status=503)]
    await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-a")
    assert len(minter.calls) == 2
    assert box.created_with["envs"]["GH_TOKEN"] == minter.issued[0]


@pytest.mark.parametrize("error, reason", [
    (aiohttp.ClientResponseError(None, (), status=404), "HTTP 404"),
    (aiohttp.ClientResponseError(None, (), status=422), "HTTP 422"),
    (aiohttp.ContentTypeError(None, (), status=200), "HTTP 200"),
    (KeyError("token"), "KeyError"),
])
async def test_permanent_mint_error_fails_at_once(sandbox, minter, error, reason):
    err = await _mint_failure(sandbox, minter, error)
    assert err.message == f"could not mint a GitHub App token for o/r: {reason}"
    assert len(minter.calls) == 1


async def test_bad_private_key_fails_with_its_class_name(sandbox, monkeypatch):
    # The real client: its constructor decodes the key, before any request.
    import webhook_bridge.github_app as github_app
    monkeypatch.setattr(activities, "GitHubAppClient", github_app.GitHubAppClient)
    box = sandbox(_Result(_ok_stdout()))
    with pytest.raises(ApplicationError, match=r"for o/r: Error$"):
        await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-a")
    assert box.created_with == {}


@pytest.mark.parametrize("missing", ["SWE_AGENT_APP_ID", "SWE_AGENT_APP_PRIVATE_KEY"])
async def test_missing_app_env_fails_without_a_mint(sandbox, minter, monkeypatch, missing):
    monkeypatch.delenv(missing)
    err = await _mint_failure(sandbox, minter)
    assert err.message.endswith("SWE_AGENT_APP_ID or SWE_AGENT_APP_PRIVATE_KEY is not set")
    assert minter.calls == []


@pytest.mark.parametrize("grant", [
    {"repositories": ["r", "other"]},
    {"permissions": {**activities._SANDBOX_TOKEN_PERMISSIONS, "workflows": "write"}},
    {"permissions": {**activities._SANDBOX_TOKEN_PERMISSIONS, "contents": "read"}},
])
async def test_grant_other_than_asked_fails(sandbox, minter, grant):
    err = await _mint_failure(sandbox, minter, minter.token_for("o/r", **grant))
    assert err.message.endswith(": grant mismatch")


async def test_minted_token_stays_out_of_logs(sandbox, minter, caplog):
    sandbox(_Result(_ok_stdout()))
    with caplog.at_level(logging.DEBUG):
        await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-a")
    assert "sandbox token minted for o/r" in caplog.text
    assert "expires_at=2026-10-11T13:00:00Z" in caplog.text
    assert minter.issued[0] not in caplog.text
    assert PAT not in caplog.text


async def test_pr_url_from_sandbox_stdout_is_redacted(sandbox, minter):
    minter.outcomes = [minter.token_for("o/r")]
    minted = minter.outcomes[0].token
    sandbox(_Result(_ok_stdout() + f"done {minted} {PAT}\n"))
    result = await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-a")
    assert result["pr_url"] == "done *** ***"


async def test_failed_run_logs_no_secret(sandbox, minter, monkeypatch, caplog):
    app_key = "app-key-test-only-0123456789"
    monkeypatch.setenv("SWE_AGENT_APP_PRIVATE_KEY", app_key)
    minter.outcomes = [minter.token_for("o/r")]
    minted = minter.outcomes[0].token
    sandbox(_exit(1, stderr=f"push failed: {minted} {PAT} {TOKEN}"))
    with caplog.at_level(logging.DEBUG), pytest.raises(RuntimeError):
        await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-a")
    for secret in (minted, PAT, TOKEN, app_key):
        assert secret not in caplog.text


async def test_run_failure_message_redacts_every_github_token(sandbox, minter):
    stray = "ghu_" + "A" * 30  # token-shaped, known to nobody
    minter.outcomes = [minter.token_for("o/r")]
    minted = minter.outcomes[0].token
    sandbox(_exit(1, stderr=f"push failed: {minted} {PAT} {TOKEN} {stray}"))
    with pytest.raises(RuntimeError, match=r"sandbox run failed \(1\): push failed") as exc:
        await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-a")
    for secret in (minted, PAT, TOKEN, stray):
        assert secret not in str(exc.value)


async def test_sandbox_create_failure_is_wrapped_and_redacted(sandbox, minter, monkeypatch):
    class _FailingSandbox:
        @staticmethod
        async def create(**kwargs):
            raise ValueError(f"bad envs: {kwargs['envs']}")

    sandbox(_Result(_ok_stdout()))
    monkeypatch.setattr(activities, "AsyncSandbox", _FailingSandbox)
    with pytest.raises(RuntimeError, match="^sandbox create failed: ") as exc:
        await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-a")
    assert exc.value.__cause__ is None
    assert exc.value.__suppress_context__
    for secret in (minter.issued[0], TOKEN):
        assert secret not in str(exc.value)


def test_run_failure_redacts_the_workers_token(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", PAT)
    with pytest.raises(RuntimeError) as exc:
        activities._run(["false", f"https://x-access-token:{PAT}@github.com/o/r.git"])
    assert PAT not in str(exc.value)
    assert "x-access-token:***@" in str(exc.value)


def test_command_budget_ends_before_the_token_expires():
    # The token exists from the mint on; after it come sandbox create (bounded
    # by e2b's request timeout) and the command. Mint retries come before it.
    from e2b.connection_config import REQUEST_TIMEOUT
    assert REQUEST_TIMEOUT + activities._COMMAND_TIMEOUT_SECONDS < 60 * 60


# --- architect_stage_activity on seats (T035) -----------------------------------

@pytest.fixture
def architect(monkeypatch):
    """Replace run_architect_stage; returns the kwargs it was called with."""
    seen: dict = {}
    monkeypatch.setenv("CLAUDE_OAUTH_SEAT_A", TOKEN)
    monkeypatch.delenv("CREDENTIAL_POOL_CONFIG", raising=False)
    monkeypatch.setattr(activities, "_HEARTBEAT_INTERVAL_SECONDS", 3600)

    def use(outcome):
        async def fake(repo, branch, pr_url, attempt, **kwargs):
            seen.update(kwargs)
            if isinstance(outcome, BaseException):
                raise outcome
            return dict(outcome)
        monkeypatch.setattr(activities._architect_agent, "run_architect_stage", fake)
        return seen

    return use


def _arch(seat_id="seat-a"):
    return activities.architect_stage_activity(
        "o/r", "feat-x", "https://github.com/o/r/pull/1", 1, None, seat_id,
    )


async def test_architect_seat_mode_passes_token_and_reports_usage(architect):
    seen = architect({"plan_md": "p", "_seat_usage": {
        "utilization": 0.4, "rate_limit_type": "seven_day", "resets_at": 1}})
    result = await _arch()
    assert seen["seat_token"] == TOKEN
    assert "_seat_usage" not in result
    assert result["seat_id"] == "seat-a"
    assert (result["utilization"], result["rate_limit_type"]) == (0.4, "seven_day")


async def test_architect_idempotent_hit_on_seat_has_null_usage(architect):
    architect({"attempt": 1, "comment_body": "c", "idempotent_hit": True})
    result = await _arch()
    assert result["idempotent_hit"] is True
    assert result["utilization"] is None


async def test_architect_without_seat_stays_litellm_routed(architect):
    seen = architect({"plan_md": "p"})
    result = await _arch(seat_id=None)
    assert seen["seat_token"] is None
    assert "seat_id" not in result


async def test_architect_seat_exhausted_maps_before_plan_failure_types(architect):
    architect(activities._architect_agent.SeatExhausted(1791655200, {"utilization": 1.0}))
    with pytest.raises(ApplicationError) as exc:
        await _arch()
    assert exc.value.type == "SeatExhausted"
    assert exc.value.non_retryable
    assert list(exc.value.details) == ["seat-a", "2026-10-10T18:00:00+00:00"]


async def test_architect_seat_invalid_maps_to_typed_error(architect):
    architect(activities._architect_agent.SeatInvalid())
    with pytest.raises(ApplicationError) as exc:
        await _arch()
    assert exc.value.type == "SeatInvalid"
    assert list(exc.value.details) == ["seat-a"]
    assert TOKEN not in str(exc.value)


async def test_architect_plan_failure_mapping_unchanged(architect):
    architect(ValueError("no SC ids"))
    with pytest.raises(ApplicationError) as exc:
        await _arch()
    assert exc.value.type == "PlanDeterministicFailure"


async def test_architect_missing_seat_token_is_typed_pool_failure(architect, monkeypatch):
    architect({"plan_md": "p"})
    monkeypatch.delenv("CLAUDE_OAUTH_SEAT_A")
    with pytest.raises(ApplicationError) as exc:
        await _arch()
    assert exc.value.type == "CredentialPoolUnavailable"
    assert exc.value.non_retryable
    assert "CLAUDE_OAUTH_SEAT_A" in str(exc.value)


# --- specs/011: handoff index (F5) and force hook by handoff (F6) -------------

async def test_sandbox_env_carries_handoff_index(sandbox):
    box = sandbox(_Result(_ok_stdout()))
    await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-a")
    assert box.created_with["envs"]["SEAT_HANDOFF_INDEX"] == "0"
    box = sandbox(_Result(_ok_stdout()))
    await activities.run_swe_agent_activity("o/r", "feat-x", "fix it", "seat-a", 2)
    assert box.created_with["envs"]["SEAT_HANDOFF_INDEX"] == "2"


async def test_force_hook_by_handoff_index_on_any_seat(sandbox, monkeypatch, tmp_path):
    pool = tmp_path / "pool.yaml"
    pool.write_text(
        "seats:\n"
        "  seat-a: {token_env: CLAUDE_OAUTH_SEAT_A}\n"
        "  seat-b: {token_env: CLAUDE_OAUTH_SEAT_A}\n"
        "assignments: {swe-agent: [seat-a, seat-b]}\n"
    )
    monkeypatch.setenv("CREDENTIAL_POOL_CONFIG", str(pool))
    monkeypatch.setenv("SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS", "1")
    monkeypatch.setenv("SEAT_GUARD_FORCE_EXHAUST_HANDOFF", "0")
    for seat_id in ("seat-a", "seat-b"):
        box = sandbox(_Result(_ok_stdout()))
        await activities.run_swe_agent_activity("o/r", "feat-x", None, seat_id, 0)
        assert box.created_with["envs"]["SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS"] == "1"

    box = sandbox(_Result(_ok_stdout()))
    await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-a", 1)
    assert "SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS" not in box.created_with["envs"]


async def test_force_hook_by_handoff_needs_the_commit_count(sandbox, monkeypatch):
    monkeypatch.setenv("SEAT_GUARD_FORCE_EXHAUST_HANDOFF", "0")
    box = sandbox(_Result(_ok_stdout()))
    await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-a", 0)
    assert "SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS" not in box.created_with["envs"]


# --- specs/011 F2: the reading's window reset reaches the workflow ------------

async def test_success_result_carries_the_readings_reset_as_iso(sandbox):
    sandbox(_Result(_ok_stdout(utilization_resets_at=1791831600)))
    result = await activities.run_swe_agent_activity("o/r", "feat-x", None, "seat-a")
    assert result["utilization_resets_at"] == "2026-10-12T19:00:00+00:00"
