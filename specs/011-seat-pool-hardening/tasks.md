# Tasks: Seat Pool Hardening (closing out 009)

**Input**: Design documents from `specs/011-seat-pool-hardening/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Required. Every behavior change gets a test in the right suite: harness → `tests/`, pool/activity/workflow → `orchestration/tests/`. The hooks run ruff and both suites on every `.py` edit, so edit `.py` files one at a time (live-Temporal tests race under parallel runs).

**Usage Constraint (binding):** internal, single-operator use only (see spec.md).

**Order note:** User Story 2 (the live V5 re-run) is P1, but it needs F1 (US1), F5 (US6) and F6 (US7) in the sandbox image. It therefore runs last, after review and the template rebuild.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [X] T001 Create branch `011-seat-pool-hardening`, mark 009 `**Status**: Implemented` with a pointer to 011 in specs/009-credential-pool-handoff/spec.md, and point .specify/feature.json at specs/011-seat-pool-hardening

---

## Phase 2: Foundational (handoff index reaches the Build sandbox)

**Purpose**: US6 (F5) and US7 (F6) both need the Build activity to know its handoff index.

- [X] T002 Add `with_handoff: bool = False` to `_with_seat` in orchestration/workflows/pipeline_workflow.py (appends `handoff` after `seat_id` in the activity args), and pass `with_handoff=True` from the Build loop
- [X] T003 Add trailing `handoff: int = 0` to `run_swe_agent_activity`, and make `_sandbox_envs(seat_id, handoff)` always set `SEAT_HANDOFF_INDEX` in orchestration/activities.py
- [X] T004 Test in orchestration/tests/test_seat_activities.py that `_sandbox_envs` sets `SEAT_HANDOFF_INDEX`, and in orchestration/tests/test_pipeline_workflow.py that a Build handoff passes handoff index 0 then 1 to the activity (the stub records the trailing arg)

**Checkpoint**: Build activity receives 0 on the first seat and 1 on the successor.

---

## Phase 3: User Story 1 - Every finished task is saved (Priority: P1) 🎯 MVP

**Goal**: The harness commits a checkpoint whenever the done-task set grows (F1).

**Independent Test**: A scripted model ticks T001 without committing → a `checkpoint: T001` commit exists; force-after-1-commit fires right after it and the pushed branch holds it.

- [X] T005 [US1] Add `TaskCheckpointer` (done-task keys from `_task_files`, seeded at start; commit `checkpoint: <IDs>` on growth plus dirty tree; record on a clean tree; swallow `CalledProcessError` and retry; `finish()` commits leftovers as `checkpoint: end of run`; git identity fallback per research R7) in harness/swe-agent/agent.py
- [X] T006 [US1] Wire it in harness/swe-agent/agent.py: `run_implement(..., on_message=...)` calls it after each message; `run()` calls it once more before `checkpoint_push` on a seat outcome, and `finish()` after a normal stream end before `verify_left_main`/`verify_new_commit`
- [X] T007 [US1] Update `IMPLEMENT_PROMPT` in harness/swe-agent/agent.py: tick each task `[X]` as soon as it is done, don't batch ticks, the harness saves a checkpoint commit
- [X] T008 [US1] Tests in tests/test_swe_agent_seat.py: commit on tick with a dirty tree; no commit on a clean tree (model committed) and no re-report; one commit for a batched tick naming both IDs; failed commit retried on the next message; end-of-run leftovers committed; forced exhaustion after 1 commit fires right after `checkpoint: T001` and the origin holds it; predecessor's `[X]` tasks are not re-committed; git identity fallback when none is configured; update the prompt test

**Checkpoint**: SC-002 holds in scripted tests even when the model never commits.

---

## Phase 4: User Story 7 - Force hook by handoff index (Priority: P3, needed by US2)

**Goal**: `SEAT_GUARD_FORCE_EXHAUST_HANDOFF=N` arms forced exhaustion for whichever seat runs handoff N (F6).

**Independent Test**: `_sandbox_envs` forwards the force env on handoff 0 for any seat and not on handoff 1; the seat-name hook still works.

- [X] T009 [US7] Extend `_sandbox_envs` in orchestration/activities.py: forward `SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS` when the seat name matches **or** `str(handoff) == SEAT_GUARD_FORCE_EXHAUST_HANDOFF`
- [X] T010 [US7] Tests in orchestration/tests/test_seat_activities.py: handoff-index match on any seat, no match on another index, the seat-name path unchanged, nothing forwarded without the count variable

---

## Phase 5: User Story 6 - Feedback retry hands off without a false "no new commit" (Priority: P3, needed by US2)

**Goal**: The successor (`SEAT_HANDOFF_INDEX > 0`) skips `verify_new_commit` (F5).

**Independent Test**: Feedback plus handoff index 1 plus a model making no commit → the PR step runs and the exit code is 0; index 0 → it still fails.

- [X] T011 [US6] Add `_handoff_index()` (from `SEAT_HANDOFF_INDEX`, default 0) and skip `verify_new_commit` when it is > 0 in harness/swe-agent/agent.py
- [X] T012 [US6] Tests in tests/test_swe_agent_seat.py: index 1 with feedback and no new commit reaches the PR step; index 0 with the same input fails

---

## Phase 6: User Story 3 - Reset-aware utilization (Priority: P2)

**Goal**: A reading stops counting once its own window resets (F2).

**Independent Test**: The selection matrix in orchestration/tests/test_credential_pool.py.

- [X] T013 [US3] Add `utilization_resets_at` (the max window's `resetsAt`, falling back to `resets_at`) to `usage_from_rate_limit_info` in harness/swe-agent/seat_guard.py, then copy it byte-identically to harness/architect-agent/seat_guard.py
- [X] T014 [US3] Test the max-window reset choice and the fallback in tests/test_seat_guard.py
- [X] T015 [US3] Add `utilization_resets_at` to every `seat_status` line in `_seat_status_line` in harness/swe-agent/agent.py, and test it in tests/test_swe_agent_seat.py
- [X] T016 [US3] Pool rule in orchestration/credentials/pool.py: `new_seat_state` gains `utilization_resets_at: None`; add `effective_utilization(state, now)`; `select_seat` sorts by it
- [X] T017 [US3] In orchestration/workflows/credential_pool.py: `release` gains `utilization_resets_at=None` (validated tz-aware) and stores it with the reading; `mark_exhausted` sets it to `exhausted_until`; `_apply_config` upgrades old state; `seats()` shows it
- [X] T018 [US3] In orchestration/activities.py: `release_seat_activity` gains the trailing arg; `run_swe_agent_activity` and `architect_stage_activity` results carry `utilization_resets_at` (ISO). In orchestration/workflows/pipeline_workflow.py: `_with_seat` passes `result.get("utilization_resets_at")` to release
- [X] T019 [US3] Tests in orchestration/tests/test_credential_pool.py (selection matrix: past reset → 0, future → as is, none → as is, expired exhaustion → 0, old state without the key; release stores and clears the reset; validator rejects a naive timestamp) and orchestration/tests/test_seat_activities.py (status parsing carries `utilization_resets_at`)

---

## Phase 7: User Story 4 - Wait for a reset (Priority: P2)

**Goal**: An empty pool with a reset at most 6 h away waits durably instead of failing (F3).

**Independent Test**: A stub acquire returns "no seat, reset in 2 s" once and then a seat → the run succeeds with no budget charged.

- [X] T020 [US4] In orchestration/workflows/pipeline_workflow.py: `POOL_WAIT_HORIZON = 6h`, `MAX_POOL_WAITS = 2`; `_pool_wait(earliest_reset, waits)` returns a delay only under `workflow.patched("seat-pool-wait-v1")` (evaluated only when no seat), a known reset ≤ horizon and waits left; `_with_seat` sleeps with `workflow.sleep` and re-acquires with the same lease key, without advancing the handoff
- [X] T021 [US4] Tests in orchestration/tests/test_pipeline_workflow.py: one wait then success (no extra Build attempt or plan charge, Build ran once, a timer exists in history); no reset known (`earliest_reset=None`) → fails at once; reset more than 6 h away → fails at once (the existing 2099 tests keep passing unchanged); two waits spent → `CredentialPoolExhausted`

---

## Phase 8: User Story 5 - Expiry warning (Priority: P3)

**Goal**: The operator sees seats about to expire (F4).

**Independent Test**: A pool with seats at 3 days, 400 days and no date → one warning, and correct `expires_in_days` values.

- [X] T022 [US5] Add `EXPIRY_WARN_DAYS = 14`, `expires_in_days(seat_cfg, today)` and `expiring_seats(pool, today)` to orchestration/credentials/pool.py; `seats()` in orchestration/workflows/credential_pool.py adds `expires_in_days` from `workflow.now().date()`
- [X] T023 [US5] Log one WARNING per expiring seat (ID and date only) after `load_pool()` in orchestration/worker.py
- [X] T024 [US5] Tests in orchestration/tests/test_credential_pool.py: `expires_in_days` for future, past and missing dates; `expiring_seats` threshold; `seats()` row carries it

---

## Phase 9: Polish, review and docs

- [X] T025 Run the `py-codereviewer` subagent on `git diff main...011-seat-pool-hardening`; fix every confirmed finding (at most two rounds per finding) and re-review the fixes
- [X] T026 [P] Update harness/swe-agent/SKILL.md and registry/agents/swe-agent SKILL.md (if present), plus harness/architect-agent/SKILL.md, for checkpoints, the handoff index, `utilization_resets_at` and the Usage Constraint
- [X] T027 [P] Update CLAUDE.md's Harness/Runtime swe-agent row and Orchestration row (011 only: harness checkpoints, the wait-for-reset patch `seat-pool-wait-v1`, the expiry warning)
- [X] T028 Run the full gate: `uv run pytest tests/ -q`, `cd orchestration && uv run pytest -q` (0 skipped), `uv run ruff check .`; record the output lines in quickstart.md

---

## Phase 10: User Story 2 - Live proof of mid-task resume (Priority: P1)

**Goal**: The V5 re-run shows the successor starting at T002 or later (closes 009 SC-002).

**Independent Test**: quickstart.md V5.

- [X] T029 [US2] Rebuild the `swe-agent-sandbox` E2B template and verify the sha256 of `/app/agent.py` and `/app/seat_guard.py` against the repo files
- [X] T030 [US2] Cut fixture branch `v5-seat-handoff-3` from scratch-repo commit `fe874169` (rename the spec dir, update feature.json and spec.md) and push it from a temporary clone, with the token redacted
- [X] T031 [US2] Check headroom with orchestration/scripts/seat_smoke.py (PASS, utilization below about 0.8); start the worker per quickstart V5 step 4; start the run, approve the plan after checking that tasks.md is a checklist, and wait for completion
- [ ] T032 [US2] Run `.handoff/v5/v5_verify.py` (IDs set to `v5-seat-handoff-run-3` and `credential-pool-v5b`) with the worker log; check the pass criteria against the remote branch's commit log; record the results in specs/011-seat-pool-hardening/quickstart.md "Results"
  - Results are recorded in quickstart.md ("V5 re-run 3"). Pass criteria 1 and 3 are **not met**: the model batched T001–T003 into one tick, so the single checkpoint held all three tasks and the successor had nothing left to resume. This waits on the operator's F7 ruling (spec.md).
- [X] T033 [US2] Stop the worker, terminate `credential-pool-v5b`, and remove the temporary clones

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → Phases 3–8.
- US1 (F1), US7 (F6) and US6 (F5) are prerequisites for US2. US3 (F2), US4 (F3) and US5 (F4) are independent of each other and of US2.
- Phase 9 needs all code phases done. Phase 10 needs Phase 9 (the image is built from reviewed code).
- Within a story: implementation, then its tests (the hooks run both suites on every edit anyway).

## Parallel Opportunities

Few, on purpose. Most tasks touch the same four files (`agent.py`, `activities.py`, `pipeline_workflow.py`, `credential_pool.py`), and parallel runs of the live-Temporal suite race. T026 and T027 (docs) can run in parallel.

## Implementation Strategy

MVP is US1 plus the foundational handoff plumbing: deterministic checkpoints are the SC-002 promise. Then US7 and US6 make the live run deterministic, then US3, US4 and US5. Review, docs, the gate, the image rebuild, and finally the live V5 re-run.
