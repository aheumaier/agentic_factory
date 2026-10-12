# Research: Test Suite Leaves No Running Temporal Workflows

**Feature**: 014-test-workflow-cleanup | **Date**: 2026-10-12

**Usage Constraint (binding, from 009 and 011):** internal, single-operator use only. The seats in the pool belong to the operator, and the pipeline and its seat pool are never offered to third parties. This feature changes only tests.

## R1. Which time limit: `execution_timeout`, not `run_timeout`

- **Decision**: Pass `execution_timeout=TEST_WORKFLOW_TIMEOUT` to every test-side `start_workflow`.
- **Rationale**: `CredentialPoolWorkflow` calls `workflow.continue_as_new` (`orchestration/workflows/credential_pool.py`). Temporal's `run_timeout` covers one run, so a restarted pool would get a fresh limit each time and could run for good. `execution_timeout` covers the whole chain of runs (FR-001, US2 scenario 4). A workflow that hits it ends with status TimedOut; no code in the workflow runs, so no workflow change is needed.
- **Alternatives considered**: (a) `run_timeout`: rejected, see above. (b) `task_timeout`: limits one workflow task, not the workflow. (c) Teaching the workflows themselves to give up: production change, out of scope (FR-010).

## R2. The value: 2 minutes

- **Decision**: `TEST_WORKFLOW_TIMEOUT = timedelta(minutes=2)`.
- **Rationale**: pytest-timeout ends each test after 60 s (`orchestration/pyproject.toml`, `timeout = 60`). A limit longer than that never ends a workflow while its test is still allowed to run (US2 scenario 3). 2 minutes gives a 60 s margin for a slow server and still clears a killed run's leftovers within a few minutes (FR-002, SC-002).
- **Alternatives considered**: 90 s (too thin a margin over 60 s); 5 or 10 minutes (leftovers of a killed run linger longer for no gain).

## R3. Where the constant lives

- **Decision**: A new module `orchestration/tests/_workflow_limits.py` with only the constant. Both test packages import it as `from tests._workflow_limits import TEST_WORKFLOW_TIMEOUT`.
- **Rationale**: One shared value (FR-002). `orchestration/` has no `__init__.py`, while `orchestration/tests/` and `orchestration/webhook_bridge/` are packages, so pytest's rootdir-based import puts `orchestration/` on `sys.path`. That is how the tests already import `activities`, `workflows.*` and `webhook_bridge.*`. The leading underscore keeps pytest from collecting it.
- **Alternatives considered**: (a) A conftest fixture: FR-009 leaves conftest to feature 012, and a constant needs no fixture. (b) Repeating the literal in 4 files: four places to keep in sync.

## R4. Ending the pipeline workflow in `_harness`

- **Decision**: `_harness` in `test_pipeline_workflow.py` ends `pipeline-workflow-test-<run>` in its `finally`, by ID, through `client.get_workflow_handle(...).terminate()` inside `contextlib.suppress(Exception)`. It ends the pipeline workflow first, then the pool, each in its own `suppress` block, both inside `async with Worker` (architect A4). The ID comes from one helper, `_pipeline_id(run_id)`, used by both `_start` and `_harness`, so a rename can't silently turn the cleanup into a no-op (architect A3).
- **Rationale**: The ID is fixed by the run ID, so the cleanup needs no handle from the test body (FR-003, FR-007). `get_workflow_handle(id)` terminates the latest run of that ID; that is safe only because every ID carries a fresh `uuid4().hex[:8]`, so it can never reach another test's or the operator's workflow (FR-007). Terminating a workflow that doesn't exist or already finished raises; suppressing it keeps the test's own error visible (FR-006). The same idiom (`with contextlib.suppress(Exception):  # best-effort cleanup only`) is already used in these files.
- **Alternatives considered**: Yield the handle from `_harness` and let each test end it: seven call sites to keep right, and a test that fails before it holds the handle still leaks.

## R5. One start path in `test_pipeline_workflow.py`

- **Decision**: Replace the 7 inline `client.start_workflow(AgentPipelineWorkflow.run, …)` calls with the existing `_start(client, run_id)`, and give `_start` the limit.
- **Rationale**: The inline calls are identical to `_start` (same args, ID and task queue). One start path means one place for the limit, and a new test can't forget it.
- **Alternatives considered**: Adding the keyword to all 8 call sites: same effect, eight places to keep in sync.

