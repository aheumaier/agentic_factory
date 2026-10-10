# Contract: Bridge core operations and the GitHub adapter

**Package**: `orchestration/webhook_bridge/core/` (new).
**Spec**: FR-013 to FR-019a. Research: R2, R3, R4, R8.

The core is surface-neutral. It takes a command, an actor and an origin,
calls Temporal, emits one audit line, and **returns** an outcome. It never
posts a reaction, a card or a comment (FR-014). Adapters authorize the
actor before calling any core operation, and the core trusts the
`resolved_by` / `via` it is given (FR-019a).

The core does not import the workflow class. It uses the workflow type,
signal, update and query names as strings:

- `"AgentPipelineWorkflow"`;
- `"plan_approved"`, `"plan_rejected"`;
- `"decide_plan"`;
- `"status"`.

## Shared types (`core/commands.py`)

```python
@dataclass(frozen=True)
class RunCommand: ...      # moved from grammar.py unchanged; grammar re-imports it
@dataclass(frozen=True)
class GateCommand: ...     # moved from grammar.py unchanged; grammar re-imports it

@dataclass(frozen=True)
class Origin:
    surface: str           # "github" | "teams" (009)
    delivery_id: str       # X-GitHub-Delivery today; Teams activity.id in 009

    @property
    def dedup_key(self) -> str:      # f"{surface}:{delivery_id}"  (FR-018)
    @property
    def request_id(self) -> str:     # "decide_plan-" + sha256(dedup_key)[:32]  (FR-016, R4)

@dataclass(frozen=True)
class PlanDecisionRequest:
    decision: Literal["approved", "rejected"]
    feedback: str | None
    attempt: int
    resolved_by: str
    via: str
```

`core/policy.py`: `repo_allowed(repo, allowed_repos) -> bool`. This is
`server.py:102`'s normalization (`strip().lower()` membership), moved
verbatim. `server.py` calls it, so GitHub behaviour is unchanged.

## Operations

Every operation takes `allowed_repos` as a **required keyword** (no default)
and returns `repo_not_allowed` before any Temporal call when the repo is not
on the list (FR-019). For `submit_plan_decision` and `get_status` the type
is `Collection[str]`. For `start_run` and `signal_gate` it is
`Collection[str] | None`: `None` is accepted only so the two pinned GitHub
shims can forward their legacy default (see "GitHub adapter" below), and it
means "already enforced by the adapter". Run resolution in all three gate/decision/status operations
is the existing `resolve_gate_target(client, repo, pr_number)`, unchanged.

### `core.runs.start_run(client, repo, pr_number, branch, agent_name, version, *, allowed_repos) -> StartRunResult`

This is today's `temporal_client.start_run` body, unchanged: the same
`start_workflow` call shape and the same `StartRunResult`. Only the
allow-list guard is added.

### `core.gate.signal_gate(client, repo, pr_number, gate, decision, feedback, *, author, comment, allowed_repos) -> GateSignalOutcome`

```python
@dataclass(frozen=True)
class GateSignalOutcome:
    outcome: Literal["signal_issued", "signal_issued_no_handler", "signal_failed", "repo_not_allowed"]
    reason: str
```

- The signal is sent with **exactly** today's call shape:
  - `handle.signal(name)` when feedback is `None`;
  - `handle.signal(name, feedback)` otherwise.
  No attribution payload in 008 (spec Clarification 2026-10-09).
- Outcome per gate (FR-017):
  - `plan` → `signal_issued`;
  - `pm` and `security` → `signal_issued_no_handler` until spec 005.
- If the target is not found or ambiguous, or the signal call raises →
  `signal_failed`, with today's reason strings.
- Emits one audit line, with the same author, comment and reason text as
  today. Only the outcome name changes, and only for the plan gate.

### `core.decisions.submit_plan_decision(client, repo, pr_number, request: PlanDecisionRequest, origin: Origin, *, allowed_repos, timeout=timedelta(seconds=5)) -> DecisionOutcome`

```python
@dataclass(frozen=True)
class DecisionOutcome:
    status: Literal["accepted", "refused", "worker_unavailable", "target_not_found", "repo_not_allowed"]
    reason: str | None = None        # refused: malformed | empty_feedback | no_window_open | stale_attempt | already_resolved
                                     # target_not_found: "no in-flight run for this PR" | "multiple in-flight runs for this PR"
    resolved_by: str | None = None   # set only for refused/already_resolved
    via: str | None = None           # set only for refused/already_resolved
    request_id: str = ""             # origin.request_id, always set
```

Call sequence (research R2). The whole body runs under
`asyncio.timeout(8 s)`, and expiry maps to `worker_unavailable`.

1. Allow-list check, then local shape check. A missing or ill-typed
   `attempt` / `decision` → `refused/malformed`; a `rejected` decision with
   blank feedback → `refused/empty_feedback`. These save an RPC; the
   workflow validator re-checks both and is authoritative.
2. `resolve_gate_target`. No match or several matches →
   `target_not_found`.
3. `upd = await handle.start_update("decide_plan", asdict(request),
   id=origin.request_id, wait_for_stage=WorkflowUpdateStage.ACCEPTED,
   rpc_timeout=timeout)`.
