# Contract: `AgentPipelineWorkflow` plan-gate handlers

**Workflow type**: `"AgentPipelineWorkflow"` (unchanged), task queue
`agent-factory-pipeline` (unchanged).
**Spec**: FR-004 to FR-012, FR-021. Research: R1, R2, R5, R6.

The bridge addresses every handler **by name string**. Handler names are
part of the external contract.

## Decision window (shared by both paths)

- **Opening.** A window opens each time the plan loop reaches the gate,
  identified by `("plan", plan_attempt)`. `plan_attempt` is the loop
  iteration number: it only increases, may have gaps (a failed architect
  attempt uses up a number but opens no window), and is never reused in a
  run (FR-004).
- **Recording.** A window holds **at most one** decision. The first
  handler to run against it records the decision before returning, with no
  `await` (research R1).
- **Closing.** The plan loop wakes when the window holds a decision. It
  then closes the window (no window open), moves the decision into
  `last_applied_decision`, and acts on it with CO-1..CO-4 charging
  unchanged (FR-011).
- **Duplicates.** Every handler in the same activation runs before the loop
  wakes. Any of them that finds the window already decided is a duplicate:
  an ignored signal, or a refused update. Each decided window is also
  remembered by attempt after it closes, so a later decision that names it
  is still recognized as a duplicate (see the validator table).
- **No window, no effect.** A decision handled while no window is open
  never affects a later window (FR-009). Nothing is buffered for later.

## Signals (legacy path; GitHub today)

```python
@workflow.signal
def plan_approved(self, attribution: dict | None = None) -> None: ...

@workflow.signal
def plan_rejected(self, feedback: str, attribution: dict | None = None) -> None: ...
```

- **Today's calls keep working (FR-008).**
  - `handle.signal("plan_approved")` → `attribution=None`.
  - `handle.signal("plan_rejected", feedback)` → `attribution=None`.
- **Optional attribution.** The payload is
  `{"resolved_by": str?, "via": str?, "attempt": int?}`, sent as
  `handle.signal("plan_approved", attribution)` or
  `handle.signal("plan_rejected", args=[feedback, attribution])`.
- **Outcome.** Each signal is either **applied** to the open window, or
  **ignored** and appended to the ignored-signals list (max 20, oldest
  dropped). Ignore reasons are checked in this order:
  1. `malformed`: `plan_rejected` feedback is empty or whitespace-only, or
     `attribution` is present but not a dict of
     `resolved_by: str`, `via: str`, `attempt: int`, each optional.
  2. `stale_attempt`: a window is open, and `attribution.attempt` is
     present and ≠ its attempt.
  3. `duplicate`: either the open window already holds a decision, or no
     window is open and `attribution.attempt` names a window this run
     already decided. This mirrors the validator's `already_resolved`.
  4. `no_window_open`: any other signal arriving with no window open,
     including every legacy signal that names no attempt.
- **Missing attribution.** Absent `resolved_by` / `via` are recorded as
  `"unknown"` (FR-010).
- **Legacy fields.** Both handlers also keep writing the legacy
  `_plan_decision` / `_plan_feedback` fields exactly as today, so a replay
  of a run started before this change behaves as before (research R6).

## Update (validated path; no production caller until 009)

```python
@workflow.update
def decide_plan(self, request: dict) -> dict: ...

@decide_plan.validator
def _validate_decide_plan(self, request: dict) -> None: ...
```

### Request (`request: dict`)

| Key | Type | Required | Notes |
|---|---|---|---|
| `decision` | `"approved"` \| `"rejected"` | yes | |
| `feedback` | string | when `rejected` | non-empty after strip |
| `attempt` | int | **yes** | must equal the open window's attempt. A validated decision may never omit it (spec edge case) |
| `resolved_by` | string | yes | trusted as passed; the adapter authorizes (FR-019a) |
| `via` | string | yes | e.g. `"teams"`, `"github"` |

### Validator: refusal reasons

The validator is read-only: it must never mutate state, or the workflow
task fails with `ReadOnlyContextError`. It refuses by raising
`ApplicationError(message, *details, type=<reason>)`. Checks run in this
order, and the first match wins:

| Order | `type` (reason) | When | `details[0]` |
|---|---|---|---|
| 1 | `malformed` | a required key is missing, a type is wrong, or `decision` is not one of the two values | — |
| 2 | `empty_feedback` | `decision == "rejected"` and the feedback strips to `""` | — |
| 3 | `stale_attempt` | a window **is open**, and `attempt` ≠ its attempt | `{"open_attempt": int}` |
| 4 | `already_resolved` | a window is open for `attempt` and already holds a decision (a same-task race), **or** no window is open and `attempt` names a window this run already decided | `{"resolved_by": str, "via": str, "decision": str}` from that window's decision |
| 5 | `no_window_open` | no window is open, and `attempt` names no decided window | — |
| — | *(accept)* | a window is open for `attempt` and holds no decision | — |

A refusal leaves **no history events** (FR-007, verified in research R2).
The submitter receives it synchronously through `update_handle.result()`.
`start_update` alone does **not** raise on refusal; see
`core-operations.md`.

Two cases need explaining:

- **`already_resolved` after the window has closed.** Example: a Teams
  click arrives two seconds after someone approved on GitHub. It still gets
  `already_resolved` with the winner's attribution, because `PlanGate`
  remembers each decided window by attempt. That drives docs/80 §14.8's
  "already resolved by X via Y" card, and it is what User Story 3
  scenario 3 and FR-021's standalone "already-resolved refusal with
  attribution" test exercise, without needing a race.
- **Stale is checked first.** A decision for attempt N while attempt N+1
  is open is always `stale_attempt`, even though window N was decided
  (User Story 1, scenario 3). A decision for an attempt that never opened
  a window, made while the run is not at the gate, is `no_window_open`
  (User Story 1, scenario 4).

### Handler

The handler is synchronous. It records the decision into the open window
with `path: "update"` and returns:

```json
{ "outcome": "accepted", "gate": "plan", "attempt": 2 }
```

An accepted update is written to history (accepted and completed events)
like any accepted Update.

### Idempotency

The update id is set by the core (`core-operations.md`, request id).
Resubmitting with the same id returns the first result and never applies a
second decision (research R4).

## Query

```python
@workflow.query
def status(self) -> dict: ...
```

This returns the snapshot defined in `status-snapshot.md`.

## Determinism

One new marker, `workflow.patched("plan-decision-window-v1")`, is evaluated
inside the existing `architect-stage-v1` block at the gate:

- **Patched (all new runs):** use the window logic above.
- **Unpatched (replay):** reset the legacy fields, wait, and act, exactly as
  `pipeline_workflow.py:133-149` does today. 008 removes today's
  reset-before-wait only in the patched branch.

No other marker is added (research R6).
