# Data Model: Test Suite Leaves No Running Temporal Workflows

**Feature**: 014-test-workflow-cleanup | **Date**: 2026-10-12

**Usage Constraint (binding, from 009 and 011):** internal, single-operator use only. This feature changes only tests.

There is no stored data. The only "entities" are the workflows the tests start on the local Temporal server.

## Test workflow

A workflow that a test starts. `<run>` is the test's own random 8-hex run ID (`uuid.uuid4().hex[:8]`), so two suite runs never share an ID, and a test's cleanup only reaches its own workflows (FR-007).

| Test module | Workflow type | ID shape | Started by | Ended by (cleanup) |
|---|---|---|---|---|
| `orchestration/tests/test_pipeline_workflow.py` | `CredentialPoolWorkflow` | `credential-pool-test-<run>` | `_harness` | `_harness` `finally` (exists) |
| `orchestration/tests/test_pipeline_workflow.py` | `AgentPipelineWorkflow` | `pipeline-workflow-test-<run>` | `_start` | `_harness` `finally`, by ID (**new**) |
| `orchestration/tests/test_credential_pool.py` | `CredentialPoolWorkflow` | `credential-pool-test-<run>` | `_running_pool` | `_running_pool` `finally` (exists) |
| `orchestration/webhook_bridge/tests/test_integration.py` | `_IntegrationProbeWorkflow` | `pipeline/owner/integration-test-repo-<run>/probe-<run>/v1` | the test body | the test's `finally` (exists) |
| `orchestration/webhook_bridge/tests/test_e2e_pipeline_gate.py` | `AgentPipelineWorkflow` (test stub) | `pipeline/owner/repo/demo-widget-<run>/v1` | the bridge's production `start_run` | the test's `finally`, by `wf_id` (**changed**: no longer only when `handle` is set) |

Every row gets `execution_timeout = TEST_WORKFLOW_TIMEOUT` (2 minutes) at start (FR-001, FR-002).

The quickstart count matches exactly these shapes: an ID that contains `-test-` or starts with `pipeline/owner/`. The operator's real pool, `credential-pool`, matches neither.

## States

```text
             start (with execution_timeout = 2 min)
                          │
                          ▼
                       Running ──── test passes ─────────────► Completed / Failed
                          │
                          ├── test cleanup step (terminate) ──► Terminated
                          │
                          └── process killed, 2 min passed ───► TimedOut   (Temporal enforces it)
```

- A test that checks the workflow's result still sees Completed or Failed: no passing test runs a workflow for more than 60 s (pytest-timeout), far under the 2-minute limit.
- Terminating a workflow that is already closed, or was never started, raises in the client. The cleanup suppresses that (FR-006).
- `CredentialPoolWorkflow` restarts itself with continue-as-new. The 2-minute limit covers the whole chain, because it is an execution limit, not a per-run one.
