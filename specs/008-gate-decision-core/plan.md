# Implementation Plan: Gate Decision Core

**Branch**: `008-gate-decision-core` | **Date**: 2026-10-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/008-gate-decision-core/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

This feature makes the plan gate safe for more than one decision surface.
It changes no GitHub behaviour and needs no Teams access. There are four
pieces, one per user story.

1. **First-valid-wins in the workflow (US1)**. `AgentPipelineWorkflow`
   gains a per-attempt **decision window** for the plan gate, held in a new
   pure-state module `orchestration/workflows/plan_gate.py`.
   - The existing `plan_approved` / `plan_rejected` signals become
     set-if-unset. They also take an optional `{resolved_by, via, attempt}`
     dict, and still accept today's zero-payload calls.
   - A new synchronous `@workflow.update decide_plan` with a validator
     refuses, before anything is recorded, a decision that is malformed,
     has empty feedback, names a stale attempt, arrives with no window
     open, or targets an attempt that is already decided. The last case
     returns the winner's attribution, even after the window has closed.
   - Both handlers are plain `def` and record before returning. Every
     handler in a workflow task runs before the plan loop wakes, so the
     first one in the run's recorded order wins and the rest become ignored
     duplicates or refusals. This was verified for all four pairings
     (research R1).
   - The change sits behind one new `workflow.patched("plan-decision-window-v1")`
     marker inside the existing `architect-stage-v1` block (research R6).
2. **Status Query (US2)**. `@workflow.query status()` returns a versioned
   snapshot: stage, open window, budgets, PR URL, the last applied decision
   with attribution, and the last 20 ignored signals
   (`contracts/status-snapshot.md`). It is read-only and verified to add
   no history (research R7).
3. **Bridge core/adapter split (US3)**. A new package
   `orchestration/webhook_bridge/core/` holds the surface-neutral
   operations: start run, gate signal, validated plan decision, status.
   Each one returns an outcome instead of reacting.
   - The existing modules keep their paths and signatures as the GitHub
     adapter's contract. `temporal_client.signal_gate(..., github_client)`
     becomes a thin shim that renders the reaction from the core's outcome
     (research R8, `contracts/core-operations.md`).
   - The audit set gains `signal_issued` (plan gate only) and
     `worker_unavailable`.
   - Validated decisions use `start_update(ACCEPTED)` + `result()`, with
     a deterministic, surface-namespaced request id for idempotent
     resubmission (research R2, R4).
4. **Pinned Temporal stack (US4)**. `docker-compose.yml` replaces the
   deprecated `temporalio/auto-setup:latest` (server 1.29.3) with
   `temporalio/server:1.29.7` + `temporalio/admin-tools:1.29.7-tctl-1.18.4-cli-1.7.2`.
   Two one-shot setup services reproduce auto-setup's schema setup, update
   and namespace steps, and also register `TargetRepo` / `PRNumber`
   (research R10).

The workflow-level tests run the real `AgentPipelineWorkflow` with stubbed
activities under `WorkflowEnvironment.start_local()`, the repo's first
in-process Temporal test environment (research R9).

## Technical Context

**Language/Version**: Python 3.12 (orchestration venv; `requires-python >=3.11`)

**Primary Dependencies**:

- `temporalio` 1.32.0 (resolved in `orchestration/uv.lock`; no bump needed,
  since Updates, validators and Queries are all present);
- `aiohttp` (bridge HTTP server, unchanged).

No new runtime dependency.

**Storage**: none new. Workflow state is durable through Temporal event
history. The local stack keeps the existing `temporal-pg-data` Postgres
volume.

**Testing**: `pytest` + `pytest-asyncio` (`asyncio_mode = "auto"`), run as
`cd orchestration && uv run pytest`.

- New workflow and core tests use `temporalio.testing.WorkflowEnvironment.start_local()`:
  an in-memory dev server subprocess with `TargetRepo` / `PRNumber`
  registered. It uses the `temporal` CLI on `PATH` if one is present
  (1.8.2 / server 1.31.2 on the dev machine), or else downloads it once.
- The existing bridge tests run **unmodified** (FR-015, SC-003).

**Target Platform**: local docker-compose stack (macOS/Linux dev),
Temporal at `localhost:7233`.

**Project Type**: orchestration service (Temporal workflow + worker) plus a
webhook bridge (aiohttp).

**Performance Goals**: validated-decision submission and status return
within 10 s when no worker is running (SC-005). Design values: 5 s RPC
timeout, 8 s wall-clock guard per core operation (research R3).

**Constraints**:

- The bridge test suite stays byte-for-byte unchanged.
- Determinism uses `workflow.patched` only.
- 002 FR-016 (disposable repos only) stays in force, and the allow-list
  applies to every core entry point.
- No dependency on spec 005.
- The core never imports the workflow class: every reference is by name
  string.

**Scale/Scope**:

- One gate (plan) and at most `MAX_PLAN_ATTEMPTS = 3` charged attempts per
  run.
- The ignored-signal list is capped at 20, so workflow state stays bounded
  regardless of comment volume.
