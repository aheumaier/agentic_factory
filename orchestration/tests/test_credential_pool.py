"""Credential pool (specs/009-credential-pool-handoff): config loading, pure
seat selection, and the long-lived CredentialPoolWorkflow.

Pure tests need nothing; workflow tests run against a real local Temporal
server (`make up`), like every other Temporal-facing test in this repo, and
skip without one. Every pool workflow started here is terminated in a
`finally` — it never completes on its own, so a missed terminate would leak
a live workflow onto the dev server for every test run.
"""
import contextlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from temporalio.client import Client, WorkflowUpdateFailedError
from temporalio.worker import Worker

from credentials.pool import (
    LEASE_TTL,
    earliest_reset,
    load_pool,
    new_seat_state,
    select_seat,
    token_for,
)
from workflows.credential_pool import CredentialPoolWorkflow

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def _write_pool(tmp_path, text: str):
    path = tmp_path / "pool.yaml"
    path.write_text(text)
    return path


TWO_SEATS = """
seats:
  seat-a: {token_env: SEAT_A_TOKEN, max_concurrent: 1, token_expires_on: 2027-10-10}
  seat-b: {token_env: SEAT_B_TOKEN, max_concurrent: 2}
assignments:
  swe-agent: [seat-a, seat-b]
  architect-agent: [seat-b]
"""


# --- load_pool / token_for (T005) -------------------------------------------

def test_load_pool_valid(tmp_path):
    pool = load_pool(_write_pool(tmp_path, TWO_SEATS))
    assert pool["seats"]["seat-a"] == {
        "token_env": "SEAT_A_TOKEN", "max_concurrent": 1, "token_expires_on": "2027-10-10",
    }
    assert pool["seats"]["seat-b"]["max_concurrent"] == 2
    assert pool["assignments"] == {
        "swe-agent": ["seat-a", "seat-b"], "architect-agent": ["seat-b"],
    }


def test_load_pool_default_file_is_seat_a_only():
    pool = load_pool()
    assert list(pool["seats"]) == ["seat-a"]
    assert pool["seats"]["seat-a"]["token_env"] == "CLAUDE_OAUTH_SEAT_A"


def test_load_pool_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_POOL_CONFIG", str(_write_pool(tmp_path, TWO_SEATS)))
    assert set(load_pool()["seats"]) == {"seat-a", "seat-b"}


@pytest.mark.parametrize(
    "text, match",
    [
        ("seats:\n  seat-a: {token_env: X}\nassignments:\n  a: [seat-z]\n", "unknown seat"),
        ("seats:\n  seat-a: {token_env: X}\nassignments:\n  a: [seat-a, seat-a]\n", "duplicate"),
        ("seats:\n  seat-a: {token_env: X, max_concurrent: 0}\n", "max_concurrent"),
        ("seats:\n  seat-a: {}\n", "token_env"),
        ("seats:\n  Seat_A: {token_env: X}\n", "invalid seat id"),
    ],
)
def test_load_pool_rejects_malformed(tmp_path, text, match):
    with pytest.raises(ValueError, match=match):
        load_pool(_write_pool(tmp_path, text))


def test_token_for_set_and_unset(tmp_path, monkeypatch):
    pool = load_pool(_write_pool(tmp_path, TWO_SEATS))
    monkeypatch.setenv("SEAT_A_TOKEN", "sk-ant-oat01-secret-value")
    assert token_for("seat-a", pool) == "sk-ant-oat01-secret-value"

    monkeypatch.delenv("SEAT_B_TOKEN", raising=False)
    with pytest.raises(KeyError) as exc:
        token_for("seat-b", pool)
    assert "SEAT_B_TOKEN" in str(exc.value)
    with pytest.raises(KeyError, match="unknown seat"):
        token_for("seat-z", pool)


def test_token_for_error_never_contains_a_value(tmp_path, monkeypatch):
    pool = load_pool(_write_pool(tmp_path, TWO_SEATS))
    monkeypatch.setenv("SEAT_A_TOKEN", "")
    with pytest.raises(KeyError) as exc:
        token_for("seat-a", pool)
    assert "sk-ant" not in str(exc.value)


