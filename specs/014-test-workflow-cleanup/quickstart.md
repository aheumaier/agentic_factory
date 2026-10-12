# Quickstart: Test Suite Leaves No Running Temporal Workflows

**Feature**: 014-test-workflow-cleanup | **Date**: 2026-10-12

**Usage Constraint (binding, from 009 and 011):** internal, single-operator use only. The seats in the pool belong to the operator, and the pipeline and its seat pool are never offered to third parties. This feature changes only tests.

The test workflows and their ID shapes are listed in [data-model.md](data-model.md). This page is the run guide.

## Prerequisites

- The local stack runs: `make up` (Temporal on `localhost:7233`).
- The `temporal` CLI and `jq` are on `PATH`.

## The count command

Prints every running workflow whose ID contains `-test-` or starts with `pipeline/owner/`, one per line, sorted. The operator's real pool, `credential-pool`, is never matched.

```sh
temporal workflow list --query 'ExecutionStatus="Running"' --limit 1000 -o jsonl \
  | jq -r '.execution.workflowId' | grep -E -- '-test-|^pipeline/owner/' | sort
```

Add `| wc -l` for the number. Run it twice in a row: both runs must print the same IDs.

## V1: A full suite run leaves nothing running (SC-001)

1. Count. Write down the number (`before`).
2. Run the orchestration suite:
   ```sh
   cd orchestration && uv run --locked pytest -q
   ```
3. Count again (`after`).

**Pass**: `after` ≤ `before`.

## V2: A killed run cleans up after itself (SC-002)

1. Count (`before`).
2. Start the suite in the background and kill it hard while a live-Temporal test runs, so no cleanup step runs. Kill the **python process running pytest**, not the `uv` parent: killing `uv` leaves the pytest child running, and it then runs every cleanup step. For example `kill -9 $(pgrep -f 'python.*pytest')`, about 10 s after the first live test starts.
3. Count right away. It should be higher than `before`: those are the killed run's workflows. Note their IDs.
4. Wait 2 minutes 30 seconds (the 2-minute limit plus margin), then count again (`after`).
5. Run `temporal workflow describe -w <id>` on one of step 3's new IDs.

**Pass**: `after` = `before`, and step 5 shows status `TimedOut` (not `Terminated`). Only `TimedOut` proves the limit ended it rather than a cleanup step.

When debugging a live test (`--pdb`, a debugger), pytest-timeout turns itself off but the 2-minute workflow limit does not. Raise `TEST_WORKFLOW_TIMEOUT` locally for a longer debugging session.

## V3: Gate (SC-003, SC-004)

From the worktree root, one after the other (live-Temporal tests time out when suites run at the same time):

```sh
uv run --locked pytest tests/ -q
(cd orchestration && uv run --locked pytest -q)
uv run --locked ruff check .
```

**Pass**: 0 failures, 0 ruff findings, and the orchestration suite's time within 10% of before.

## Leftovers from before this feature

This feature stops new leaks. It does not end the 8 test workflows that already leaked before it (baseline below), nor `pipeline-workflow-test-efde5375`, which the red run of the new pipeline test (T003) left on 2026-10-12, before the fix: 9 in all. A 10th, `pipeline-workflow-test-2bf7f1e6`, started 2026-10-12 18:11 local after V1-V3 had passed. It records no time limit, and its pool was terminated after 10 s, so it came from a checkout without this fix, not from this suite. Ending them is the operator's call, for example with `temporal workflow terminate -w <id>` for each ID the count prints. Never terminate `credential-pool` or any ID the count does not print.

## Results

*Filled in on 2026-10-12 after the live checks ran.*

| Check | When | Count before | Count after | Result |
|---|---|---|---|---|
| Baseline | 2026-10-12 | 8 | – | 4 pairs, all from killed runs (see spec.md "Why") |
| V1 | 2026-10-12 | 9 | 9 | Pass: the same 9 pre-existing IDs before and after. Orchestration suite 195 passed in 24.97 s (26.88 s before the fix, SC-004) |
| V2 | 2026-10-12 | 9 | 9 | Pass: python and `uv` killed with `kill -9` at 18:01:25, 6 s into `test_pipeline_workflow.py` + `test_credential_pool.py`. Right after the kill: 11 (`credential-pool-test-457337ce`, `pipeline-workflow-test-457337ce`). After waiting until 18:03:56: 9. `describe` on both: status `TIMED_OUT`, limit `120s`, closed 16:03:25 UTC (18:03:25 local) |
| V3 | 2026-10-12 | – | – | Pass: root suite 271 passed in 26.38 s; orchestration suite 195 passed in 25.16 s (26.88 s before the fix, within 10%); `ruff check .` all checks passed |
