# Data Model: Webhook Trigger Bridge

All entities are process-local (in-memory), per-request or per-process
lifetime — no database, per research.md's dedup/audit decisions.

## WebhookDelivery

One inbound `issue_comment` (created) HTTP POST.

| Field | Type | Source | Notes |
|---|---|---|---|
| `delivery_id` | `str` | `X-GitHub-Delivery` header | Fast-path dedup key (FR-006) |
| `signature` | `str` | `X-Hub-Signature-256` header | `sha256=<hex>`; verified against raw body + `GH_WEBHOOK_SECRET` before any parsing (FR-002) |
| `raw_body` | `bytes` | HTTP request body | Verified as-is (not re-serialized JSON) — HMAC is over exact bytes |
| `is_pull_request` | `bool` | `payload["issue"]["pull_request"] is not None` | FR-004: non-PR issue comments are ignored |
| `author_association` | `str` | `payload["comment"]["author_association"]` | Fast-path only: `OWNER` skips the permission-level API call below (FR-003) |
| `author_login` | `str` | `payload["comment"]["user"]["login"]` | Input to the permission-level check (`GET /repos/{repo}/collaborators/{author_login}/permission`, via the installation token) — FR-003, closes H2 |
| `comment_body` | `str` | `payload["comment"]["body"]` | Parsed per research.md's grammar rule |
| `repo` | `str` | `payload["repository"]["full_name"]` | Passed to `start_workflow`; also checked against the repo allowlist (FR-014) |
| `pr_number` | `int` | `payload["issue"]["number"]` | Used for signal-failure log context (FR-012) |
| `comment_id` | `int` | `payload["comment"]["id"]` | Target of the FR-012 reaction (`POST /repos/{repo}/issues/comments/{comment_id}/reactions`, via the installation token) — 👀 on issued signal, ❌ on signal-target-not-found |
| `branch` | `str` | GitHub REST API (`GET /repos/{repo}/pulls/{pr_number}`, via the installation token), NOT the webhook payload | Resolved once per `RunCommand`, right before `start_workflow` (research.md's App-token decision) |
| `is_cross_repository` | `bool` | Same REST API call as `branch` (`head.repo.full_name != base.repo.full_name`) | FR-013: `true` → reject, do not start a run |

**Validation**: signature MUST verify before any other field is read
(FR-002). `is_pull_request` MUST be true before authorization or grammar
checks run (FR-004). `repo` MUST be in the configured allowlist before
`branch`/`is_cross_repository` are resolved (FR-014 gates the API call
itself, per research.md). `branch` and `is_cross_repository` are only
ever populated for a `RunCommand` dispatch — a `GateCommand` needs
neither.

## PipelineCommand

The parsed intent extracted from an authorized, PR-scoped comment. A
discriminated union of two shapes; a comment matching neither shape (per
research.md's grammar rule) produces no `PipelineCommand` at all (Edge
Case 5 / FR-011 audit log instead).

### RunCommand

| Field | Type | Notes |
|---|---|---|
| `kind` | `Literal["run"]` | |
| `mode` | `Literal["full", "vibe"]` | Parsed/validated only — not forwarded to the workflow (research.md) |
| `agent_name` | `str` | Explicit comment argument (assumption: no branch/spec-derived resolution, out of scope) |
| `version` | `str` | Explicit comment argument |

### GateCommand

| Field | Type | Notes |
|---|---|---|
| `kind` | `Literal["gate"]` | |
| `gate` | `Literal["pm", "plan", "security"]` | Which of the three gate pairs |
| `decision` | `Literal["approved", "rejected"]` | |
| `feedback` | `str \| None` | Present only when `decision == "rejected"` |

**No `agent_name`/`version` field — by design.** A gate comment never
carries these (spec.md's Clarifications); see `GateTargetResolution`
below for how it still reaches exactly one run.

## PipelineRunIdentity

| Field | Type | Notes |
|---|---|---|
| `repo` | `str` | `repository.full_name` (`owner/name`), used as-is — no slug normalization |
| `agent_name` | `str` | Slug-validated (T019): never contains `/` |
| `version` | `str` | Slug-validated (T019): never contains `/`; bare value, no `v` prefix (e.g. `"3"`) |
| `workflow_id` | `str` | Derived: `f"pipeline/{repo}/{agent_name}/v{version}"` — `/`-delimited, no ambiguity at field boundaries since `repo` is the only segment containing `/` and it always contains exactly one; `mode` still excluded (clarification session). Supersedes the earlier `repo_slug`-based form, which could collide at slug boundaries (e.g. `repo=a/b-c, agent=d` vs. `repo=a-b/c, agent=d`) |

`RunCommand` dispatch builds `workflow_id` directly from its own
`repo`/`agent_name`/`version` (via `PipelineRunIdentity`) to call
`start_workflow`. `GateCommand` dispatch does **not** build a
`workflow_id` at all — it has no `agent_name`/`version` to build one
from — and instead resolves its target via `GateTargetResolution` below.
This is what closes the cross-repo collision gap (architect finding A3)
for run starts, and what FR-008 depends on for gate routing.

## GateTargetResolution (query, not a stored entity)

How a `GateCommand` — which carries only `repo` and `pr_number`, never
`agent_name`/`version` — finds the one running workflow it targets:

1. At `start_workflow` time (`RunCommand` dispatch), the bridge attaches
   `repo` and `pr_number` as Temporal **custom search attributes**
   (`TargetRepo: Keyword`, `PRNumber: Int`) to the new workflow execution.
2. At `GateCommand` dispatch, the bridge calls
   `client.list_workflows(query=f"TargetRepo = '{repo}' AND PRNumber = {pr_number} AND ExecutionStatus = 'Running'")`.
3. Exactly one match → that workflow's ID is signaled (FR-007/FR-008).
   Zero matches → `outcome="signal_failed"` (target not found, FR-012).
   More than one match (should not happen given FR-006's dedup) →
   `outcome="signal_failed"` with a distinct `reason` rather than
   guessing.

**Prerequisite**: `TargetRepo`/`PRNumber` must be registered as custom
search attributes on the Temporal server before first use (one-time
`temporal operator search-attribute create` call per namespace — see
research.md and quickstart.md).

## DeliveryCache (process state, not a persisted entity)

In-memory set/dict of recently-seen `delivery_id` values with a bounded
size/TTL (e.g. last N=1000 or last 24h — implementation detail, not
spec-mandated). A delivery ID is **reserved (marked) at the same point it
is checked**, before dispatch — not after the corresponding Temporal call
resolves — closing a check-then-mark race that has no other backstop for
`GateCommand` (H3; `RunCommand` also gets `WorkflowAlreadyStartedError`
as a second, authoritative line of defense, but `GateCommand` does not).
A cache hit short-circuits to "already handled, no action" (fast path
for FR-006/FR-008). A `WorkflowAlreadyStartedError` from Temporal on a
`RunCommand` is the authoritative fallback when the cache misses (e.g.
after a restart). A delivery with no `X-GitHub-Delivery` header at all is
never passed to `DeliveryCache.seen()`/`mark()` (undefined for `None`) —
it is rejected upstream as `outcome="malformed"` (research.md).

## AuditLogEntry (structured log line, not a stored record)

| Field | Type | Notes |
|---|---|---|
| `author` | `str` | Commenter's GitHub login |
| `comment` | `str` | Raw comment body (or truncated) |
| `reason` | `str` | e.g. `"permission_denied: permission=read"`, `"malformed: no grammar match"`, `"signal target not found: workflow_id=..."` |
| `outcome` | `Literal["ignored", "permission_denied", "malformed", "signal_failed", "fork_rejected", "repo_not_allowed", "signal_issued_no_handler", "duplicate_ignored", "mode_not_supported"]` | `"ignored"` is specifically the non-PR-comment (FR-004) and wrong-event/wrong-action (`X-GitHub-Event != issue_comment`, `action != "created"`) paths — every other filtered/rejected path gets its own more specific outcome. `"permission_denied"` supersedes the earlier `"unauthorized"` name now that FR-003 checks permission level, not `author_association` alone (H2). `"mode_not_supported"` covers both an unrecognized `mode` value and a pre-005 `mode=vibe` command (FR-005) |

Written via stdlib `logging` to stdout/stderr per FR-011/FR-012, from a
dedicated `audit.py` module (not `server.py`, to avoid a circular import
with `temporal_client.py` — research.md/M3) — no separate store. Every
outcome that has a `comment_id` available also gets a GitHub reaction
posted (FR-012/FR-015): 🚀 on a started run, 👀 on an issued signal, 😕 on
any rejection/failure outcome.
</content>