## R6. The bridge end-to-end tests: limit without a production change

- **Decision**: In `test_e2e_pipeline_gate.py`, replace `start_workflow` on the test's own `Client` instance through `monkeypatch.setattr(client, "start_workflow", functools.partial(client.start_workflow, execution_timeout=TEST_WORKFLOW_TIMEOUT))`. The `finally` ends the workflow through `client.get_workflow_handle(wf_id)`, whether or not `handle` was set.
- **Rationale**: These tests start the workflow through the bridge's production `temporal_client.start_run`, which calls `client.start_workflow` on the client the test passed to `BridgeApp`. Patching that one instance gives the limit to this test's workflow only, leaves `start_run` unchanged (FR-005), and `monkeypatch` undoes it when the test ends. `temporalio.client.Client` has no `__slots__`, so an instance attribute is allowed. A keyword given to a `functools.partial` can still be overridden by the caller, so if `start_run` ever sets its own limit, that one wins. `wf_id` is computed before anything runs, so terminate-by-ID covers a failure between the start and the handle (FR-004).
- **Alternatives considered**: (a) An `execution_timeout` parameter on `start_run`: production change, rejected by FR-005. (b) Patching `Client.start_workflow` on the class: affects every client in the process, and any other test running in it.

## R7. How the tests prove it (FR-008)

- **Decision**:
  - A new test in `test_pipeline_workflow.py` enters `_harness` with one plan result (`_stub_activities(calls, [_plan_result()])`), starts the pipeline workflow with `_start`, waits until it is parked at the plan decision (`_wait_plan_parked(handle, 1)`), raises a sentinel error, and catches it with `pytest.raises`. Parked, the workflow can only end by being terminated, so the check is not timing-dependent (architect A2). It then checks that `(await handle.describe()).status` is `WorkflowExecutionStatus.TERMINATED`, and that both the pipeline workflow and the pool record a 2-minute limit.
  - The recorded limit is read as `(await handle.describe()).raw_description.execution_config.workflow_execution_timeout.ToTimedelta()`. The raw value is a protobuf `Duration`; comparing it to a `timedelta` with `==` is always false (architect A1, checked in the venv).
  - The bridge integration and end-to-end tests check the recorded limit of their own workflow the same way, with one assertion each.
- **Rationale**: Reading the server's own execution config shows what Temporal itself will enforce, not what the test meant to pass. Raising inside `_harness` is the exact leak mode 1 from the spec. The sentinel test needs no worker progress, so it is fast. Written first, it fails on today's code (the pipeline workflow stays Running and has no limit).
- **Alternatives considered**: Waiting 2 minutes for a timeout in a test: too slow for the suite, and covered by the live check V2 in `quickstart.md` instead.

- **Deviation in the build (2026-10-12)**: the plan put only the constant in `orchestration/tests/_workflow_limits.py`. The build also put the read-back there, as `recorded_limit(handle)`, because three test files need the same `.ToTimedelta()` read and three copies could drift.

## R8. A count command that gives the same answer every time (US3)

- **Decision**:

  ```sh
  temporal workflow list --query 'ExecutionStatus="Running"' --limit 1000 -o jsonl \
    | jq -r '.execution.workflowId' | grep -E -- '-test-|^pipeline/owner/' | sort
  ```

  `wc -l` on the same pipe gives the number.
- **Rationale**: Earlier ad-hoc counts on 2026-10-12 gave 4, 5 and 10 for the same server. This one reads exact IDs (JSON, not the table), has a limit far above the number of workflows, and matches only test ID shapes. The operator's `credential-pool` has neither `-test-` nor the `pipeline/owner/` prefix, so it is never counted. Run twice in a row on 2026-10-12 it printed the same 8 IDs both times.
- **Finding**: the true baseline on 2026-10-12 is **8** leaked workflows, not 4. The 4 the earlier count missed date from 2026-10-11 (`fe4bd182` at 09:58 UTC, `a108bda1` at 10:15 UTC; a pool and a pipeline workflow each). `spec.md` is corrected.

