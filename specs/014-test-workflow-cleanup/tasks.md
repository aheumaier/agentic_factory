# Tasks: Test Suite Leaves No Running Temporal Workflows

**Input**: Design documents from `specs/014-test-workflow-cleanup/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Usage Constraint (binding, from 009 and 011):** internal, single-operator use only. This feature changes only tests.

**Tests**: requested by the spec (FR-008), written first. They must fail on today's code before the fix.

**Gate**: run serially from the worktree root, never in parallel (live-Temporal tests time out when suites overlap):
`uv run --locked pytest tests/ -q`, then `(cd orchestration && uv run --locked pytest -q)`, then `uv run --locked ruff check .`

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependencies)
- **[Story]**: the user story from spec.md (US1, US2, US3)

## Phase 1: Setup

- [X] T001 Record the baseline: run the quickstart count command and confirm it prints the 8 baseline IDs (quickstart.md "Results" baseline row). Record the orchestration suite's time on today's code (`time (cd orchestration && uv run --locked pytest -q)`) for SC-004.

## Phase 2: Foundational (blocks every story)

- [X] T002 Create `orchestration/tests/_workflow_limits.py` with `TEST_WORKFLOW_TIMEOUT = timedelta(minutes=2)` and a comment: longer than pytest-timeout's 60 s; `execution_timeout`, not `run_timeout`, because of continue-as-new; it also bounds a debugger session, raise it locally to debug (research R1-R3, architect A6).

**Checkpoint**: `from tests._workflow_limits import TEST_WORKFLOW_TIMEOUT` imports from both `orchestration/tests/` and `orchestration/webhook_bridge/tests/`.

## Phase 3: User Story 1 + User Story 2 (P1) - A suite run, and a killed run, leave nothing running

US1 (cleanup) and US2 (time limit) change the same lines of the same four files, so they are one phase. Tests first.

**Independent test**: quickstart V1 and V2.

### Tests (write first, see them fail)

- [X] T003 [US1] [US2] In `orchestration/tests/test_pipeline_workflow.py`, add a test that enters `_harness` with `_stub_activities(calls, [_plan_result()])`, starts the pipeline workflow with `_start`, waits with `_wait_plan_parked(handle, 1)`, raises a sentinel error inside `_harness`, and catches it with `pytest.raises`. After `_harness` exits it asserts that `(await handle.describe()).status == WorkflowExecutionStatus.TERMINATED`, and that the pipeline workflow and the pool `credential-pool-test-<run>` each record `raw_description.execution_config.workflow_execution_timeout.ToTimedelta() == TEST_WORKFLOW_TIMEOUT` (research R7, architect A1 and A2). Run it alone and confirm it fails on today's code.
- [X] T004 [P] [US2] In `orchestration/webhook_bridge/tests/test_integration.py`, add one assertion after the probe start that its recorded `workflow_execution_timeout.ToTimedelta()` is `TEST_WORKFLOW_TIMEOUT`.
- [X] T005 [P] [US2] In `orchestration/webhook_bridge/tests/test_e2e_pipeline_gate.py`, in both tests, add one assertion once `handle` is set that its recorded `workflow_execution_timeout.ToTimedelta()` is `TEST_WORKFLOW_TIMEOUT`.

### Implementation

- [X] T006 [US1] [US2] In `orchestration/tests/test_pipeline_workflow.py`: add a `_pipeline_id(run_id)` helper used by `_start` and `_harness`; give `_start` and the pool start in `_harness` `execution_timeout=TEST_WORKFLOW_TIMEOUT`; in `_harness`'s `finally`, inside `async with Worker`, terminate the pipeline workflow by ID first, then the pool, each in its own `contextlib.suppress(Exception)` block; replace the 7 inline `client.start_workflow(AgentPipelineWorkflow.run, …)` calls with `_start`; update the module docstring (research R4, R5, architect A3 and A4).
- [X] T007 [P] [US2] In `orchestration/tests/test_credential_pool.py`, give the `_running_pool` start `execution_timeout=TEST_WORKFLOW_TIMEOUT`, and update the module docstring if it describes cleanup.
- [X] T008 [P] [US2] In `orchestration/webhook_bridge/tests/test_integration.py`, give the probe start `execution_timeout=TEST_WORKFLOW_TIMEOUT`.
- [X] T009 [P] [US1] [US2] In `orchestration/webhook_bridge/tests/test_e2e_pipeline_gate.py`, in both tests: `monkeypatch.setattr(client, "start_workflow", functools.partial(client.start_workflow, execution_timeout=TEST_WORKFLOW_TIMEOUT))` before the bridge starts the run; in the `finally`, terminate through `client.get_workflow_handle(wf_id)` in `contextlib.suppress(Exception)`, whether or not `handle` was set. No change to `orchestration/webhook_bridge/temporal_client.py` (research R6, FR-004, FR-005).
- [X] T010 [US1] [US2] Run T003-T005 and confirm they pass. Then run the gate serially. Fix any failure; stop and ask if still red after two attempts.

**Checkpoint**: every test-side workflow start in `orchestration/` passes `execution_timeout` (check with `grep -rn "start_workflow" orchestration/tests orchestration/webhook_bridge/tests`), and the gate is green.

## Phase 4: User Story 3 (P2) - One count command

The command is already in quickstart.md (research R8).

- [X] T011 [US3] Run the quickstart count command twice in a row with no suite run in between, and confirm both runs print the same IDs.

## Phase 5: Polish and proof

- [X] T012 Live check V1 (quickstart.md): count, run the orchestration suite, count again. Record the numbers and the suite time (SC-001, SC-004).
- [X] T013 Live check V2 (quickstart.md): kill the python process running pytest mid-test, count, wait 2 min 30 s, count again, and `temporal workflow describe` one new ID, which must show `TimedOut` (SC-002).
- [X] T014 Run `py-codereviewer` on the diff. Fix confirmed findings and re-run once; record rejected findings and the reason in research.md.
- [X] T015 Write the V1/V2/V3 results into the quickstart.md "Results" table, tick this file, and commit (`feat(014): …` for the tests, `docs(014): …` for the spec dir).

## Dependencies

- T001 → T002 → T003-T005 (tests) → T006-T009 (fix) → T010 (gate) → T011-T013 (live checks) → T014 → T015.
- US1 and US2 share files and land together. US3 needs only quickstart.md and the stack.

## Parallel opportunities

- T004 and T005 are different files; so are T007, T008 and T009. Edits can be parallel. Test runs must stay serial.

## Implementation strategy

One small change: the time limit and the cleanup in four test modules. No MVP split. Prove it with the gate and with live checks V1 and V2, then stop for the operator before any push or PR.
