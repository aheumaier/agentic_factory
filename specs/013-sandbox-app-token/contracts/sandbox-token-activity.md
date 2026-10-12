# Contract: Build activity and its sandbox token

**Feature**: 013-sandbox-app-token | **File**: `orchestration/activities.py`

**Usage Constraint (binding, from 009 and 011):** internal, single-operator use only.

## Activity signature (unchanged)

```python
@activity.defn
async def run_swe_agent_activity(repo, branch, feedback, seat_id, handoff=0) -> dict
```

No new argument and no new result field. The token is never in either (FR-007).

## Worker environment it reads

| Name | Meaning | Missing → |
|---|---|---|
| `SWE_AGENT_APP_ID` | GitHub App ID | `SandboxTokenMintFailed` |
| `SWE_AGENT_APP_PRIVATE_KEY` | App private key, base64-encoded PEM (same format as the bridge) | `SandboxTokenMintFailed` |

The worker's own `GH_TOKEN` is still read elsewhere (`_clone_url`, register and architect pushes; out of scope). It is no longer passed into the Build sandbox.

## Sandbox environment it sets

| Name | Value |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | seat token (unchanged) |
| `GH_TOKEN` | the freshly minted App token for `repo` |
| `SEAT_HANDOFF_INDEX` | handoff index (unchanged) |
| `SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS` | test hook, unchanged |

## Order

`_validate_target` → seat token (`token_for`) → mint (up to 3 tries) → check grant → log grant → `AsyncSandbox.create` → run → kill.

An unknown seat fails before any GitHub call (architect finding A7). A mint failure happens before `AsyncSandbox.create`, so no sandbox exists and nothing is pushed.

## Errors

| Case | Raised | Message |
|---|---|---|
| App ID or key missing | `ApplicationError`, `type="SandboxTokenMintFailed"`, `non_retryable=True` | `could not mint a GitHub App token for <repo>: SWE_AGENT_APP_ID or SWE_AGENT_APP_PRIVATE_KEY is not set` |
| Bad key (JWT signing fails) | same type | `…: <exception class name>` |
| HTTP 4xx (App not installed, right not granted) | same type, no retry | `…: HTTP <status>` |
| HTTP 5xx, network error, timeout, 3 times | same type | `…: HTTP <status>` or `…: <exception class name>` |
| Grant differs from the request | same type | `…: grant mismatch` |
| Any other exception during the mint (for example a bad base64 key, a non-JSON answer, a missing `token` field) | same type | `…: <exception class name>` (architect finding A4) |
| `AsyncSandbox.create` fails | `RuntimeError`, raised `from None` | `sandbox create failed: <error text, redacted>` (finding A10) |
| Sandbox exit 75 / 77 | `SeatExhausted` / `SeatInvalid` (unchanged) | unchanged |
| Any other sandbox exit | `RuntimeError` (unchanged type) | `sandbox run failed (<code>): <stderr or stdout, redacted>` |
| A local git or `gh` command fails (`_run`, used by the eval gate and the registry PR) | `RuntimeError` (unchanged type) | `<command> failed (<code>): <output>`, redacted (finding A1: the command can hold the worker's `GH_TOKEN` in the clone URL) |

All `SandboxTokenMintFailed` errors are raised `from None` and carry no details payload. "Redacted" means the minted token, the worker's `GH_TOKEN` and the seat token are replaced by `***`, and so is any text shaped like a GitHub token (`ghs_`, `ghp_`, `gho_`, `ghu_`, `ghr_`, `github_pat_`).

## Log line on success (INFO, `activity.logger`)

```
sandbox token minted for <owner/name>: repositories=['<name>'] permissions={'contents': 'write', 'metadata': 'read', 'pull_requests': 'write'} expires_at=<iso>
```

No token, no prefix of it.

## Workflow effect

None in code. The error is a non-seat `ActivityError`: `_with_seat` releases the seat and re-raises, so the run fails. No seat handoff is charged (FR-006).
