# Research: Gate Decision Core

**Feature**: `specs/008-gate-decision-core` | **Date**: 2026-10-10

Every decision below that depends on Temporal runtime behaviour was checked
empirically on 2026-10-10, not taken from docs alone. The spike used the
repo's own pinned SDK (`temporalio` 1.32.0, `orchestration/uv.lock`) against
`WorkflowEnvironment.start_local()` (Temporal CLI 1.8.2, dev server 1.31.2),
with throwaway workflows that mirror the planned handler shapes. The spike
code is not part of the repo; the results it produced are quoted below.

---

## R1. How first-valid-wins is enforced inside the workflow

**Decision**: Enforce it in `AgentPipelineWorkflow` itself, with:

- **set-if-unset signal handlers** for `plan_approved` / `plan_rejected`;
- a **synchronous `@workflow.update decide_plan`** with a
  `@decide_plan.validator`;
- one shared per-window state object both paths check and write.

Both handlers are plain `def` (never `async def`, never `await`), so the
decision is recorded in the handler's first and only step.

**Rationale (SDK mechanics, read from `temporalio/worker/_workflow_instance.py`
in the pinned 1.32.0)**:

- An activation's jobs are split into job sets: patches, then
  **signals + updates together, in activation order**, then everything else
  (`activate()`, lines 472-488). Each signal job and each update job becomes
  one asyncio task (`_process_signal_job` line 2618, `_apply_do_update`
  line 795), and tasks run FIFO.
- The update validator runs at the start of the update's task
  (`run_update`, line 702), not at job-apply time. So it sees every state
  change made by tasks that ran before it in the same activation.
- `wait_condition` predicates are checked only after the ready queue drains
  (`_run_once(check_conditions=True)`). So every handler in an activation
  runs before the plan loop wakes. That is exactly why today's last-writer
  overwrite happens (`pipeline_workflow.py:66-73`). It is also why
  set-if-unset alone is enough to make the first handler win.

**Rule this creates (not a style preference)**: a decision handler MUST
record the decision before any `await`. With a synchronous handler that
holds by construction. Making either handler `async def` with an `await`
before the write would reopen the race.

**Evidence: two decisions in one workflow task, all four pairings.** Method:
run the worker until the workflow blocks at an open window, stop the worker,
deliver decision A then decision B one second apart, restart the worker.
Signals were recorded with `workflow.info().get_current_history_length()`;
equal values mean the same activation.

| Pairing (submission order) | Applied | Second decision's fate |
|---|---|---|
| signal A → signal B | A | B ignored, same history length (same activation) |
| update A → update B | A | B refused by validator: `ApplicationError(type="already_resolved")` |
| signal A → update B | A | B refused: `already_resolved` |
| **update A → signal B** | **B** | **A refused: `already_resolved`** |

The last row matters. The Update was *submitted* a second earlier and still
lost to the later signal. That is because the server delivers signals as
history events and admitted Updates as protocol messages attached to the
workflow task, and SDK core places the signal job ahead of the update job in
that activation. This is the spec's "first in the run's recorded order, not
first in the PR thread" caveat (User Story 1) made concrete. It is the
expected, deterministic outcome, not a defect. FR-021's "signal + validated
in both orders" tests therefore assert this: whichever order they are
*submitted* in within one processing step, the signal is first in the run's
recorded order and wins.

**Alternatives considered**:

- *Serialize in the bridge (a lock per run).* Rejected. Two bridge
  processes, or a Teams adapter in another process (spec 009), would bypass
  it. docs/80 §12.1 says this must be enforced in the workflow.
- *Signals only, with an attempt check.* Rejected. A signal gives the
  sender no synchronous result, so a Teams card could never show "already
  resolved by X" (FR-016, docs/80 §14.8).
- *Async update handler using `workflow.Lock`.* Rejected as unnecessary.
  Nothing in the handler needs to await.

---

## R2. Validated-decision call shape and how refusal surfaces

**Decision**: The core calls

```
handle.start_update("decide_plan", request, id=<request id>,
                    wait_for_stage=WorkflowUpdateStage.ACCEPTED,
                    rpc_timeout=<remaining budget>)
```

then `await update_handle.result(rpc_timeout=<remaining budget>)`. Mapping:

- `result()` returns → **accepted**.
- `result()` raises `WorkflowUpdateFailedError` whose `.cause` is an
  `ApplicationError` → **refused**. The reason is `cause.type`; for
  `already_resolved`, `cause.details[0]` holds `{resolved_by, via}`.
