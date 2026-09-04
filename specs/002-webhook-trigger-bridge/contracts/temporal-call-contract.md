# Contract: bridge → Temporal call shape

**Scope note**: `AgentPipelineWorkflow` (`orchestration/workflows/pipeline_workflow.py`)
today defines `run(self, repo, branch, agent_name, version)` and **zero**
`@workflow.signal` handlers (verified via
`grep -n "@workflow.signal" orchestration/workflows/pipeline_workflow.py`
→ no matches). The `mode` parameter and the three signal handlers are
owned by `specs/005-pipeline-mode-signals-escalation/`, not this spec.
This contract therefore specifies **the call the bridge issues**, not
workflow-side behavior — tests verify the call shape against a
fake/mocked `temporalio.client.Client`, not that a run advances.

## Client setup

Same as `orchestration/worker.py`: `Client.connect("localhost:7233")`.
No change to Temporal's own network exposure (FR-010). The target
workflow is referenced by its registered name string,
`"AgentPipelineWorkflow"`, not by importing the class — importing
`orchestration/workflows/pipeline_workflow.py` would also import
`orchestration/activities.py`, which has module-level side effects
(e2b/braintrust/importlib setup) this standalone process has no reason to
trigger (research.md).

## Preconditions before `start_workflow` (`RunCommand` only)

Before any of the below runs, in order:

1. **Repo allowlist** (FR-014): `repo` (`repository.full_name`) MUST be
   in `BRIDGE_ALLOWED_REPOS`. Not allowed → audit log
   `outcome="repo_not_allowed"`, no API call, no run started.
2. **Branch + fork resolution**: one non-blocking, timeout-bounded
   `aiohttp` call to `GET /repos/{repo}/pulls/{pr_number}` using the
   minted installation token (research.md), reading `head.ref` (→
   `branch`) and `head.repo.full_name != base.repo.full_name` (→
   `is_cross_repository`) from the same response — not `subprocess.run`,
   not the `gh` CLI.
3. **Fork/cross-repo refusal** (FR-013): `is_cross_repository == true` →
   audit log `outcome="fork_rejected"`, no run started.

Only once all three pass does `start_workflow` get called.

## Starting a run (`RunCommand`)

```python
handle = await client.start_workflow(
    "AgentPipelineWorkflow",
    args=[repo, branch, agent_name, version],  # NOT mode — see scope note
    id=f"pipeline/{repo}/{agent_name}/v{version}",
    task_queue="agent-factory-pipeline",
    id_conflict_policy=WorkflowIDConflictPolicy.FAIL,  # pinned explicitly, not relied on as SDK default
    search_attributes={
        "TargetRepo": [repo],       # Keyword search attribute — must be
        "PRNumber": [pr_number],    # registered on the server first, see below
    },
)
```

- `repo` (`owner/name`) is used as-is in the workflow ID — no slug
  normalization — per data-model.md's revised `PipelineRunIdentity`
  (closes A3's cross-repo collision without reintroducing a
  slug-boundary collision).
