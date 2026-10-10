"""seat_guard (specs/009-credential-pool-handoff): seat-outcome classification,
usage parsing, the seat-only options env, and the guarded query stream.

Runs against the claude_agent_sdk stub in tests/conftest.py — no network,
no model call. Payload shapes mirror what research R1-R3 observed live.
"""
import asyncio

import claude_agent_sdk as sdk
import pytest

from conftest import REPO_ROOT, _load_agent

SWE_GUARD = REPO_ROOT / "harness" / "swe-agent" / "seat_guard.py"
ARCH_GUARD = REPO_ROOT / "harness" / "architect-agent" / "seat_guard.py"

guard = _load_agent("seat_guard_under_test", SWE_GUARD)

# research R2: what a real seat emitted on 2026-10-10.
R2_RAW = {
    "status": "allowed", "resetsAt": 1791655200, "rateLimitType": "five_hour",
    "unifiedWindows": {
        "five_hour": {"utilization": 0.26, "resetsAt": 1791655200},
        "seven_day": {"utilization": 0.37, "resetsAt": 1791831600},
    },
}


def _event(status="allowed", raw=None, **kw):
    return sdk.RateLimitEvent(sdk.RateLimitInfo(status=status, raw=raw, **kw))


def _fake_query(*messages, raise_at_end=None):
    async def fake(*, prompt, options=None):
        for m in messages:
            yield m
        if raise_at_end is not None:
            raise raise_at_end
    return fake


async def _drain(gen):
    return [m async for m in gen]


# --- exception hierarchy (FR-011) ---------------------------------------------

def test_seat_exceptions_are_not_runtime_or_value_errors():
    for exc in (guard.SeatExhausted(), guard.SeatInvalid()):
        assert not isinstance(exc, RuntimeError | ValueError)


def test_guard_copies_are_byte_identical():
    assert SWE_GUARD.read_bytes() == ARCH_GUARD.read_bytes()


# --- classify_result_error (research R3) --------------------------------------

@pytest.mark.parametrize(
    "data, expected",
    [
        ({"api_error_status": 401, "result": "Failed to authenticate. API Error: 401 "
          "OAuth access token is invalid."}, "invalid"),
        ({"api_error_status": 403, "result": "forbidden"}, "invalid"),
        ({"result": "Your login expired, please log in again"}, "invalid"),
        ({"api_error_status": 429, "result": "Too many requests"}, "exhausted"),
        ({"result": "Claude usage limit reached. Resets at 5pm"}, "exhausted"),
        ({"result": "API Error: rate_limit_error"}, "exhausted"),
        ({"api_error_status": 500, "result": "Internal server error"}, None),
        ({"result": "API Error: Connection refused"}, None),
        (None, None),
    ],
)
def test_classify_result_error(data, expected):
    assert guard.classify_result_error(data) == expected


# --- usage_from_rate_limit_info (research R2) ---------------------------------

def test_usage_takes_max_unified_window():
    info = sdk.RateLimitInfo(raw=R2_RAW, resets_at=1791655200, rate_limit_type="five_hour")
    assert guard.usage_from_rate_limit_info(info) == {
        "utilization": 0.37, "rate_limit_type": "seven_day", "resets_at": 1791655200,
    }


def test_usage_falls_back_to_typed_fields():
    info = sdk.RateLimitInfo(utilization=0.5, rate_limit_type="five_hour", resets_at=7)
    assert guard.usage_from_rate_limit_info(info) == {
        "utilization": 0.5, "rate_limit_type": "five_hour", "resets_at": 7,
    }


def test_usage_all_missing_is_none():
    usage = guard.usage_from_rate_limit_info(sdk.RateLimitInfo())
    assert usage == {"utilization": None, "rate_limit_type": None, "resets_at": None}


def test_usage_resets_at_from_raw_when_typed_missing():
    info = sdk.RateLimitInfo(raw={"resetsAt": 123})
    assert guard.usage_from_rate_limit_info(info)["resets_at"] == 123


# --- seat_options_env (research R1) -------------------------------------------

def test_seat_options_env_blanks_competing_credentials():
    assert guard.seat_options_env("tok") == {
        "CLAUDE_CODE_OAUTH_TOKEN": "tok",
        "ANTHROPIC_API_KEY": "",
        "ANTHROPIC_BASE_URL": "",
        "ANTHROPIC_AUTH_TOKEN": "",
    }


