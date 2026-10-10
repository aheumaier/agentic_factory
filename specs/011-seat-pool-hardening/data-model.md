# Data Model: Seat Pool Hardening (011)

Deltas to `specs/009-credential-pool-handoff/data-model.md`. Everything not listed here is unchanged. Usage Constraint (internal, single-operator use only) as in 009.

## UsageSnapshot (in-agent, from `RateLimitEvent`)

| Field | Type | Source |
|---|---|---|
| `utilization` | float \| None | max over `raw.unifiedWindows` (009) |
| `rate_limit_type` | str \| None | name of that window (009) |
| `resets_at` | int \| None (epoch s) | top-level `resetsAt`, the exhaustion reset (009) |
| **`utilization_resets_at`** | int \| None (epoch s) | **new:** `resetsAt` of the max window; fallback `resets_at` |

## SeatState (runtime, owned by `CredentialPoolWorkflow`)

| Field | Type | Initial | Updated by |
|---|---|---|---|
| **`utilization_resets_at`** | ISO str \| None | `None` | `release` (set, or cleared to `None`, whenever `utilization` is non-null); `mark_exhausted` (= `exhausted_until`) |

State carried from 009 lacks the key and is upgraded on load (`{**new_seat_state(), **old}`).

### Effective utilization (selection input)

```
effective_utilization(s, now) = 0.0                  if s.utilization_resets_at and parse(s.utilization_resets_at) <= now
                                s.last_utilization   otherwise
pick = min(eligible seats in assignments[agent], key=(effective_utilization, index))
```

Eligibility is unchanged from 009.

## Seat table row (`seats()` query)

New key: **`expires_in_days`**: int \| None, `(token_expires_on - workflow.now().date()).days`. It is negative once expired, and `None` without a configured date. `last_utilization` stays the raw stored value; the query also shows `utilization_resets_at`.

## Pool wait (workflow-local, F3)

| Name | Value |
|---|---|
| `POOL_WAIT_HORIZON` | 6 h: wait only if the earliest reset is at most this far away |
| `MAX_POOL_WAITS` | 2 per stage invocation (`_with_seat` call) |
| margin | +1 s after the reset |

A wait never advances the handoff index and never charges `MAX_BUILD_ATTEMPTS`/`MAX_PLAN_ATTEMPTS`/`MAX_SEAT_HANDOFFS`.

## Handoff index

`handoff` ∈ [0, `MAX_SEAT_HANDOFFS`]: the last segment of the lease key `{workflow_id}/{stage}/{invocation}/{handoff}`. It is passed to the Build activity as a trailing argument and into the sandbox as `SEAT_HANDOFF_INDEX`.

## Checkpoint (F1)

A commit whose message is `checkpoint: <IDs>`. `<IDs>` are the task IDs (`T\d+`) newly marked `[X]` in the feature's `tasks.md`, in file order, space-separated. Without IDs the message is `checkpoint: tasks`. The end-of-run commit of leftover edits is `checkpoint: end of run`. Commits the model makes itself still count as checkpoints, as in 009.