- About 6 new modules (5 in `core/` plus `plan_gate.py`) and 3 modified
  workflow/bridge modules.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is still the unfilled placeholder
template: no principles have been ratified for this repo, so there are no
gates to check against and no violations to justify. Re-checked after
Phase 1: unchanged.

The repo's working rules from `CLAUDE.md` are followed in place of
ratified gates:

- design rationale cross-referenced by section: `docs/80` §7.2, §12, §14.8,
  §15;
- Spec Kit flow ahead of code;
- determinism markers on workflow changes;
- the bridge's FR-016 allow-list kept.

## Project Structure

### Documentation (this feature)

```text
specs/008-gate-decision-core/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output: R1-R10, spike-verified Temporal behaviour
├── data-model.md        # Phase 1 output: DecisionWindow, AppliedDecision, IgnoredSignal, PlanGate, core outcomes
├── quickstart.md        # Phase 1 output: three validation scenarios
├── contracts/
│   ├── status-snapshot.md     # versioned status Query payload (consumed by 005, 009)
│   ├── workflow-handlers.md   # plan_approved/plan_rejected signals, decide_plan update + validator, status query
│   └── core-operations.md     # core ops, outcomes, audit mapping, pinned GitHub adapter surface
├── checklists/requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
orchestration/
├── workflows/
│   ├── plan_gate.py              # NEW: pure state (no temporalio import): DecisionWindow,
│   │                             # AppliedDecision, IgnoredSignal, PlanGate (open/on_signal/
│   │                             # check_update/apply_update/close/snapshot parts); 20-entry cap
│   └── pipeline_workflow.py      # MODIFIED:
│                                 #  - signals: set-if-unset via PlanGate + optional attribution
│                                 #    dict; legacy _plan_decision/_plan_feedback writes kept
│                                 #  - @workflow.update decide_plan (sync) + @decide_plan.validator
│                                 #  - @workflow.query status() -> snapshot v1
│                                 #  - _stage/_pr_url/_plan_charged/_build_charged instance state;
│                                 #    try/except sets "failed"; "completed" before return
│                                 #  - patched("plan-decision-window-v1") inside architect-stage-v1;
│                                 #    unpatched branch = today's reset+wait, verbatim
├── tests/
│   ├── _stubs.py                 # NEW: _stub_activities/_plan_result moved here from
│   │                             # test_pipeline_workflow.py (which then imports them)
│   ├── conftest.py               # NEW: session-scoped start_local() fixture, SA registration,
│   │                             # TEMPORAL_CLI_PATH / shutil.which("temporal") lookup
│   ├── test_plan_gate.py         # NEW: pure PlanGate unit tests (precedence, cap of 20,
│   │                             # unknown attribution, legacy no-arg)
│   ├── test_plan_gate_workflow.py # NEW (FR-021): real AgentPipelineWorkflow, same-task
│   │                             # pairings x4, malformed empty-feedback signal, stale,
│   │                             # no-window, already-resolved w/ attribution, legacy no-arg,
│   │                             # status while blocked + history length unchanged, budgets
│   ├── test_decision_core_e2e.py # NEW: core.submit_plan_decision / get_status against the real
│   │                             # workflow (accepted, refused reasons, idempotent resubmit,
│   │                             # worker_unavailable within bound for both ops)
│   └── test_pipeline_workflow.py # MODIFIED (imports only + docstring: WorkflowEnvironment now used)
└── webhook_bridge/
    ├── core/                     # NEW package: surface-neutral core
    │   ├── __init__.py
    │   ├── commands.py           # RunCommand, GateCommand (moved), Origin, PlanDecisionRequest
    │   ├── policy.py             # repo_allowed() (moved verbatim from server.py:102)
    │   ├── runs.py               # connect, workflow_id, start_run, resolve_gate_target,
    │   │                         # TASK_QUEUE, WORKFLOW_TYPE (moved from temporal_client.py)
    │   ├── gate.py               # signal_gate -> GateSignalOutcome (no reactions)
    │   ├── decisions.py          # submit_plan_decision -> DecisionOutcome
    │   └── status.py             # get_status -> StatusOutcome
    ├── temporal_client.py        # MODIFIED: re-exports core.runs names; signal_gate = shim
    │                             # (core call + reaction render); kw-only allowed_repos=None
    ├── server.py                 # MODIFIED: uses core.policy.repo_allowed; passes allowed_repos;
    │                             # dedup via Origin("github", id).dedup_key
    ├── grammar.py                # MODIFIED: imports RunCommand/GateCommand from core.commands
    ├── audit.py                  # MODIFIED: Outcome += signal_issued, worker_unavailable;
    │                             # reaction map += signal_issued -> eyes
    ├── auth.py, dedup.py, github_app.py   # unchanged
    └── tests/
        ├── (all existing files)  # UNCHANGED (FR-015, SC-003)
        ├── test_core_gate.py     # NEW: outcome per gate (plan signal_issued, pm/security
        │                         # _no_handler), no reaction calls from core, audit line
        ├── test_core_decisions.py # NEW (mocks): result() always awaited; refusal mapping incl.
        │                         # already_resolved details; RPC-timeout -> worker_unavailable;
        │                         # request_id determinism + surface namespacing; allow-list
        ├── test_core_status.py   # NEW (mocks): ok / target_not_found / RPCError -> worker_unavailable
        └── test_server_allowlist_passthrough.py  # NEW guard: BridgeApp passes allowed_repos

docker-compose.yml                # MODIFIED: temporal-schema-setup (admin-tools, one-shot) ->
                                  # temporal (server:1.29.7) -> temporal-namespace-setup
                                  # (admin-tools, one-shot: default namespace + TargetRepo/PRNumber);
                                  # pg_isready healthcheck on temporal-postgres
specs/002-webhook-trigger-bridge/quickstart.md   # MODIFIED: SA registration now automatic
                                  # (manual commands kept as a fallback note)
docs/80-teams-workspace-design.md # MODIFIED: §12.1 / §12.4 corrected per spec Assumptions
                                  # (losing GitHub comment recorded by the run, not the bridge;
                                  # late GitHub answer gets 👀, not 😕); §15 image row -> 1.29.7
CLAUDE.md                         # MODIFIED: Orchestration row mentions decide_plan/status +
                                  # webhook_bridge/core; Commands note on start_local tests
```

