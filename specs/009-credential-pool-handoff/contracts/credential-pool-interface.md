# Contract: `CredentialPoolWorkflow` and the seat activities (009)

Workflow type: `CredentialPoolWorkflow`. Task queue: `agent-factory-pipeline`. ID: `os.environ.get("CREDENTIAL_POOL_ID", "credential-pool")`.
It starts at worker boot with `id_conflict_policy=USE_EXISTING`.

**Input.** `{"seats": {...}, "assignments": {...}, "state": {...} | None}`. This is the parsed `pool.yaml` plus the state carried over a `continue_as_new`. The config is re-read at worker boot, but a running pool keeps its config until it next continues-as-new. Applying `pool.yaml` edits needs an explicit `reload_config` update (below), which merges state for seat IDs that still exist.

All payloads contain seat **IDs**, never credentials (FR-023).

## Updates

| Update | Args | Returns | Semantics |
|---|---|---|---|
| `acquire` | `agent: str, lease_key: str` | `str \| None` (seat_id) | Idempotent per `lease_key`: if `lease_key` already holds a seat, return that seat. Otherwise use `select_seat(…, now=workflow.now())`, add the lease and return the seat ID, or return `None`. Prunes TTL-expired leases. |
| `release` | `seat_id, lease_key, utilization: float \| None, rate_limit_type: str \| None` | `None` | Removes the lease (a no-op if absent). Updates `last_utilization`/`last_rate_limit_type` when `utilization` is not None. |
| `mark_exhausted` | `seat_id, lease_key, resets_at_iso: str \| None` | `None` | Removes the lease. `exhausted_until = resets_at or now + 1h`. `last_utilization = 1.0`. |
| `mark_invalid` | `seat_id, lease_key` | `None` | Removes the lease. `invalid = True`. |
| `reset_seat` | `seat_id` | `None` | Operator action after renewing a credential: clears `invalid` and `exhausted_until`. |
| `reload_config` | `seats, assignments` | `None` | Replaces the config. Keeps state for surviving seat IDs, drops removed ones, and initializes new ones. |

Unknown `seat_id` in `release`/`mark_*`/`reset_seat`: a no-op. A stale run must never crash the pool.

## Query

`seats() -> dict[seat_id, {"active_leases": int, "last_utilization": float, "last_rate_limit_type": str|None, "exhausted_until": str|None, "invalid": bool, "max_concurrent": int}]`

## History bound

After each handler, once `workflow.info().is_continue_as_new_suggested()` is true, the main loop waits for `workflow.all_handlers_finished()` and then calls `continue_as_new` with the current config and state.

## Activities (`orchestration/activities.py`)

All three activities resolve the pool through `activity.client().get_workflow_handle(pool_id)`. All three are safe to retry: acquire and release are idempotent per `lease_key`, and the mark operations are idempotent in effect. They use the workflow's `_TRANSIENT_RETRY` policy.

| Activity | Args | Returns |
|---|---|---|
| `acquire_seat_activity` | `agent, lease_key` | `{"seat_id": str\|None, "earliest_reset": str\|None}`. `earliest_reset` is filled only when `seat_id` is None, read from the `seats()` query. |
| `release_seat_activity` | `seat_id, lease_key, utilization, rate_limit_type` | `None` |
| `report_seat_failure_activity` | `seat_id, lease_key, kind: "exhausted"\|"invalid", resets_at_iso` | `None` |

## Workflow helper: `AgentPipelineWorkflow._with_seat(agent, stage, invocation, activity, args, **opts)`

```
for handoff in range(MAX_SEAT_HANDOFFS + 1):
    key = f"{workflow_id}/{stage}/{invocation}/{handoff}"
    got = acquire_seat_activity(agent, key)
    if got.seat_id is None: raise ApplicationError(type="CredentialPoolExhausted", details=[got.earliest_reset])
    try:
        result = execute_activity(activity, args + [got.seat_id], **opts)
    except ActivityError as e with e.cause.type in {"SeatExhausted","SeatInvalid"}:
        report_seat_failure_activity(seat, key, kind, resets_at); continue      # lease already removed by mark_*
    except BaseException:
        release_seat_activity(seat, key, None, None); raise                     # never strand a lease
    release_seat_activity(seat, key, result.get("utilization"), result.get("rate_limit_type"))
    return result
raise ApplicationError(type="SeatHandoffsExhausted", details=[stage, MAX_SEAT_HANDOFFS])
```

Both raised failures are `non_retryable=True`. The Build loop does not catch them, so they fail the run. The plan loop's existing `except` must check `cause.type in {"CredentialPoolExhausted", "SeatHandoffsExhausted"}` **before** its budget-charging branch, and re-raise without charging, the same way it handles `MalformedRetriesExhausted`.

Gated by `workflow.patched("seat-pool-v1")`. On the unpatched path, Build and Architect are called exactly as before.
