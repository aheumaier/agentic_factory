# Implementation Plan: Per-Run GitHub App Token for the Build Sandbox

**Branch**: `013-sandbox-app-token` | **Date**: 2026-10-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/013-sandbox-app-token/spec.md`

**Usage Constraint (binding, from 009 and 011):** internal, single-operator use only. The seats and the GitHub App belong to the operator, the pipeline and its seat pool are never offered to third parties, and seat rotation is a knowingly accepted Consumer-Terms grey area. Nothing here presents seat pooling as a product feature.

## Summary

The Build sandbox stops receiving the worker's personal `GH_TOKEN`. Instead, `run_swe_agent_activity` mints a GitHub App installation token for the one target repo, narrowed to contents write, pull requests write and metadata read, just before it creates the sandbox. It passes that token in as `GH_TOKEN`. Every call of the activity mints its own token, so every Build attempt and every seat handoff gets a new one.

| Change | Where | What |
|---|---|---|
| C1 narrowed mint | `orchestration/webhook_bridge/github_app.py` | New public `GitHubAppClient.mint_repo_token(repo, permissions)`. It reuses `_mint_jwt` and `_get_installation_id`, posts the narrowing body to `access_tokens`, skips the `_tokens` cache, and returns the token plus the grant (repo names, permissions, expiry). The bridge's cached path is unchanged. |
| C2 mint in the activity | `orchestration/activities.py` | New `_mint_sandbox_token(repo)`. It reads `SWE_AGENT_APP_ID` / `SWE_AGENT_APP_PRIVATE_KEY`, opens one `aiohttp.ClientSession`, calls C1 with up to 3 tries (network errors and 5xx only, 2 s apart), checks the grant, and logs the grant (never the token). The client is built inside the `try`, and any other exception (bad base64 key, non-JSON answer, missing field) becomes the reason `<exception class name>` (architect finding A4). Any failure raises `ApplicationError(type="SandboxTokenMintFailed", non_retryable=True)` that names the repo and the reason. Neither the message nor the details hold a secret. |
| C3 sandbox env | `orchestration/activities.py::_sandbox_envs` | Takes the minted token as a parameter and sets `GH_TOKEN` to it. `os.environ["GH_TOKEN"]` is no longer read here. |
| C4 scrub worker errors | `orchestration/activities.py` (`run_swe_agent_activity`, `_run`) | `_redact` removes the minted token, the worker's `GH_TOKEN`, the seat token, and anything shaped like a GitHub token (`ghs_…`, `ghp_…`, `gho_…`, `ghu_…`, `ghr_…`, `github_pat_…`). It is applied to the `RuntimeError` for a non-seat sandbox exit (quoted `e.stderr or e.stdout`), to an `AsyncSandbox.create` failure, and inside `_run`, whose error quotes a git command that can carry the worker's PAT in the clone URL (architect findings A1, A10). |
| C5 live smoke | `orchestration/scripts/sandbox_token_smoke.py` | Operator-run check (quickstart V0), like `seat_smoke.py`. Mints through C2 for a target repo, prints the grant, then calls the GitHub API with the token: the target repo must answer 200, and `GET /installation/repositories` must list exactly the target (a 404 on another repo proves nothing for a public repo). Prints status codes only, never the token. |

There is no workflow change. A `SandboxTokenMintFailed` is a non-seat `ActivityError`. `_with_seat` releases the seat and re-raises it, and the Build loop has no handler, so the run fails without charging a handoff (FR-006, research R5). The patch IDs are untouched.

`harness/swe-agent/agent.py` needs no change, so the E2B template needs no rebuild (research R6).

## Technical Context

**Language/Version**: Python ≥ 3.11 (worker venv 3.12)

**Primary Dependencies**: `aiohttp`, `pyjwt`, `cryptography` (already used by the bridge's App client), `temporalio` 1.32, `e2b`. All are already in `orchestration/pyproject.toml`. No new dependency.

**Storage**: None. The token lives only in worker memory and in the sandbox environment (FR-007).

**Testing**: `pytest` + `pytest-asyncio` in `orchestration/` (`cd orchestration && uv run --locked pytest -q`). The App client is faked through the existing `_FakeSession` pattern (`webhook_bridge/tests/test_github_app.py`), and the activity through the existing `_FakeAsyncSandbox` fixture (`tests/test_seat_activities.py`) plus a fake `GitHubAppClient`.

**Target Platform**: The Temporal worker on the operator's Mac; the E2B `swe-agent-sandbox` template (unchanged).

**Project Type**: Internal pipeline (Temporal worker + activities).

**Performance Goals**: Minting adds 2 GitHub API calls (about 0.5 s) per Build attempt. In the worst case, 3 tries × 2 calls × 10 s timeout + 2 × 2 s waits ≈ 64 s, well inside the 60 min `start_to_close_timeout`.

**Constraints**: The token is never an activity argument or result (FR-007), so minting happens inside `run_swe_agent_activity`, not as a separate activity. The token lives 1 h from minting. Mint retries happen before the token exists, so they don't use up its life. After the mint come only sandbox create (at most 60 s, e2b's request timeout) and the command (stopped after 3300 s): 3360 s at most, so the agent's last push comes before expiry; a test pins this (spec Edge Cases, architect finding A6).

**Scale/Scope**: One operator, one target repo per run. 2 source files changed and 1 small script added, about 120 lines plus tests.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is the unfilled Spec Kit template, so there are no constitution gates. The repo's own rules apply instead:

| Rule | How this plan meets it |
|---|---|
| AF-SPEC | `tasks.md` exists before any edit under `orchestration/`. |
| AF-SECRET | No step reads `.env`. Live values are checked only through the operator's `!` command (quickstart V0). |
| AF-COMMIT | Ruff and both suites, run serially, before each commit. |
| Architecture §3.3 (sandbox) / §3.4 (routing) | The sandbox stays the only execution path. Model routing is untouched. |
| Building blocks decide, not convenience (CLAUDE.md) | It reuses the bridge's App client (FR-009) instead of a second minter. |
| 011 patch IDs | Not renamed, not touched (FR-012). |

Post-design re-check: still passes. The design adds no activity and no workflow branch. The only new file is an operator-run script.

## Project Structure

### Documentation (this feature)

```text
specs/013-sandbox-app-token/
├── spec.md
├── plan.md              # this file
├── research.md          # decisions R1–R8 + architect review findings
├── data-model.md        # sandbox token, grant
├── quickstart.md        # operator setup, unit checks, live V1–V3, post-merge step
├── contracts/
│   ├── github-app-mint.md       # GitHubAppClient.mint_repo_token
│   └── sandbox-token-activity.md  # activity env + error contract
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
orchestration/
├── activities.py                       # C2 _mint_sandbox_token, C3 _sandbox_envs, C4 _redact
├── scripts/sandbox_token_smoke.py      # C5 operator-run live check
├── webhook_bridge/
│   ├── github_app.py                   # C1 mint_repo_token
│   └── tests/test_github_app.py        # C1 tests
└── tests/
    └── test_seat_activities.py         # C2–C4 tests (existing sandbox fixture, plus a fake App client)
```

**Structure Decision**: Extend the two existing files. `activities.py` imports `GitHubAppClient` from `webhook_bridge.github_app`. That package already lives in `orchestration/` and its dependencies are in the worker's venv, so the import adds nothing new to install. The architect suggested moving `github_app.py` to `orchestration/credentials/`; rejected for 013 (research, finding A5).

**Order inside `run_swe_agent_activity`**: validate target → resolve the seat token → mint → `AsyncSandbox.create` → run → kill (finding A7).

## Complexity Tracking

No violations to justify.