4. **`await upd.result(rpc_timeout=timeout)`**. This step is mandatory:
   `start_update` returns normally even when the validator refused, and
   only `result()` raises the refusal.
   - It returns → `accepted`.
   - `WorkflowUpdateFailedError` with an `ApplicationError` cause →
     `refused`, `reason = cause.type`. For `already_resolved`, take
     `resolved_by` / `via` from `cause.details[0]`.
5. `WorkflowUpdateRPCTimeoutOrCancelledError` at step 3 or 4 →
   `worker_unavailable`.

This operation does **not** consult `DeliveryCache`. Idempotency comes from
`id=origin.request_id`, on the server (research R4).

**`worker_unavailable` is indeterminate.** The run may still apply the
decision once a worker polls. Callers MUST present it as "outcome unknown —
check the run's status", never as "not applied". Resubmitting the same
`origin` can never yield a second decision.

### `core.status.get_status(client, repo, pr_number, *, allowed_repos, timeout=timedelta(seconds=5)) -> StatusOutcome`

```python
@dataclass(frozen=True)
class StatusOutcome:
    status: Literal["ok", "target_not_found", "worker_unavailable", "repo_not_allowed"]
    snapshot: dict | None = None     # contracts/status-snapshot.md, when ok
    reason: str | None = None
```

- The run is resolved as above, then queried with
  `await handle.query("status", rpc_timeout=timeout)`, under
  `asyncio.timeout(8 s)`.
- `RPCError` with status `CANCELLED` / `DEADLINE_EXCEEDED`, or the outer
  timeout → `worker_unavailable`. Here that just means "try later": the
  operation is read-only.
- It writes no audit line, since it is a read. 008 gives it no GitHub
  command (FR-016a). Its first surface is spec 009.

## Audit mapping (FR-017)

The `audit.Outcome` literal gains `signal_issued` and `worker_unavailable`.
Every other outcome is kept with its current meaning.

| Core operation result | Audit `outcome` | `author` / `comment` fields |
|---|---|---|
| gate signal, plan | `signal_issued` | as today |
| gate signal, pm/security | `signal_issued_no_handler` | as today |
| gate signal failed | `signal_failed` | as today |
| decision `accepted` | `signal_issued` | `resolved_by` / `"decide_plan <decision> attempt=<n> via <via>"` |
| decision `refused` (`no_window_open`, `stale_attempt`, `already_resolved`) | `duplicate_ignored` | same |
| decision `refused` (`malformed`, `empty_feedback`) | `malformed` | same |
| decision `worker_unavailable` | `worker_unavailable` | same |
| decision `target_not_found` | `signal_failed` | same |
| any `repo_not_allowed` | `repo_not_allowed` | same |

## GitHub adapter: what stays pinned

These existing public names and signatures are the adapter's contract. The
unchanged bridge test suite enforces them (FR-014, FR-015, SC-003).

| Name | Change |
|---|---|
| `server.BridgeApp(client, github_client, secret, allowed_repos)`, `.cache`, `.handle_webhook` | none visible. `_dispatch_run` / `_dispatch_gate` now pass `allowed_repos=self.allowed_repos` to the shims. The dedup call becomes `self.cache.reserve(Origin("github", delivery_id).dedup_key)`. The cache is per-process and GitHub-only today, so its behaviour is identical |
| `temporal_client.connect`, `workflow_id`, `start_run`, `resolve_gate_target`, `StartRunResult`, `GateTargetResolution`, `TASK_QUEUE`, `WORKFLOW_TYPE` | re-exported from `core.runs`; `start_run` gains kw-only `allowed_repos=None` |
| `temporal_client.signal_gate(client, repo, pr_number, gate, decision, feedback, comment_id, author, comment_body, github_client)` | becomes a thin shim (below); gains kw-only `allowed_repos=None` |
| `grammar.parse`, `RunCommand`, `GateCommand`, `is_valid_slug` | `RunCommand` / `GateCommand` re-imported from `core.commands` |
| `audit.log_entry`, `audit.reaction_for_outcome` | `_REACTION_BY_OUTCOME` gains `"signal_issued": "eyes"` and keeps `"signal_issued_no_handler": "eyes"` |
| `auth.verify_signature`, `auth.is_authorized`, `dedup.DeliveryCache`, `github_app.GitHubAppClient` | none |

`temporal_client.signal_gate` after the split:

1. `outcome = await core.gate.signal_gate(...)`, with `allowed_repos`
   passed through. `None` means the GitHub adapter already enforced it in
   `handle_webhook`.
2. `await _react(github_client, repo, comment_id,
   audit.reaction_for_outcome(outcome.outcome))`. A reaction failure is
   still swallowed, exactly as today.

User-visible GitHub reactions are unchanged:

- 👀 for an issued signal on any gate;
- 😕 for `signal_failed`.

**Guard test (new)**: `BridgeApp` passes a non-`None` `allowed_repos` on
every dispatch to the shims. This keeps the `None` default reachable only
from the legacy unit tests (research R8).