- `start_update` or `result()` raises
  `WorkflowUpdateRPCTimeoutOrCancelledError` → **worker_unavailable**
  (indeterminate).

**Evidence**:

- `start_update` **does not raise when the validator refuses**, with either
  `wait_for_stage=ACCEPTED` or `COMPLETED`. It returns a handle whose known
  outcome is the failure (`client/_impl.py:780`, `handle._known_outcome`).
  The refusal surfaces only from `handle.result()`, which raises
  immediately from the known outcome without another RPC. Spike output:
  `ACCEPTED returned handle on rejection; result() -> already_resolved
  ({'resolved_by': 'x', 'via': 'github'},)`. A core that called only
  `start_update` would report every refusal as accepted. This is the
  single easiest bug to write here, and the contract pins it
  (`contracts/core-operations.md`).
- Because the handler is synchronous, acceptance and completion are
  written in the same workflow-task completion. So `result()` after an
  acceptance returns at once. "Wait only until accepted or refused"
  (FR-016) costs one extra short poll.
- A refused Update writes **no history events**. Spike: only the accepted
  update's `workflow_execution_update_accepted` / `_completed` events
  appeared. This satisfies FR-007.

**Alternatives considered**: `execute_update` (= `start_update(COMPLETED)`
+ `result()`) behaves the same here, since the handler is synchronous. The
two-step form was chosen because it states FR-016's "until accepted or
refused" intent and follows docs/80 §7.2.

---

## R3. `worker_unavailable` detection and the timeout value

**Decision**: There are two catch sites, because the SDK raises two
different types:

| Operation | No worker polling → raises | Core outcome |
|---|---|---|
| Update (`start_update` / `result`) | `WorkflowUpdateRPCTimeoutOrCancelledError` | `worker_unavailable` (outcome **unknown**) |
| Query (`handle.query("status", rpc_timeout=…)`) | `temporalio.service.RPCError`, status `CANCELLED` or `DEADLINE_EXCEEDED` ("Timeout expired") | `worker_unavailable` (plain "try later") |

Timeout: `DECISION_RPC_TIMEOUT = STATUS_RPC_TIMEOUT = 5 s`. Each core
operation also wraps its whole body in `asyncio.timeout(8 s)`, mapping
expiry to `worker_unavailable`, so the 10 s SC-005 bound holds even if the
run-resolution visibility call is slow. Tests inject a 1 s timeout.

**Evidence**: with no worker running, both calls returned at
**2.0 s for a 2 s rpc_timeout**, with exactly the types above.

**Rationale for 5 s**: it fits inside SC-005's 10 s. It also leaves room
under the 10-15 s Teams invoke budget that spec 009 inherits (research J.3,
cited in docs/80 §14.3). `resolve_gate_target`'s `list_workflows` call is
left exactly as it is, with no `rpc_timeout` kwarg, because
`test_temporal_client.py:85` pins its exact call. That is why the outer
`asyncio.timeout` exists.

---

## R4. Idempotent resubmission after `worker_unavailable`

**Decision**: The request id (the Temporal update id) is
`"decide_plan-" + sha256(origin.dedup_key).hexdigest()[:32]`, where
`origin.dedup_key = f"{surface}:{delivery_id}"` (FR-018). It is hashed so
its length stays bounded, whatever a surface's delivery ids look like.

**Evidence**:

- An Update sent with no worker timed out as
  `WorkflowUpdateRPCTimeoutOrCancelledError`. When a worker started two
  seconds later, the run **applied it anyway**. This confirms the spec's
  "indeterminate, not a refusal" reading (Clarification 2026-10-10).
- Resubmitting with the **same update id** returned the original result,
  with no second application (`final: {'decided': 'Z', 'log':
  [['upd-applied', 'Z', 10]]}`).

**Consequence for the core's dedup cache**: validated decisions do **not**
go through `DeliveryCache.reserve()`. If they did, a resubmission after
`worker_unavailable` would be short-circuited as `duplicate_ignored`, and
the submitter would never learn the real outcome. Server-side update-id
dedup is strictly stronger anyway: it survives a bridge restart. The
in-memory cache keeps guarding signals and run starts, which have no such
server-side backstop (`dedup.py` docstring).

---

## R5. Legacy zero-argument signals with an optional attribution parameter

**Decision**: the new signal signatures are

- `plan_approved(self, attribution: dict | None = None)`;
- `plan_rejected(self, feedback: str, attribution: dict | None = None)`.

`attribution` is a plain `dict`, validated in the handler, not a dataclass.

**Evidence**: all four call shapes were delivered and decoded correctly:

