# Research: Per-Run GitHub App Token for the Build Sandbox

**Feature**: 013-sandbox-app-token | **Date**: 2026-10-11

**Usage Constraint (binding, from 009 and 011):** internal, single-operator use only. The seats and the GitHub App belong to the operator, the pipeline and its seat pool are never offered to third parties, and seat rotation is a knowingly accepted Consumer-Terms grey area.

## R1. Where the token is minted

- **Decision**: Inside `run_swe_agent_activity`, after `_validate_target` and before `AsyncSandbox.create`.
- **Rationale**: FR-007 forbids the token as an activity argument or result. A separate "mint" activity would have to return it, so the token would land in workflow history. Minting inside the Build activity keeps it in worker memory only. It also gives FR-004 for free: every activity call (each Build attempt, each seat handoff) mints its own token.
- **Alternatives considered**: (a) A `mint_sandbox_token_activity` that returns the token. Rejected: the token would sit in history (FR-007). (b) Minting once per workflow run and passing it down. Rejected for the same reason, and handoffs would share a token (FR-004).

## R2. Reusing the bridge's App client

- **Decision**: Add a public method `GitHubAppClient.mint_repo_token(repo, permissions)` in `orchestration/webhook_bridge/github_app.py`. It reuses `_mint_jwt` and `_get_installation_id`, posts `{"repositories": [<name>], "permissions": {...}}` to `/app/installations/{id}/access_tokens`, never reads or writes `_tokens`, and returns the token plus the grant.
- **Rationale**: FR-009 requires one implementation of the exchange. The existing `_installation_token` caches per repo and posts no body, so it would hand out a full-rights, reused token. That breaks FR-002 and FR-004. A separate uncached method leaves the bridge's behaviour exactly as it is.
- **Alternatives considered**: (a) A `narrow=` flag on `_installation_token`. Rejected: it mixes two cache rules in one method, and a wrong flag silently serves a cached full-rights token. (b) A new module in `activities.py` with its own JWT code. Rejected by FR-009.

## R3. Retry rule (settled by `/speckit-clarify`, 2026-10-11)

- **Decision**: Up to 3 tries in total, 2 s apart. Retry only on `aiohttp.ClientConnectionError`, `asyncio.TimeoutError` and `aiohttp.ClientResponseError` with status ≥ 500. Any 4xx, a missing App setting or a bad key fails at once. Never fall back to the worker's `GH_TOKEN`.
- **Rationale**: The operator chose this (spec Clarifications). Temporal's own retry can't be used: Build runs with `maximum_attempts=1` because the activity is not idempotent once the sandbox has pushed. The retry has to sit inside the activity, before the sandbox exists, where a retry is safe.
- **Alternatives considered**: Fail at once on any error (cheaper, but a GitHub blip fails a whole run). Unbounded retry (hides a broken App setup).

## R4. Error shape

- **Decision**: `ApplicationError("could not mint a GitHub App token for <repo>: <reason>", type="SandboxTokenMintFailed", non_retryable=True)`. `<reason>` is one of: `SWE_AGENT_APP_ID or SWE_AGENT_APP_PRIVATE_KEY is not set`, `HTTP <status>`, the exception class name for network errors, or `grant mismatch`. No details payload. Raised `from None`, so no chained exception text reaches history.
- **Rationale**: FR-005 wants an error that says "token failure" and names the repo. FR-008 forbids secrets in it. A status code and a class name hold no secret. `from None` keeps aiohttp's own message (it includes request URLs and headers in some versions) out of the Temporal failure.
- **Alternatives considered**: Re-raising aiohttp's exception. Rejected: its text is not under our control.

## R5. No workflow change for a mint failure

- **Decision**: No change in `pipeline_workflow.py`.
- **Rationale**: `_with_seat` (seat-pool-v1 path) maps only `SeatExhausted` / `SeatInvalid` to a handoff. Any other `ActivityError` releases the seat and re-raises. The Build loop has no `try`, so the run fails without charging a handoff or a Build attempt beyond the current one (FR-006). `non_retryable=True` plus `_NO_AUTO_RETRY` means Temporal does not retry it either.
- **Alternatives considered**: A dedicated failure type at workflow level (like `CredentialPoolExhausted`). Not needed: the activity's typed error already reaches the run's failure, and nothing branches on it.

## R6. `harness/swe-agent/agent.py` needs no change

