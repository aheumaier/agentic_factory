# Tasks: Per-Run GitHub App Token for the Build Sandbox

**Input**: Design documents from `specs/013-sandbox-app-token/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Usage Constraint (binding, from 009 and 011):** internal, single-operator use only. The seats and the GitHub App belong to the operator, and the pipeline is never offered to third parties.

**Tests**: Requested (spec SC-004). The App client and the E2B sandbox are faked. No test reads `.env` or calls GitHub.

**Format**: `[ID] [P?] [Story] Description`. `[P]` = different file, no open dependency.

## Phase 1: Setup

- [X] T001 Record the `senior-architect-reviewer` findings on plan.md and the contracts under "Architect review findings" in specs/013-sandbox-app-token/research.md, and fold accepted fixes into plan.md, contracts/ and this file before any code edit

## Phase 2: Foundational (blocks all stories)

C1, the narrowed mint in the bridge's App client. Every story builds on it.

- [X] T002 [P] Add tests in orchestration/webhook_bridge/tests/test_github_app.py: `mint_repo_token("o/r", perms)` posts to `/app/installations/<id>/access_tokens` with body `{"repositories": ["r"], "permissions": perms}`; it returns a `MintedToken` with the token, the repo names, the permissions and `expires_at` from the response; `repr()`/`str()` of the result does not contain the token; an HTTP error raises `aiohttp.ClientResponseError` (add a `_FakeResponse` variant whose `raise_for_status` raises with a status)
- [X] T003 Implement `MintedToken` (frozen dataclass, `token` excluded from repr) and `GitHubAppClient.mint_repo_token(repo, permissions)` in orchestration/webhook_bridge/github_app.py per contracts/github-app-mint.md: reuse `_mint_jwt` and `_get_installation_id`, no retry, no logging, and leave `_installation_token` and its callers unchanged

**Checkpoint**: `cd orchestration && uv run --locked pytest -q webhook_bridge/tests/test_github_app.py` green.

## Phase 3: User Story 1 — The sandbox works with a token for the target repo only (P1) 🎯 MVP

**Goal**: `run_swe_agent_activity` mints a narrowed token and passes it as the sandbox's only `GH_TOKEN`.

**Independent test**: with a fake App client, the sandbox env's `GH_TOKEN` is the minted token, the worker's `GH_TOKEN` value appears nowhere in the env, and the mint was asked for exactly the target repo and the 3 rights.

- [X] T004 [US1] In orchestration/tests/test_seat_activities.py: extend the `sandbox` fixture with a fake App client (monkeypatched where `activities` builds it) that records each `mint_repo_token` call and returns a `MintedToken` with a distinct fake `ghs_…` value; set `SWE_AGENT_APP_ID` / `SWE_AGENT_APP_PRIVATE_KEY` to dummy values in the fixture; change the fixture's worker `GH_TOKEN` to a `github_pat_…` value so it differs from the fake minted `ghs_…` (architect finding A8)
- [X] T005 [US1] In orchestration/tests/test_seat_activities.py: change `test_sandbox_env_carries_seat_token_not_api_key` to expect the minted token as `GH_TOKEN` and assert the worker's `GH_TOKEN` value is in no env value; add a test that the mint was called with the target repo and `{"contents": "write", "pull_requests": "write", "metadata": "read"}`; extend `test_unknown_seat_fails_before_any_sandbox` to assert no mint call was made (finding A7)
- [X] T006 [US1] Implement C2 `_mint_sandbox_token(repo)` (happy path: read the App env, one `aiohttp.ClientSession`, call `mint_repo_token`, check the grant, log the grant line from contracts/sandbox-token-activity.md via `activity.logger`) and C3 `_sandbox_envs(seat_id, handoff, gh_token)` in orchestration/activities.py; in `run_swe_agent_activity` the order is `_validate_target` → seat token (`token_for`) → mint → `AsyncSandbox.create` (finding A7)

**Checkpoint**: US1 tests green; the bridge tests still green.

## Phase 4: User Story 2 — A failure to obtain the token stops the run safely (P1)

**Goal**: any mint failure raises `SandboxTokenMintFailed` before a sandbox exists, with retries only for network errors and 5xx.

**Independent test**: with a failing fake client, no sandbox is created, the error type and message match the contract, and the message holds no secret.

- [X] T007 [US2] Add tests in orchestration/tests/test_seat_activities.py: missing `SWE_AGENT_APP_ID` → `SandboxTokenMintFailed`, no sandbox created; a 4xx → one mint call, `…: HTTP 404`; a 5xx then success → 2 calls, sandbox created; 3 × 5xx or 3 × `aiohttp.ClientConnectionError` → 3 calls, failure; grant with a second repo or an extra right → `…: grant mismatch`; a bad base64 key (`binascii.Error`) and a response without `token` (`KeyError`) each → `…: <ClassName>`; a non-JSON answer (`aiohttp.ContentTypeError`, a `ClientResponseError` subclass) → `…: HTTP <status>` (finding A4); every failure is `non_retryable`, has no `__cause__`/`__context__` shown (`from None`), names the repo, and contains neither the fake token nor the worker `GH_TOKEN`. Patch the retry wait to 0 so tests stay fast
- [X] T008 [US2] Implement the failure path of `_mint_sandbox_token` in orchestration/activities.py per research R3/R4 and the contract's error table: up to 3 tries 2 s apart for `aiohttp.ClientConnectionError`, `asyncio.TimeoutError` and 5xx; 4xx, missing env and key errors fail at once; build the client inside the `try` and map any other exception to its class name (finding A4); raise `ApplicationError(..., type="SandboxTokenMintFailed", non_retryable=True) from None` with no details

**Checkpoint**: US1 + US2 tests green.

## Phase 5: User Story 3 — Every sandbox gets its own token (P2)

**Goal**: each activity call mints anew; the bridge cache never serves these requests.

**Independent test**: two activity calls (attempt 2, or handoff 1) make two mint calls and pass two different tokens.

- [X] T009 [P] [US3] Add a test in orchestration/webhook_bridge/tests/test_github_app.py: two `mint_repo_token` calls make two POSTs, return two tokens and leave `_tokens` empty
- [X] T010 [US3] Add a test in orchestration/tests/test_seat_activities.py: two calls of `run_swe_agent_activity` (second with `handoff=1`) make two mint calls and the two sandboxes get different `GH_TOKEN` values

**Checkpoint**: US3 tests green (no code change expected beyond Phase 2/3).

## Phase 6: User Story 4 — The token is never written down (P1)

**Goal**: no worker log line or error carries the minted token, the worker `GH_TOKEN`, the seat token or the App key.

**Independent test**: a sandbox that exits 1 with the token in its stderr raises a `RuntimeError` without it, and `caplog` across a whole run holds no token.

- [X] T011 [US4] Add tests in orchestration/tests/test_seat_activities.py: a sandbox exit 1 whose stderr holds the minted token, the worker `GH_TOKEN`, the seat token and an unrelated `ghp_…`/`github_pat_…` string raises `RuntimeError` with each replaced by `***`; keep `test_other_exit_raises_runtime_error_without_token` passing unchanged; with `caplog` at DEBUG over a successful and a failed run, no record contains any of those values or the App key
- [X] T012 [US4] Implement C4 `_redact(text, secrets)` (known secrets → `***`, then the regex from research R8) in orchestration/activities.py and apply it to the non-seat `RuntimeError` message in `run_swe_agent_activity`; also wrap an `AsyncSandbox.create` failure as `RuntimeError("sandbox create failed: <redacted>") from None` (finding A10)

- [X] T019 [US4] Add a test in orchestration/tests/test_seat_activities.py: `_run` on a failing command whose argv holds `x-access-token:<github_pat_…>@` in a clone URL raises `RuntimeError` without the PAT (finding A1)
- [X] T020 [US4] Apply `_redact` inside `_run` in orchestration/activities.py, with the worker `GH_TOKEN` as a known secret (finding A1)
- [X] T021 [US4] Add a test next to `test_timeouts_command_budget_inside_sandbox_lifetime` asserting e2b's `REQUEST_TIMEOUT` (sandbox create) `+ _COMMAND_TIMEOUT_SECONDS < 3600`: the command ends before the token expires; mint retries come before the token exists (finding A6)

**Checkpoint**: all new tests green.

## Phase 7: Polish & cross-cutting

- [X] T013 [P] Add C5 orchestration/scripts/sandbox_token_smoke.py (pattern of scripts/seat_smoke.py): mint through `_mint_sandbox_token` for argv[1], print the grant line, then `GET /repos/<argv[1]>` and `GET /installation/repositories` with the token and print `target repo: HTTP <code>` / `token repos: [<names>]` only (a 404 on another repo proves nothing when that repo is public: review finding 4); also read the target's default branch (`GET /repos/<repo>` → `default_branch`, then `GET /repos/<repo>/branches/<b>` → `protected`) and print `default branch <b>: protected=<true|false>` (finding A2); exit 0 only on 200 and a token repo list of exactly the target's name
- [X] T014 [P] Update docs that mention the sandbox's `GH_TOKEN`: .env.example (`SWE_AGENT_APP_ID`/`SWE_AGENT_APP_PRIVATE_KEY` now also used by the worker), CLAUDE.md (Harness/Runtime swe-agent row), harness/swe-agent/SKILL.md and registry/agents/swe-agent/SKILL.md if they describe the token source; keep 011's Usage Constraint wording wherever it appears
- [X] T015 Run the gate serially from the worktree root: `uv run --locked ruff check .`, then `uv run --locked pytest tests/ -q`, then `cd orchestration && uv run --locked pytest -q`
- [X] T016 Run `py-codereviewer` on the diff; fix confirmed findings, re-run once, record rejected ones with the reason in research.md
- [X] T017 Live check (quickstart V0 then V2), run by the operator with `!` commands; record the results under "Results" in specs/013-sandbox-app-token/quickstart.md (grant line, PR author, 0 token matches in the worker log and the workflow history)
- [X] T018 Commit (`feat(013)` code, `docs(013)` spec dir) with the `Co-Authored-By` trailer; check `git log --oneline origin/main..013-sandbox-app-token`; stop and ask before any push or PR

## Dependencies

- T001 before any code task (architect findings may change the design).
- Phase 2 (T002–T003) blocks Phases 3–6.
- US1 (T004–T006) before US2, US3, US4: they share the fixture and `_mint_sandbox_token`.
- US2, US3, US4 are independent of each other after US1, but touch the same test file, so run them one after the other.
- T019–T021 after T012, before T015.
- T013 needs T008. T015–T018 run last, in order.

## Parallel opportunities

- T002 and T004 are in different files once T001 is done (the fake client in T004 only needs the `MintedToken` shape from the contract).
- T009 can run alongside T007/T010.
- T013 and T014 can run alongside each other.
- The gate (T015) never runs in parallel with itself: live-Temporal tests time out under concurrency.

## Implementation strategy

MVP is Phase 2 + US1: the sandbox gets a narrowed App token. US2 and US4 are both P1 and are needed before the live check, because a live run without them could fall back silently or leak a token in an error. US3 is mostly proven by the design (no cache, mint per call) and only adds tests.
