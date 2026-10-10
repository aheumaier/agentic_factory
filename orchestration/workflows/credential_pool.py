"""Long-lived credential pool (specs/009-credential-pool-handoff, §3.5).

One instance (ID `credential-pool`, overridable via CREDENTIAL_POOL_ID) owns
all subscription-seat lease/usage state, so seat selection is serialized and
survives worker restarts. Pipeline workflows can't call updates on another
workflow, so they reach this one through the three thin seat activities in
activities.py (research R5).

Payloads carry seat IDs only — never a token (FR-023). Selection logic lives
in credentials/pool.py as pure functions, fed `workflow.now()`.
"""
from datetime import datetime

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from credentials.pool import (
        DEFAULT_EXHAUST_WINDOW,
        LEASE_TTL,
        active_leases,
        earliest_reset,
        expires_in_days,
        new_seat_state,
        parse_aware_iso,
        select_seat,
        validate_pool,
    )


@workflow.defn
class CredentialPoolWorkflow:
    # @workflow.init: an update can arrive in the very first activation,
    # before `run` starts — config/state must already be in place then.
    @workflow.init
    def __init__(self, pool: dict) -> None:
        self._seats: dict = {}
        self._assignments: dict = {}
        self._state: dict = {}
        self._apply_config(pool["seats"], pool["assignments"], pool.get("state"))

    @workflow.run
    async def run(self, pool: dict) -> None:
        # Never completes on its own; bounds history by continuing-as-new
        # once Temporal suggests it, carrying config + state forward.
        await workflow.wait_condition(
            lambda: workflow.info().is_continue_as_new_suggested()
        )
        await workflow.wait_condition(workflow.all_handlers_finished)
        workflow.continue_as_new(
            {"seats": self._seats, "assignments": self._assignments, "state": self._state}
        )

    def _apply_config(self, seats: dict, assignments: dict, state: dict | None) -> None:
        state = state or {}
        self._seats = seats
        self._assignments = assignments
        # Merged over defaults: state carried from an older pool version
        # (e.g. 009, before utilization_resets_at) gains the new keys.
        self._state = {
            seat_id: {**new_seat_state(), **(state.get(seat_id) or {})} for seat_id in seats
        }

    def _prune(self, now: datetime) -> None:
        for seat_state in self._state.values():
            seat_state["leases"] = {
                key: acquired for key, acquired in seat_state["leases"].items()
                if now - datetime.fromisoformat(acquired) < LEASE_TTL
            }

    def _holder(self, lease_key: str) -> str | None:
        for seat_id, seat_state in self._state.items():
            if lease_key in seat_state["leases"]:
                return seat_id
        return None

    def _drop_lease(self, seat_id: str, lease_key: str) -> dict | None:
        seat_state = self._state.get(seat_id)
        if seat_state is not None:
            seat_state["leases"].pop(lease_key, None)
        return seat_state

    @workflow.update
    def acquire(self, agent: str, lease_key: str) -> str | None:
        now = workflow.now()
        self._prune(now)
        # Idempotent per lease_key: a Temporal-retried acquire gets the same seat.
        held = self._holder(lease_key)
        if held is not None:
            return held
        seat_id = select_seat(self._seats, self._state, self._assignments, agent, now)
        if seat_id is not None:
            self._state[seat_id]["leases"][lease_key] = now.isoformat()
        return seat_id

    @workflow.update
    def release(
        self, seat_id: str, lease_key: str,
        utilization: float | None, rate_limit_type: str | None,
        utilization_resets_at: str | None = None,
    ) -> None:
        seat_state = self._drop_lease(seat_id, lease_key)
        if seat_state is not None and utilization is not None:
            seat_state["last_utilization"] = float(utilization)
            seat_state["last_rate_limit_type"] = rate_limit_type
            # Always with the reading (None included): a new reading never
            # inherits an older one's reset time (specs/011 F2).
            seat_state["utilization_resets_at"] = utilization_resets_at

    @release.validator
    def _validate_release(
        self, seat_id: str, lease_key: str,
        utilization: float | None, rate_limit_type: str | None,
        utilization_resets_at: str | None = None,
    ) -> None:
        if utilization_resets_at is not None:
            parse_aware_iso(utilization_resets_at)

    @workflow.update
    def mark_exhausted(self, seat_id: str, lease_key: str, resets_at_iso: str | None) -> None:
        seat_state = self._drop_lease(seat_id, lease_key)
        if seat_state is None:
            return
        until = resets_at_iso or (workflow.now() + DEFAULT_EXHAUST_WINDOW).isoformat()
        seat_state["exhausted_until"] = until
        seat_state["last_utilization"] = 1.0
        # The 1.0 stops counting when the exhaustion ends (specs/011 F2).
        seat_state["utilization_resets_at"] = until

    # Validators reject bad input before it is stored (and without writing
    # history): a value the selection code can't compare would otherwise
    # fail every later workflow task — taking the whole pool down.
    @mark_exhausted.validator
    def _validate_mark_exhausted(
        self, seat_id: str, lease_key: str, resets_at_iso: str | None,
    ) -> None:
        if resets_at_iso is not None:
            parse_aware_iso(resets_at_iso)

    @workflow.update
    def mark_invalid(self, seat_id: str, lease_key: str) -> None:
        seat_state = self._drop_lease(seat_id, lease_key)
        if seat_state is not None:
            seat_state["invalid"] = True

    @workflow.update
    def reset_seat(self, seat_id: str) -> None:
        """Operator action after renewing a seat's token."""
        seat_state = self._state.get(seat_id)
        if seat_state is not None:
            seat_state["invalid"] = False
            seat_state["exhausted_until"] = None
            # The exhaustion's 1.0 reading goes too (specs/011 F2), or the
            # reset seat would stay last in line until the old reset time.
            seat_state["last_utilization"] = 0.0
            seat_state["utilization_resets_at"] = None

    @workflow.update
    def reload_config(self, seats: dict, assignments: dict) -> None:
        """Apply pool.yaml edits: keeps state for surviving seat IDs."""
        self._apply_config(seats, assignments, self._state)

    @reload_config.validator
    def _validate_reload_config(self, seats: dict, assignments: dict) -> None:
        validate_pool(seats, assignments, source="reload_config")

    @workflow.query
    def earliest_reset_for(self, agent: str) -> str | None:
        """Earliest future reset among `agent`'s assigned, non-invalid seats
        (specs/011 F3: what an empty-pool stage waits for)."""
        return earliest_reset(self._state, workflow.now(), self._assignments.get(agent, []))

    @workflow.query
    def seats(self) -> dict:
        now = workflow.now()
        return {
            seat_id: {
                "active_leases": active_leases(self._state[seat_id], now),
                "last_utilization": self._state[seat_id]["last_utilization"],
                "last_rate_limit_type": self._state[seat_id]["last_rate_limit_type"],
                "utilization_resets_at": self._state[seat_id]["utilization_resets_at"],
                "exhausted_until": self._state[seat_id]["exhausted_until"],
                "invalid": self._state[seat_id]["invalid"],
                "max_concurrent": cfg["max_concurrent"],
                "expires_in_days": expires_in_days(cfg, now.date()),  # specs/011 F4
            }
            for seat_id, cfg in self._seats.items()
        }