# --- select_seat matrix (T029 / SC-005) ----------------------------------------

def _state(**overrides):
    state = {"seat-a": new_seat_state(), "seat-b": new_seat_state()}
    for seat_id, fields in overrides.items():
        state[seat_id.replace("_", "-")].update(fields)
    return state


@pytest.fixture
def two(tmp_path):
    return load_pool(_write_pool(tmp_path, TWO_SEATS))


def _pick(pool, state, agent="swe-agent", now=NOW):
    return select_seat(pool["seats"], state, pool["assignments"], agent, now)


def test_select_lowest_utilization_wins(two):
    assert _pick(two, _state(seat_a={"last_utilization": 0.7},
                             seat_b={"last_utilization": 0.2})) == "seat-b"


def test_select_tie_breaks_by_assignment_order(two):
    assert _pick(two, _state()) == "seat-a"


def test_select_shared_seat_serves_both_agents(two):
    state = _state(seat_a={"last_utilization": 0.9})
    assert _pick(two, state, "swe-agent") == "seat-b"
    assert _pick(two, state, "architect-agent") == "seat-b"


def test_select_skips_seat_at_concurrency_cap(two):
    state = _state(seat_a={"leases": {"k1": NOW.isoformat()}})  # seat-a max_concurrent=1
    assert _pick(two, state) == "seat-b"


def test_select_shared_seat_cap_counts_all_agents(two):
    leases = {"k1": NOW.isoformat(), "k2": NOW.isoformat()}  # seat-b max_concurrent=2
    assert _pick(two, _state(seat_b={"leases": leases}), "architect-agent") is None


def test_select_exhaustion_expires(two):
    future = _state(seat_a={"exhausted_until": (NOW + timedelta(minutes=5)).isoformat()},
                    seat_b={"last_utilization": 0.9})
    assert _pick(two, future) == "seat-b"
    past = _state(seat_a={"exhausted_until": (NOW - timedelta(minutes=5)).isoformat()},
                  seat_b={"last_utilization": 0.9})
    assert _pick(two, past) == "seat-a"


def test_select_invalid_seat_skipped_regardless_of_time(two):
    state = _state(seat_a={"invalid": True}, seat_b={"last_utilization": 0.99})
    assert _pick(two, state) == "seat-b"
    assert _pick(two, state, now=NOW + timedelta(days=365)) == "seat-b"


def test_select_ignores_leases_older_than_ttl(two):
    stale = (NOW - LEASE_TTL - timedelta(seconds=1)).isoformat()
    assert _pick(two, _state(seat_a={"leases": {"leaked": stale}})) == "seat-a"


def test_select_unassigned_agent_gets_none(two):
    assert _pick(two, _state(), "pm-agent") is None


def test_select_all_ineligible_gets_none(two):
    state = _state(seat_a={"invalid": True},
                   seat_b={"exhausted_until": (NOW + timedelta(hours=1)).isoformat()})
    assert _pick(two, state) is None


# --- earliest_reset (T032) -----------------------------------------------------

def test_earliest_reset_picks_minimum_future():
    soon, later = NOW + timedelta(minutes=10), NOW + timedelta(hours=3)
    state = _state(seat_a={"exhausted_until": later.isoformat()},
                   seat_b={"exhausted_until": soon.isoformat()})
    assert earliest_reset(state, NOW) == soon.isoformat()


def test_earliest_reset_none_when_only_invalid_or_expired():
    state = _state(seat_a={"invalid": True},
                   seat_b={"exhausted_until": (NOW - timedelta(minutes=1)).isoformat()})
    assert earliest_reset(state, NOW) is None


# --- CredentialPoolWorkflow against local Temporal (T009 / T030) --------------

async def _connect_or_skip() -> Client:
    try:
        return await Client.connect("localhost:7233")
    except Exception as exc:  # noqa: BLE001 - environment-dependent skip
        pytest.skip(f"Temporal not reachable at localhost:7233: {exc}")