- `signal("plan_approved")` → `attribution=None`;
- `signal("plan_rejected", "fb")`;
- `signal("plan_approved", {...})`;
- `signal("plan_rejected", args=["fb2", {...}])`.

The bridge tests pin the first two shapes
(`test_temporal_client.py:117-120`).

**Why `dict`, not a dataclass**: if a dataclass-typed argument fails to
decode, the SDK logs "dropping the signal" (`_process_signal_job`) and the
handler never runs, so the bad input would leave no trace in status. A
`dict` always decodes, and the handler can record a bad payload as an
ignored `malformed` entry (FR-001).

---

## R6. Determinism-preserving migration (FR-012)

**Decision**: one new patch marker, `workflow.patched("plan-decision-window-v1")`,
evaluated inside the existing `architect-stage-v1` block, at the point
where today's code resets `_plan_decision` and waits
(`pipeline_workflow.py:133-140`):

- **Patched** (all new runs): open a `DecisionWindow` for `plan_attempt`,
  wait until that window holds a decision, close it, act on it.
- **Not patched** (replay of a run started before this change): run
  today's code unchanged: reset `_plan_decision`/`_plan_feedback`, wait,
  act on whatever is there.

The signal handlers keep writing the legacy `_plan_decision` /
`_plan_feedback` fields exactly as today (last-writer-wins), *in addition
to* the new window bookkeeping. Signal handlers cannot call
`workflow.patched()` meaningfully themselves. Instead, the window only ever
opens in the patched branch, so in an unpatched run the new bookkeeping only
ever records "no window open" entries. Those are workflow state only and
emit no commands, so replay stays deterministic.

**Edges checked**:

- *A signal in the same activation as `initialize_workflow`.* Signal jobs
  run before the run task's first step, so no window can be open yet. In
  the patched path the signal is ignored as `no_window_open`. That matches
  today's net behaviour: today's reset-before-wait would discard it too.
- *The new query and update handlers.* Registering handlers emits no
  commands, so neither needs a marker.
- *Stage and budget fields becoming instance state* (the query needs them;
  they are locals today). This is state only, with no commands, so no
  marker is needed.
- *Landing order with 005.* Per the spec's Assumptions, whichever lands
  second rebases onto the other's marker rather than adding a parallel one.
  This plan names exactly one new marker, so the rebase target is
  unambiguous.

**Alternative considered**: a new workflow type name or task queue
(005 FR-015's other option). Rejected. The bridge references the type by
name string (`temporal_client.py:21`), so a rename would ripple into the
pinned bridge tests (`test_temporal_client.py:27`), and the patch idiom
is already the repo's convention (`architect-stage-v1`).

---

## R7. Status: Query, snapshot shape, and terminal stages

**Decision**:

- `@workflow.query def status(self) -> dict` returns the versioned
  snapshot in `contracts/status-snapshot.md`.
- The core's status operation calls it **by name string**
  (`handle.query("status", rpc_timeout=…)`), for the same reason
  `temporal_client.py` never imports the workflow class: importing it
  pulls in `activities.py`'s side effects.
- `run()`'s body is wrapped in `try/except BaseException`, which sets
  `self._stage = "failed"` and re-raises, so a failed run reports a
  terminal stage rather than the stage it raised from. `completed` is set
  just before the final `return`.

**Evidence**: the query left the history length unchanged (spike:
`history len before/after query: 16 16`, measured with `fetch_history()`,
not self-reported), as required by FR-002 and SC-004. A Query on a run with
no polling worker fails as described in R3.

**Rationale (Query, not Update)**: an Update writes history and counts
toward Temporal's in-flight and total Update limits (research L.2, docs/80
§12.5). A Query does neither.

