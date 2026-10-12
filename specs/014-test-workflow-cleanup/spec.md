# Feature Specification: Test Suite Leaves No Running Temporal Workflows

**Feature Branch**: `014-test-workflow-cleanup`

**Created**: 2026-10-12

**Status**: Draft

**Input**: User description: "The orchestration test suite must stop leaving `-test-` workflows running in Temporal. Terminate each workflow in the test helper; give each test workflow a short `execution_timeout`, so Temporal ends it even if the test process dies. Pass check: after a full suite run, and after a run killed mid-test, no `-test-` workflow is still running once the timeout has passed. Out of scope: 012's `temporal` mark and conftest, the dogfood run's blockers, and the cleanup of workflows that already leaked."

Design input: the handoff prompt of 2026-10-12 (`.handoff/2026-10-12-014-leaked-test-workflows-PROMPT.md`, untracked) and Part B of `.handoff/2026-10-11-dogfood-next-PROMPT.md` (untracked).

## Usage Constraint *(binding, restated from 009 and 011)*

This pipeline is for **internal, single-operator use only**:
- The subscription seats in the pool belong to the operator who runs this pipeline.
- The pipeline and its seat pool are never offered as a product or service to third parties.
- Seat login or rate limits are never exposed to anyone else's product.

This feature changes only tests. It adds no capability and does not change this constraint.

## Clarifications

### Session 2026-10-12

- Ruling 1 (branch protection on `main`, from 013 quickstart "V0 step 2"): **(b)**, a ruleset that requires 1 approval, with the operator as the only bypass actor. The operator applies it in GitHub settings; no code in this feature does. *Operator, 2026-10-12.*
- Ruling 2 (how 014 is built): **(a)**, by hand with `/speckit-implement`, not by a dogfood pipeline run. *Operator, 2026-10-12.*
- Ruling 3 (which repo a dogfood run's Register writes to): not applicable, because Ruling 2 is (a).
- Overlap with feature 012 (peer session, 2026-10-12): 014 lands first and 012 rebases. 012 adds the `temporal` mark guard (`orchestration/conftest.py`) and the missing marks. 014 adds no marks and no new Temporal client connection.

## Why

The orchestration tests start real workflows on the operator's local Temporal server. Some of them are never ended, and so they keep running for good. On 2026-10-12, before this feature, 8 test workflows were still running from earlier test runs (counted with the quickstart's count command; an earlier ad-hoc count found only 4). They come in 4 pairs, one pair per pipeline test run, each a pipeline workflow and its per-test credential pool with the same run ID:

- `pipeline-workflow-test-fe4bd182` and `credential-pool-test-fe4bd182` (2026-10-11);
- `pipeline-workflow-test-a108bda1` and `credential-pool-test-a108bda1` (2026-10-11);
- `pipeline-workflow-test-c501d81e` and `credential-pool-test-c501d81e` (2026-10-11);
- `pipeline-workflow-test-78081496` and `credential-pool-test-78081496` (2026-10-12).

The pipeline test helper ends the pool in its cleanup step. That the pool leaked too means the cleanup step never ran: the test process was killed.

Every leaked workflow clutters the operator's workflow list, next to real pipeline runs. A leaked pipeline workflow waits on its signals for good. It holds no seat or sandbox today, but it hides real runs and makes "is anything still running?" impossible to answer at a glance.

There are three ways a test workflow leaks today:

1. **Never ended.** The pipeline workflow tests end only the per-test credential pool, never the pipeline workflow itself. A test that fails before the workflow finishes leaves the workflow waiting for a signal for good. For example, a "plan parked" check times out, or the per-test time limit (60 s) stops the test. When the per-test time limit stops a test, whether its cleanup step still runs depends on where the test was stopped, so the cleanup step alone is not enough; the workflow time limit (US2) covers that case.
2. **Killed test process.** The credential-pool tests, the bridge integration test and the bridge end-to-end tests end their workflows in a cleanup step. A test process that is killed hard skips every cleanup step, so those workflows run for good. Examples: a kill signal, a hook that times out, or Ctrl+C pressed twice.
3. **Cleanup that depends on a late step.** The bridge end-to-end tests start their workflow through the bridge's real start path. Their IDs look like `pipeline/owner/repo/demo-widget-<run>/v1`, with no `-test-` in them. The cleanup ends the workflow only if the test got far enough to fetch its handle. A failure between the start and that step leaks it.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A suite run leaves nothing running (Priority: P1)

The operator runs the orchestration suite, which passes or fails. Afterwards, no workflow that the suite started is still running.

**Why this priority**: This is the normal case. Every pipeline test that fails before its workflow finishes leaks that workflow today, even when the test process is not killed.

**Independent Test**: Count the running test workflows, run the orchestration suite, then count again. The second count is not higher than the first.

**Acceptance Scenarios**:

1. **Given** a pipeline workflow test, **When** it fails before the workflow finishes, **Then** the workflow is ended in the test's cleanup step, and Temporal shows it as terminated, not running.
2. **Given** any test that starts a workflow, **When** the test ends (passed, failed or timed out), **Then** the workflow it started is not running.
3. **Given** a bridge end-to-end test, **When** it fails after the workflow started but before it fetched the handle, **Then** the workflow is still ended, by its known ID.

---

### User Story 2 - A killed suite run cleans up after itself (Priority: P1)

The operator, or a hook, kills a suite run mid-test. No cleanup step runs. A short, fixed time later, Temporal has ended every workflow that the killed run started.

**Why this priority**: A cleanup step can never cover a killed process. Only a time limit that Temporal itself enforces covers it. All 8 baseline leaks came from killed runs: each pool had a cleanup step and still leaked.

