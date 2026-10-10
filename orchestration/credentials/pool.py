"""Subscription-seat credential pool: config loading and pure seat selection
(specs/009-credential-pool-handoff; Orchestration §3.5, Inference Routing
§3.4 deviation — seat-backed calls go direct to Anthropic, see research R4).

Deliberately free of Temporal imports: `CredentialPoolWorkflow` imports this
through `workflow.unsafe.imports_passed_through()`, and every function the
workflow calls here is pure (time is always passed in as `now`), so it stays
deterministic on replay.

Config holds seat IDs and the *name* of each seat's token env var — never a
token. `token_for()` is the only place a token value is read, and it runs in
activities only, never in workflow code.
"""
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import yaml

DEFAULT_POOL_PATH = Path(__file__).resolve().parent / "pool.yaml"

# Longer than a single attempt of the longest stage (Build: 60 min, one
# attempt; Architect: 30 min), so normally only a genuinely leaked lease —
# e.g. a pipeline workflow terminated mid-stage — ever ages out (research
# R6). Architect retries under _TRANSIENT_RETRY (4 x 30 min + backoff), so a
# worst-case all-timeouts run can outlive its lease by ~35 s, briefly
# letting the seat be oversubscribed by one; accepted.
LEASE_TTL = timedelta(hours=2)

# Used when a seat is exhausted but no reset time was reported (research R7).
DEFAULT_EXHAUST_WINDOW = timedelta(hours=1)

_SEAT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects a repeated mapping key — plain safe_load keeps
    the last one silently, so a copy-pasted `seat-a:` block would quietly
    rebind seat-a to the second block's token_env."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise ValueError(f"duplicate key {key!r} in pool config")
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def load_pool(path: str | Path | None = None) -> dict:
    """Load and validate the pool config. Fails fast on a malformed pool;
    does NOT require the token env vars to be set (only `token_for` does),
    so tests and the workflow can load a pool without credentials."""
    path = Path(path or os.environ.get("CREDENTIAL_POOL_CONFIG") or DEFAULT_POOL_PATH)
    raw = yaml.load(path.read_text(), Loader=_UniqueKeyLoader) or {}  # noqa: S506 - SafeLoader subclass
    return validate_pool(raw.get("seats") or {}, raw.get("assignments") or {}, source=str(path))


def validate_pool(raw_seats: dict, raw_assignments: dict, source: str = "pool config") -> dict:
    """Normalize + validate seats/assignments; raises ValueError. Shared by
    load_pool and CredentialPoolWorkflow's reload_config validator, so an
    operator's live config change gets the same checks as worker boot."""
    path = source
    seats: dict[str, dict] = {}
    for seat_id, cfg in raw_seats.items():
        if not isinstance(seat_id, str) or not _SEAT_ID_RE.match(seat_id):
            raise ValueError(f"{path}: invalid seat id {seat_id!r}")
        cfg = cfg or {}
        token_env = cfg.get("token_env")
        if not isinstance(token_env, str) or not token_env:
            raise ValueError(f"{path}: seat {seat_id!r} has no token_env")
        max_concurrent = int(cfg.get("max_concurrent", 1))
        if max_concurrent < 1:
            raise ValueError(f"{path}: seat {seat_id!r} max_concurrent must be >= 1")
        expires = cfg.get("token_expires_on")
        seats[seat_id] = {
            "token_env": token_env,
            "max_concurrent": max_concurrent,
            "token_expires_on": str(expires) if expires is not None else None,
        }

    assignments: dict[str, list[str]] = {}
    for agent, seat_ids in raw_assignments.items():
        seat_ids = list(seat_ids or [])
        if len(set(seat_ids)) != len(seat_ids):
            raise ValueError(f"{path}: duplicate seat in assignment for {agent!r}")
        unknown = [s for s in seat_ids if s not in seats]
        if unknown:
            raise ValueError(f"{path}: assignment for {agent!r} names unknown seat(s) {unknown}")
        assignments[str(agent)] = seat_ids

    return {"seats": seats, "assignments": assignments}


def parse_aware_iso(ts: str) -> datetime:
    """Parse an ISO timestamp, requiring a timezone — pool state compares it
    against tz-aware `workflow.now()`, so a naive value would break every
    later selection. Raises ValueError."""
    parsed = datetime.fromisoformat(ts)
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp {ts!r} has no timezone")
    return parsed


def token_for(seat_id: str, pool: dict) -> str:
    """The seat's OAuth token, read from the env var its config names.
    Activity-side only. Errors name the env var, never a value."""
    seat = pool["seats"].get(seat_id)
    if seat is None:
        raise KeyError(f"unknown seat {seat_id!r}")
    token = os.environ.get(seat["token_env"])
    if not token:
        raise KeyError(f"seat {seat_id!r}: env var {seat['token_env']} is not set")
    return token


def new_seat_state() -> dict:
    return {
        "leases": {},  # lease_key -> acquired_at (ISO)
        "last_utilization": 0.0,
        "last_rate_limit_type": None,
        "exhausted_until": None,  # ISO or None
        "invalid": False,
    }


def _parse(ts: str | None) -> datetime | None:
    return datetime.fromisoformat(ts) if ts else None


def active_leases(seat_state: dict, now: datetime, lease_ttl: timedelta = LEASE_TTL) -> int:
    return sum(
        1 for acquired in seat_state["leases"].values()
        if now - datetime.fromisoformat(acquired) < lease_ttl
    )


def is_eligible(seat_cfg: dict, seat_state: dict, now: datetime,
                lease_ttl: timedelta = LEASE_TTL) -> bool:
    if seat_state["invalid"]:
        return False
    until = _parse(seat_state["exhausted_until"])
    if until is not None and until > now:
        return False
    return active_leases(seat_state, now, lease_ttl) < seat_cfg["max_concurrent"]


def select_seat(seats: dict, state: dict, assignments: dict, agent: str,
                now: datetime, lease_ttl: timedelta = LEASE_TTL) -> str | None:
    """Pick the eligible seat assigned to `agent` with the lowest last-seen
    utilization, tie-broken by the agent's assignment order. Pure."""
    candidates = [
        (state[seat_id]["last_utilization"], index, seat_id)
        for index, seat_id in enumerate(assignments.get(agent, []))
        if is_eligible(seats[seat_id], state[seat_id], now, lease_ttl)
    ]
    return min(candidates)[2] if candidates else None


def earliest_reset(state: dict, now: datetime) -> str | None:
    """Earliest future `exhausted_until` across seats (ISO), or None — e.g.
    when every unavailable seat is invalid rather than exhausted."""
    until = [datetime.fromisoformat(s["exhausted_until"])
             for s in state.values() if s["exhausted_until"]]
    future = [t for t in until if t > now]
    return min(future).isoformat() if future else None