**Note**: the core's status operation resolves runs by
`ExecutionStatus = 'Running'` (the same resolution gate signalling uses,
FR-016a). So it reports `no in-flight run` for a finished run. The
terminal stage values exist for direct `handle.query("status")` callers
(tests, the Temporal CLI, and spec 009's board, which addresses runs by id).
This is consistent with the spec, and the contract states it.

---

## R8. Where the core lives, and what stays put (FR-013/FR-014/FR-015)

**Decision**: a new package `orchestration/webhook_bridge/core/` holds the
new surface-neutral code. The existing modules keep their paths and public
names, so the unchanged bridge tests keep importing them:

| Concern | Lives in | Why there |
|---|---|---|
| Command shapes (`RunCommand`, `GateCommand`) + new `Origin`, `PlanDecisionRequest` | `core/commands.py` | `grammar.py` re-imports the two existing dataclasses, so `grammar.RunCommand` and `grammar.GateCommand` stay identical objects for `test_grammar.py` |
| Run identity + resolution (`workflow_id`, `start_run`, `resolve_gate_target`, `connect`, `TASK_QUEUE`, `WORKFLOW_TYPE`) | `core/runs.py` | `temporal_client.py` re-exports every name; `test_temporal_client.py` calls them as `temporal_client.X` |
| Gate signalling | `core/gate.py` → returns `GateSignalOutcome` | FR-014: no reactions in core |
| Validated decision | `core/decisions.py` → returns `DecisionOutcome` | new, no pinned signature |
| Status | `core/status.py` → returns `StatusOutcome` | new, no pinned signature |
| Allow-list check | `core/policy.py` (`repo_allowed`) | `server.py`'s inline check (`:102`) is moved here verbatim and called from it, and from every core op |
| Delivery dedup | `dedup.py` (unchanged, already surface-neutral) + `Origin.dedup_key` | `test_dedup.py` pins `DeliveryCache.reserve(id)` |
| Audit outcome set + JSON log | `audit.py` (unchanged path; `Outcome` gains `signal_issued`, `worker_unavailable`) | `test_audit.py` pins `audit.log_entry` / `audit.reaction_for_outcome` |
| GitHub reaction map | stays in `audit.py` (`_REACTION_BY_OUTCOME` gains `signal_issued → eyes`, keeps `signal_issued_no_handler → eyes`) | pinned by `test_audit.py:24-25`; the "slightly awkward layout" the spec's Assumptions accept |
| GitHub adapter | `server.py`, `auth.py`, `github_app.py`, `grammar.py` (parsing), `temporal_client.py` (thin shim) | unchanged paths |

`temporal_client.signal_gate(client, repo, pr_number, gate, decision,
feedback, comment_id, author, comment_body, github_client)` keeps its exact
positional signature. It:

1. calls `core.gate.signal_gate(...)`;
2. gets back a `GateSignalOutcome`;
3. renders the reaction via `audit.reaction_for_outcome(outcome.outcome)`.

The core emits the audit line, so the shim only reacts. The reactions are
the same as today:

- `signal_issued` / `signal_issued_no_handler` → 👀;
- `signal_failed` → 😕.

**The allow-list reaching the core (FR-019)**: every new core operation
(`submit_plan_decision`, `get_status`, and the core `signal_gate` /
`start_run`) takes `allowed_repos` as a **required keyword argument** and
refuses with `repo_not_allowed` before any Temporal call. The two pinned
shims (`temporal_client.signal_gate` / `start_run`) gain a keyword-only
`allowed_repos: Collection[str] | None = None`:

- `server.py` (the only production caller) always passes
  `self.allowed_repos`;
- the legacy unit tests omit it, and `None` then means "the adapter
  already enforced it". This is the one deliberate seam the pinned
  signatures force.

A new bridge test asserts that `BridgeApp` passes `allowed_repos` on every
dispatch, so the seam cannot silently become a production bypass.

**Alternatives considered**:

- *A `BridgeCore` class owning `client` + `allowed_repos`.* Rejected. The
  existing module-function style (`temporal_client.start_run(client, …)`)
  is pinned by tests, and a class next to free functions would give two
  ways to call the same thing.
- *Moving `audit.py` / `dedup.py` under `core/` with re-export stubs.*
  Rejected as churn with no behaviour gain. They are already
  surface-neutral.

---

## R9. In-process test environment (FR-021)

**Decision**: the new workflow-level and core-level tests use
`temporalio.testing.WorkflowEnvironment.start_local(...)`, with:

- `search_attributes=[SearchAttributeKey.for_keyword("TargetRepo"),
  SearchAttributeKey.for_int("PRNumber")]`, so `resolve_gate_target`'s
  visibility query works;
- `dev_server_existing_path=shutil.which("temporal")` when a `temporal`
  CLI is on `PATH`. Otherwise the SDK downloads the CLI once into its
  temp cache.

This is the **first `WorkflowEnvironment` use in the repo**. The
`tests/test_pipeline_workflow.py` docstring says no such usage exists, so
it is updated. The existing real-server tests are left as they are.

**Why `start_local`, not `start_time_skipping`**: the time-skipping test
server does not implement visibility `ListWorkflowExecutions` queries,
which `resolve_gate_target` depends on. Nothing in these tests needs time
skipping either.

**"No external services"**: the dev server is a subprocess the fixture
owns, with in-memory persistence. It needs neither `make up` nor Docker.
The only network touch is the one-time CLI download, when no binary is
found. CI can pre-install the CLI, or set
`TEMPORAL_CLI_PATH` → `dev_server_existing_path`.

**Producing "two decisions in one processing step" deterministically**
(the spike's method, reused):

1. Run the worker until `status()` reports `awaiting_plan_decision`.
2. Exit the `Worker` context.
3. Send the decisions: signals directly, Updates as background tasks
   (they block until a worker accepts them).
4. Restart a worker.

For signal + signal pairs, the test also asserts from `fetch_history()`
that both `WorkflowExecutionSignaled` events precede a single
`WorkflowTaskStarted`. Restarting on a fresh `Worker` also forces a full
replay of the run's history, so these tests double as replay-determinism
checks for the new code. Activities are stubbed by name, reusing
`tests/test_pipeline_workflow.py::_stub_activities` / `_plan_result`
(moved into a shared `tests/_stubs.py`).

---

## R10. Pinned Temporal server image (FR-020, User Story 4)

**Decision**:

- `temporalio/server:1.29.7`;
- `temporalio/admin-tools:1.29.7-tctl-1.18.4-cli-1.7.2`.

They replace `temporalio/auto-setup:latest` and are split into three
services:

1. **`temporal-schema-setup`** (one-shot, admin-tools). It repeats
   `auto-setup.sh`'s `setup_postgres_schema` exactly:
   - on DB `temporal`: `temporal-sql-tool --plugin postgres12 … setup-schema -v 0.0`,
     then `update-schema -d /etc/temporal/schema/postgresql/v12/temporal/versioned`;
   - for `temporal_visibility`: `create` first, then the same pair against
     `…/v12/visibility/versioned`.
2. **`temporal`** (server, same `DB`/`POSTGRES_*` env as today). It starts
   once (1) has completed successfully.
3. **`temporal-namespace-setup`** (one-shot, admin-tools, with
   `TEMPORAL_ADDRESS=temporal:7233` so its CLI reaches the server
   container). It waits for `temporal operator cluster health` to report
   `SERVING`, then:
   - runs `namespace describe default || namespace create --retention 24h default`
     (auto-setup's `register_default_namespace`);
   - creates the bridge's `TargetRepo` (Keyword) and `PRNumber` (Int)
     search attributes, tolerating "already exists". Today
     `specs/002-webhook-trigger-bridge/quickstart.md:6-9` has this as a
     manual step.

**Evidence**:

- *Tags* (Docker Hub API, 2026-10-10): `auto-setup:latest` was pushed on
  2026-02-05 along with `auto-setup:1.29.3`, confirming the spec's floor.
  `server:1.29.7` exists (2026-06-12). Plain `admin-tools:1.29.7` does
  **not** (HTTP 404); the exact compound tag above does.
- *Image layout*: the admin-tools image was pulled and inspected.
  `/usr/local/bin/temporal-sql-tool`, `/usr/local/bin/temporal`, and
  `/etc/temporal/schema/postgresql/v12/{temporal,visibility}/versioned/`
  are all present.
- *Existing-volume safety (SC-007)*: `auto-setup.sh` (temporalio/docker-builds
  `main`) runs `setup-schema -v 0.0` then `update-schema` on **every**
  container start, unconditionally. So today's stack already re-runs
  exactly these commands against the existing `temporal-pg-data` volume on
  every `make up`. Repeating them is tolerated by construction.

**Why 1.29.7 and not the newest (1.32.1)**: Temporal supports upgrading the
server one minor version at a time. Existing volumes carry 1.29.3 data, so
a jump to 1.32 would skip two minors on first start. 1.29.7 is the newest
patch on the volume's own minor:

- it meets the ≥1.29.3 floor, so there is no schema downgrade;
- it is above the ≥1.28 Update / update-with-start floor (docs/80 §15);
- it changes nothing about upgrade risk.

Moving to 1.30+ later is a deliberate one-minor-at-a-time bump, outside
this feature.

**Out of scope, noted**: `temporalio/ui:latest` is also unpinned. FR-020
names only the server and admin-tools images.

---

## Open items carried to tasks

None of these block planning; each becomes an explicit task check.

- Confirm `temporal-namespace-setup`'s search-attribute step is
  idempotent on an existing volume: re-running `search-attribute create`
  for an existing name should be a tolerated error (`|| true`, with output
  checked).
- During the manual stack check, confirm that `make worker` and
  `make bridge` connect unchanged to `localhost:7233` on the new stack
  (User Story 4, scenario 3).
