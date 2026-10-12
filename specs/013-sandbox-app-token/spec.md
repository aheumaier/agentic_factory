# Feature Specification: Per-Run GitHub App Token for the Build Sandbox

**Feature Branch**: `013-sandbox-app-token`

**Created**: 2026-10-11

**Status**: Draft

**Input**: User description: "Each swe-agent E2B sandbox run on the Temporal path gets its own GitHub App installation token, minted just before the sandbox is created, for the one target repo only (contents: write, pull_requests: write, metadata: read), instead of the worker's personal GH_TOKEN (a fine-grained PAT that lets the agent act as the operator and merge its own PRs). Reuse the webhook bridge's App client rather than writing a second minter. The token lives 1 hour; a build that outlives it fails on push — a stated limit. Each 011 seat handoff starts a new sandbox and mints a new token. Minting failure fails the run; never fall back to the personal token. PRs opened in the sandbox are authored by the App's bot account so the operator can approve them. Operator step after merge (quickstart, not code): 1 required approval on main, enforce_admins false. The token must never appear in a log line, exception message, or Temporal payload."

Design input: the handoff prompt of 2026-10-11 (`.handoff/2026-10-11-dogfood-next-PROMPT.md`, untracked), `specs/002-webhook-trigger-bridge/` (the App client this feature reuses), `specs/009-credential-pool-handoff/` and `specs/011-seat-pool-hardening/` (seat handoffs, which each start a new sandbox).

## Usage Constraint *(binding, restated from 009 and 011)*

This capability is for **internal, single-operator use only**:
- The subscription seats in the pool belong to the operator who runs this pipeline.
- The pipeline and its seat pool are never offered as a product or service to third parties.
- Seat login or rate limits are never exposed to anyone else's product.

This follows from the Agent SDK's terms ("Unless previously approved, Anthropic does not allow third party developers to offer claude.ai login or rate limits for their products"). Rotating several subscription seats to extend usage limits is a grey area under the Consumer Terms, chosen knowingly by the operator on 2026-10-10. Every artifact this feature produces MUST restate this constraint and MUST NOT present seat pooling as a supported product feature.

The GitHub App of this feature is likewise private to the operator: it is installed only on the operator's own repositories and is not offered to anyone else.

## Clarifications

### Session 2026-10-11

- Q: When the worker cannot get the App token, what happens? → A: Retry only on network errors and GitHub 5xx answers, 3 tries in total a few seconds apart, then fail the run. A 4xx answer (App not installed, bad key, wrong rights) fails at once. Never fall back to the personal token. *Operator-confirmed, 2026-10-11.*

## Why

Today every Build sandbox receives the worker's own `GH_TOKEN`, a fine-grained personal access token. Inside the sandbox the model can run any `git` or `gh` command, so it can act as the operator: push to any repo the token reaches, and approve or merge its own pull requests. Branch protection cannot tell the agent's work from the operator's, because both carry the operator's name.

After this feature, the sandbox holds a short-lived token that belongs to the App's bot account and reaches only the one target repo, with only the rights a Build needs. The operator's own token never enters a sandbox. Pull requests are opened by the bot, so the operator can review and approve them as a second person, and a required approval on `main` becomes a real check on the agent.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The Build sandbox works with a token for the target repo only (Priority: P1)

The operator starts a pipeline run for a target repo. Just before the Build sandbox is created, the worker obtains a fresh App token that reaches only that repo, with only "write code", "write pull requests" and "read metadata". The sandbox receives that token and no other GitHub credential. The agent clones, commits, pushes and opens its pull request exactly as before.

**Why this priority**: This is the whole security gain. Without it the agent keeps the operator's full reach.

**Independent Test**: Run the Build activity with the App client replaced by a fake that returns a known dummy token. Check that the sandbox environment carries the dummy token, that it carries no value of the worker's own `GH_TOKEN`, and that the fake was asked for exactly the target repo and exactly the three rights.

**Acceptance Scenarios**:

1. **Given** a run for `owner/repo`, **When** the Build sandbox is created, **Then** its GitHub token is a freshly obtained App token, not the worker's own token.
2. **Given** that token, **When** it was requested, **Then** the request named only `repo` and only the rights "contents: write", "pull requests: write" and "metadata: read".
3. **Given** the worker's own `GH_TOKEN` is set, **When** the sandbox is created, **Then** its value appears nowhere in the sandbox environment.
4. **Given** the sandbox run finishes, **When** the agent opened a pull request, **Then** the pull request's author is the App's bot account (`<app-slug>[bot]`), not the operator.

---

### User Story 2 - A failure to obtain the token stops the run safely (Priority: P1)

