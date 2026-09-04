# Research: Webhook Trigger Bridge

## Decision: HTTP framework — aiohttp

**Rationale**: `orchestration/worker.py` and `activities.py` are already
asyncio-native (`Client.connect`, `asyncio.run`). `aiohttp` gives an async
request handler that can `await Client.connect(...)` /
`handle.signal(...)` directly, no extra ASGI server process, and no new
heavyweight dependency class (FastAPI+uvicorn) in a repo whose
`orchestration/pyproject.toml` today lists exactly four deps
(`temporalio`, `e2b`, `pyyaml`, `braintrust`).

**Alternatives considered**:
- `FastAPI` + `uvicorn` — heavier (two new deps, ASGI server config) for a
  single `/webhook` POST route with no OpenAPI/validation need.
- stdlib `http.server` — would need manual threading to avoid blocking
  the Temporal client's asyncio loop; no benefit over `aiohttp` here.

## Decision: signature verification — stdlib `hmac`/`hashlib`

**Rationale**: `X-Hub-Signature-256` is `sha256=<hex hmac>` of the raw
request body against `GH_WEBHOOK_SECRET`. Stdlib `hmac.compare_digest`
over `hashlib.sha256` is exactly GitHub's documented verification
algorithm — no library needed.

## Decision: bridge → Temporal call contract stops at "the call was made"

**Rationale**: `orchestration/workflows/pipeline_workflow.py`'s
`AgentPipelineWorkflow.run` today takes only `(repo, branch, agent_name,
version)` — no `mode` parameter — and defines **zero** `@workflow.signal`
handlers. The multi-agent pipeline design doc (§6) proposes `mode`, the
three gate signal pairs (`pm_approved`/`pm_rejected`, etc.), and the
deterministic workflow ID `pipeline-{agent_name}-v{version}`, but that
work is tracked separately in `specs/005-pipeline-mode-signals-escalation/`
(confirmed untouched: `grep -n "@workflow.signal" pipeline_workflow.py`
returns nothing). This spec (002) is scoped to the bridge process only —
it must not invent workflow-side behavior 005 owns.

Consequence for this plan:
- The bridge parses and validates `mode` (`full`/`vibe`) per FR-005 (a
  grammar-recognition requirement, satisfiable independent of the
  workflow) but does **not** pass it into `AgentPipelineWorkflow.run` —
  doing so would require a signature change out of this spec's scope.
  Tracked as a dependency: 005 must land the `mode` parameter and the
  signal handlers before the bridge's `mode` argument or its signal
  delivery does anything downstream.
- `contracts/` documents the **bridge-to-Temporal call contract**
  (`start_workflow`/`signal` call shape: method, args, workflow ID,
  signal name, payload) rather than workflow behavior, since there is no
  workflow behavior to contract against yet.
- Tests assert the client call is issued with the right method name,
  positional args, and workflow ID (against a fake/mocked Temporal
  client) — not that a run advances past a gate, since no gate exists to
  advance past.

**Amendment — signal call shape**: 005's design has the three
`*_approved`/`security_cleared` signals as *bare* signals (no payload
argument at all), not `handle.signal(name, None)`. The bridge issues
`handle.signal(signal_name)` (no second argument) for `pm_approved`,
`plan_approved`, `security_cleared`, and `handle.signal(signal_name,
feedback)` (with the feedback string) only for the three rejection
signals. This supersedes any earlier framing of `feedback=None` for the
approval case — an arity mismatch there would be invisible until 005
lands its signal handlers and started raising on the extra argument.

