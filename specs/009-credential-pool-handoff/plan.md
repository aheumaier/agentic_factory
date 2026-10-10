# Implementation Plan: Subscription-Seat Credential Pool with Checkpointed Agent Handoff

**Branch**: `009-credential-pool-handoff` | **Date**: 2026-10-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/009-credential-pool-handoff/spec.md`

## Summary

The pipeline's agents run on a pool of Claude Max subscription seats. Each seat is one `claude setup-token` OAuth token, held in the worker env and referenced by seat ID.

**The pool**
- A long-lived Temporal `CredentialPoolWorkflow` owns lease and usage state, through `@workflow.update` handlers.
- Pipeline stages reach it through three thin activities (research R5).
- A pure `select_seat` picks the lowest *last-seen* utilization among an agent's eligible seats (data-model).

**The agents**
- Each agent wraps `query()` in a shared `seat_guard`. The guard records usage from `RateLimitEvent.raw.unifiedWindows` (R2) and turns rejection, 429, 401 or expired-login results into `SeatExhausted`/`SeatInvalid` (R3).
- Seat credentials go in through `options.env` with blanked API-key and base-URL variables, which was empirically verified to take precedence (R1).

**Lossless handoff**
- swe-agent checkpoints after each task (marks it `[X]` and commits). On a seat outcome it pushes, then exits 75 or 77.
- The workflow's `_with_seat` helper re-acquires another seat. The successor resumes at the first `[ ]`.
- Handoffs have their own budget and never charge `MAX_BUILD_ATTEMPTS`/`MAX_PLAN_ATTEMPTS`.

**Delivery** is a vertical slice that is testable with today's single seat. Build is wired first and Architect last. Failover is tested with two logical seats on one token.

## Technical Context

**Language/Version**: Python ≥ 3.11 (worker venv 3.12; sandbox image `python:3.11-slim`)

**Primary Dependencies**:
- `temporalio` 1.32.0, using `@workflow.update`, `activity.client()`, `WorkflowIDConflictPolicy.USE_EXISTING` and `is_continue_as_new_suggested` (all verified present);
- `claude-agent-sdk` ≥ 0.2.152 (`RateLimitEvent`, `ResultError` with `.data`);
- `e2b` (`CommandExitException`);
- `pyyaml`.

**Storage**: Temporal workflow state, plus a checked-in `orchestration/credentials/pool.yaml` (config only). Credentials live in the worker `.env` only.

**Testing**:
- `uv run pytest tests/` (root; harness unit tests with the SDK stubbed in `tests/conftest.py`);
- `cd orchestration && uv run pytest` (pool, activity and workflow tests against a real `localhost:7233`, skipped without it);
- ruff and both suites are enforced by `.claude/hooks/py-check.sh`.

**Target Platform**:
- Temporal worker on the operator's host (in-process architect);
- E2B sandbox (Linux) for swe-agent.

**Project Type**: multi-component monorepo (orchestration worker plus per-agent harnesses plus a sandbox image).

**Performance Goals**:
- selecting a seat costs O(seats), so it is negligible;
- acquiring and releasing each add one activity plus one update round trip, so well under a second;
- `CredentialPoolExhausted` is raised on the first failed acquire (SC-008).

**Constraints**:
- No credential in any Temporal payload or log (FR-023).
- Workflow code must stay deterministic: `workflow.now()` only, and no I/O.
- `workflow.patched("seat-pool-v1")` gates the new pipeline path.
- Internal, single-operator use only (spec, Usage Constraint).

**Scale/Scope**: 1 seat today, and a handful later. Three agents are assigned, two of them wired in this feature. Up to 2 concurrent leases per seat.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is the unfilled Spec Kit template. It contains no ratified principles, so there are no formal gates. In their place, the plan is checked against the repo's binding conventions from `CLAUDE.md`:

| Convention | Status |
|---|---|
| Feature planned in Spec Kit before code | ✅ this directory |
| Building block per `agent-factory-architecture.md` | ✅ Temporal for durable state/leasing (§3.5); harness changes stay in the per-agent dirs (§3.2) |
| Model calls through LiteLLM (§3.4) | ⚠️ **deviation, justified**: see Complexity Tracking |
| Registry is the portability boundary (`SKILL.md`) | ✅ swe-agent and architect-agent `SKILL.md` updated, with no vendor-format tool definitions |
| Runtime deps in the agent's own `pyproject.toml`; test deps at the root | ✅ SDK pin in `harness/swe-agent/pyproject.toml` and the Dockerfile |
| Secrets never logged / scrubbed (`_scrubbed` pattern) | ✅ seat IDs only (FR-023, SC-006) |
| Ruff and pytest green on every change | ✅ hook-enforced |

**Post-design re-check:** unchanged. The only deviation is §3.4, documented below.

## Project Structure

### Documentation (this feature)

```text
specs/009-credential-pool-handoff/
├── spec.md
├── plan.md              # this file
├── research.md          # R1–R9 (R1–R3 empirical)
├── data-model.md
├── quickstart.md        # V1–V5 validation guide
├── contracts/
│   ├── credential-pool-interface.md
│   └── seat-guard-and-agent-protocol.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
orchestration/
├── credentials/
│   ├── __init__.py
│   ├── pool.py                 # NEW: load_pool, select_seat (pure), token_for, earliest_reset
│   └── pool.yaml               # NEW: seat-a only
├── workflows/
│   ├── credential_pool.py      # NEW: CredentialPoolWorkflow
│   └── pipeline_workflow.py    # _with_seat, Build + Architect wiring, patched("seat-pool-v1")
├── activities.py               # 3 seat activities; run_swe_agent_activity / architect_stage_activity gain seat_id
├── worker.py                   # register; start pool (USE_EXISTING) before worker.run()
├── scripts/seat_smoke.py       # NEW: V4 live smoke (reads token itself, never prints it)
└── tests/
    ├── test_credential_pool.py # NEW: select_seat matrix + pool workflow (local Temporal)
    ├── test_seat_activities.py # NEW: exit-code/seat_status mapping (CommandExitException mocked)
    └── test_pipeline_workflow.py  # stubs updated; handoff + pool-exhausted cases