If the worker cannot obtain the App token (the App is not installed on the target repo, its key is missing or wrong, or GitHub answers with an error), the run fails with an error that says so and names the repo. It never falls back to the operator's token.

**Why this priority**: A silent fallback would undo User Story 1 exactly when something is misconfigured, which is when nobody is watching.

**Independent Test**: Make the fake App client fail. Check that no sandbox is created, that the error is recognisable as a token failure and names the repo, and that it contains no credential value.

**Acceptance Scenarios**:

1. **Given** the App is not installed on the target repo, **When** the Build starts, **Then** the run fails with a token error naming the repo, and no sandbox is created.
2. **Given** the App settings are missing from the worker's environment, **When** the Build starts, **Then** the run fails the same way, and the worker's own `GH_TOKEN` is not used instead.
3. **Given** a token failure, **When** the workflow handles it, **Then** it does not count as a seat handoff and the seat is released as for any other non-seat failure.

---

### User Story 3 - Every sandbox gets its own token (Priority: P2)

Each new sandbox gets a newly obtained token: each Build attempt after Eval-Gate feedback, and each seat handoff (specs/009, specs/011) that starts a successor sandbox. A token is never reused from an earlier sandbox.

**Why this priority**: The token lives one hour. A successor that reused its predecessor's token could start with only minutes left. Fresh tokens also limit what one leaked token can do.

**Independent Test**: Call the Build activity twice for the same repo (handoff 0, then handoff 1) with the fake App client. Check that the fake was asked twice and that each sandbox got the token from its own request.

**Acceptance Scenarios**:

1. **Given** a seat handoff, **When** the successor sandbox is created, **Then** it receives a token obtained for it, not the predecessor's.
2. **Given** two Build attempts in one run, **When** each sandbox is created, **Then** each receives its own token.

---

### User Story 4 - The token is never written down (Priority: P1)

The token exists only in the worker process, for as long as it takes to start the sandbox, and in the sandbox's environment. It never appears in a log line, an error message, an activity argument or result, a workflow payload or a pull-request comment, even when the agent's own output inside the sandbox contains it.

**Why this priority**: Temporal keeps workflow history, and worker logs are kept too. A token written there can be read by anyone who can read those, for as long as it is valid.

**Independent Test**: With the fake App client, make the sandbox fail and put the dummy token into its stdout and stderr. Check that the token does not appear in the raised error, in any captured log record, in the activity's arguments or in its result.

**Acceptance Scenarios**:

1. **Given** a successful Build, **When** the activity returns, **Then** its result contains no token.
2. **Given** the sandbox fails and its output contains the token, **When** the activity raises, **Then** the error message contains no token.
3. **Given** a token failure from GitHub, **When** the error is raised, **Then** it contains no token and no App private key.

---

### Edge Cases

