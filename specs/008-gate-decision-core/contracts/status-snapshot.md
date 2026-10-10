# Contract: Run status snapshot (v1)

**Producer**: `AgentPipelineWorkflow.status` (`@workflow.query`, name `"status"`)
**Consumers**:

- the core status operation (`webhook_bridge/core/status.py`, FR-016a);
- spec 005 (stage and budget values for its gates);
- spec 009 (Teams board and gate cards).

**Spec**: FR-001, FR-002, FR-003, SC-004

The snapshot is a JSON object, the default Temporal JSON payload converter's
encoding of a `dict`. Consumers address the query **by name string**
(`handle.query("status")`) and never import the workflow class.

## Shape

```json
{
  "schema_version": 1,
  "workflow_id": "pipeline/owner/repo/widget-export/v3",
  "stage": "awaiting_plan_decision",
  "open_window": { "gate": "plan", "attempt": 2, "opened_at": "2026-10-10T14:02:11Z" },
  "budgets": {
    "plan":  { "charged": 1, "max": 3 },
    "build": { "charged": 0, "max": 3 }
  },
  "pr_url": "https://github.com/owner/repo/pull/17",
  "last_applied_decision": {
    "gate": "plan",
    "attempt": 1,
    "decision": "rejected",
    "feedback": "use candidate B",
    "resolved_by": "unknown",
    "via": "unknown",
    "path": "signal",
    "decided_at": "2026-10-10T13:58:40Z"
  },
  "ignored_signals": [
    {
      "reason": "duplicate",
      "gate": "plan",
      "decision": "approved",
      "attempt": null,
      "resolved_by": "unknown",
      "via": "unknown",
      "window_attempt": 1,
      "received_at": "2026-10-10T13:58:40Z"
    }
  ]
}
```

## Fields

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | int | `1` for this contract (see Versioning) |
| `workflow_id` | string | `workflow.info().workflow_id` |
| `stage` | enum (below) | where the run is now |
| `open_window` | object \| null | the decision window currently open, or `null`. `gate` ∈ {`plan`} in 008; `attempt` is the plan loop iteration (FR-004) |
| `budgets` | object | charged vs. maximum attempts per budgeted stage. `plan.charged` follows CO-1..CO-4 exactly as `pipeline_workflow.py` charges today (FR-011); `build.charged` = failed Eval-Gate attempts so far |
| `pr_url` | string \| null | target PR URL once known (`ensure_target_pr_activity`, later `run_swe_agent_activity`) |
| `last_applied_decision` | object \| null | the most recent **applied** decision only. Duplicates and refusals never appear here |
| `last_applied_decision.path` | `"signal"` \| `"update"` | which decision path applied it |
| `last_applied_decision.resolved_by` / `.via` | string | as supplied, or the literal `"unknown"` when absent (FR-010, SC-006). `via` ∈ {`github`, `teams`, `unknown`} by convention; the workflow records whatever the caller sent and never guesses |
| `ignored_signals` | array, **oldest first, length ≤ 20** | the last 20 decision **signals** the run ignored, across windows. On the 21st, the oldest entry is dropped. Refused validated decisions never appear (FR-007) |
| `ignored_signals[].reason` | enum | `duplicate` (the open window already had a decision, or no window was open and the signal named an attempt this run already decided) · `stale_attempt` (a window was open and the signal named a different attempt) · `no_window_open` · `malformed` (empty/whitespace `plan_rejected` feedback, or an attribution that is not a `{resolved_by?, via?, attempt?}` object with str/str/int values) |
| `ignored_signals[].attempt` | int \| null | the attempt the signal named, if any |
| `ignored_signals[].window_attempt` | int \| null | the attempt of the window open when it arrived, or `null` |
| timestamps | ISO-8601 UTC string | from `workflow.now()` (deterministic) |

### `stage` values (fixed set)

| Value | Meaning | Terminal |
|---|---|---|
| `starting` | before the first activity | |
| `preparing_pr` | `ensure_target_pr_activity` running | |
| `planning` | `architect_stage_activity` running for `budgets.plan`'s current attempt | |
| `awaiting_plan_decision` | blocked at the plan gate; `open_window` is non-null | |
| `building` | `run_swe_agent_activity` running | |
| `evaluating` | `eval_gate_activity` running | |
| `registering` | `register_activity` running | |
| `completed` | `run()` returned | ✔ |
| `failed` | `run()` raised (budget exhausted, CO-3 malformed-retries, activity failure) | ✔ |

Invariants:

- `open_window != null` ⇔ `stage == "awaiting_plan_decision"`.
- `budgets.plan.charged ≤ budgets.plan.max`.
- The `ignored_signals` length is ≤ 20.

**Terminal stages and the core status operation**: the core resolves runs
with `ExecutionStatus = 'Running'` (FR-016a), so it returns
`no in-flight run` for a finished run and never shows `completed` or
`failed`. Those values exist for callers that query a run handle directly,
such as tests, the Temporal CLI, or spec 009's board addressing runs by id.
Querying a closed run needs a polling worker, because Temporal replays it to
answer.

**Legacy runs**: a run replaying under the unpatched path (research R6)
never opens a window. It reports `open_window: null` throughout, and every
decision signal shows up in `ignored_signals` as `no_window_open`. No such
runs are expected at rollout (spec Assumptions).

## Semantics

- **Read-only (FR-002)**: answering never mutates workflow state or adds
  history events. Verified in research R7, and asserted by test via
  `fetch_history()` length before and after.
- **Advisory (FR-003)**: the snapshot can be stale by the time a decision
  arrives. Nothing may use it alone to predict acceptance. The
  `decide_plan` validator stays authoritative.
- **Where callers get `attempt`**: callers take the attempt they put on a
  decision from `open_window.attempt` (or the stage's PR comment), and
  never compute it (FR-004).

## Versioning

- **Additive changes keep `schema_version: 1`**: a new optional field, or a
  new `stage` / `reason` / `via` value that spec 005 or 013 introduces. Consumers
  MUST ignore unknown fields and MUST treat an unknown `stage` / `reason`
  as opaque, rendering it as-is.
- **Breaking changes bump `schema_version`**: removing or renaming a field,
  changing a type, or changing an existing value's meaning.
