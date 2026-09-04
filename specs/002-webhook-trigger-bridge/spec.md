# Feature Specification: Webhook Trigger Bridge

**Feature Branch**: `002-webhook-trigger-bridge`

**Created**: 2026-09-02

**Status**: Draft

**Input**: User description: "Webhook trigger bridge for the multi-agent SDLC pipeline (docs/70-multi-agent-pipeline-design.md §1.1). Add a new orchestration/webhook_bridge/ component: a persistent local HTTP server, reusing the existing swe-agent GitHub App identity, subscribed to issue_comment (created) webhook deliveries relayed via smee-client from a smee.io channel (WEBHOOK_PROXY_URL) to a local port. Each delivery's X-Hub-Signature-256 HMAC is verified against a new GH_WEBHOOK_SECRET before any processing. Authorization re-implements the existing swe-agent-build.yml allowlist in code (author_association in OWNER/MEMBER/COLLABORATOR). Grammar: a not-yet-running \"@pipeline-agent run mode=<full|vibe>\" PR comment starts AgentPipelineWorkflow.run with a deterministic workflow ID pipeline-{agent_name}-v{version}; comments matching pm_approved/pm_rejected:<feedback>/plan_approved/plan_rejected:<feedback>/security_cleared/security_rejected:<feedback> on an already-running workflow issue the matching Temporal signal via get_workflow_handle(id).signal(...). The bridge connects to Temporal exactly as orchestration/worker.py does (Client.connect to the local Temporal instance) — no change to Temporal's own network exposure. A make bridge target should run the smee relay and the bridge server together. Resolution of agent_name/version from the PR comment or branch is out of scope for this spec (left as an explicit open question, matching §9 of the design doc) — for this feature, assume agent_name/version are passed as explicit comment arguments."

## Clarifications

### Session 2026-09-03

