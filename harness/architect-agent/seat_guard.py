"""Seat guard for subscription-seat-backed agent calls
(specs/009-credential-pool-handoff; Harness/Runtime §3.2, Inference Routing
§3.4 deviation — seat calls go direct to Anthropic, see research R4).

Wraps a Claude Agent SDK `query()` stream to (a) record the seat's last-seen
usage from `RateLimitEvent`s and (b) turn a seat-level failure into one of
two typed exceptions the caller hands back to the credential pool:

  SeatExhausted — usage limit hit (rejected event / 429 / usage message)
  SeatInvalid   — the seat's OAuth token is invalid/expired (401/403/login)

Anything else re-raises unchanged. Both exceptions subclass `Exception`
directly — NOT RuntimeError/ValueError — so no existing generic handler
(e.g. architect-agent's per-candidate `except (ValueError, RuntimeError)`)
can swallow or remap them (FR-011).

This file is duplicated byte-for-byte at harness/swe-agent/seat_guard.py and
harness/architect-agent/seat_guard.py (each harness runs in its own process
with its own deps); tests/test_seat_guard.py enforces the copies match.

Never logs, prints, or embeds a token.
"""
import contextlib
import os
import re
from collections.abc import AsyncIterator, Callable
from typing import Any

from claude_agent_sdk import RateLimitEvent, ResultError, query

# research R3: structured `api_error_status` first, message text as fallback.
_INVALID_STATUSES = {401, 403}
_EXHAUSTED_STATUSES = {429}
_INVALID_RE = re.compile(
    r"failed to authenticate|oauth .*invalid|login expired|token .*(expired|revoked)",
    re.IGNORECASE,
)
_EXHAUSTED_RE = re.compile(r"rate.?limit|usage limit|limit reached|quota", re.IGNORECASE)

FORCE_EXHAUST_ENV = "SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS"


class SeatExhausted(Exception):  # noqa: N818 - domain name, mirrors the ApplicationError type
    def __init__(self, resets_at: int | None = None, usage: dict | None = None) -> None:
        super().__init__("subscription seat usage limit reached")
        self.resets_at = resets_at
        self.usage = usage or {}


class SeatInvalid(Exception):  # noqa: N818 - domain name, mirrors the ApplicationError type
    def __init__(self, usage: dict | None = None) -> None:
        super().__init__("subscription seat credential is invalid or expired")
        self.usage = usage or {}


def seat_options_env(token: str) -> dict[str, str]:
    """`ClaudeAgentOptions.env` entries that make the seat token the only
    credential the CLI sees. `options.env` can override but never delete an
    inherited variable, and an inherited API key / base URL would otherwise
    win over the OAuth token — empty strings verified to override (R1)."""
    return {
        "CLAUDE_CODE_OAUTH_TOKEN": token,
        "ANTHROPIC_API_KEY": "",
        "ANTHROPIC_BASE_URL": "",
        "ANTHROPIC_AUTH_TOKEN": "",
    }


def usage_from_rate_limit_info(info: Any) -> dict:
    """{utilization, rate_limit_type, resets_at} from a RateLimitInfo.

    The typed `utilization` field is empty in practice; real per-window
    figures live in `raw["unifiedWindows"]` (R2). The tightest window binds,
    so take the max."""
    raw = getattr(info, "raw", None) or {}
    windows = raw.get("unifiedWindows") or {}
    scored = [
        (float(w["utilization"]), name)
        for name, w in windows.items()
        if isinstance(w, dict) and isinstance(w.get("utilization"), int | float)
    ]
    if scored:
        utilization, rate_limit_type = max(scored)
    else:
        utilization = getattr(info, "utilization", None)
        rate_limit_type = getattr(info, "rate_limit_type", None)
    resets_at = getattr(info, "resets_at", None) or raw.get("resetsAt")
    return {
        "utilization": utilization,
        "rate_limit_type": rate_limit_type,
        "resets_at": resets_at,
    }


def classify_result_error(data: dict | None) -> str | None:
    """'invalid' | 'exhausted' | None for a ResultError's result payload (R3)."""
    data = data or {}
    status = data.get("api_error_status")
    text = str(data.get("result") or "")
    if status in _INVALID_STATUSES or _INVALID_RE.search(text):
        return "invalid"
    if status in _EXHAUSTED_STATUSES or _EXHAUSTED_RE.search(text):
        return "exhausted"
    return None


def _merge_usage(usage: dict, snapshot: dict) -> None:
    for key, value in snapshot.items():
        if value is not None:
            usage[key] = value


async def guarded_query(
    prompt: str,
    options: Any,
    usage: dict,
    *,
    query_fn: Callable[..., Any] = query,
    force_check: Callable[[], bool] | None = None,
) -> AsyncIterator[Any]:
    """Yield every message of `query_fn(prompt=..., options=...)`, updating
    `usage` in place, raising SeatExhausted/SeatInvalid on a seat outcome.

    `query_fn` is injectable so each harness passes its own module-level
    `query` (which its tests monkeypatch). `force_check`, when given, is a
    test hook polled after every message — raising SeatExhausted once it
    returns True (see FORCE_EXHAUST_ENV). The stream runs inside `aclosing`,
    so raising mid-stream (or being cancelled) tears down the CLI subprocess
    instead of leaving it to keep hitting an exhausted seat."""
    try:
        async with contextlib.aclosing(query_fn(prompt=prompt, options=options)) as stream:
            async for message in stream:
                if isinstance(message, RateLimitEvent):
                    info = message.rate_limit_info
                    _merge_usage(usage, usage_from_rate_limit_info(info))
                    if getattr(info, "status", None) == "rejected":
                        raise SeatExhausted(usage.get("resets_at"), dict(usage))
                yield message
                if force_check is not None and force_check():
                    raise SeatExhausted(None, dict(usage))
    except ResultError as e:
        kind = classify_result_error(getattr(e, "data", None))
        if kind == "invalid":
            raise SeatInvalid(dict(usage)) from None
        if kind == "exhausted":
            # No rejected event was seen (that path raises above), so any
            # recorded resets_at belongs to an earlier *allowed* window —
            # possibly another window or already past. Unknown reset -> None
            # (the pool then applies its default window, research R7).
            raise SeatExhausted(None, dict(usage)) from None
        raise


def force_exhaust_after_commits() -> int | None:
    """N from SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS (test hook), else None."""
    value = os.environ.get(FORCE_EXHAUST_ENV, "").strip()
    return int(value) if value.isdigit() else None