@contextlib.asynccontextmanager
async def _running_pool(pool: dict):
    client = await _connect_or_skip()
    run_id = uuid.uuid4().hex[:8]
    task_queue = f"credential-pool-test-{run_id}"
    async with Worker(client, task_queue=task_queue, workflows=[CredentialPoolWorkflow]):
        handle = await client.start_workflow(
            CredentialPoolWorkflow.run, pool,
            id=f"credential-pool-test-{run_id}", task_queue=task_queue,
        )
        try:
            yield handle
        finally:
            with contextlib.suppress(Exception):  # best-effort cleanup only
                await handle.terminate()


async def test_pool_acquire_release_updates_utilization(two):
    async with _running_pool(two) as pool:
        seat = await pool.execute_update(CredentialPoolWorkflow.acquire, args=["swe-agent", "k1"])
        assert seat == "seat-a"
        table = await pool.query(CredentialPoolWorkflow.seats)
        assert table["seat-a"]["active_leases"] == 1

        await pool.execute_update(
            CredentialPoolWorkflow.release, args=["seat-a", "k1", 0.42, "seven_day"]
        )
        table = await pool.query(CredentialPoolWorkflow.seats)
        assert table["seat-a"]["active_leases"] == 0
        assert table["seat-a"]["last_utilization"] == 0.42
        assert table["seat-a"]["last_rate_limit_type"] == "seven_day"


async def test_pool_acquire_is_idempotent_per_lease_key(two):
    async with _running_pool(two) as pool:
        first = await pool.execute_update(CredentialPoolWorkflow.acquire, args=["swe-agent", "k1"])
        again = await pool.execute_update(CredentialPoolWorkflow.acquire, args=["swe-agent", "k1"])
        assert first == again == "seat-a"
        table = await pool.query(CredentialPoolWorkflow.seats)
        assert table["seat-a"]["active_leases"] == 1


async def test_pool_mark_exhausted_then_none_for_sole_seat(two):
    async with _running_pool(two) as pool:
        seat = await pool.execute_update(
            CredentialPoolWorkflow.acquire, args=["architect-agent", "k1"]
        )
        assert seat == "seat-b"
        resets = "2099-01-01T00:00:00+00:00"
        await pool.execute_update(CredentialPoolWorkflow.mark_exhausted, args=["seat-b", "k1", resets])
        table = await pool.query(CredentialPoolWorkflow.seats)
        assert table["seat-b"]["exhausted_until"] == resets
        assert table["seat-b"]["active_leases"] == 0
        assert table["seat-b"]["last_utilization"] == 1.0
        assert await pool.execute_update(
            CredentialPoolWorkflow.acquire, args=["architect-agent", "k2"]
        ) is None


async def test_pool_mark_exhausted_without_reset_defaults_one_hour(two):
    async with _running_pool(two) as pool:
        await pool.execute_update(CredentialPoolWorkflow.acquire, args=["swe-agent", "k1"])
        await pool.execute_update(CredentialPoolWorkflow.mark_exhausted, args=["seat-a", "k1", None])
        until = datetime.fromisoformat(
            (await pool.query(CredentialPoolWorkflow.seats))["seat-a"]["exhausted_until"]
        )
        assert timedelta(minutes=55) < until - datetime.now(UTC) <= timedelta(hours=1)


async def test_pool_mark_invalid_and_reset_seat(two):
    async with _running_pool(two) as pool:
        await pool.execute_update(CredentialPoolWorkflow.acquire, args=["swe-agent", "k1"])
        await pool.execute_update(CredentialPoolWorkflow.mark_invalid, args=["seat-a", "k1"])
        assert (await pool.query(CredentialPoolWorkflow.seats))["seat-a"]["invalid"] is True
        # seat-a is skipped now; swe-agent falls back to seat-b.
        assert await pool.execute_update(
            CredentialPoolWorkflow.acquire, args=["swe-agent", "k2"]
        ) == "seat-b"

        await pool.execute_update(CredentialPoolWorkflow.reset_seat, args=["seat-a"])
        table = await pool.query(CredentialPoolWorkflow.seats)
        assert table["seat-a"]["invalid"] is False
        assert table["seat-a"]["exhausted_until"] is None