harness/swe-agent/
├── seat_guard.py               # NEW (canonical copy)
├── agent.py                    # guarded run_implement, resume prompt, checkpoint, exit 75/77, all-done shortcut
└── pyproject.toml              # claude-agent-sdk>=0.2.152
harness/architect-agent/
├── seat_guard.py               # NEW (byte-identical copy)
└── agent.py                    # seat_token threading through option builders; guarded _model_text; TaskGroup fan-out

sandbox/swe-agent/Dockerfile    # COPY seat_guard.py; pin SDK  (template rebuild: manual `e2b template build`)
tests/
├── test_seat_guard.py          # NEW: classification, usage parsing, options env, copies identical
├── test_swe_agent_seat.py      # NEW: exit protocol, all-done shortcut, force-exhaust hook
└── test_architect_agent.py     # seat-mode option builders, sibling cancellation
.env.example                    # CLAUDE_OAUTH_SEAT_A/B placeholders
```

**Structure Decision**: The repo's existing layout is kept. Pool logic goes in a new `orchestration/credentials/` package, since the orchestration worker is the only reader of `pool.yaml`. The guard is duplicated per harness because each harness has its own `pyproject.toml` and runs in a different process: the E2B sandbox for swe-agent, and a by-path load into the worker for architect. A byte-equality test enforces that the copies stay identical.

## Implementation Phases (vertical slice; each step's tests go green before the next)

1. **Pool core.** Write `pool.yaml`, `pool.py` (pure) and the `select_seat` test matrix.
2. **Pool workflow and activities.** Write `CredentialPoolWorkflow`, the three activities, and the worker boot and registration. Add a workflow test against local Temporal, smoke-testing `execute_update` early (R5). If the server refuses updates, enable `frontend.enableUpdateWorkflowExecution` in `docker-compose.yml`.
3. **Seat guard.** Write `seat_guard.py`, its unit tests, and the V4 live smoke against seat-a.
4. **swe-agent.** Add the guarded `query`, the resume and checkpoint prompt, the all-done shortcut, the exit protocol, the force hook, the SDK pin and the Dockerfile change.
5. **Build wiring.** Change `run_swe_agent_activity` (seat_id, env, timeouts R8, exit mapping), add `_with_seat`, and wire the Build call and Eval-Gate `pr_url`. Update the pipeline workflow test stubs and add the handoff and pool-exhausted cases. **This completes the one-seat happy path (SC-001).**
6. **Architect seat mode.** Thread `seat_token`, use the guarded `_model_text`, cancel siblings with a TaskGroup, map the exceptions in the activity, and wire the plan loop. `CredentialPoolExhausted`/`SeatHandoffsExhausted` are re-raised before the budget-charging branch.
7. **Docs.** Update the `CLAUDE.md` Inference Routing, Orchestration and Harness rows; `agent-factory-architecture.md` §3.4 (the seat path deviation and the usage constraint); the swe-agent and architect-agent `SKILL.md` files; and `.env.example`.

Run `py-codereviewer` after each phase, before its commit.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Seat-backed model calls bypass LiteLLM (§3.4) | Subscription seats authenticate with a per-client OAuth token. swe-agent runs in E2B, which can't reach the local proxy. | **Rotation in LiteLLM:** not supported, because LiteLLM forwards client tokens per request and cannot pool them (R4). **LiteLLM pass-through for architect:** deferred until LiteLLM ≥ 1.81.14 with an `anthropic/*` route is deployed and the `RateLimitEvent` passthrough is verified (R4 follow-up). |
| Duplicated `seat_guard.py` (2 copies) | Separate processes and dependency sets per harness (sandbox vs. worker by-path load) | **A shared installable package:** no packaging exists for harnesses, and the root `pyproject.toml` is explicitly not a package. Byte equality is enforced by a test. |
| A second long-lived workflow (the pool) | Cross-run lease state must be durable and shared, and selection must be serialized | **In-memory pool in the worker:** lost on restart, not shared across workers. **Signals plus polling:** racy and noisier history (R5). |
