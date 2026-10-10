# Quickstart: validating Gate Decision Core

Three scenarios prove the feature: two are automated, one is a manual stack
check. Expected behaviour is defined in the contracts; this guide only says
how to run each check and what a pass looks like.

## Prerequisites

- `uv` installed; dependencies synced with `cd orchestration && uv sync`.
- For the in-process tests, either a `temporal` CLI on `PATH`
  (`brew install temporal`) or network access for a one-time CLI download
  by the SDK. To point at a specific binary, set `TEMPORAL_CLI_PATH`.
- Scenarios A and B need no Docker and no `make up`. Scenario C needs
  Docker.

## A. GitHub behaviour is unchanged (US3, FR-015, SC-003)

```bash
git diff --stat main -- orchestration/webhook_bridge/tests/ ':!orchestration/webhook_bridge/tests/test_core_*' ':!orchestration/webhook_bridge/tests/test_server_allowlist_passthrough.py'
cd orchestration && uv run pytest webhook_bridge/tests -q
```

**Pass**:

- The `git diff` prints nothing: no pre-existing bridge test file changed.
- Every test passes. The real-server tests (`test_integration.py`,
  `test_e2e_pipeline_gate.py`) skip without `make up`, exactly as before.
  Run them once with the stack up (scenario C) to see them pass.
- New core tests pass, including:
  - `test_core_gate.py`: the plan gate audits as `signal_issued`, while PM
    and security audit as `signal_issued_no_handler`. The core makes no
    reaction call; the shim renders 👀.
  - `test_core_decisions.py`: a refusal raised from `result()` maps to
    `refused`, with the reason and attribution from the `ApplicationError`.
    An RPC timeout maps to `worker_unavailable`.

## B. First-valid-wins, validated path, and status on the real workflow (US1, US2, US3; FR-021)

```bash
cd orchestration && uv run pytest tests/test_plan_gate.py tests/test_plan_gate_workflow.py tests/test_decision_core_e2e.py -v
```

**Pass**: every test below passes against the real `AgentPipelineWorkflow`
(stubbed activities, `WorkflowEnvironment.start_local()`), with no Docker.

| FR-021 case | Look for |
|---|---|
| same-task signal + signal | first applied; second in `status().ignored_signals` as `duplicate`; both `WorkflowExecutionSignaled` events precede one `WorkflowTaskStarted` |
| same-task update + update | first `accepted`; second `refused/already_resolved` with the first's `resolved_by` / `via` |
| same-task signal + update, both submission orders | **the signal wins in both** (it comes first in the run's recorded order, research R1); the update is `refused/already_resolved` |
| empty-feedback `plan_rejected` signal | window not released; `ignored_signals[-1].reason == "malformed"` |
| already resolved, sequential | after a GitHub-style approval releases attempt N, a validated decision for attempt N → `refused/already_resolved`, carrying the winner's `resolved_by` / `via` (`unknown` / `unknown` for a legacy signal, or X / `github` when the winner came through the validated path) |
| stale attempt | update naming attempt N while N+1 is open → `refused/stale_attempt`; attempt N+1 still open |
| no window | decision during `planning` → `refused/no_window_open`; signal → ignored `no_window_open`; the next window is not released |
| legacy no-arg signals | `signal("plan_approved")` releases the window; `last_applied_decision.resolved_by == via == "unknown"` |
| status while blocked | `stage == "awaiting_plan_decision"`, `open_window.attempt`, `budgets.plan`, `pr_url` correct; `fetch_history()` length identical before and after the query |
| `worker_unavailable` (decision and status) | with no worker, both core ops return `worker_unavailable` in < 10 s (1 s test timeout). Starting a worker afterwards and resubmitting the same `Origin` applies **at most one** decision |
| budgets unchanged (FR-011) | a reject → approve run charges 1; duplicates and refusals charge 0. The existing `tests/test_pipeline_workflow.py` scenarios still pass with `make up` |

## C. Pinned local stack (US4, FR-020, SC-007): manual

**C1: clean start, twice.**

```bash
docker compose down -v          # destroys local Temporal/Langfuse volumes: do this only on a disposable machine state
make up && docker compose ps    # temporal-schema-setup and temporal-namespace-setup show "Exited (0)"
temporal operator cluster system | grep -i version     # server version 1.29.7
temporal operator namespace describe default
temporal operator search-attribute list | grep -E "TargetRepo|PRNumber"
make down && make up            # repeat: same version, setup services exit 0 again
```

**Pass**: both runs report server **1.29.7** (≥1.29.3). The `default`
namespace exists, and `TargetRepo` (Keyword) and `PRNumber` (Int) are
listed with no manual step.

**C2: existing volume from `auto-setup:latest`.**

1. Before this change lands, bring the old stack up once so the
   `temporal-pg-data` volume holds 1.29.3's schema.
2. Check out this change and run `make up`. **Do not** pass `-v` to
   `down`.
3. Run `docker compose logs temporal-schema-setup temporal`.

**Pass**: no downgrade or schema error. `update-schema` reports the schema
as already current (or applies only forward 1.29.x patches). The server
starts, and the earlier workflow history is still visible in the UI at
`localhost:8080`.

**C3: the worker and bridge connect.**

```bash
make worker                     # connects to localhost:7233, polls agent-factory-pipeline
make bridge                     # needs .env per specs/002-webhook-trigger-bridge/quickstart.md
cd orchestration && uv run pytest webhook_bridge/tests/test_integration.py tests/test_pipeline_workflow.py -q
```

**Pass**: both processes start without connection errors. The real-server
tests that skipped in scenario A now pass. The 002 quickstart's
search-attribute step is now automatic, and the quickstart says so.

## Rollback

- Revert `docker-compose.yml` to go back to `auto-setup:latest`. The schema
  is unchanged within 1.29.x, so the volume stays usable.
- Workflow runs started under the new code keep their
  `plan-decision-window-v1` marker. Reverting the workflow code while such
  a run is in flight would break its replay. Per 002 FR-016, only
  disposable repos run today, so terminate those runs first.