## R9. Overlap with feature 012 (peer session `012-dev-harness-followups-71`, 2026-10-12)

- **Exchange**: Asked 012 what it will change in the 4 shared test modules and who lands first. Answer: 014 lands first and 012 rebases. 012 adds `orchestration/conftest.py` (an autouse fixture that wraps `Client.connect` and requires a `temporal` mark), `test_temporal_marker_guard.py`, and the missing marks (its T050).
- **Consequence for 014**: no marks, no new `Client.connect`, no conftest (FR-009). The new FR-008 test reuses `_connect_or_skip` and lives in a module that already has `pytestmark = pytest.mark.temporal`, so 012's guard accepts it without a change. 014 will message 012 when `main` moves.

## R10. Handoff file not edited

The handoff prompt asks for the three rulings to be written into its "Decisions" section. This session runs in the 014 worktree, and the handoff file is in the shared checkout's untracked `.handoff/`; the edit was blocked there. It was not worked around. The rulings are recorded in `spec.md` Clarifications instead: 1 = (b), 2 = (a), 3 = not applicable. The operator can copy them into the handoff file.

## R11. Architect review of plan.md

`senior-architect-reviewer` reviewed plan.md, spec, research, data-model and quickstart against the code and temporalio 1.32 on 2026-10-12. Verdict: the design is sound; `execution_timeout`, the 2-minute value, the `tests._workflow_limits` import (no clash with the repo-root `tests/`, which is not a package) and the instance-level patch reaching `start_run` (`server.py` → `temporal_client.start_run` → `client.start_workflow`) were all confirmed. No test sets its own `pytest.mark.timeout`, and no workflow start was missed. All findings accepted:

| ID | Severity | Finding | What was done |
|---|---|---|---|
| A1 | Medium | Comparing the recorded protobuf `Duration` to a `timedelta` with `==` is always false, so the first test could never pass | R7: read `describe().raw_description.execution_config.workflow_execution_timeout.ToTimedelta()` |
| A2 | Medium | The sentinel test is timing-dependent if the workflow can end on its own before the error | R7: one plan result, `_wait_plan_parked(handle, 1)`, then raise |
| A3 | Low | The pipeline ID would be built in two places and the suppressed terminate hides a mismatch | R4: one `_pipeline_id(run_id)` helper |
| A4 | Low | Terminate order not stated | R4: pipeline first, then pool, separate `suppress` blocks, inside `async with Worker` |
| A5 | Low | Quickstart V2 can kill `uv` and leave the pytest child running its cleanups, passing without testing the limit | quickstart V2: kill the python process running pytest; a `TimedOut` status is required |
| A6 | Low | pytest-timeout turns off under a debugger; the 2-minute limit doesn't | comment on `TEST_WORKFLOW_TIMEOUT` |

Notes from the review, no change needed here:
- When pytest-timeout fires, whether a `finally` still runs depends on where the alarm lands (not reproduced). The 2-minute limit is the backstop either way, which is why every workflow gets it (FR-001).
- `from tests....` relies on pytest's default `prepend` import mode. Feature 012 is told this with the "main moved" message, since its conftest could change the import mode.
- Outside this change: `test_integration.py` uses a fixed shared task queue, and four copies of `_connect_or_skip` remain; 012's conftest is the place to merge them.

## R12. Code review of the build

`py-codereviewer` reviewed the 5 changed test files against spec, plan, research and tasks on 2026-10-12, with Temporal running, so the new assertions ran against a live server (271 and 195 passed, ruff clean). Verdict: approve, no defects. It confirmed that the instance-level patch reaches `start_run`, that all 4 live test starts carry the limit, that every cleanup is by a uuid-based ID, and that a suppressed terminate can't hide the test's own error. Two notes, neither a defect:

| Note | What was done |
|---|---|
| The `tests._workflow_limits` import in `test_e2e_pipeline_gate.py` sits after the `sys.path.insert` for `harness/pm-agent` and could move to the top import block | Not changed. It only matters if `harness/pm-agent/` ever gets a `tests/` package, which it has none of today; feature 012's conftest is the natural place to revisit import order |
| `monkeypatch` undo on an instance leaves the bound method in `client.__dict__` | Not changed: each client lives only for its own test |