async def test_pool_unknown_seat_updates_are_noops(two):
    async with _running_pool(two) as pool:
        await pool.execute_update(CredentialPoolWorkflow.release, args=["seat-z", "k", 0.5, None])
        await pool.execute_update(CredentialPoolWorkflow.mark_invalid, args=["seat-z", "k"])
        assert set(await pool.query(CredentialPoolWorkflow.seats)) == {"seat-a", "seat-b"}


async def test_pool_seats_query_never_exposes_token_env(two):
    async with _running_pool(two) as pool:
        table = await pool.query(CredentialPoolWorkflow.seats)
        assert "SEAT_A_TOKEN" not in repr(table)
        assert set(table["seat-a"]) == {
            "active_leases", "last_utilization", "last_rate_limit_type",
            "exhausted_until", "invalid", "max_concurrent",
        }


async def test_pool_reload_config_keeps_surviving_state(two, tmp_path):
    async with _running_pool(two) as pool:
        await pool.execute_update(CredentialPoolWorkflow.acquire, args=["swe-agent", "k1"])
        await pool.execute_update(
            CredentialPoolWorkflow.release, args=["seat-a", "k1", 0.33, "five_hour"]
        )
        new = load_pool(_write_pool(tmp_path, """
seats:
  seat-a: {token_env: SEAT_A_TOKEN}
  seat-c: {token_env: SEAT_C_TOKEN}
assignments:
  swe-agent: [seat-c, seat-a]
"""))
        await pool.execute_update(
            CredentialPoolWorkflow.reload_config, args=[new["seats"], new["assignments"]]
        )
        table = await pool.query(CredentialPoolWorkflow.seats)
        assert set(table) == {"seat-a", "seat-c"}
        assert table["seat-a"]["last_utilization"] == 0.33
        assert table["seat-c"]["last_utilization"] == 0.0


def test_load_pool_rejects_duplicate_seat_key(tmp_path):
    text = """
seats:
  seat-a: {token_env: SEAT_A_TOKEN}
  seat-a: {token_env: SEAT_B_TOKEN}
"""
    with pytest.raises(ValueError, match="duplicate key 'seat-a'"):
        load_pool(_write_pool(tmp_path, text))


async def test_pool_rejects_naive_reset_and_stays_healthy(two):
    async with _running_pool(two) as pool:
        await pool.execute_update(CredentialPoolWorkflow.acquire, args=["swe-agent", "k1"])
        with pytest.raises(WorkflowUpdateFailedError):
            await pool.execute_update(
                CredentialPoolWorkflow.mark_exhausted, args=["seat-a", "k1", "2026-10-10T17:00:00"]
            )
        with pytest.raises(WorkflowUpdateFailedError):
            await pool.execute_update(
                CredentialPoolWorkflow.mark_exhausted, args=["seat-a", "k1", "1791655200"]
            )
        # Rejected before mutation: lease still held, and the pool still serves.
        table = await pool.query(CredentialPoolWorkflow.seats)
        assert table["seat-a"]["active_leases"] == 1
        assert table["seat-a"]["exhausted_until"] is None
        assert await pool.execute_update(
            CredentialPoolWorkflow.acquire, args=["swe-agent", "k2"]
        ) == "seat-b"


async def test_pool_rejects_invalid_reload_config_and_stays_healthy(two):
    async with _running_pool(two) as pool:
        bad_assignments = {"swe-agent": ["seat-z"]}
        with pytest.raises(WorkflowUpdateFailedError):
            await pool.execute_update(
                CredentialPoolWorkflow.reload_config, args=[two["seats"], bad_assignments]
            )
        assert await pool.execute_update(
            CredentialPoolWorkflow.acquire, args=["swe-agent", "k1"]
        ) == "seat-a"
