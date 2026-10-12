# Contract: `GitHubAppClient.mint_repo_token`

**Feature**: 013-sandbox-app-token | **File**: `orchestration/webhook_bridge/github_app.py`

**Usage Constraint (binding, from 009 and 011):** internal, single-operator use only.

## Signature

```python
async def mint_repo_token(self, repo: str, permissions: dict[str, str]) -> MintedToken
```

`MintedToken` is a small frozen dataclass: `token: str`, `repositories: list[str]`, `permissions: dict[str, str]`, `expires_at: str`. Its `__repr__` leaves out `token`, so printing it never shows the secret.

## Behaviour

1. Signs a fresh App JWT (`_mint_jwt`).
2. `GET /repos/{repo}/installation` → installation ID (`_get_installation_id`).
3. `POST /app/installations/{id}/access_tokens` with body `{"repositories": ["<name part of repo>"], "permissions": <permissions>}`.
4. Returns the token and the grant from the response (`token`, `repositories[*].name`, `permissions`, `expires_at`).

## Rules

- Never reads or writes the bridge's `_tokens` cache. Two calls make two POSTs and return two tokens.
- Does not retry. HTTP errors surface as `aiohttp.ClientResponseError` (from `raise_for_status`), network errors as `aiohttp.ClientError` / `asyncio.TimeoutError`. The caller decides about retries.
- Never logs the token.
- The bridge's existing `_installation_token` and its callers (`get_permission`, `get_pull_request`, `post_reaction`) are unchanged.