**Amendment — audit outcome for the pre-005 window**: today, every signal
call in this feature lands on a workflow with zero `@workflow.signal`
handlers (005 hasn't shipped yet), so a signal that is *issued
successfully* at the Temporal-client level still does nothing
workflow-side. Logging that as a plain success would produce a
false-positive audit trail. The bridge logs a distinct outcome,
`signal_issued_no_handler`, for this case — call succeeded, but no
handler exists yet to act on it — separate from `signal_failed` (target
run not found at all).

**Amendment — SC-005 scope**: "no duplicate signal delivery" (SC-005) is
guaranteed only against *redelivery* of the same webhook delivery
(`X-GitHub-Delivery` cache hit) — it does not and cannot catch two
distinct comments with identical text (e.g. a human posting `pm_approved`
twice by mistake), since each is a genuinely new delivery ID. That
stronger guarantee — treating a second identical decision as a no-op —
belongs to `specs/005-pipeline-mode-signals-escalation/`'s workflow-side
idempotency (e.g. an already-passed gate ignoring a repeat signal), not
this bridge. SC-005's wording in spec.md is scoped accordingly.

## Decision: workflow ID format — `pipeline/{repo}/{agent_name}/v{version}`

**Rationale**: The design doc §6's originally proposed
`pipeline-{agent_name}-v{version}` (also this spec's own initial
clarification-session answer) has no repo namespace — two repos running
the same `agent_name`/`version` would collide on one workflow ID, and any
repo the App is installed on could drive a paid run under an existing
identity (A3). An intermediate fix (`repo_slug` = `repository.full_name`
with `/` → `-`, prepended with `-` separators) closed the cross-repo
collision but reintroduced a field-boundary collision at lower
probability: `repo=a/b-c, agent=d` and `repo=a-b/c, agent=d` both slug to
`pipeline-a-b-c-d-v...`. Temporal workflow IDs are unconstrained strings
(they permit `/`), so this revision drops the slugging step entirely:
`repo` (`owner/name`, exactly one `/`) is used as-is, `agent_name`/`version`
are slug-validated to disallow `/` (T019), and `/` is the field separator
throughout — `pipeline/{repo}/{agent_name}/v{version}`. `owner/name`'s one
`/` can never be confused with a field boundary because `agent_name` and
`version` are validated to contain none. `mode` remains excluded from
identity per this spec's own clarification session — a run command with a
different `mode` for the same `repo`/`agent_name`/`version` targets the
same run/identity. This supersedes both the clarification session's
literal `pipeline-{agent_name}-v{version}` wording (spec.md) and the
`repo_slug`-based intermediate form; the repo-agnostic part of the
original answer — `mode` excluded from identity — still holds.

## Decision: gate-command target resolution — Temporal search attributes on `repo`/`pr_number`, not agent_name/version reconstruction

**Rationale**: A gate comment (`pm_approved` etc.) carries no
`agent_name`/`version` — data-model.md's `GateCommand` never had those
fields, and no comment grammar in this spec adds them. FR-007/FR-008 as
originally worded ("the run in flight whose identity matches the PR's
`agent_name`/`version`") was therefore unsatisfiable: there is no input
from which to reconstruct `workflow_id`. Every comment on a PR — run or
gate — does carry `repo` and `pr_number` directly from the webhook
payload (data-model.md's `WebhookDelivery`), and that pair is already
sufficient to identify "the run this PR is for," since FR-006's dedup
guarantees at most one in-flight run per `repo`/`agent_name`/`version`
and a PR is conventionally one run's home.

The bridge tags each started run with `repo` and `pr_number` as Temporal
**custom search attributes** (`TargetRepo: Keyword`, `PRNumber: Int`) at
`start_workflow` time. A gate comment resolves its target by calling
`client.list_workflows(query=f"TargetRepo = '{repo}' AND PRNumber = {pr_number} AND ExecutionStatus = 'Running'")`
and taking the single match. Zero matches → `outcome="signal_failed"`
(FR-012, unchanged). More than one match is a "should never happen" case
given FR-006's dedup — if the query ever returns more than one running
workflow, the bridge logs a `signal_failed` with a distinct `reason`
("multiple in-flight runs for this PR") rather than guessing which one
to signal.

**Prerequisite**: custom search attributes must be registered on the
Temporal server before first use — `temporal operator search-attribute
create --name TargetRepo --type Keyword` and `--name PRNumber --type
Int` (Temporal CLI, one-time, per Temporal namespace/cluster; see
`quickstart.md`'s updated prerequisites). This is a one-time operational
step, not something the bridge process can do at request time.

**Alternatives considered**:
- Extending the gate grammar to require explicit `agent=... version=...`
  arguments on every gate comment, mirroring the run command. Rejected:
  ugly for the six-comment-a-day human workflow this feature exists for,
  and inconsistent with spec.md's own Assumptions, which never asked
  gate comments to carry these.
- An in-process `PR -> workflow_id` map populated at run start. Rejected:
  loses all state on a bridge restart, silently breaking FR-008 rather
  than degrading visibly — the same restart-survives-badly property this
  spec already accepted for delivery-ID dedup, but here the failure mode
  is wrong-or-no signal delivery instead of a harmless duplicate.
- Temporal workflow **memo** instead of a search attribute. Rejected:
  memos are not queryable via `list_workflows`' visibility API — only
  attached, retrievable metadata on a handle you already have. Search
  attributes are the only mechanism that supports "find the workflow for
  this `repo`/`pr_number`" as a query.

## Decision: authorization — installation-token permission check, not `author_association` alone

**Rationale**: FR-003 originally mirrored `swe-agent-build.yml`'s
`author_association ∈ {OWNER, MEMBER, COLLABORATOR}` allowlist exactly.
Bug-for-bug parity with an existing CI check was a reasonable default,
but the two have different blast radii: the Actions workflow runs a
build; this bridge starts a billable sandbox run and, once
`specs/005-pipeline-mode-signals-escalation` lands, clears a security
review gate. GitHub's `COLLABORATOR` association includes **read-only**
collaborators — someone who can comment but was never granted write
access. The bridge therefore calls
`GET /repos/{repo}/collaborators/{username}/permission` (installation
token, already minted for the branch/fork-check call, T010) and requires
`permission ∈ {"write", "admin"}`, or `author_association == "OWNER"` as
a fast-path that skips the extra call for the repo owner. This applies to
**both** run and gate commands — a gate decision is not lower-trust than
a run start.

**Alternatives considered**: keeping `author_association` alone —
rejected as too coarse once a gate decision is a possible consequence of
the check passing.

## Decision: dedup cache — reserve delivery ID before dispatch, not after

**Rationale**: The original ordering (check cache → dispatch → mark
cache) leaves a TOCTOU window: two concurrent deliveries with the same
`X-GitHub-Delivery` ID can both pass the `seen()` check before either
calls `mark()`, because there is at least one `await` between them (the
branch-resolution call for a `RunCommand`, the signal RPC for a
`GateCommand`). For run starts, `WorkflowAlreadyStartedError` is a
genuine backstop against the resulting double-dispatch. **For gate
signals there is no such backstop** — Temporal signals have no
server-side "already delivered" collision to catch — so this race is a
real way to violate SC-005 for a `GateCommand`. Fix: `mark()` the
delivery ID (reserve it) at the same point `seen()` is checked, before
any `await` — a cache hit and a cache reservation happen atomically, in
the same synchronous step. This applies to both `RunCommand` and
`GateCommand` dispatch.

## Decision: post a GitHub reaction on every terminal outcome, not gate signals only

**Rationale**: FR-012 already required a reaction (👀/😕) for gate-signal
outcomes, but every run-command rejection path (`unauthorized`,
`malformed`, `fork_rejected`, `repo_not_allowed`, `mode_not_supported`)
only produced a bridge stdout log line — invisible to the commenter, a
regression versus `swe-agent-build.yml`, which posts a visible PR comment
on fork rejection today. The bridge now posts a reaction on **every**
terminal outcome of both command kinds: 🚀 `"rocket"` on a successfully
started run, 👀 `"eyes"` on a successfully issued signal, 😕 `"confused"`
on any rejection or failure (unauthorized, malformed, fork-rejected,
repo-not-allowed, mode-not-supported, signal-target-not-found). The
`comment_id`/installation-token plumbing already exists for the T028
signal-reaction path (FR-012); this extends the same call to the
run-command dispatch path (FR-015), at no new-dependency cost. A
rejection the bridge never got far enough to identify a `comment_id` for
(invalid signature, wrong event type, non-PR comment) has no comment to
react to and gets no reaction — only log visibility, as before.

**Reaction-POST failure handling**: a reaction POST failing (rate limit,
expired token) MUST be caught and logged as a warning — it must never
crash the request handler or mask whether the underlying signal/run
outcome itself succeeded.

## Decision: grammar anchoring — first non-empty line, exact or prefixed match

**Rationale**: Edge case in spec.md: a gate keyword embedded in prose
must not fire (FR-007's "recognize" requirement is untestable without a
pinned rule). Rule: a comment is a recognized command only if its first
non-empty line, trimmed of leading/trailing whitespace, either:
- equals exactly one of `pm_approved`, `plan_approved`, `security_cleared`, or
- matches `^(pm_rejected|plan_rejected|security_rejected):\s*(.+)$` (feedback = capture group 2), or
- matches `^@pipeline-agent run (mode=(full|vibe)|agent=(\S+)|version=(\S+))(\s+(mode=(full|vibe)|agent=(\S+)|version=(\S+))){2}$`
  — i.e. exactly the three `key=value` tokens `mode=`, `agent=`,
  `version=`, each appearing exactly once, in **any** order. The design
  doc's own worked example (`docs/70-multi-agent-pipeline-design.md`)
  orders them `agent=... version=... mode=full`, which the original
  fixed-order regex (`mode` first) would have rejected — order
  insensitivity closes that self-inconsistency rather than requiring the
  design doc's example to be wrong.

Anything else (including a keyword appearing mid-sentence, or on a later
line) is ignored — matches Edge Case 5 and FR-003/FR-007's "act only on"
framing. A run command whose three tokens parse but whose `mode` value is
neither `full` nor `vibe` (e.g. `mode=turbo`, a likely typo) is
distinguished from a fully unrecognized comment: it produces
`outcome="mode_not_supported"` rather than `outcome="malformed"`, so an
operator reading logs can tell "almost right, bad mode value" apart from
"not a command at all." A `mode=vibe` command parses successfully but is
then rejected at dispatch time with the same `mode_not_supported` outcome
until `specs/005-pipeline-mode-signals-escalation` ships the relaxed-rigor
path (see the shipping-order decision below) — silently running it as
`mode=full` would give the commenter no way to know their request wasn't
honored.

**Missing `X-GitHub-Delivery` header**: required per the HTTP contract;
a delivery missing it entirely cannot be deduplicated. Treated as
malformed at the transport level — `202`, `outcome="malformed"`, `reason`
noting the missing header — rather than passing `None` into
`DeliveryCache.seen()`, which is undefined.

**Alternatives considered**: substring search anywhere in the body —
rejected explicitly by Edge Case 5 ("must not be misinterpreted").

## Decision: duplicate detection scope

**Rationale**: FR-006 specifies two defenses for **run starts**:
- an in-memory `X-GitHub-Delivery` ID cache (fast path, process-local,
  bounded TTL/size — this is a single persistent process per the design
  doc, not a distributed service, so in-memory is sufficient and no new
  storage dependency is introduced), and
- Temporal's own `WorkflowAlreadyStartedError` on the deterministic
  workflow ID as the authoritative fallback (catch and treat as "no
  second run started", not an error).

Gate **signals** (FR-006's "double-fire a signal" edge case) only get the
delivery-ID cache — Temporal signals are fire-and-forget with no
equivalent "already delivered" collision to catch server-side. This means
SC-005's "no duplicate signal delivery" guarantee does not survive a
bridge process restart that loses the in-memory cache mid-way through a
GitHub retry window. Accepted bound, stated here rather than building
persistent dedup storage this spec does not otherwise call for.

## Decision: audit logging — structured stdlib `logging`, stdout/stderr, in its own module

**Rationale**: FR-011/FR-012 require structured audit entries (author,
comment, reason) for ignored/unauthorized/malformed comments and failed
signal deliveries, written to the bridge process's own logs — no
separate audit store, per this spec's clarification session. Python's
stdlib `logging` module with a structured (JSON-per-line) formatter
satisfies this with no new dependency. The `outcome` enum is extended
(data-model.md) to include `fork_rejected`, `repo_not_allowed`,
`signal_issued_no_handler`, `mode_not_supported`, and `permission_denied`
(renamed from `unauthorized` now that the check is permission-level, not
association-only) — see the amendments above and FR-013/FR-014/FR-003. A
`DeliveryCache` fast-path hit also gets its own log line (`outcome=
"duplicate_ignored"`) rather than being silently swallowed, so the
dedup path is observable without attaching a debugger.

Audit logging lives in its own `orchestration/webhook_bridge/audit.py`,
not `server.py`. `temporal_client.py` needs to emit `signal_failed`/
`signal_issued_no_handler` (T028) and `server.py` needs to emit every
other outcome, but `server.py` already imports `temporal_client.py` for
dispatch — putting the logger in `server.py` would make `temporal_client.py`
import back into it, a circular import. A standalone `audit.py` with no
dependency on either is the natural fix (plan.md's Project Structure and
tasks.md T007 are updated accordingly).

## Decision: GitHub App installation-token minting

**Rationale**: FR-009 says "reuse the existing GitHub App identity" but
does not say how a standalone process (not a GitHub Actions runner, which
gets a token for free) mints one. The bridge signs a JWT with
`SWE_AGENT_APP_PRIVATE_KEY` (RS256, `iss=SWE_AGENT_APP_ID`, ≤10 min `exp`),
exchanges it for an installation access token via
`POST /app/installations/{id}/access_tokens`, and caches the result in
memory until shortly before its ~1h expiry (GitHub-documented lifetime).
The token is used for the same "resolve PR branch + `isCrossRepository`"
API call `swe-agent-build.yml` makes today (`gh pr view ... --json
headRefName,isCrossRepository`), just issued directly against the REST
API instead of via the `gh` CLI. The token value itself is never logged.

**Dependencies**: `PyJWT` (JWT signing) + `cryptography` (RS256 key
handling) — added to `orchestration/pyproject.toml` (T002).

**Alternatives considered**: shelling out to `gh api` with a
pre-provisioned PAT — rejected because it reintroduces a second credential
(defeats FR-009's "reuse the existing App identity") and a blocking
subprocess call (see the non-blocking-API-call note below).

**`SWE_AGENT_APP_PRIVATE_KEY` encoding convention**: a multi-line PEM
value in a single-line `.env` entry has no established convention in
this repo's `.env.example` to follow. The bridge requires the env var to
hold the PEM **base64-encoded** (decode before passing to `PyJWT`), not
literal `\n`-escaped or raw multi-line — base64 round-trips through
every shell/`.env`/CI-secret mechanism without quoting ambiguity, unlike
literal newlines in a `.env` file. `.env.example` documents this with a
comment and a placeholder showing the expected shape.

## Decision: delivery-path guarantee is best-effort, not at-least-once

**Rationale**: smee.io (and equivalent webhook-proxy relays) fan out over
a live SSE connection only — they store and retry nothing. GitHub marks a
delivery "delivered" the instant the relay's edge responds `200`,
regardless of whether `smee-client` is even running, let alone whether the
bridge processed it. This falsifies the original Edge Case 4 wording
("GitHub's own webhook retry covers transient gaps") — GitHub's retry
logic reacts to the *relay's* response code, not the bridge's, so a downed
`smee-client` or unreachable bridge loses the trigger silently with no
retry ever firing. spec.md's Edge Case 4 and the HTTP contract's `500` row
are corrected to state this explicitly; the only recovery path is a human
noticing (e.g. an expected pipeline never started) and using GitHub's
manual delivery-redelivery feature, which only works while some relay
client is connected to receive it.

**Confidentiality addendum**: the above analyzes reliability only. A
smee.io-style channel is also **public and unauthenticated for reads** —
anyone who knows or guesses the `smee.io/<channel>` URL can subscribe and
read every relayed delivery in full: private-repo PR comment bodies,
author logins, repo names, PR titles. The HMAC secret (`GH_WEBHOOK_SECRET`)
protects integrity (the bridge can tell a forged delivery from a real
one) but does nothing for confidentiality, since the relay itself is not
the thing being authenticated. Because the bridge binds loopback-only, an
outside observer of the channel cannot use it to *inject* a delivery —
this is a disclosure risk, not an injection one. `WEBHOOK_PROXY_URL` MUST
therefore be treated as a secret value (not committed, not logged, not
shared outside the people who need to configure the relay), and this
relay approach is scoped to development/single-operator use — a
production deployment should move to a directly-addressed webhook
endpoint instead (spec.md's Assumptions now say this explicitly).

## Decision: shipping order — 002 must not run against a real repo before 005 lands

**Rationale**: `orchestration/workflows/pipeline_workflow.py`'s `run()`
has zero `@workflow.signal` handlers and no `workflow.wait_condition` —
confirmed by reading all of `run()` (lines 55-81), not just grepping for
the signal decorator. It executes Build → Eval-Gate → Register straight
through, up to `MAX_BUILD_ATTEMPTS` retries, with no human gate at any
point. This bridge is the first thing in this repository that can start
that workflow from a GitHub comment. Until `specs/005-pipeline-mode-signals-escalation`
ships its signal handlers and pauses, enabling FR-005's run-start path
against a real target repository would let any authorized commenter
(now a `write`/`admin` collaborator, per the authorization decision
above — but that is a lower bar than "a human deliberately started this
build") trigger an unsupervised build-and-register run with no PM/plan/
security gate in between, contradicting `registry/agents/swe-agent/`'s
own `requires_human_supervision: true` manifest flag. FR-016 makes this
an explicit, spec-level constraint on `BRIDGE_ALLOWED_REPOS` (test/
disposable repos only, pre-005) rather than an implicit assumption buried
in a scope-boundary note.

## Decision: pin a `temporalio` version floor; add one real-SDK integration test

**Rationale**: Every Temporal-facing test in this feature (T017, T026)
runs against a mocked `Client` — necessary for unit-speed feedback, but
it means a wrong kwarg name, a wrong import path (`WorkflowIDConflictPolicy`
lives in `temporalio.common`, which no artifact previously stated), or a
renamed exception class would pass every mocked test and fail only on
first real use. `orchestration/pyproject.toml` lists `temporalio`
unpinned today, so a future `uv sync` could silently pick up a version
where these names moved. Fix: pin a `temporalio>=` floor matching the
version already resolved in `orchestration/uv.lock` (`1.32.0`, confirmed
to contain both APIs used here), and add one Phase 6 integration test
that runs against a real local Temporal instance (`make up`) — starts a
throwaway workflow by name string, signals it, confirms both calls
actually round-trip — rather than relying solely on T037's manual
quickstart pass for real-SDK coverage.

## Decision: fork/cross-repo refusal + repo allowlist as two separate authorization gates

**Rationale**: FR-013 (fork refusal) and FR-014 (repo allowlist) are
distinct failure modes — a same-repo PR from a disallowed repo, and an
allowed repo's PR that happens to be a fork — and get distinct audit
outcomes (`fork_rejected`, `repo_not_allowed`). Both are evaluated using
the one App-token API call that already resolves `branch` (T018):
`isCrossRepository` comes back in the same response as `headRefName`, so
no second round-trip is needed. The allowlist check (`repository.full_name
in BRIDGE_ALLOWED_REPOS`) runs first, since it needs no API call and gates
whether the branch-resolution call happens at all; the fork check runs
once that call's response is available.

**Alternatives considered**: a single combined "authorization" check —
rejected because collapsing the two audit outcomes into one would lose the
distinction a human reviewing logs needs (misconfigured allowlist vs. an
actual fork-PR attempt).

**Scope note (L2)**: the fork check applies to `RunCommand` dispatch
only — a `GateCommand` never triggers it. This is a deliberate decision,
not an oversight: approving/rejecting a gate doesn't execute anything on
the fork's own code, and a fork-PR author's `author_association` is
typically `CONTRIBUTOR`/`NONE` anyway, which the permission-level check
(FR-003, above) already excludes independent of fork status.

## Decision: pin `id_conflict_policy` explicitly

**Rationale**: FR-006's dedup logic depends on `client.start_workflow`
raising `WorkflowAlreadyStartedError` on a colliding deterministic ID —
that only happens with Temporal's default `WORKFLOW_ID_CONFLICT_POLICY_FAIL`.
The call in `contracts/temporal-call-contract.md` now pins
`id_conflict_policy=WorkflowIDConflictPolicy.FAIL` explicitly rather than
relying on an unstated default, so a future Temporal SDK default change
can't silently turn FR-006's dedup into `USE_EXISTING`/queued-restart
behavior.

## Decision: reference the target workflow by registered name string, not by importing `AgentPipelineWorkflow`

**Rationale**: `orchestration/activities.py` has module-level side effects
(e2b/braintrust/importlib setup) that run at import time. Importing
`AgentPipelineWorkflow` directly into the bridge process (a long-lived,
network-facing server, unlike the short-lived `worker.py` process) would
pull those side effects into a process that has no need for them and no
control over when they run. `client.start_workflow` accepts the
workflow's registered type name as a string
(`"AgentPipelineWorkflow"`, matching `orchestration/worker.py`'s
registration) instead of the class object — the bridge uses that form.

## Decision: non-blocking PR-branch/fork-check API call

**Rationale**: A blocking `subprocess.run(["gh", "pr", "view", ...])` or
blocking `requests.get(...)` inside the async `POST /webhook` handler
would stall the process's single event loop — including the Temporal
client's own RPCs — for the call's full duration. The bridge issues this
call (and the installation-token exchange above) via `aiohttp.ClientSession`
(already a dependency) with an explicit timeout (e.g. 10s), never
`subprocess.run` or a synchronous HTTP client.

## Decision: test/dev tooling location — `orchestration/pyproject.toml`, not root

**Rationale**: Per `CLAUDE.md`, the root `pyproject.toml`/`uv.lock` is
scoped to the repo-root `tests/` suite and has no `temporalio`/`aiohttp`
in its environment. `orchestration/pyproject.toml` already carries
`orchestration`'s own runtime deps separately; this feature adds
`aiohttp` there as a runtime dependency and `pytest`/`pytest-asyncio` as
a `dependency-groups.dev` entry in that same file, mirroring how
`harness/swe-agent/pyproject.toml` is self-contained. Tests run via
`uv run --directory orchestration pytest`, not the root `uv run pytest`.