# --- guarded_query --------------------------------------------------------------

def test_guarded_query_passes_messages_and_records_usage():
    done = sdk.ResultMessage(result="OK")
    usage: dict = {}
    out = asyncio.run(_drain(guard.guarded_query(
        "p", None, usage, query_fn=_fake_query(_event(raw=R2_RAW, resets_at=99), done),
    )))
    assert out[-1] is done
    assert usage == {"utilization": 0.37, "rate_limit_type": "seven_day", "resets_at": 99}


def test_guarded_query_rejected_event_raises_exhausted_with_reset():
    usage: dict = {}
    fake = _fake_query(_event(status="rejected", resets_at=1791655200, raw=R2_RAW),
                       sdk.ResultMessage(result="never reached"))
    with pytest.raises(guard.SeatExhausted) as exc:
        asyncio.run(_drain(guard.guarded_query("p", None, usage, query_fn=fake)))
    assert exc.value.resets_at == 1791655200
    assert exc.value.usage["utilization"] == 0.37


def test_guarded_query_closes_stream_on_seat_outcome():
    closed = []

    async def fake(*, prompt, options=None):
        try:
            yield _event(status="rejected", resets_at=1)
            yield sdk.ResultMessage(result="never reached")
        finally:
            closed.append(True)

    with pytest.raises(guard.SeatExhausted):
        asyncio.run(_drain(guard.guarded_query("p", None, {}, query_fn=fake)))
    assert closed == [True]


@pytest.mark.parametrize(
    "data, exc_type",
    [
        ({"api_error_status": 401, "result": "Failed to authenticate."}, "SeatInvalid"),
        ({"api_error_status": 429, "result": "rate limited"}, "SeatExhausted"),
    ],
)
def test_guarded_query_maps_result_errors(data, exc_type):
    fake = _fake_query(raise_at_end=sdk.ResultError("boom", data=data))
    with pytest.raises(getattr(guard, exc_type)):
        asyncio.run(_drain(guard.guarded_query("p", None, {}, query_fn=fake)))


def test_guarded_query_reraises_unrelated_result_error_unchanged():
    err = sdk.ResultError("boom", data={"api_error_status": 500, "result": "server error"})
    with pytest.raises(sdk.ResultError) as exc:
        asyncio.run(_drain(guard.guarded_query(
            "p", None, {}, query_fn=_fake_query(raise_at_end=err),
        )))
    assert exc.value is err


def test_guarded_query_reraises_other_exceptions_unchanged():
    with pytest.raises(ValueError, match="bad json"):
        asyncio.run(_drain(guard.guarded_query(
            "p", None, {}, query_fn=_fake_query(raise_at_end=ValueError("bad json")),
        )))


def test_guarded_query_force_check_raises_exhausted():
    checks = iter([False, True])
    fake = _fake_query(sdk.ResultMessage(result="a"), sdk.ResultMessage(result="b"),
                       sdk.ResultMessage(result="c"))
    with pytest.raises(guard.SeatExhausted) as exc:
        asyncio.run(_drain(guard.guarded_query(
            "p", None, {}, query_fn=fake, force_check=lambda: next(checks),
        )))
    assert exc.value.resets_at is None


def test_force_exhaust_after_commits_env(monkeypatch):
    monkeypatch.delenv(guard.FORCE_EXHAUST_ENV, raising=False)
    assert guard.force_exhaust_after_commits() is None
    monkeypatch.setenv(guard.FORCE_EXHAUST_ENV, "2")
    assert guard.force_exhaust_after_commits() == 2
    monkeypatch.setenv(guard.FORCE_EXHAUST_ENV, "nope")
    assert guard.force_exhaust_after_commits() is None


def test_result_error_exhaustion_ignores_reset_from_earlier_allowed_event():
    """An earlier *allowed* event's resetsAt belongs to whatever window was
    binding then; a 429 with no rejected event has an unknown reset."""
    fake = _fake_query(
        _event(raw=R2_RAW, resets_at=1791655200),
        raise_at_end=sdk.ResultError("boom", data={"api_error_status": 429}),
    )
    usage: dict = {}
    with pytest.raises(guard.SeatExhausted) as exc:
        asyncio.run(_drain(guard.guarded_query("p", None, usage, query_fn=fake)))
    assert exc.value.resets_at is None
    assert exc.value.usage["utilization"] == 0.37