**Independent Test**: Start a suite run in the background, kill it mid-test, wait out the time limit, then count running test workflows. The count is back to the count before the run.

**Acceptance Scenarios**:

1. **Given** any workflow a test starts, **When** it is started, **Then** it carries a whole-run time limit that Temporal enforces.
2. **Given** a test process killed while its workflow runs, **When** the time limit has passed, **Then** Temporal shows that workflow as timed out, not running.
3. **Given** the per-test time limit of 60 s, **When** the workflow time limit is chosen, **Then** it is longer than 60 s, so it never ends a workflow while its test is still allowed to run.
4. **Given** a credential-pool workflow that restarts itself as a new run of the same workflow, **When** the time limit is set, **Then** it covers the whole chain of runs, not just the first one.

---

### User Story 3 - The operator can check it with one command (Priority: P2)

The operator has one fixed command that counts running test workflows. It also counts the bridge end-to-end IDs, which have no `-test-` in them.

**Why this priority**: The pass check depends on a count that gives the same answer every time. On 2026-10-12, three ad-hoc counts of the same server gave 4, 5 and 10.

**Independent Test**: Run the command twice with no suite run in between. Both runs print the same number.

**Acceptance Scenarios**:

1. **Given** the quickstart, **When** the operator runs its count command, **Then** it prints the running workflows whose ID contains `-test-` or starts with `pipeline/owner/`, and nothing else.
2. **Given** the operator's real credential pool (`credential-pool`) is running, **When** the count runs, **Then** it is not counted.

### Edge Cases

- A test that never reached its workflow start: ending it by ID finds no workflow. That must not fail the test or hide the test's own error.
- A workflow that already finished: ending it again must not fail the test.
- The Temporal server is not reachable: the tests skip as they do today, and nothing changes.
- A test that checks the workflow's final result must still see the same result. The time limit is far longer than any passing test, so it never cuts a passing run short.
- A test that waits for a workflow to time out on purpose: none exists today. If one is added, it must set its own limit.
- Two suite runs at the same time: each test uses its own random run ID, so one run's cleanup never ends another run's workflow.
- The operator's real workflows: no test cleanup ever ends a workflow that the test did not start. Cleanup works only on IDs built from the test's own run ID.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every workflow that a test in `orchestration/tests/` or `orchestration/webhook_bridge/tests/` starts on the live Temporal server MUST carry a whole-run time limit enforced by Temporal. The limit MUST cover restarts of the same workflow as a new run.
- **FR-002**: That time limit MUST be one shared value, longer than the per-test time limit (60 s) and short enough that a killed run's leftovers are gone within a few minutes. The default is 2 minutes.
- **FR-003**: The pipeline workflow test helper MUST end the pipeline workflow of its test in its cleanup step, by the test's known workflow ID, whether the test passed or failed.
- **FR-004**: The bridge end-to-end tests MUST end their workflow in the cleanup step by its known ID, even when the test failed before it fetched the workflow handle.
- **FR-005**: The bridge end-to-end tests MUST get the FR-001 time limit without any change to the bridge's production start path. The production start path MUST NOT get a time limit from this feature.
- **FR-006**: Cleanup MUST be best effort. Ending a workflow that does not exist or has already finished MUST NOT fail the test or replace the test's own error.
- **FR-007**: Cleanup MUST only end workflows whose ID was built from the test's own run ID. It MUST NOT end any other workflow.
- **FR-008**: Tests MUST prove FR-001 and FR-003: one check reads a test-started workflow's recorded time limit, and one check makes a test fail inside the pipeline helper and then sees the workflow as terminated.
- **FR-009**: This feature MUST NOT add a `temporal` mark, a new Temporal client connection, or a shared test setup file (conftest). Those belong to feature 012.
- **FR-010**: This feature MUST NOT change production code under `orchestration/` outside the test directories, and MUST NOT rename the patch IDs `seat-pool-v1`, `architect-seat-pool-v1` or `seat-pool-wait-v1`.
- **FR-011**: The quickstart MUST record one fixed count command, and the live-check results (before a suite run, after it, and after a killed run once the time limit has passed).

### Key Entities

- **Test workflow**: a workflow started by a test, identified by an ID that contains the test's random run ID. ID shapes: `pipeline-workflow-test-<run>`, `credential-pool-test-<run>`, `pipeline/owner/integration-test-repo-<run>/probe-<run>/v1`, and `pipeline/owner/repo/demo-widget-<run>/v1`.
- **Workflow time limit**: the whole-run limit Temporal enforces on a test workflow. When it passes, the workflow ends as timed out.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After one full orchestration suite run, the number of running test workflows (the quickstart count) is not higher than before the run.
- **SC-002**: After a suite run killed mid-test, and 2 minutes plus 30 seconds later, the count is back to the count before the run.
- **SC-003**: The orchestration suite, the repo-root suite and the linter pass with 0 failures and 0 findings, as before this feature.
- **SC-004**: The orchestration suite takes no more than 10% longer than before this feature.

## Out of Scope

- Feature 012's `temporal` mark guard, its `orchestration/conftest.py`, and the marks it adds.
- The dogfood pipeline run and its blockers (013's SC-001 target PR author, the scratch repo's Register branch, the repo hooks inside the sandbox).
- Time limits on production workflows.
- Ending the workflows that already leaked before this feature. That is the operator's own command; this feature only stops new leaks.

## Assumptions

- The operator's local Temporal server runs (`make up`). Without it, the live tests skip, as today.
- No workflow under test starts a child workflow. If one ever does, its own time limit is a separate concern.
- 2 minutes is enough: no passing test runs a workflow for longer than the 60 s per-test limit.
- A test workflow ending as "timed out" after a killed run is acceptable. Nothing reads those results.