- **Decision**: No agent change, no E2B template rebuild.
- **Rationale**: The agent already reads `GH_TOKEN` for the clone URL (`clone_and_checkout`) and for `gh` (which reads `GH_TOKEN` itself). It scrubs the token from clone and checkpoint-push errors. `push_and_open_pr`'s own push and `gh pr create` errors are not scrubbed inside the agent. They reach the worker only as the sandbox's `stderr`/`stdout`, and C4 (`_redact` in the activity) removes the token there. An installation token works for `git clone/fetch/push` as `x-access-token` and for `gh pr create/list` with pull requests write.
- **Alternatives considered**: Adding `_scrubbed` to `push_and_open_pr`. It is defence in depth, but it forces a template rebuild for no gain the worker-side scrub does not already give. Logged as a follow-up, not done here.

## R7. Grant check and what gets logged

- **Decision**: After minting, check that the response's `repositories` is exactly the one target repo and that `permissions` equals the requested map. If not, fail with reason `grant mismatch`. On success, log one INFO line: `sandbox token minted for <repo>: repositories=[<name>] permissions={...} expires_at=<iso>`. The token is never logged.
- **Rationale**: This is the evidence for SC-002 without showing the token. GitHub answers a request for a right the App lacks with 422, so a mismatch should never happen; the check guards against a silent widening.
- **Alternatives considered**: Only logging, no check. Rejected: a widened token would then go into the sandbox unnoticed.

## R8. Scrubbing sandbox output

- **Decision**: `_redact(text, secrets)` replaces each known secret (the minted token, the worker's `GH_TOKEN`, the seat's OAuth token) with `***`. It then replaces anything matching `\b(gh[opsur]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b`. It is applied to the quoted `e.stderr or e.stdout` in the non-seat `RuntimeError`.
- **Rationale**: FR-008 covers errors that quote sandbox output. The pattern pass also catches a token the worker doesn't know, such as one from an older run that the agent printed.
- **Alternatives considered**: Dropping the quoted output entirely. Rejected: it is the operator's main clue when a Build fails.

## R9. Which App mints the sandbox token (2026-10-11)

- **Decision**: Only the swe-agent App (App ID 5272695) mints, through `SWE_AGENT_APP_ID` / `SWE_AGENT_APP_PRIVATE_KEY`. The operator also created a second App, `7ed-pm-agent` (App ID 5272760), and put both Apps in `.env` (said by the operator; this session does not read `.env`). 013 does not read the second App.
- **Rationale**: The Build sandbox acts for swe-agent, and the spec names that App. The pm-agent App is meant for pm-agent's own identity. That is a later feature.
- **Check at the live run (T017)**: the smoke script's grant line must come from the swe-agent App. A PR authored by `7ed-pm-agent[bot]` would mean the env names point at the wrong App.

## Architect review findings

`senior-architect-reviewer` reviewed plan.md, research.md and both contracts on 2026-10-11. Verdict: the core design is sound (mint inside the activity, no workflow change, `from None`, uncached narrowed mint). It confirmed that the token is in no activity argument, result or heartbeat, that e2b's logger logs only URLs, and that a `CalledProcessError` message holds the command, not stderr. Its 10 findings and what this feature does with each:

| # | Severity | Finding | Decision |
|---|---|---|---|
| A1 | High | The worker's PAT already leaks today: `_clone_url` puts `GH_TOKEN` into the git command, and `_run` quotes the command in its `RuntimeError` (`eval_gate_activity`, `_open_factory_pr`). | **Accept.** FR-008 covers every error message the worker produces. Apply `_redact` inside `_run` (one call). Tasks T019/T020. |
| A2 | High | "The agent can't merge its own PR" holds only where the default branch requires an approval. `pm-agent-scratch-test` `main` is unprotected (checked 2026-10-11: `protected: false`); `agentic_factory` `main` requires a PR with 0 approvals. With `contents: write` the bot can merge its own PR on both. `enforce_admins: false` also reverses the operator's 2026-10-11 choice of `enforce_admins: true`. Suggested: a ruleset with an operator bypass. | **Record; the operator decides.** Branch rules are a GitHub settings change, which this session may not make. The quickstart lists it as a precondition per installed repo, with both options. The smoke script prints whether the target's default branch is protected (T013). Code does not enforce it. |
| A3 | Medium | The token has no Workflows right. If the agent's `git add -A` stages a change under `.github/workflows/`, every later push is rejected, and `checkpoint_push` exits 1 instead of 75. | **Defer to 014.** The fix is in `harness/swe-agent/agent.py` and needs a template rebuild. The missing right is the intended safety property (the agent can't change CI). The quickstart names the rejection so the operator recognises it. |
| A4 | Medium | The mint's error mapping has no catch-all. `binascii.Error` (bad base64 key), `aiohttp.ContentTypeError` (non-JSON 200) or `KeyError` on `data["token"]` would escape with their own text. | **Accept.** Build the client inside the `try`; a last `except Exception` → `SandboxTokenMintFailed: <class name>` `from None`. Contract error table, T007 and T008 updated. |
| A5 | Medium | Core `activities.py` would import from the `webhook_bridge` entry package; `github_app.py` belongs in `orchestration/credentials/`. | **Reject for 013.** `webhook_bridge/__init__.py` is empty and has no import side effects, so the import pulls in only `github_app.py`, whose deps the worker venv already has. Moving the module touches the bridge and its tests for no behaviour change. Worth doing when a third caller appears. |
| A6 | Low | The "Build outlives the token" edge case cannot happen: the token exists only from the mint on, and after it come sandbox create (at most 60 s, e2b's request timeout) and the command (3300 s): 3360 s, less than the token's 3600 s. Mint retries (worst case about 64 s) come before the token exists. (Corrected 2026-10-11: an earlier draft added a 34 s mint instead.) | **Accept.** Spec Edge Case and plan Constraints reworded. A test pins the inequality (T021). |
| A7 | Low | Resolve the seat token before minting, so an unknown seat fails without a GitHub call. | **Accept.** Order: validate → seat token → mint → create. `test_unknown_seat_fails_before_any_sandbox` also asserts no mint call (T005). |
| A8 | Low | The fixture's worker `GH_TOKEN` is `ghs_test`, the same shape as a minted token; a test could pass by accident. | **Accept.** The fixture uses a `github_pat_…` worker value and a different `ghs_…` fake mint (T004). |
| A9 | Low | The spec says the bot "authors the agent's commits". Commits keep the agent's git identity (`_git_identity`); only the push and the PR are attributed to the bot. | **Accept.** Spec Key Entities reworded. |
| A10 | Low | An `AsyncSandbox.create` error could echo the env it was given. | **Accept, cheaply.** An exception from `AsyncSandbox.create` is re-raised as `RuntimeError("sandbox create failed: <redacted text>")` `from None` (T012). |

Process note: the plan was reviewed after `/speckit-tasks`, so tasks.md was edited by hand for these findings instead of being regenerated.

## Code review findings

`py-codereviewer` reviewed the diff on 2026-10-11, before the live check. Its 5 findings and what this feature does with each:

| # | Finding | Decision |
|---|---|---|
| 1 | The failure tests checked `__cause__` only. A bare `raise` inside `except` also leaves `__cause__` empty, so they did not prove `from None`. | **Accept.** The mint-failure and sandbox-create tests also assert `__suppress_context__`. |
| 2 | T011 was not fully covered: the redaction test left out the seat token, and no test checked captured logs over a failed run. | **Accept.** The stderr test now holds the minted token, the worker PAT, the seat token and a stray token. A new test checks `caplog` at DEBUG over a failed run for all of them and the App key. |
| 3 | The `pr_url` the activity returns is the sandbox's last stdout line, and was not redacted. It ends up in the Temporal history. | **Accept.** `pr_url` goes through `_redact`, with a test. |
| 4 | The smoke script's "other repo answers 404" check fails for a public repo: `agentic_factory` is public, so any token can read it. | **Accept.** The script asks GitHub which repos the token reaches (`GET /installation/repositories`) and passes only on exactly the target. The second argument is gone. |
| 5 | The grant check compares repo names case-sensitively. | **Reject.** It fails safe: a case mismatch fails the run with "grant mismatch" and leaks nothing. The bridge passes GitHub's canonical `full_name`, so it does not happen in practice. |

Second pass, 2026-10-11, after fixes 1–4: no findings, verdict APPROVE (ruff clean, 271 root tests and 194 orchestration tests green). One optional gap was noted and not acted on: the `pr_url` test leaves out the seat token. The stderr redaction test already covers it, so dropping the seat token from the secret list would still fail a test.
