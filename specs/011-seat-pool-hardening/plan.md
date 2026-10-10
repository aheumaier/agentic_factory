# Implementation Plan: Seat Pool Hardening (closing out 009)

**Branch**: `011-seat-pool-hardening` | **Date**: 2026-10-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/011-seat-pool-hardening/spec.md`

**Usage Constraint (binding, from 009):** internal, single-operator use only. The seats belong to the operator, the pipeline and its pool are never offered to third parties, and seat rotation is a knowingly accepted Consumer-Terms grey area. Nothing here presents seat pooling as a product feature.

## Summary

Six small changes on top of 009's credential pool. Each rides an existing seam:

| Fork | Where | Change |
|---|---|---|
| F1 checkpoints | `harness/swe-agent/agent.py` | A `TaskCheckpointer`, called after every streamed message in `run_implement`, commits `checkpoint: T001 …` when the feature's done-task IDs grow and the tree is dirty. One more call before the seat-outcome push, and an end-of-run commit of leftover edits. The prompt now says "tick each task; the harness commits". |
| F2 stale utilization | `seat_guard.py` (both copies), `agent.py` status line, `activities.py`, `credential_pool.py`, `credentials/pool.py` | The usage snapshot gains `utilization_resets_at` (the max window's own `resetsAt`). It travels to `release` and is stored as `SeatState.utilization_resets_at`. `select_seat` reads a reading whose reset has passed as 0. `mark_exhausted` sets it to `exhausted_until`. |
| F3 wait for reset | `pipeline_workflow.py::_with_seat` | When acquire returns no seat and the earliest reset is ≤ 6 h away, `workflow.sleep` until it (+1 s) and ask again, at most 2 waits per invocation. Gated by the new patch ID `seat-pool-wait-v1`, checked only on that path. |
| F4 expiry warning | `credentials/pool.py`, `worker.py`, `credential_pool.py` | Pure `expires_in_days(seat_cfg, today)`. The worker logs one warning per seat ≤ 14 days from expiry at boot. `seats()` gains `expires_in_days`. |
| F5 feedback handoff | `_with_seat`, `run_swe_agent_activity`, `agent.py` | `_with_seat(..., with_handoff=True)` appends the handoff index to the Build activity's args. The activity puts `SEAT_HANDOFF_INDEX` in the sandbox env. `agent.py` skips `verify_new_commit` when it is > 0. |
| F6 force hook | `activities.py::_sandbox_envs` | `SEAT_GUARD_FORCE_EXHAUST_HANDOFF=N` arms the force hook on handoff N of Build for any seat. The 009 `SEAT_GUARD_FORCE_EXHAUST_SEAT` still works. |

Then the live V5 re-run (quickstart V5) proves mid-task resume.

## Technical Context

**Language/Version**: Python ≥ 3.11 (worker venv 3.12; sandbox image `python:3.11-slim`)

**Primary Dependencies**: `temporalio` 1.32 (`workflow.sleep`, `workflow.patched`, `@workflow.update` validators; all present), `claude-agent-sdk` ≥ 0.2.152, `e2b`, `pyyaml`. No new dependency.

**Storage**: Temporal workflow state (the pool's `SeatState` gains one key); `orchestration/credentials/pool.yaml` unchanged.

**Testing**:
- `uv run pytest tests/ -q` for the harness and `seat_guard` (scripted `query`, real git in a temp origin);
- `cd orchestration && uv run pytest -q` for the pool, the activities and the workflow, against a live `localhost:7233`, 0 skipped;
- `uv run ruff check .`; the hooks in `.claude/hooks/py-check.sh` run all three on every `.py` edit.

**Target Platform**: Temporal worker on the operator's host; E2B sandbox `swe-agent-sandbox` (rebuilt after `harness/swe-agent/*.py` changes).

**Project Type**: multi-component monorepo (worker plus per-agent harnesses plus a sandbox image).

**Performance Goals**: one `git status`/`git diff` per streamed message, only when the done-task set changed (a file read otherwise). Negligible next to a model turn.

**Constraints**:
- Never a credential in a payload, log, exception or PR comment (009 FR-023). New fields are timestamps, an integer and day counts.
- Workflow determinism: F3's sleep is the only new command, and it sits behind `seat-pool-wait-v1`. The extra activity argument (F5) and the extra `release` argument (F2) change no command type or order (research R2).
- `seat-pool-v1` and `architect-seat-pool-v1` keep their IDs; replay depends on them.
- The two `seat_guard.py` copies stay byte-identical (`tests/test_seat_guard.py`).

**Scale/Scope**: one real seat today and two logical seats in V5; about 150 lines of code plus tests.

## Constitution Check

`.specify/memory/constitution.md` is still the unfilled template, so it sets no gates. The binding project rules come from `CLAUDE.md` and the 009 decisions:

| Gate | Status |
|---|---|
| Spec Kit flow (spec → plan → tasks before code) | Pass |
| Design defers to `docs/agent-factory-architecture.md` §-sections (§3.2 Harness, §3.4 Inference Routing deviation, §3.5 Orchestration) | Pass, no new building block |
| New workflow branch behind a **new** patch ID | Pass: `seat-pool-wait-v1` (F3) |
| Credential secrecy (009 FR-023) | Pass: no new field carries a credential |
| Usage Constraint restated | Pass: spec, plan, contracts, SKILL.md |
| Tests in the right suite; never weaken a test | Pass: harness → `tests/`, workflow/pool → `orchestration/tests/`; existing tests keep their assertions |

Re-check after Phase 1: still passes. The pool-workflow changes (F2, F4) add no command, so they need no patch ID (research R3).

## Project Structure

### Documentation (this feature)

```text
specs/011-seat-pool-hardening/
├── spec.md
├── plan.md          # this file
├── research.md
├── data-model.md
├── quickstart.md    # validation plus V5 re-run results
├── contracts/
│   ├── seat-guard-and-agent-protocol.md   # deltas to 009's
│   └── credential-pool-interface.md       # deltas to 009's
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
harness/swe-agent/agent.py          # F1 TaskCheckpointer, F2 status line, F5 handoff index
harness/swe-agent/seat_guard.py     # F2 utilization_resets_at   ┐ byte-identical
harness/architect-agent/seat_guard.py                          # ┘
orchestration/credentials/pool.py   # F2 select_seat/new_seat_state, F4 expires_in_days
orchestration/workflows/credential_pool.py   # F2 release/mark_exhausted/state upgrade, F4 seats()
orchestration/workflows/pipeline_workflow.py # F2 release arg, F3 wait, F5 with_handoff
orchestration/activities.py         # F2 result/release arg, F5/F6 _sandbox_envs
orchestration/worker.py             # F4 startup warning
tests/test_seat_guard.py, tests/test_swe_agent_seat.py
orchestration/tests/test_credential_pool.py, test_seat_activities.py, test_pipeline_workflow.py
```

**Structure Decision**: no new modules. Every change extends a 009 file at the seam 009 already defined.

## Complexity Tracking

None.
