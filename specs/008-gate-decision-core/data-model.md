# Data Model: Gate Decision Core

**Feature**: `specs/008-gate-decision-core` | **Date**: 2026-10-10

There is no persistent storage. Workflow-side entities are
`AgentPipelineWorkflow` instance state, durable through Temporal's event
history. Bridge-side entities are in-memory values passed between the
adapter and the core.

## Workflow side (`orchestration/workflows/`)

The pure state lives in a new module, `orchestration/workflows/plan_gate.py`.
It holds no Temporal imports and no I/O, so the same code runs inside the
workflow sandbox and in plain unit tests. `AgentPipelineWorkflow` owns one
`PlanGate` instance, and its handlers delegate to it.

### DecisionWindow

| Field | Type | Rule |
|---|---|---|
| `gate` | `"plan"` | only gate in 008; 005 adds `pm`, `security`, `escalation` with the same model |
| `attempt` | int ≥ 1 | the plan loop iteration (`plan_attempt`). Strictly increasing per run, gaps allowed, never reused (FR-004) |
| `opened_at` | datetime | `workflow.now()` |
| `decision` | `AppliedDecision` \| None | at most one. Set by the first handler that runs against the window, never overwritten (FR-005) |

Lifecycle:

```
(no window) ──open(attempt)──▶ OPEN, undecided
OPEN, undecided ──first valid signal/update──▶ OPEN, decided
OPEN, decided ──plan loop wakes: close()──▶ (no window)
```

An "open, decided" window only exists inside the workflow task in which
the decision was recorded. The loop wakes and closes it before that task
completes (research R1). Any later decision in that same task is a
duplicate: an ignored signal or a refused update.

When the window closes, its decision is kept in `PlanGate.decided`, keyed by
attempt. Later decisions that name that attempt with no window open are
still recognized as duplicates: they get `already_resolved` with the
winner's attribution, or are ignored as `duplicate`
(`contracts/workflow-handlers.md`).

### AppliedDecision

| Field | Type | Rule |
|---|---|---|
| `gate`, `attempt` | as window | |
| `decision` | `"approved"` \| `"rejected"` | |
| `feedback` | str \| None | non-blank when `rejected` |
| `resolved_by` | str | caller-supplied, else `"unknown"` (FR-010) |
| `via` | str | caller-supplied, else `"unknown"` (FR-010) |
| `path` | `"signal"` \| `"update"` | |
| `decided_at` | datetime | `workflow.now()` |

### IgnoredSignal

| Field | Type | Rule |
|---|---|---|
| `reason` | `duplicate` \| `stale_attempt` \| `no_window_open` \| `malformed` | precedence: malformed → stale_attempt (window open, other attempt) → duplicate (open window decided, or no window and the named attempt was decided) → no_window_open |
| `gate` | `"plan"` | |
| `decision` | `"approved"` \| `"rejected"` | |
| `attempt` | int \| None | the attempt the signal named, if any |
| `resolved_by`, `via` | str | `"unknown"` when absent |
| `window_attempt` | int \| None | the attempt of the window open on arrival |
| `received_at` | datetime | `workflow.now()` |

Kept in a rolling list capped at **20** entries, across windows, oldest
first. Appending the 21st drops the oldest. Refused updates are never
stored (FR-007).

### PlanGate (state holder)

| Field | Type |
|---|---|
| `window` | `DecisionWindow` \| None |
| `last_applied` | `AppliedDecision` \| None |
| `decided` | dict[int, `AppliedDecision`]: every closed window's decision, by attempt. Bounded: one entry per window, and windows are capped by `MAX_PLAN_ATTEMPTS` |
| `ignored` | list[`IgnoredSignal`] (≤ 20) |

| Method | Called from | Effect |
|---|---|---|
| `open(attempt, now)` | plan loop (patched branch) | creates the window; asserts that no window is open and that `attempt` is greater than any earlier one |
| `on_signal(decision, feedback, attribution, now)` | `plan_approved` / `plan_rejected` | either records the decision into the open window or appends an `IgnoredSignal` |
| `check_update(request) -> Refusal \| None` | `decide_plan` validator | returns the first refusal (`reason`, `details`) per `contracts/workflow-handlers.md`. **Read-only**. The workflow's validator turns a refusal into `ApplicationError(type=reason)`, so `plan_gate.py` stays free of Temporal imports |
| `apply_update(request, now)` | `decide_plan` handler | records into the open window (validator already passed) |
| `close() -> AppliedDecision` | plan loop after wake | clears the window, sets `last_applied`, stores the decision in `decided[attempt]` |

### AgentPipelineWorkflow: new instance state

Today these are locals in `run()` (or don't exist). They become instance
attributes so `status()` can read them. They emit no commands, so they need
no patch marker (research R6).

| Attribute | Today | Source of truth for |
|---|---|---|
| `_stage` | — | `status.stage` (enum in `contracts/status-snapshot.md`) |
| `_pr_url` | local `pr_url` | `status.pr_url` |
| `_plan_charged` | local `charged` | `status.budgets.plan.charged`. Charged at exactly today's CO-1/CO-2/human-rejection points (FR-011) |
| `_build_charged` | derived from local `attempt` | `status.budgets.build.charged` (failed Eval-Gate attempts) |
| `_plan_gate` | — | `PlanGate` above |
| `_plan_decision`, `_plan_feedback` | existing | **kept**, written by signal handlers as today. Read only by the unpatched (legacy replay) branch |

`plan_attempt` stays a loop local. Its value reaches status through
`_plan_gate.window.attempt`.

## Bridge side (`orchestration/webhook_bridge/core/`)

Full signatures are in `contracts/core-operations.md`.

| Entity | Fields | Notes |
|---|---|---|
| `Origin` | `surface`, `delivery_id` | `dedup_key = f"{surface}:{delivery_id}"` (FR-018). `request_id = "decide_plan-" + sha256(dedup_key)[:32]` (FR-016) |
| `PlanDecisionRequest` | `decision`, `feedback`, `attempt`, `resolved_by`, `via` | sent as the `decide_plan` update argument (`asdict`) |
| `RunCommand`, `GateCommand` | unchanged | moved from `grammar.py` into `core/commands.py`; `grammar` re-imports them |
| `GateSignalOutcome` | `outcome`, `reason` | `outcome` ∈ `signal_issued`, `signal_issued_no_handler`, `signal_failed`, `repo_not_allowed` |
| `DecisionOutcome` | `status`, `reason`, `resolved_by`, `via`, `request_id` | `status` ∈ `accepted`, `refused`, `worker_unavailable`, `target_not_found`, `repo_not_allowed` |
| `StatusOutcome` | `status`, `snapshot`, `reason` | `status` ∈ `ok`, `target_not_found`, `worker_unavailable`, `repo_not_allowed` |
| `audit.Outcome` | literal set | gains `signal_issued`, `worker_unavailable` (FR-017) |

## Relationships

```
GitHub comment ──(adapter: verify, authorize, parse)──▶ GateCommand ──▶ core.gate.signal_gate ──signal──▶ PlanGate.on_signal
spec 009 card  ──(adapter: authorize)──▶ PlanDecisionRequest + Origin ──▶ core.decisions.submit_plan_decision ──update──▶ PlanGate.check_update / apply_update
any surface    ──(adapter: authorize)──▶ core.status.get_status ──query──▶ AgentPipelineWorkflow.status ─▶ snapshot
```
