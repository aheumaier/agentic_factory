# Implementation Plan: Test Suite Leaves No Running Temporal Workflows

**Branch**: `014-test-workflow-cleanup` | **Date**: 2026-10-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/014-test-workflow-cleanup/spec.md`

## Usage Constraint *(binding, restated from 009 and 011)*

This pipeline is for **internal, single-operator use only**. The seats in the pool belong to the operator who runs it. The pipeline and its seat pool are never offered as a product or service to third parties. This feature changes only tests and does not change this constraint.

## Summary

Every workflow that an orchestration test starts on the live Temporal server gets a whole-run time limit of 2 minutes, which Temporal enforces even if the test process dies. In addition, each test's cleanup step ends the workflows the test started, by their known ID, whether or not the test got far enough to hold a handle.

Technical approach (details and alternatives in [research.md](research.md)):

1. One shared constant, `TEST_WORKFLOW_TIMEOUT = timedelta(minutes=2)`, in a new module `orchestration/tests/_workflow_limits.py`. It is passed as `execution_timeout` (not `run_timeout`), because `CredentialPoolWorkflow` calls `continue_as_new` and only `execution_timeout` spans the whole chain.
2. `test_pipeline_workflow.py`:
   - `_harness` starts the pool with the limit and, in its `finally`, ends `pipeline-workflow-test-<run>` by ID first, then the pool, each best effort in its own block. One helper, `_pipeline_id(run_id)`, builds the ID for `_start` and `_harness`.
   - The 7 inline `AgentPipelineWorkflow` starts are replaced by the existing `_start` helper, which gets the limit. One start path, one place for the limit.
3. `test_credential_pool.py`: `_running_pool` starts the pool with the limit. Its `finally` already ends it.
4. `webhook_bridge/tests/test_integration.py`: the probe workflow start gets the limit. Its `finally` already ends it.
5. `webhook_bridge/tests/test_e2e_pipeline_gate.py`:
   - The bridge's production `start_run` starts the workflow. The test does not change it. Instead it replaces `start_workflow` on its own `Client` instance with `functools.partial(client.start_workflow, execution_timeout=TEST_WORKFLOW_TIMEOUT)`, through `monkeypatch`, so the change is undone when the test ends.
   - The `finally` ends the workflow by `wf_id` through `client.get_workflow_handle(wf_id)`, not only when `handle` was set.
6. Tests first (FR-008), in `test_pipeline_workflow.py`:
   - One test starts the pipeline workflow inside `_harness`, waits until it is parked at the plan decision, raises a sentinel error, then checks that Temporal reports it as terminated.
   - The same test reads the recorded limit of the pipeline workflow and of the pool from `describe()` (`execution_config.workflow_execution_timeout`, converted with `.ToTimedelta()`), and checks that it is 2 minutes.
   - The e2e and integration starts are checked the same way, by reading the recorded limit inside the existing tests (one assertion each).

No production code changes. No new Temporal connection, no `temporal` mark, no conftest (feature 012 owns those).

## Technical Context

**Language/Version**: Python ≥ 3.11 (`orchestration/pyproject.toml` `requires-python`).

**Primary Dependencies**: `temporalio>=1.32.0` (client `start_workflow(execution_timeout=…)`, `WorkflowHandle.terminate()`, `describe()`); `pytest`, `pytest-asyncio`, `pytest-timeout>=2.4.0`.

**Storage**: N/A. The only state is the workflows on the local Temporal dev server.

**Testing**: `cd orchestration && uv run --locked pytest -q` (the live tests skip without `make up`); the repo-root suite and ruff as the gate.

**Target Platform**: the operator's machine, local Temporal dev server on `localhost:7233` (docker-compose).

**Project Type**: test infrastructure inside an existing Python service (`orchestration/`).

**Performance Goals**: the orchestration suite takes no more than 10% longer than before (SC-004). Terminating a workflow is one RPC per test.

**Constraints**:
- pytest-timeout is 60 s per test (`orchestration/pyproject.toml`), so the workflow limit must be longer (2 min).
- The limit must cover `continue_as_new` (FR-001), so `execution_timeout`.
- No production change, so the e2e limit is applied test-side (FR-005).
- No new `Client.connect`, no marks, no conftest (FR-009; feature 012 lands after 014 and adds those).
- Don't rename the patch IDs `seat-pool-v1`, `architect-seat-pool-v1`, `seat-pool-wait-v1` (FR-010). This feature doesn't touch workflow code at all.

**Scale/Scope**: 4 test modules and 1 new 5-line module; about 40 changed lines.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is still the unfilled template, so it has no gates. The repo's binding rules come from `CLAUDE.md` instead:

| Rule | Status |
|---|---|
| Spec Kit is the only way to plan a feature | Pass: `specs/014-test-workflow-cleanup/` with spec, plan, tasks |
| AF-SPEC: edits under `orchestration/` need branch `NNN-slug` and `specs/NNN-*/tasks.md` | Pass once `tasks.md` exists (before any test edit) |
| AF-COMMIT: ruff and both suites green before a commit | Planned: gate run serially before each commit |
| AF-SECRET: never read `.env` | Pass: nothing here reads it |
| Model calls through LiteLLM / seat rules | N/A: no model call |
| Registry is the portability boundary | N/A: no registry change |
| Usage Constraint (009/011) | Kept in spec, plan and quickstart |

Re-check after Phase 1 design: unchanged, all pass.

## Project Structure

### Documentation (this feature)

```text
specs/014-test-workflow-cleanup/
├── spec.md
├── plan.md              # this file
├── research.md          # decisions, 012 exchange, architect review findings (R11)
├── data-model.md        # test workflow ID shapes and states
├── quickstart.md        # count command, live checks V1/V2, results
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks output
```

No `contracts/`: the change is internal to the test suites and exposes no interface.

### Source Code (repository root)

```text
orchestration/
├── tests/
│   ├── _workflow_limits.py          # NEW: TEST_WORKFLOW_TIMEOUT
│   ├── test_pipeline_workflow.py    # _harness ends the pipeline wf; _start used everywhere; new FR-008 test
│   └── test_credential_pool.py      # _running_pool start gets the limit
└── webhook_bridge/tests/
    ├── test_integration.py          # probe start gets the limit
    └── test_e2e_pipeline_gate.py    # instance-level start_workflow partial; terminate by wf_id
```

**Structure Decision**: the constant lives in a plain module under `orchestration/tests/`, imported as `from tests._workflow_limits import TEST_WORKFLOW_TIMEOUT` by both test packages. A conftest would also work, but FR-009 leaves conftest to feature 012, and a fixture is not needed for a constant.

## Complexity Tracking

No violations to justify.