- Q: Redelivery dedup (FR-006/SC-005/Edge-Case-1): how must bridge detect "already in flight" to skip duplicate run starts? → A: Both — delivery-ID cache as fast-path, Temporal workflow-ID collision as authoritative fallback.
- Q: Gate-signal failure (FR-012, Edge-Case-2): target run not found when signaling — how must this be reported? → A: A structured log entry (author/comment/reason) plus a GitHub reaction on the triggering comment (❌ not-found / 👀 issued) — superseded by FR-013/FR-014's architect review, which added the reaction requirement; the original "no GitHub-visible action" framing no longer applies.
- Q: Audit record (FR-011) for ignored/unauthorized/malformed comments — where must it be recorded? → A: Structured stdout/stderr logs from the bridge process.
- Q: Does `mode` (full|vibe) participate in the deterministic run identity, or only agent_name/version? → A: agent_name/version only — identity excludes `mode` regardless of it. (Superseded in part: the identity string itself gained a repo-derived segment, now `pipeline/{repo}/{agent_name}/v{version}` (`/`-delimited, `repo` used as-is — see research.md's revised workflow-ID-format decision, which closes a slug-collision gap in an earlier `repo_slug` form), per FR-013/FR-014's architect review. The `mode`-exclusion answer is unchanged.)

### Session 2026-09-03 (second architect review pass)

- Q: A gate comment (`pm_approved` etc.) carries no `agent_name`/`version` — how does the bridge resolve which in-flight run it targets? → A: Every started run is tagged with `repo` and `pr_number` as Temporal search attributes at `start_workflow` time. A gate comment resolves its target by querying Temporal for the one running workflow whose `repo`/`pr_number` search attributes match the comment's own PR — never by requiring `agent_name`/`version` in the gate comment itself, which FR-007 never asked for and no artifact ever supplied.
- Q: Is `author_association` alone sufficient authorization for both run-start and gate-decision comments? → A: No. `COLLABORATOR` includes read-only collaborators, and a gate decision (`security_cleared` once 005 lands) is a higher-trust action than opening an issue. Both run-start and gate-decision comments additionally require the commenter's actual repository permission level — fetched via the installation token — to be `write` or `admin`, or `author_association == OWNER`. `author_association` alone is no longer sufficient for either command.
- Q: When must a delivery ID be marked "seen" in the dedup cache — before or after the corresponding Temporal call resolves? → A: Before dispatch (reserve-then-act), not after. Gate signals have no server-side collision Temporal can catch (unlike run starts, which get `WorkflowAlreadyStartedError`), so a check-then-mark ordering leaves a race window that can double-signal a gate. Marking at check time closes it for both command kinds.
- Q: Must a rejected/failed run command (unauthorized, malformed, fork PR, disallowed repo) be visible to the commenter, or is a bridge log line enough? → A: A GitHub reaction MUST be posted on the triggering comment for every terminal outcome of both run and gate commands, not gate signals only — a dispatched/successful outcome gets 🚀 (run) or 👀 (signal), a rejected/failed outcome gets 😕. A commenter must never have to read bridge process logs to learn whether their comment did anything.
- Q: May this bridge be pointed at a real target repository (via `BRIDGE_ALLOWED_REPOS`) before `specs/005-pipeline-mode-signals-escalation` ships? → A: No. `AgentPipelineWorkflow.run` today has zero `@workflow.signal` handlers and no `wait_condition` — it runs Build → Eval-Gate → Register straight through with no human gate at all. Until 005 lands its signal handlers and pauses, `BRIDGE_ALLOWED_REPOS` MUST list only a disposable/test repository; pointing it at a real target repo would let any allowlisted commenter trigger an unsupervised build-and-register run.
- Q: Before 005 implements the relaxed `vibe` path, should a `mode=vibe` run command execute silently as `mode=full`? → A: No. Pre-005, a `mode=vibe` run command is rejected (`outcome="mode_not_supported"`, a 😕 reaction posted, no run started) rather than silently executed at full rigor with zero observable difference — a user who explicitly asked for the relaxed path deserves to know it isn't available yet, not a silent substitution.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Start a pipeline run from a PR comment (Priority: P1)

An authorized reviewer comments `@pipeline-agent run mode=full agent=<agent_name> version=<version>` on a target-repo pull request. The pipeline starts without anyone touching the orchestration engine directly.

**Why this priority**: This is the only entry point into the pipeline. Without it, nothing downstream (PM review, architect fan-out, build, gates) can ever begin — every other story depends on a run existing first.

**Independent Test**: Post the comment on a PR with no in-flight run for that agent/version; verify a new pipeline run starts exactly once and its identity is derived deterministically from `agent_name`/`version`.

**Acceptance Scenarios**:

1. **Given** no pipeline run is in flight for `agent_name=widget-export`, `version=v3`, **When** an authorized commenter posts `@pipeline-agent run mode=full agent=widget-export version=v3`, **Then** a new pipeline run starts with a deterministic identity derived from `widget-export`/`v3`.
2. **Given** a pipeline run is already in flight for `agent_name=widget-export`, `version=v3`, **When** the same run comment is posted again (e.g. a redelivered webhook), **Then** no second run is started.

---

### User Story 2 - Advance a running pipeline via gate comments (Priority: P1)

An authorized reviewer comments one of the gate decisions (`pm_approved`, `pm_rejected: <feedback>`, `plan_approved`, `plan_rejected: <feedback>`, `security_cleared`, `security_rejected: <feedback>`) on the PR of an already-running pipeline. The correct in-flight run receives the decision and proceeds or loops back accordingly.

**Why this priority**: The pipeline is designed around human approval gates (PM, plan, security); without a working feedback channel every run stalls forever at the first gate.

**Independent Test**: With a run already in flight and waiting on a gate, post each of the six gate comments in turn (across separate runs) and verify each reaches that run's gate and none other.

**Acceptance Scenarios**:

1. **Given** a run is waiting at the PM gate, **When** an authorized commenter posts `pm_approved` on that run's PR, **Then** the run proceeds past the PM gate.
2. **Given** a run is waiting at the plan gate, **When** an authorized commenter posts `plan_rejected: use candidate C's approach`, **Then** the run receives the rejection with the feedback text and loops back.
3. **Given** two runs are in flight for different agents/versions, **When** a gate comment is posted on one run's PR, **Then** only that run receives the signal.

---

### User Story 3 - Ignore comments from unauthorized or unrecognized sources (Priority: P2)

A comment is posted by someone outside the allowlist, or the comment text does not match any recognized command, or the webhook signature does not verify.

**Why this priority**: Without this, anyone who can comment on a PR could start or steer a pipeline run — a safety requirement, but the pipeline is non-functional either way until Stories 1–2 work, hence P2.

**Independent Test**: Post a run/gate comment from a non-allowlisted account, and separately deliver a payload with an invalid signature; verify neither results in any pipeline action.

**Acceptance Scenarios**:

1. **Given** a commenter whose repository permission level is below `write` and whose `author_association` is not `OWNER` (see FR-003's Clarifications amendment — supersedes the original `author_association ∈ {OWNER, MEMBER, COLLABORATOR}` wording here), **When** they post `@pipeline-agent run mode=full ...`, **Then** no pipeline run starts.
2. **Given** a webhook delivery whose signature does not match the shared secret, **When** it is received, **Then** the delivery is rejected before any comment parsing happens.
3. **Given** an authorized comment that does not match any recognized grammar, **When** it is received, **Then** it is ignored with no signal or run started.

### Edge Cases

- What happens when the same webhook delivery is redelivered (GitHub's own retry behavior)? Must not start a duplicate run or double-fire a signal. Detected via a delivery-ID cache (`X-GitHub-Delivery`) as the fast-path, with Temporal's own workflow-already-started collision on the deterministic run ID as the authoritative fallback.
- What happens when a gate comment (e.g. `security_cleared`) is posted but no matching run is currently in flight (already completed, wrong agent/version, or never started)? Signal delivery must fail without crashing the bridge, and must be reported via a structured error log entry (author, comment, reason) and a ❌ GitHub reaction on the triggering comment (per FR-012).
- What happens when a comment is posted on a plain issue rather than a pull request? Must be ignored — this bridge only acts on PR comments.
- What happens when `WEBHOOK_PROXY_URL` relay is down or the local server is temporarily unreachable? The relay (smee.io-style) only forwards live connections — it stores and retries nothing itself, and GitHub considers the delivery "delivered" the instant the relay responds `200`, independent of whether the bridge ever received it. A downed relay client or unreachable bridge therefore loses the trigger silently unless a human notices and uses GitHub's delivery-redelivery feature (Settings → Webhooks → Recent Deliveries → Redeliver) — which only succeeds while a relay client is connected again. No additional queuing is added by this feature; this is a best-effort delivery guarantee, not at-least-once.
- What happens when a comment contains a gate keyword as part of unrelated prose rather than as a standalone command? Must not be misinterpreted as a command.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST receive GitHub `issue_comment` (created) webhook deliveries for the target repository.
- **FR-002**: System MUST verify each delivery's signature against a shared secret before any further processing, and MUST discard any delivery that fails verification.
- **FR-003**: System MUST act only on commands (run or gate) from a commenter whose repository permission level — resolved via the installation token, not the webhook payload's own `author_association` field alone — is `write` or `admin`, or whose `author_association` is `OWNER`; all other comments MUST be ignored. (Supersedes the original `OWNER`/`MEMBER`/`COLLABORATOR` `author_association`-only check — `COLLABORATOR` includes read-only collaborators, too coarse for a command that can start a billable run or, once specs/005 lands, clear a security gate.)
- **FR-004**: System MUST act only on comments attached to a pull request; comments on plain issues MUST be ignored by this feature.
- **FR-005**: System MUST recognize a run command of the form `@pipeline-agent run mode=<full|vibe>` (with explicit `agent_name` and `version` arguments, in any order) and start exactly one new pipeline run per distinct `repo`/`agent_name`/`version` triple, identified by a deterministic run identity derived from `repo`, `agent_name`, and `version` only (`mode` does not affect identity — a second run command for the same triple under a different `mode` is treated as targeting the same run). Until `specs/005-pipeline-mode-signals-escalation` ships the relaxed-rigor path, `mode=vibe` MUST be rejected (`outcome="mode_not_supported"`) rather than silently executed as `mode=full`.
- **FR-006**: System MUST NOT start a second run for a run command whose derived identity already matches a run in flight. Duplicate-start detection MUST reserve the delivery ID in the dedup cache before dispatch (not after), using a delivery-ID cache (`X-GitHub-Delivery`) as a fast-path, and MUST also treat a Temporal "workflow already started" collision on the deterministic run ID as authoritative confirmation that no second run was started.
- **FR-007**: System MUST recognize each of the six gate comments (`pm_approved`, `pm_rejected: <feedback>`, `plan_approved`, `plan_rejected: <feedback>`, `security_cleared`, `security_rejected: <feedback>`) and deliver the corresponding decision, including any feedback text, to the one in-flight run tagged with the same `repo` and pull-request number as the comment itself (a gate comment carries neither `agent_name` nor `version` — see the Pipeline Run Identity entity below for how resolution works without them).
- **FR-008**: System MUST route each gate decision to the correct in-flight run only — never to an unrelated run or to no run. Duplicate-signal detection MUST reserve the delivery ID in the dedup cache before dispatch (not after) — gate signals have no Temporal-side collision to fall back on, so reserve-before-dispatch is the only defense FR-008/SC-005 has for signals.
- **FR-009**: System MUST reuse the existing GitHub App identity already used elsewhere in this repository, rather than registering a separate one.
- **FR-010**: System MUST run as a persistent process reachable from GitHub's webhook delivery mechanism without requiring the orchestration engine's own network endpoint to be exposed publicly.
- **FR-011**: System MUST record enough information about ignored/unauthorized/malformed comments (author, comment, reason) to audit why no action was taken, via structured entries written to the bridge process's own stdout/stderr logs (no separate audit store).
- **FR-012**: System MUST attempt delivery of a gate signal even when the target run cannot be found, and MUST report that failure via a structured error log entry (author, comment, reason). System MUST also post a GitHub reaction on the triggering comment — 👀 when the signal was issued, a stand-in reaction (GitHub's reaction API has no literal ❌; the bridge uses 😕 `"confused"`) when the target run could not be found — in addition to the structured log entry.
- **FR-013**: System MUST reject a run command whose PR is a cross-repository (fork) pull request (`isCrossRepository == true`), mirroring `swe-agent-build.yml`'s existing check, and MUST record this via a structured audit log entry rather than starting a run.
- **FR-014**: System MUST act only on deliveries whose `repository.full_name` is in an explicit, operator-configured allowlist (matched case-insensitively, with surrounding whitespace trimmed); deliveries for any other repository MUST be ignored with a structured audit log entry, even if the signature verifies and the author is otherwise allowlisted.
- **FR-015**: System MUST post a GitHub reaction on the triggering comment for every terminal outcome of a run command, not gate signals only — 🚀 `"rocket"` when a run is started, 😕 `"confused"` when the command is rejected or fails for any reason (unauthorized, malformed, fork-rejected, repo-not-allowed, mode-not-supported). A commenter MUST be able to tell whether their comment did anything without reading the bridge's own process logs.
- **FR-016**: Until `specs/005-pipeline-mode-signals-escalation` ships its `@workflow.signal` handlers and `wait_condition` pauses on `AgentPipelineWorkflow`, the operator-configured repo allowlist (FR-014) MUST list only a disposable/test repository, never a real target repository — `AgentPipelineWorkflow.run` today has no human gate at all, so enabling FR-005's run-start path against a real repo before then would let any authorized commenter trigger an unsupervised build-and-register run.

### Key Entities

- **Webhook Delivery**: One inbound GitHub `issue_comment` event — carries the raw comment body, the commenting user's `author_association` and resolved permission level, whether the comment is on a PR or a bare issue, the PR number, the comment ID (for posting reactions), and a signature used to verify authenticity.
- **Pipeline Command**: The parsed intent extracted from an authorized comment — either "start a run" (with mode, agent name, version) or "signal a gate" (which gate, approve/reject, optional feedback text). A gate command never carries `agent_name`/`version` — see Pipeline Run Identity for how it still resolves to exactly one run.
- **Pipeline Run Identity**: The deterministic identifier derived from the target repository plus `agent_name` and `version` (`mode` excluded) used to start a run and to detect a duplicate start. Every started run is additionally tagged with its `repo` and pull-request number as Temporal search attributes at start time — this is what a gate comment (which has no `agent_name`/`version` of its own) resolves against: the bridge looks up the one running workflow whose `repo`/PR-number search attributes match the comment's own PR, rather than reconstructing the run identity string from the gate comment's content.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An authorized run comment results in a new pipeline run starting with no manual orchestration-engine interaction, reliably (i.e. every authorized, correctly-formed run comment that targets a not-yet-running identity starts exactly one run).
- **SC-002**: 100% of webhook deliveries with an invalid signature are rejected before any comment content is acted on.
- **SC-003**: 100% of comments from commenters below the required permission level produce no pipeline action.
- **SC-004**: Each of the six gate decisions, when posted by an authorized commenter on an in-flight run's PR, reaches that specific run with no manual signal delivery.
- **SC-005**: Redelivery of an identical run or gate comment (same `X-GitHub-Delivery` ID) never results in a duplicate run or a duplicate signal delivery. (Scoped to redelivery of the same delivery ID — a human posting the same gate decision twice as two genuinely distinct comments is a workflow-side idempotency concern for `specs/005-pipeline-mode-signals-escalation`, not this bridge.)

## Assumptions

- Resolution of `agent_name`/`version` from a bare *run* comment (without explicit arguments) or from the PR's branch name is out of scope for this feature — this spec assumes both are supplied as explicit arguments in the run comment, per the design doc's own open question (§9). Gate comments never needed this resolution in the first place — they resolve via the PR's own `repo`/PR-number, tagged onto the run at start time (see Pipeline Run Identity).
- The `version` comment argument is a bare value with no `v` prefix (e.g. `version=3`, not `version=v3`) — the workflow-ID template supplies the `v` itself.
- The orchestration engine (Temporal) is already running and reachable from the same host this bridge runs on; this feature does not change that engine's own network exposure. The bridge connects once at startup and refuses to start if that connection fails (fail-closed, matching the `GH_WEBHOOK_SECRET` behavior).
- The existing GitHub App identity used elsewhere in this repository is reused; no second GitHub App is registered.
- Local reachability from GitHub (the bridge has no public IP) is solved by an external relay (e.g. smee.io-style) forwarding deliveries to the bridge's local port; operating that relay's own uptime/security is not in scope for this feature. The relay channel URL (`WEBHOOK_PROXY_URL`) MUST be treated as a secret, not ordinary config — smee.io-style channels are public and unauthenticated, so anyone who obtains the URL can read every relayed delivery in full (private PR comment bodies, author logins, repo names) even though they cannot forge one past the HMAC check.
- Only the six named gate comments and the one run command are in scope; any other comment grammar is future work.