**Structure Decision**: the existing layout is extended in place. The
surface-neutral core is a **sub-package of the bridge**
(`webhook_bridge/core/`), not a new top-level project. It keeps the bridge's
import root (`from webhook_bridge...`), test discovery
(`cd orchestration && uv run pytest`), and the
`python -m orchestration.webhook_bridge.server` entrypoint (`Makefile`
`bridge` target) unchanged. Spec 009's Teams adapter will import it the
same way.

Workflow-side gate state goes in `orchestration/workflows/plan_gate.py`,
next to the workflow, because it must be importable inside the workflow
sandbox. `pipeline_workflow.py` passes `activities` through
`imports_passed_through()`. `plan_gate.py` is pure, so it needs no
pass-through.

## Implementation notes that tasks must honour

- **The refusal surfaces only from `result()`**. A core that calls only
  `start_update` reports every refusal as accepted (research R2). Unit
  test: a mocked handle whose `result()` raises `WorkflowUpdateFailedError`
  must map to `refused`.
- **Handlers stay synchronous**. `plan_approved`, `plan_rejected` and
  `decide_plan` are `def`, with no `await` anywhere in them (research R1).
  Making one `async` reopens the race.
- **Validated decisions bypass `DeliveryCache`**. They rely on the server's
  update-id dedup instead, so a resubmission after `worker_unavailable`
  reaches the run and returns the real outcome (research R4).
- **`resolve_gate_target` is unchanged**. Its exact `list_workflows(query=…)`
  call is pinned by `test_temporal_client.py:85`. The SC-005 bound comes
  from the outer `asyncio.timeout`, not from an added kwarg (research R3).
- **`already_resolved` outlives the window**. `PlanGate.decided` keeps each
  closed window's decision by attempt. A late validated decision naming a
  decided attempt (with no window open) is refused as `already_resolved`
  with the winner's attribution, not as `no_window_open`. That is what
  drives docs/80 §14.8's "already resolved by X" card, and it makes
  US3-3 / FR-021's already-resolved case testable sequentially, not only
  as a race. `stale_attempt` still takes precedence while a newer window
  is open (US1-3). Precedence is in `contracts/workflow-handlers.md`.
- **`core/__init__.py` stays import-light**. `grammar.py` imports
  `core.commands`, which runs `core/__init__.py`. The `__init__` must not
  eagerly import `runs` / `gate` / `decisions` / `status`, or every
  grammar import (including `test_grammar.py`) would pull in
  `temporalio.client`. Keep it empty, or re-export `commands` / `policy`
  only.
- **The compose setup services need `TEMPORAL_ADDRESS=temporal:7233`**.
  The admin-tools `temporal` CLI in `temporal-namespace-setup` otherwise
  looks for the server at `localhost:7233` inside its own container.
- **005 rebase point**: `plan-decision-window-v1` is the only new marker.
  If 005 lands first, this feature rebases onto 005's markers instead of
  adding a parallel one (spec Assumptions).
- **Docs to correct in the same change**: `docs/80` §12.1 / §12.4, per the
  spec's Assumptions (`duplicate_ignored` logged by the bridge for a losing
  GitHub comment → recorded by the run; 😕 → 👀). Also update the §15
  Temporal image row.

## Complexity Tracking

*No Constitution Check violations: this section is not applicable.*

One deliberate seam is recorded for reviewers. The pinned shims
`temporal_client.start_run` / `signal_gate` take `allowed_repos=None`, so
the unchanged legacy tests can call them. A guard test keeps production
calls from ever passing `None` (research R8). The simpler alternative,
changing the shim signatures, was rejected because FR-015 forbids
modifying those tests.
