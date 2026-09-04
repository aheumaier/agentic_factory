"""GitHub App installation-token minting/caching (FR-009, research.md).

Signs a JWT with SWE_AGENT_APP_PRIVATE_KEY (base64-encoded PEM, RS256,
iss=SWE_AGENT_APP_ID, <=10 min exp), resolves the installation for a
target repo, exchanges it for an installation access token, and caches
the token in memory until shortly before its ~1h expiry. The token value
is never logged. All calls go through aiohttp.ClientSession with an
explicit timeout — never subprocess/gh CLI, never a blocking HTTP client
(research.md's non-blocking-API-call decision).
"""
import base64
import time

import aiohttp
import jwt

_GITHUB_API = "https://api.github.com"
_JWT_TTL_SECONDS = 9 * 60  # stays under GitHub's 10 min ceiling
_TOKEN_REFRESH_MARGIN_SECONDS = 5 * 60  # refresh before the ~1h token actually expires
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)
_ACCEPT_HEADER = "application/vnd.github+json"


class GitHubAppClient:
    def __init__(self, app_id: str, private_key_b64: str, session: aiohttp.ClientSession) -> None:
        self._app_id = app_id
        self._private_key = base64.b64decode(private_key_b64)
        self._session = session
        self._tokens: dict[str, tuple[str, float]] = {}  # repo -> (token, expiry_epoch)

    def _mint_jwt(self) -> str:
        now = int(time.time())
        payload = {"iat": now - 30, "exp": now + _JWT_TTL_SECONDS, "iss": self._app_id}
        return jwt.encode(payload, self._private_key, algorithm="RS256")

    async def _get_installation_id(self, repo: str) -> int:
        headers = {
            "Authorization": f"Bearer {self._mint_jwt()}",
            "Accept": _ACCEPT_HEADER,
        }
        async with self._session.get(
            f"{_GITHUB_API}/repos/{repo}/installation", headers=headers, timeout=_REQUEST_TIMEOUT
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
        return data["id"]

    async def _installation_token(self, repo: str) -> str:
        cached = self._tokens.get(repo)
        if cached is not None and cached[1] > time.time():
            return cached[0]
        installation_id = await self._get_installation_id(repo)
        headers = {
            "Authorization": f"Bearer {self._mint_jwt()}",
            "Accept": _ACCEPT_HEADER,
        }
        async with self._session.post(
            f"{_GITHUB_API}/app/installations/{installation_id}/access_tokens",
            headers=headers,
            timeout=_REQUEST_TIMEOUT,
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
        token = data["token"]
        self._tokens[repo] = (token, time.time() + 3600 - _TOKEN_REFRESH_MARGIN_SECONDS)
        return token

    async def _auth_headers(self, repo: str) -> dict[str, str]:
        token = await self._installation_token(repo)
        return {"Authorization": f"token {token}", "Accept": _ACCEPT_HEADER}

    async def get_permission(self, repo: str, username: str) -> str:
        """GET /repos/{repo}/collaborators/{username}/permission -> permission level."""
        headers = await self._auth_headers(repo)
        async with self._session.get(
            f"{_GITHUB_API}/repos/{repo}/collaborators/{username}/permission",
            headers=headers,
            timeout=_REQUEST_TIMEOUT,
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
        return data["permission"]

    async def get_pull_request(self, repo: str, pr_number: int) -> dict:
        """GET /repos/{repo}/pulls/{pr_number} -> {"branch", "is_cross_repository"}."""
        headers = await self._auth_headers(repo)
        async with self._session.get(
            f"{_GITHUB_API}/repos/{repo}/pulls/{pr_number}",
            headers=headers,
            timeout=_REQUEST_TIMEOUT,
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
        return {
            "branch": data["head"]["ref"],
            "is_cross_repository": (
                data["head"]["repo"]["full_name"] != data["base"]["repo"]["full_name"]
            ),
        }

    async def post_reaction(self, repo: str, comment_id: int, content: str) -> None:
        """POST /repos/{repo}/issues/comments/{comment_id}/reactions."""
        headers = await self._auth_headers(repo)
        async with self._session.post(
            f"{_GITHUB_API}/repos/{repo}/issues/comments/{comment_id}/reactions",
            headers=headers,
            json={"content": content},
            timeout=_REQUEST_TIMEOUT,
        ) as resp:
            resp.raise_for_status()
