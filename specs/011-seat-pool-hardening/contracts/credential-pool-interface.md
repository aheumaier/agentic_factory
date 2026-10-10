# Contract delta: `CredentialPoolWorkflow` and the seat activities (011)

Extends `specs/009-credential-pool-handoff/contracts/credential-pool-interface.md`. That contract still holds except where changed below.

**Usage Constraint (binding):** internal, single-operator use only. The seats are the operator's own, they are never offered to third parties, and seat rotation is a knowingly accepted Consumer-Terms grey area.

## Updates

| Update | Change |
|---|---|
| `release` | New trailing arg `utilization_resets_at: str \| None = None` (tz-aware ISO; validator rejects a naive one). When `utilization` is non-null, it stores both the reading and this reset time (`None` clears an older one). |
| `mark_exhausted` | Also sets `utilization_resets_at = exhausted_until`, so the 1.0 reading expires with the exhaustion. |

## Selection

`select_seat` orders eligible seats by `(effective_utilization, assignment index)`. A reading whose `utilization_resets_at` has passed counts as 0 (data-model). Eligibility is unchanged.

## Query

`seats()` rows gain `"utilization_resets_at": str|None` and `"expires_in_days": int|None`.

## Activities

`release_seat_activity(seat_id, lease_key, utilization, rate_limit_type, utilization_resets_at=None)`. The other two activities are unchanged.

## Workflow helper: `_with_seat(agent, stage, invocation, activity, args, *, with_handoff=False, **opts)`

```
waits = 0
for handoff in range(MAX_SEAT_HANDOFFS + 1):
    key = f"{workflow_id}/{stage}/{invocation}/{handoff}"
    loop:
        got = acquire_seat_activity(agent, key)
        if got.seat_id: break
        wait = _pool_wait(got.earliest_reset, waits)      # None => fail fast
        if wait is None: raise CredentialPoolExhausted(details=[got.earliest_reset])
        waits += 1; workflow.sleep(wait)                    # same key, same handoff
    run activity(*args, seat_id, [handoff if with_handoff])
    ... 009 handoff / release logic, release passes result["utilization_resets_at"]
```

`_pool_wait` returns a delay only when `workflow.patched("seat-pool-wait-v1")` is true, the reset is known and at most `POOL_WAIT_HORIZON` (6 h) away, and `waits < MAX_POOL_WAITS` (2). The delay is `max(reset - now, 0) + 1 s`. `patched` is evaluated only on this path.

Build calls `_with_seat(..., with_handoff=True)`. The architect stage does not.

## Worker boot

After `load_pool()`, the worker logs `seat <id>: credential expires on <date> (<n> days)` at WARNING for every seat with `expires_in_days <= EXPIRY_WARN_DAYS` (14), including expired seats. Seat ID and date only.
