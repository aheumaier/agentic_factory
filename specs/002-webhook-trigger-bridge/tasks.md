---

description: "Task list for Webhook Trigger Bridge"

---

# Tasks: Webhook Trigger Bridge

**Input**: Design documents from `/specs/002-webhook-trigger-bridge/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/webhook-http-contract.md, contracts/temporal-call-contract.md, quickstart.md

**Tests**: Included — plan.md/research.md specify `pytest` + `pytest-asyncio` as dev deps and quickstart.md names the test command; treated as requested.

**Organization**: Tasks are grouped by user story (spec.md P1/P1/P2) to enable independent implementation and testing.

**Revision note**: This revision closes the gate-identity gap (C1: gate
comments carry no `agent_name`/`version` — resolved via Temporal search
attributes, not comment grammar), the pre-005 unsupervised-run risk (C2:
`BRIDGE_ALLOWED_REPOS` restricted to disposable/test repos, see spec.md
FR-016), and the High/Medium/Low findings from the second architect
review (permission-level authorization, reserve-before-dispatch dedup,
universal reactions, `/`-delimited workflow IDs, `audit.py` as its own
module, a real-Temporal integration test, and the env/README/pytest-config
gaps). Task IDs have been renumbered from the prior revision.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

## Path Conventions

Single component inside the existing `orchestration/` project (plan.md
Structure Decision): `orchestration/webhook_bridge/` for source,
`orchestration/webhook_bridge/tests/` for tests.

---

## Phase 1: Setup

**Purpose**: Project/package initialization, environment/docs prerequisites

- [X] T001 [P] Create `orchestration/webhook_bridge/` package skeleton: `__init__.py`, empty `server.py`, `auth.py`, `grammar.py`, `dedup.py`, `audit.py`, `temporal_client.py`, `github_app.py`, and `orchestration/webhook_bridge/tests/__init__.py`, per plan.md Project Structure
- [X] T002 Add `aiohttp`, `PyJWT`, and `cryptography` as runtime dependencies; pin `temporalio>=1.32.0` (was unpinned — matches what `uv.lock` already resolves, research.md/H6); add `pytest`/`pytest-asyncio` to `dependency-groups.dev`; add `[tool.pytest.ini_options] asyncio_mode = "auto"` — all in `orchestration/pyproject.toml` (no such pytest section exists there today; without it async tests error/skip)
- [X] T003 [P] Add a `bridge` target to `Makefile` that runs `npx smee-client --url "$WEBHOOK_PROXY_URL" --target "http://localhost:${BRIDGE_PORT:-3000}/webhook"` and the bridge server as sibling processes, with a `trap`/`wait` so that if the `smee-client` leg dies the target exits non-zero and reports it instead of leaving the bridge server orphaned and silently unreachable (mitigates A1's blast radius operationally), per quickstart.md
- [X] T004 [P] Register the `TargetRepo` (`Keyword`) and `PRNumber` (`Int`) custom search attributes on the local Temporal server (`temporal operator search-attribute create --name TargetRepo --type Keyword` and `--name PRNumber --type Int`, one-time per namespace against `make up`'s Temporal), and confirm both attributes exist before Phase 4 work begins — data-model.md's `GateTargetResolution` and T024/T032 depend on this; no application code, but the bridge's gate-routing is unimplementable without it
- [X] T005 [P] Update `.env.example` with `GH_WEBHOOK_SECRET`, `WEBHOOK_PROXY_URL` (comment marking it secret — research.md's confidentiality addendum), `BRIDGE_PORT`, `BRIDGE_ALLOWED_REPOS` (comment: disposable/test repos only pre-005, FR-016), `SWE_AGENT_APP_ID`, and `SWE_AGENT_APP_PRIVATE_KEY` (placeholder + comment documenting the base64-encoded-PEM convention, research.md)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared HTTP/auth/dedup/audit/Temporal-client/GitHub-App plumbing every command (run or gate) passes through before any story-specific dispatch runs

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T006 Implement `verify_signature(raw_body, signature_header, secret)` (HMAC-SHA256 over raw body via `hmac.compare_digest`/`hashlib.sha256`) in `orchestration/webhook_bridge/auth.py` (FR-002)
- [X] T007 Implement GitHub App installation-token minting/caching in `orchestration/webhook_bridge/github_app.py`: sign a JWT with `SWE_AGENT_APP_PRIVATE_KEY` (base64-decoded PEM)/`SWE_AGENT_APP_ID` (`PyJWT`, RS256, ≤10 min `exp`), exchange it for an installation access token via the GitHub REST API using `aiohttp.ClientSession` with a timeout, cache the result in memory until shortly before its ~1h expiry, and never log the token value (FR-009, research.md/A5). **Moved ahead of `is_authorized`** — T008 now depends on this token to check permission level, not just T025's branch/fork resolution
- [X] T008 [P] Implement `is_authorized(github_client, repo, author_login, author_association)` in `orchestration/webhook_bridge/auth.py`: `author_association == "OWNER"` is a fast-path; otherwise call `GET /repos/{repo}/collaborators/{author_login}/permission` via the installation token (T007) and require `permission ∈ {"write", "admin"}` (FR-003, research.md/H2 — supersedes the original `author_association`-only `OWNER`/`MEMBER`/`COLLABORATOR` check, which included read-only collaborators) (depends on T007)
- [X] T009 [P] Implement bounded in-memory `DeliveryCache` with a single atomic `reserve(delivery_id) -> bool` (returns `True` and marks-seen in one step if not already seen, `False` if already seen — check and mark MUST NOT be two separate steps with an `await` between them, closing the TOCTOU race research.md/H3 identifies) in `orchestration/webhook_bridge/dedup.py`, size/TTL-bounded (FR-006/FR-008, data-model.md)
- [X] T010 Implement structured audit logging in its own `orchestration/webhook_bridge/audit.py` module — NOT `server.py` (research.md/M3: `server.py` imports `temporal_client.py` for dispatch, and `temporal_client.py` needs to emit `signal_failed`/`signal_issued_no_handler`, so putting the logger in `server.py` would create a circular import): stdlib `logging`, one JSON-shaped line per `AuditLogEntry` (`author`, `comment`, `reason`, `outcome ∈ {ignored, permission_denied, malformed, signal_failed, fork_rejected, repo_not_allowed, signal_issued_no_handler, duplicate_ignored, mode_not_supported}` — `permission_denied` renamed from `unauthorized` per T008's change) (FR-011/FR-012, data-model.md's extended outcome enum)
- [X] T011 Implement `WebhookDelivery` extraction from the raw aiohttp request (`delivery_id`, `signature`, `raw_body`, `is_pull_request`, `author_association`, `author_login`, `comment_body`, `repo`, `pr_number`, `comment_id`) in `orchestration/webhook_bridge/server.py`, per data-model.md
- [X] T012 Implement the aiohttp app and `POST /webhook` route in `orchestration/webhook_bridge/server.py`: bind `127.0.0.1` only (never all interfaces, A11); set `client_max_size` (e.g. 1MB) since HMAC verification requires buffering the full raw body first (research.md/L4); refuse to start if `GH_WEBHOOK_SECRET` is empty/unset OR if the initial `Client.connect` (T013) fails (fail closed on both, A11/M4); handle `SIGTERM` gracefully (stop accepting connections, close the Temporal client — `make bridge` runs this under a `trap`/`wait`, research.md/L7); enforce dispatch order — signature verify (`401` on failure, before any parsing) → `X-GitHub-Event`/`action` filter (`202` no-op, `outcome=ignored`) → missing-`X-GitHub-Delivery` check (`202`, `outcome=malformed`, research.md/L3) → `is_pull_request` check (`202` no-op, `outcome=ignored`, FR-004) → repo allowlist check, case-insensitive and whitespace-trimmed (`202` + `outcome=repo_not_allowed` if `repo` not in `BRIDGE_ALLOWED_REPOS`, FR-014) → `is_authorized` (T008) check (`202` + audit log `outcome=permission_denied`) — per `contracts/webhook-http-contract.md` (depends on T006, T008, T010, T011)
- [X] T013 Implement Temporal client connection setup (`Client.connect("localhost:7233")`, mirroring `orchestration/worker.py`) in `orchestration/webhook_bridge/temporal_client.py`; connect once at process startup, and propagate a connect failure so `server.py` (T012) can fail closed rather than starting and failing per-request (M4)
- [X] T014 [P] Unit tests for `auth.py` signature verification (valid/invalid/missing signature) in `orchestration/webhook_bridge/tests/test_auth.py`
- [X] T015 [P] Unit tests for `auth.py` `is_authorized` permission-level check (mocked `github_client`: `write`/`admin`/`read`/`none` permission responses, plus the `OWNER` fast-path skipping the API call entirely) in `orchestration/webhook_bridge/tests/test_auth.py`
- [X] T016 [P] Unit tests for `dedup.py` `DeliveryCache.reserve()` (first call for an ID returns `True` and marks it; a second call for the same ID returns `False`; bound behavior) in `orchestration/webhook_bridge/tests/test_dedup.py`
- [X] T017 [P] Unit tests for `audit.py` (structured log line shape per outcome, and the outcome→reaction-content mapping used by T028/T034: `started`→`"rocket"`, `signal_issued_no_handler`/success→`"eyes"`, every rejection/failure→`"confused"`) in `orchestration/webhook_bridge/tests/test_audit.py`
- [X] T018 [P] Unit tests for `github_app.py` token minting/caching against a mocked HTTP client (JWT signed with the right claims, token cached and reused before expiry, re-minted after expiry, token value never appears in log output) in `orchestration/webhook_bridge/tests/test_github_app.py`
- [X] T019 [P] Tests for `server.py` startup behavior: refuses to start with empty/missing `GH_WEBHOOK_SECRET` (fail closed); refuses to start if the initial Temporal connect fails (fail closed, M4); binds `127.0.0.1` not `0.0.0.0` (A11); rejects a body larger than `client_max_size` in `orchestration/webhook_bridge/tests/test_server.py`

**Checkpoint**: Server authenticates by permission level, filters non-PR/unauthorized/disallowed-repo traffic, logs via `audit.py`, dedups via reserve-before-dispatch, and can mint a GitHub App token — ready for command-specific dispatch.

---

## Phase 3: User Story 1 - Start a pipeline run from a PR comment (Priority: P1) 🎯 MVP

**Goal**: An authorized `@pipeline-agent run mode=<full|vibe> agent=<name> version=<version>` comment (tokens in any order) on a same-repo, allowlisted PR starts exactly one new `AgentPipelineWorkflow` run per distinct `repo`/`agent_name`/`version`, tagged with `TargetRepo`/`PRNumber` search attributes so a later gate comment can find it (US2/Phase 4 depends on this tagging).

**Independent Test**: Post the run comment on a PR with no in-flight run for that identity; verify a `start_workflow` call is issued once with the deterministic ID and search attributes, and a redelivery/second comment issues no second call (quickstart.md US1).

### Tests for User Story 1

- [X] T020 [P] [US1] Grammar test: `@pipeline-agent run` followed by `mode=(full|vibe)`, `agent=...`, `version=...` in **any order**, each exactly once → `RunCommand`; a comment matching the design doc's own `agent=... version=... mode=full` ordering MUST also parse (research.md/L1) — in `orchestration/webhook_bridge/tests/test_grammar.py`
- [X] T021 [P] [US1] Contract test: `start_workflow` call shape (target referenced by name string `"AgentPipelineWorkflow"`, `args=[repo, branch, agent_name, version]`, `id=f"pipeline/{repo}/{agent_name}/v{version}"` — `/`-delimited, no slug munging — `task_queue="agent-factory-pipeline"`, `id_conflict_policy=WorkflowIDConflictPolicy.FAIL` pinned explicitly, `search_attributes={"TargetRepo": [repo], "PRNumber": [pr_number]}`) against a mocked `Client`, including `WorkflowAlreadyStartedError` → treated as no-op, in `orchestration/webhook_bridge/tests/test_temporal_client.py`

### Implementation for User Story 1

- [X] T022 [US1] Implement `RunCommand` parsing (`mode`, `agent_name`, `version`), tokens in any order, in `orchestration/webhook_bridge/grammar.py`, per research.md's revised anchored regex rule
- [X] T023 [US1] Implement a slug-validation helper (`agent_name`/`version` MUST match a fixed slug regex disallowing `/`, e.g. `^[A-Za-z0-9][A-Za-z0-9._-]*$`) and reject a `RunCommand`/`GateCommand` whose values don't match, before either is ever used to build a `workflow_id`, in `orchestration/webhook_bridge/grammar.py`
- [X] T024 [US1] Implement `workflow_id(repo, agent_name, version)` → `f"pipeline/{repo}/{agent_name}/v{version}"` (no slug normalization — `repo`'s single `/` can't be confused with a field boundary since `agent_name`/`version` are validated `/`-free, closing both A3's cross-repo collision and the follow-on slug-boundary collision, research.md/M2) in `orchestration/webhook_bridge/temporal_client.py` (data-model.md `PipelineRunIdentity`) (depends on T023)
- [X] T025 [US1] Implement `start_run(client, repo, pr_number, branch, agent_name, version)` in `orchestration/webhook_bridge/temporal_client.py`: `client.start_workflow("AgentPipelineWorkflow", args=[repo, branch, agent_name, version], id=workflow_id(...), task_queue="agent-factory-pipeline", id_conflict_policy=WorkflowIDConflictPolicy.FAIL, search_attributes={"TargetRepo": [repo], "PRNumber": [pr_number]})` — workflow referenced by registered name string, not by importing `AgentPipelineWorkflow` (avoids `activities.py`'s module-level side effects, A11) — catching `WorkflowAlreadyStartedError` and returning a "no second run" result rather than raising (depends on T024)
- [X] T026 [US1] Implement branch + fork resolution in `orchestration/webhook_bridge/server.py`: using the installation token (T007), one non-blocking `aiohttp` call with an explicit timeout to `GET /repos/{repo}/pulls/{pr_number}`, reading `head.ref` (→ `branch`) and `head.repo.full_name != base.repo.full_name` (→ `is_cross_repository`) from the same response — not `subprocess.run`, not the `gh` CLI (FR-009, A8) (depends on T007)
- [X] T027 [US1] Implement fork/cross-repo refusal (FR-013) in `orchestration/webhook_bridge/server.py`: `is_cross_repository == true` → `202` + audit log `outcome="fork_rejected"` + 😕 reaction, no `start_run` call (depends on T026)
- [X] T028 [US1] Implement pre-005 `mode` gating in `orchestration/webhook_bridge/server.py`: `mode == "vibe"` → `202` + audit log `outcome="mode_not_supported"` + 😕 reaction, no `start_run` call, until `specs/005-pipeline-mode-signals-escalation` ships (FR-005, research.md)
- [X] T029 [US1] Wire `RunCommand` dispatch in `orchestration/webhook_bridge/server.py`, in order: `DeliveryCache.reserve()` (T009; `False` → audit log `outcome="duplicate_ignored"`, no reaction, stop) → resolve branch/fork (T026) → fork refusal (T027) → `mode_not_supported` gate (T028) → `start_run` (T025) → post reaction (🚀 `"rocket"` on success, 😕 `"confused"` on any of the above rejections, via `github_app.py`'s reactions helper) → `202` response (depends on T022, T025, T026, T027, T028)

**Checkpoint**: User Story 1 fully functional and independently testable per quickstart.md.

---

## Phase 4: User Story 2 - Advance a running pipeline via gate comments (Priority: P1)

**Goal**: Each of the six gate comments (`pm_approved`, `pm_rejected:<feedback>`, `plan_approved`, `plan_rejected:<feedback>`, `security_cleared`, `security_rejected:<feedback>`) signals the one in-flight run tagged with the same `repo`/`pr_number` as the comment — resolved via Temporal search attributes (T004's prerequisite), never by reconstructing `agent_name`/`version` from the gate comment, which never carries them.

**Independent Test**: With a run in flight, post each of the six gate comments in turn and verify each reaches that run's workflow ID only (quickstart.md US2).

### Tests for User Story 2

- [X] T030 [P] [US2] Grammar tests for all six gate comments (exact match for `*_approved`/`security_cleared`; `^(pm_rejected|plan_rejected|security_rejected):\s*(.+)$` for the rejection forms) in `orchestration/webhook_bridge/tests/test_grammar.py`
- [X] T031 [P] [US2] Contract test: `list_workflows` resolution query (`TargetRepo = '{repo}' AND PRNumber = {pr_number} AND ExecutionStatus = 'Running'`) returning 0/1/2+ matches (0 and 2+ → `outcome="signal_failed"` with distinct `reason`s, closes C1); for the 1-match case, bare `handle.signal(signal_name)` (no payload) for `pm_approved`/`plan_approved`/`security_cleared`, and `handle.signal(signal_name, feedback)` for the three rejection forms, per `contracts/temporal-call-contract.md`'s table — plus a "not found" signal error caught without crashing → `outcome="signal_failed"` + a mocked `github_client` reaction call `POST .../reactions {"content":"confused"}` on `comment_id`, and a successfully-issued signal logged as `outcome="signal_issued_no_handler"` + `POST .../reactions {"content":"eyes"}` on `comment_id` — against a mocked `Client` and mocked `github_client`, in `orchestration/webhook_bridge/tests/test_temporal_client.py`

### Implementation for User Story 2

- [X] T032 [US2] Implement `GateCommand` parsing (`gate`, `decision`, `feedback` — no `agent_name`/`version` fields, data-model.md) in `orchestration/webhook_bridge/grammar.py`, per research.md's anchored regex rule and T023's slug validation (depends on T022 — same file)
- [X] T033 [US2] Implement `resolve_gate_target(client, repo, pr_number)` in `orchestration/webhook_bridge/temporal_client.py`: `client.list_workflows(query=f"TargetRepo = '{repo}' AND PRNumber = {pr_number} AND ExecutionStatus = 'Running'")`, returning the one matching workflow handle; zero or multiple matches raise a distinguishable "target not resolved" condition for the caller to turn into `outcome="signal_failed"` (data-model.md's `GateTargetResolution`, closes C1) (depends on T004's search-attribute prerequisite)
- [X] T034 [US2] Implement `signal_gate(client, repo, pr_number, gate, decision, feedback, comment_id, github_client)` in `orchestration/webhook_bridge/temporal_client.py`: resolves the target handle via `resolve_gate_target` (T033), maps `(gate, decision)` → signal name per `contracts/temporal-call-contract.md`'s table, calls `handle.signal(signal_name)` (bare) or `.signal(signal_name, feedback)` (rejections only), catches "not found"/zero-or-multiple-match as `outcome="signal_failed"` + `POST .../reactions {"content":"confused"}` on `comment_id` via `github_client` rather than raising (FR-012), and on success logs `outcome="signal_issued_no_handler"` + `POST .../reactions {"content":"eyes"}` on `comment_id` (A9/A10) — a reaction-POST failure itself is caught and logged as a warning, never allowed to crash the handler or mask the signal outcome (research.md) (depends on T007, T033)
- [X] T035 [US2] Wire `GateCommand` dispatch in `orchestration/webhook_bridge/server.py`: `DeliveryCache.reserve()` (T009; `False` → `outcome="duplicate_ignored"`, no reaction, stop — this is the *only* defense against a double-signal, since gate signals have no Temporal-side collision, research.md/H3) → `signal_gate` (T034), passing `comment_id` (data-model.md `WebhookDelivery`) and the installation-token `github_client` (T007) → `202` response (depends on T007, T032, T034)

**Checkpoint**: User Stories 1 and 2 both independently functional.

---

## Phase 5: User Story 3 - Ignore comments from unauthorized or unrecognized sources (Priority: P2)

**Goal**: Comments from commenters below the required permission level, disallowed repos, fork PRs, invalid-signature deliveries, unrecognized/prose-embedded text, and unsupported `mode` values produce no pipeline action, with audit-log visibility and a reaction for every rejected case that has a comment to react to.

**Independent Test**: Post a run/gate comment from a non-allowlisted account, and separately deliver a payload with an invalid signature; verify neither results in any pipeline action (quickstart.md US3).

### Tests for User Story 3

- [X] T036 [P] [US3] Test: commenter below the required permission level on a run/gate comment → `202`, audit log `outcome="permission_denied"`, 😕 reaction posted, no `start_workflow`/`signal` call, in `orchestration/webhook_bridge/tests/test_auth.py`
- [X] T037 [P] [US3] Test: invalid `X-Hub-Signature-256` → `401`, no comment-content parsing or logging before the signature check, in `orchestration/webhook_bridge/tests/test_auth.py`
- [X] T038 [P] [US3] Grammar test: gate keyword embedded in prose (e.g. `"this looks great, pm_approved of it I think"`) → no match (`None`), in `orchestration/webhook_bridge/tests/test_grammar.py`
- [X] T039 [P] [US3] Test: run command on a fork PR (`is_cross_repository == true`) → `202`, audit log `outcome="fork_rejected"`, 😕 reaction, no `start_workflow` call, in `orchestration/webhook_bridge/tests/test_server.py` (FR-013, A4)
- [X] T040 [P] [US3] Test: run/gate comment for a `repo` not in `BRIDGE_ALLOWED_REPOS`, including a case/whitespace variant of an allowlisted entry that MUST still match → `202`, audit log `outcome="repo_not_allowed"` only for genuinely disallowed repos, no branch-resolution API call and no `start_workflow`/`signal` call, in `orchestration/webhook_bridge/tests/test_server.py` (FR-014, A3)
- [X] T041 [P] [US3] Test: `mode=vibe` → `202`, `outcome="mode_not_supported"`, 😕 reaction, no run started; `mode=turbo` (unrecognized value) → same `outcome="mode_not_supported"`, distinguished from a fully unrecognized comment's `outcome="malformed"`, in `orchestration/webhook_bridge/tests/test_server.py` (research.md/M6, L8)

### Implementation for User Story 3

- [X] T042 [US3] Implement the malformed-comment path in `orchestration/webhook_bridge/server.py` dispatch: an authorized, PR-scoped, allowlisted-repo comment for which `grammar.py` returns neither a `RunCommand` nor a `GateCommand` → `202` + audit log `outcome="malformed"`, no run/signal call, no reaction (no recognized command means no confidently-attributable comment context) (depends on T012, T022, T032)

**Checkpoint**: All three user stories independently functional per quickstart.md.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T043 [P] Run `uv run --directory orchestration pytest webhook_bridge/` (path is relative to `--directory`; the earlier `orchestration/webhook_bridge/` form double-prefixed and would not resolve, research.md/M7) and confirm all tests pass
- [X] T044 Add one real-Temporal integration test in `orchestration/webhook_bridge/tests/test_integration.py`: against a running `make up` Temporal instance, start a throwaway workflow by name string, tag it with the search attributes, resolve it via `resolve_gate_target`, and signal it — confirming the actual SDK surface (`WorkflowIDConflictPolicy`'s import path, `list_workflows`' query syntax, `WorkflowAlreadyStartedError`'s exception path) round-trips, since every other Temporal-facing test (T021, T031) runs against a mock (research.md/H6)
- [X] T045 Update `README.md`/`CLAUDE.md`'s layer table to record `orchestration/webhook_bridge/`'s state once implemented (research.md/M5 — no prior revision of this task list had a task for this, and repo convention treats that table as the map of what's real)
- [ ] T046 Execute quickstart.md's three validation sections end-to-end (`make up`, the search-attribute prerequisite from T004, `make bridge`, real PR comments against a disposable test PR per FR-016), including the permission-level rejection, fork-PR rejection, repo-allowlist rejection, `mode=vibe` rejection, and universal comment-reaction paths, and confirm SC-001–SC-005

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories. Internally: T007 (GitHub App token) BLOCKS T008 (permission check) and T026 (branch/fork resolution); T013 (Temporal connect) BLOCKS T012 (server fail-closed-on-unreachable)
- **User Story 1 (Phase 3)**: Depends on Foundational only
- **User Story 2 (Phase 4)**: Depends on Foundational, **and on T004's search-attribute registration and T025's search-attribute tagging at start time** — a gate comment cannot resolve a target that US1's `start_run` never tagged. Shares `grammar.py`/`temporal_client.py` files with US1 (T032 after T022, both touch `grammar.py`) but adds no *behavioral* dependency on US1's dispatch beyond the tagging
- **User Story 3 (Phase 5)**: Depends on Foundational (permission/allowlist checks already exist there) and on T012/T022/T026/T032 existing so there is a dispatch path, a branch/fork resolution, and a grammar result to test against "no match" — this story is verification + a few new branches, not new plumbing
- **Polish (Phase 6)**: Depends on all three stories

### Parallel Opportunities

- T003, T004, T005 parallel to each other and to T001/T002
- T008, T009 parallel to each other (different files/functions); both still ordered after T007 for T008 specifically
- T014, T015, T016, T017, T018, T019 parallel (different test files/functions)
- T020, T021 parallel (different test files); T030, T031 parallel; T036, T037, T038, T039, T040, T041 parallel
- US1 and US2 implementation tasks can proceed in parallel by two developers once Foundational **and T004** are done, coordinating only on `grammar.py`/`temporal_client.py` edits (T022 vs T032; T025 vs T033/T034) — but US2's own tests (T031) still need US1's search-attribute tagging (T025) to have something real to resolve against in an integration sense, even though the contract test itself mocks it

---

## Parallel Example: User Story 1

```bash
Task: "Grammar test for RunCommand (order-insensitive tokens) in orchestration/webhook_bridge/tests/test_grammar.py"
Task: "Contract test for start_workflow call shape (incl. search attributes) in orchestration/webhook_bridge/tests/test_temporal_client.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Setup → Foundational → User Story 1
2. **STOP and VALIDATE**: run quickstart.md's US1 section against a real Temporal instance (search attributes registered per T004)
3. This alone proves the run-start path (SC-001) end-to-end

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. + User Story 1 → validate → MVP
3. + User Story 2 → validate gate-signal resolution and call shape (workflow-side advancement itself is out of scope until 005 lands, per plan.md's scope boundary — and per FR-016, `BRIDGE_ALLOWED_REPOS` stays disposable-repo-only until then regardless)
4. + User Story 3 → validate rejection paths (SC-002/SC-003, plus fork/allowlist/mode rejection)
5. Polish → full suite + one real-Temporal integration test + manual quickstart pass