- **Build outlives the token.** The token lives 1 hour (3600 s) from the moment it is obtained. After the token is obtained, only starting the sandbox (at most 60 s) and the agent's command (stopped after 3300 s) remain, so the agent's last push happens before the token expires. Retries while obtaining the token happen before it exists and don't count. If those limits are ever raised, a long Build could reach its final push with an expired token; that push would fail like any other non-seat sandbox failure. A test pins the limits (architect finding A6).
- **Target repo is not one the App is installed on.** Treated as a token failure (User Story 2), before any sandbox exists.
- **Target repo is the factory repo itself.** Allowed, as today, if the App is installed there. The token reaches only that repo.
- **The agent tries to change `.github/workflows/`.** A push that changes workflow files needs a right this feature does not request, so GitHub rejects it. Out of scope; noted for the operator.
- **Transient GitHub error while obtaining the token.** A network error or a 5xx answer is retried, 3 tries in total a few seconds apart (FR-005). If all 3 fail, the run fails; never with the personal token.
- **Worker started without the App settings.** Detected when the first Build starts, not at worker boot (the bridge and other activities don't need them). Fails the run per User Story 2.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Before each Build sandbox is created, the worker MUST obtain a new GitHub App installation token for the target repo of that run.
- **FR-002**: The token MUST be limited to the target repo alone, and to exactly these rights: contents write, pull requests write, metadata read.
- **FR-003**: The sandbox MUST receive that token as its only GitHub credential. The worker's own `GH_TOKEN` MUST NOT be passed into the sandbox, under any name.
- **FR-004**: Each sandbox MUST get a token obtained for it: every Build attempt and every seat handoff obtains a new one. A token MUST NOT be reused across sandboxes, so any token cache in the shared App client MUST NOT serve these requests.
- **FR-005**: If the token cannot be obtained, the Build MUST fail before any sandbox is created, with an error that identifies a token failure and names the target repo. A network error or a GitHub 5xx answer MUST be retried first, 3 tries in total a few seconds apart; a 4xx answer MUST fail at once. There MUST be no fallback to any other credential.
- **FR-006**: A token failure MUST NOT be treated as a seat outcome: it charges no seat handoff, and the seat is released as for any other non-seat failure.
- **FR-007**: The token MUST exist only in worker memory and in the sandbox environment. It MUST NOT be an activity argument, an activity result, a signal or query payload, or part of any value recorded in workflow history.
- **FR-008**: The token, the worker's own `GH_TOKEN` and the App private key MUST NOT appear in any log line or error message the worker produces, including errors that quote the sandbox's own output.
- **FR-009**: Obtaining tokens MUST reuse the webhook bridge's existing App client (its signing, installation lookup and token exchange), extended where needed. There MUST be no second implementation of the exchange.
- **FR-010**: The App's identity and private key MUST come from the worker's environment, using the names already documented in `.env.example` (`SWE_AGENT_APP_ID`, `SWE_AGENT_APP_PRIVATE_KEY`).
- **FR-011**: The feature's quickstart MUST describe the operator's one-time steps: create and install the App (rights as in FR-002, no administration right), put its ID and key in `.env`, and, after this feature is merged, set branch protection on `main` to 1 required approval with admin enforcement off.
- **FR-012**: The feature MUST leave unchanged: the worker's own use of `GH_TOKEN` outside the sandbox, the GitHub-comment trigger path, and the patch IDs `seat-pool-v1`, `architect-seat-pool-v1` and `seat-pool-wait-v1`.

### Key Entities

- **Sandbox token**: a GitHub App installation token. One per sandbox. Scope: one repo, three rights. Lifetime: 1 hour from issue. Held only in worker memory and the sandbox environment.
- **GitHub App**: the operator's private App, App ID 5272695 (not secret). Identified by its ID and private key from the worker's environment. Its bot account is shown as the author of the pull requests the agent opens and as the pusher of its commits. The commits themselves keep the agent's own git identity.
- **Personal token**: the worker's `GH_TOKEN`. Still used by the worker itself, never by a sandbox.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a live Build against `aheumaier/pm-agent-scratch-test`, the pull request the agent opens has the App's bot account as author.
- **SC-002**: In that live run, the grant GitHub returns for the sandbox token lists exactly one repo (the target) and exactly the rights contents write, pull requests write and metadata read. These fields are checked; the token itself is not shown.
- **SC-003**: A search of the worker log and of the run's workflow history for `ghs_` (App installation tokens) and `github_pat_` (personal tokens) finds 0 matches.
- **SC-004**: Unit tests show, with the App client faked: the sandbox environment holds the minted token and no personal token (US1); a token failure creates no sandbox, uses no fallback and leaks no secret (US2); two sandboxes get two separately requested tokens (US3); a failing sandbox whose output contains the token raises an error without it, and no log record contains it (US4).
- **SC-005**: Both test suites and the linter stay green, with no test weakened or removed.

## Out of Scope

- The worker's own `GH_TOKEN`: still needed for the worker's clone URL check, the register and architect pushes, and anything else outside the sandbox. This feature only stops it from entering the sandbox.
- The GitHub-comment trigger path (`.github/workflows/swe-agent-build.yml`), which already uses an App token from Actions secrets.
- The leaked test workflows in the target repos (feature 014, the first dogfood run).
- Compiled Python files (`.pyc`) showing up in the agent's commits.
- Pushes that change `.github/workflows/`: they need the "workflows" right, which this feature does not request.
- Refreshing a token during a long Build (see Edge Cases).
- Turning on branch protection itself: an operator step after merge, described in the quickstart.

## Assumptions

- The GitHub App exists: App ID 5272695, created by the operator on 2026-10-11, with Contents write, Pull requests write, Issues write (for the bridge only), Metadata read and no Administration right. Before the live check the operator still has to generate its private key, install it on `aheumaier/agentic_factory` and `aheumaier/pm-agent-scratch-test`, and put its ID and key in `.env`.
- The same App serves the webhook bridge (specs/002), so the bridge and the Build share its identity and key settings.
- The Build agent inside the sandbox already uses `GH_TOKEN` as an installation token (`x-access-token` in the clone URL, `gh` for the pull request), so it probably needs no change. *To verify in the plan*, in particular whether every path that can print the token scrubs it (FR-008); if one doesn't, the fix belongs to this feature.
- Only the Temporal path is changed. Runs that started before this feature use the same activity, so a Build that runs after deploy obtains an App token whatever patch the run started under.
