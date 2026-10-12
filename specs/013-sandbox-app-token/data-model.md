# Data Model: Per-Run GitHub App Token for the Build Sandbox

**Feature**: 013-sandbox-app-token | **Date**: 2026-10-11

**Usage Constraint (binding, from 009 and 011):** internal, single-operator use only. The seats and the GitHub App belong to the operator, and the pipeline is never offered to third parties.

Nothing here is stored. Both entities live in worker memory for one call of `run_swe_agent_activity`.

## Sandbox token

The GitHub App installation token one Build sandbox uses.

| Field | Type | Rule |
|---|---|---|
| value | string (`ghs_…`) | Secret. Lives in worker memory and in the sandbox's `GH_TOKEN` only. Never logged, never in an error, never an activity argument or result (FR-007, FR-008). |
| repo | `owner/name` | The run's target repo. The token is valid for this repo only (FR-002). |
| expires_at | ISO 8601 time | 1 h after minting, set by GitHub. The sandbox command limit (3300 s) ends the agent before that (architect finding A6). |

Lifecycle: minted → handed to one sandbox → dropped when the activity call ends. Never reused (FR-004). A new activity call (next Build attempt, next seat handoff) mints a new one.

## Grant

What GitHub says the token may do. Safe to log; it is the evidence for SC-002.

| Field | Type | Rule |
|---|---|---|
| repositories | list of repo names | Must be exactly `[<target name>]`. |
| permissions | map | Must equal `{"contents": "write", "pull_requests": "write", "metadata": "read"}`. |
| expires_at | ISO 8601 time | Same as the token's. |

If the grant does not match the request, minting fails with reason `grant mismatch` and no sandbox is created (research R7).
