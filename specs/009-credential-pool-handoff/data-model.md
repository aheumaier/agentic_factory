# Data Model: Credential Pool (009)

## SeatConfig (static, from `orchestration/credentials/pool.yaml`)

| Field | Type | Rule |
|---|---|---|
| `seat_id` | str | YAML key, `^[a-z0-9][a-z0-9-]*$`, unique |
| `token_env` | str | **name** of the env var holding the credential; never the value |
| `max_concurrent` | int | ≥ 1 |
| `token_expires_on` | date | informational; consumed by a later expiry-alert follow-up |

## Assignments (static, from `pool.yaml`)

`agent_name -> [seat_id, ...]`. The list is ordered and acts as the tie-break preference. Every `seat_id` must exist in `seats`. The same seat may appear under several agents, which makes it shared. An agent with no entry has no seats, and `acquire` returns `None` for it.

Loading MUST fail fast, at worker boot, on an unknown seat ID in an assignment, a duplicate seat ID, or `max_concurrent < 1`. Loading does not require the `token_env` variables to be set. Only `token_for(seat_id)` does, so tests can load a pool without credentials.

## SeatState (runtime, owned by `CredentialPoolWorkflow`)

| Field | Type | Initial | Updated by |
|---|---|---|---|
| `leases` | dict[lease_key → acquired_at (ISO str)] | `{}` | `acquire` adds; `release`/`mark_*` remove; entries older than `LEASE_TTL` are ignored and pruned on `acquire` |
| `last_utilization` | float 0–1 | `0.0` | `release` (when non-null) |
| `last_rate_limit_type` | str \| None | `None` | `release` |
| `exhausted_until` | ISO str \| None | `None` | `mark_exhausted` (resets_at, or now + 1h when unknown) |
| `invalid` | bool | `False` | `mark_invalid` → `True`; cleared only by the `reset_seat` update (operator, after renewing) |

**Active leases** = the leases with `now - acquired_at < LEASE_TTL`.

### Seat state transitions

```
            acquire (lease added)            release (lease removed, utilization updated)
  free ─────────────────────────► leased ───────────────────────────────► free
                                    │
                                    ├─ mark_exhausted ─► exhausted (until T) ── now ≥ T ──► free (eligible)
                                    │
                                    └─ mark_invalid ───► invalid ── reset_seat (operator) ──► free
```

"Exhausted" and "invalid" are **eligibility filters**, not exclusive states. A seat can be exhausted and still hold other, concurrent leases from other runs. Those runs finish or fail by themselves.

## Selection rule (`select_seat`, pure)

```
eligible(s) = not s.invalid
              and (s.exhausted_until is None or s.exhausted_until <= now)
              and active_leases(s, now) < s.max_concurrent
pick = min(eligible seats in assignments[agent],
           key=(last_utilization, index in assignments[agent]))
       or None
```

## Lease key (built in the workflow, deterministic)

`f"{workflow_id}/{stage}/{invocation}/{handoff}"`

- **stage** is `build` or `architect`.
- **invocation** is the Build attempt number or plan attempt number.
- **handoff** counts from 0.

## SeatOutcome (agent → activity → workflow)

| kind | Carried as | Fields |
|---|---|---|
| ok | activity result dict | `seat_id`, `utilization`, `rate_limit_type` (+ stage payload such as `pr_url`) |
| exhausted | `ApplicationError(type="SeatExhausted", non_retryable=True)` | `details=[seat_id, resets_at_iso or None]` |
| invalid | `ApplicationError(type="SeatInvalid", non_retryable=True)` | `details=[seat_id]` |
| pool empty | `ApplicationError(type="CredentialPoolExhausted", non_retryable=True)` raised by the workflow | `details=[earliest_exhausted_until_iso or None]` |
| handoff budget spent | `ApplicationError(type="SeatHandoffsExhausted", non_retryable=True)` raised by the workflow | `details=[stage, MAX_SEAT_HANDOFFS]` |
| pool itself unreachable (seat activity failed after retries) | `ApplicationError(type="CredentialPoolUnavailable", non_retryable=True)` raised by the workflow | message carries the activity failure |

## UsageSnapshot (in-agent, from `RateLimitEvent`)

`{utilization: float|None, rate_limit_type: str|None, resets_at: int|None (epoch s)}`

- `utilization` and `rate_limit_type` come from the max over `raw.unifiedWindows`, falling back to the typed `utilization` (research R2).
- `resets_at` comes from the top-level `resetsAt`.

## Checkpoint

A commit on the feature branch whose `specs/*/tasks.md` marks completed tasks as `- [X]`. The resume boundary is the first remaining `- [ ]` line. The "all done" test is that no `- [ ]` remains in any `specs/*/tasks.md`.