- `branch` comes from the preconditions above — not from the comment.
- `TargetRepo`/`PRNumber` are Temporal **custom search attributes**,
  registered once per namespace before first use:
  `temporal operator search-attribute create --name TargetRepo --type Keyword`
  and `--name PRNumber --type Int` (quickstart.md's prerequisites). These
  are what a later `GateCommand` — which has no `agent_name`/`version` of
  its own — queries against to find this run (see "Resolving a
  `GateCommand`'s target workflow" below).
- **Collision handling**: `client.start_workflow` raises
  `temporalio.exceptions.WorkflowAlreadyStartedError` when a workflow
  with this ID is already running (guaranteed by the pinned
  `id_conflict_policy=FAIL` above). The bridge MUST catch this
  specifically and treat it as "no second run started" (FR-006's
  authoritative fallback) — not as an error to surface.

## Resolving a `GateCommand`'s target workflow

A `GateCommand` carries only `repo` and `pr_number` (from the webhook
payload directly) — never `agent_name`/`version` (data-model.md's
`GateCommand` has no such fields). It cannot build the `f"pipeline/{repo}/{agent_name}/v{version}"`
ID the way a `RunCommand` can. Instead, resolve the target via the
search attributes attached at `start_workflow` time:

```python
results = [wf async for wf in client.list_workflows(
    query=f"TargetRepo = '{repo}' AND PRNumber = {pr_number} AND ExecutionStatus = 'Running'"
)]
if len(results) == 0:
    # outcome="signal_failed", reason="no in-flight run for this PR" — FR-012
elif len(results) > 1:
    # outcome="signal_failed", reason="multiple in-flight runs for this PR" — should not
    # happen given FR-006's dedup; do not guess which one to signal
else:
    handle = client.get_workflow_handle(results[0].id)
```

## Signaling a running workflow (`GateCommand`)

Once `handle` is resolved above:

```python
if feedback is None:
    await handle.signal(signal_name)          # bare signal — pm_approved / plan_approved / security_cleared
else:
    await handle.signal(signal_name, feedback) # *_rejected — feedback is required, never None here
```

| `GateCommand.gate` + `.decision` | `signal_name` | call shape |
|---|---|---|
| `pm` / `approved` | `"pm_approved"` | `handle.signal("pm_approved")` — bare, no payload |
| `pm` / `rejected` | `"pm_rejected"` | `handle.signal("pm_rejected", feedback)` |
| `plan` / `approved` | `"plan_approved"` | `handle.signal("plan_approved")` — bare, no payload |
| `plan` / `rejected` | `"plan_rejected"` | `handle.signal("plan_rejected", feedback)` |
| `security` / `approved` | `"security_cleared"` | `handle.signal("security_cleared")` — bare, no payload |
| `security` / `rejected` | `"security_rejected"` | `handle.signal("security_rejected", feedback)` |

**This corrects the previous `handle.signal(name, None)` framing for the
three approval/clearance signals** — 005's design defines those as bare
signals (no second positional argument at all), and passing `None`
explicitly would be an arity mismatch invisible until 005's handlers
land and start rejecting the extra argument.

**Signal names are asserted literals in this contract** — they will not
resolve to any workflow-side effect until 005 lands the corresponding
`@workflow.signal` handlers. That is expected and out of scope here; the
bridge logs `outcome="signal_issued_no_handler"` for this pre-005 window
(research.md), distinct from an actual delivery failure below.

**Failure handling** (FR-012): a zero-match or multi-match result from
"Resolving a `GateCommand`'s target workflow" above, or a `handle.signal(...)`
call itself raising, all count as the target not being reachable. The
bridge MUST catch every case, write a structured `AuditLogEntry`
(`outcome="signal_failed"`, `reason` naming which case), post a 😕
(`"confused"`) reaction on the triggering comment, and MUST NOT crash. On
a successfully issued signal, the bridge posts a 👀 (`"eyes"`) reaction
on the comment (FR-012/A10) in addition to the
`signal_issued_no_handler`/success log line. A reaction-POST failure
(rate limit, expired token) MUST itself be caught and logged as a
warning — it must never crash the handler or mask the signal outcome
that was already determined (research.md).

**Posting the reaction**: requires the comment's numeric ID
(`comment_id`, data-model.md) and the installation token (`github_app.py`,
T010) — neither is Temporal state. `signal_gate` therefore takes an
additional `comment_id: int` and `github_client` (the installation-token-
bearing `aiohttp.ClientSession` wrapper from `github_app.py`) parameter,
and issues `POST /repos/{repo}/issues/comments/{comment_id}/reactions`
after the signal call resolves (success or not-found), never before.
FR-015 extends the same reaction-on-every-outcome treatment to
`RunCommand` dispatch in `server.py` (🚀 started, 😕 rejected/failed) —
not part of this Temporal-call contract, since a rejected run command
never reaches Temporal at all, but using the identical reaction
mechanism and `github_client`.

**Reaction-content caveat**: GitHub's reaction API only accepts
`content ∈ {"+1", "-1", "laugh", "confused", "heart", "hooray", "rocket",
"eyes"}` — there is no literal ❌ (cross-mark) option. 👀 maps exactly to
`"eyes"`, 🚀 to `"rocket"`. ❌ has no exact match; the bridge uses
`"confused"` (😕) as the stand-in for every rejection/failure outcome.
Resolved: spec.md's FR-012/FR-015 wording now states this stand-in
explicitly rather than the literal ❌ glyph.

## Dedup

`RunCommand`: `WorkflowAlreadyStartedError` (above) is the authoritative
fallback; the in-memory `X-GitHub-Delivery` cache (data-model.md) is the
fast path checked first, to avoid a redundant `start_workflow` call on an
exact-duplicate redelivery.

`GateCommand`: has no server-side collision to fall back on — the
delivery-ID cache is the *only* defense against a double-signal, which is
why it MUST reserve (mark) the delivery ID at check time, before the
`list_workflows` resolution and `signal()` call above run, not after they
resolve (H3, data-model.md's `DeliveryCache`).
</content>
