import base64
import logging
import time

import aiohttp
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from webhook_bridge.github_app import GitHubAppClient

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PRIVATE_KEY_PEM = _PRIVATE_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
_PRIVATE_KEY_B64 = base64.b64encode(_PRIVATE_KEY_PEM).decode()
_PUBLIC_KEY = _PRIVATE_KEY.public_key()


class _FakeResponse:
    def __init__(self, json_body: dict) -> None:
        self._json_body = json_body

    def raise_for_status(self) -> None:
        pass

    async def json(self) -> dict:
        return self._json_body

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, *exc) -> None:
        pass


class _FakeSession:
    """Records every request; returns canned responses by call order."""

    def __init__(self, responses: list[dict]) -> None:
        self._responses = responses
        self.requests: list[dict] = []

    def get(self, url: str, headers: dict, timeout=None):
        self.requests.append({"method": "GET", "url": url, "headers": headers})
        return _FakeResponse(self._responses[len(self.requests) - 1])

    def post(self, url: str, headers: dict, timeout=None, json=None):
        self.requests.append({"method": "POST", "url": url, "headers": headers, "json": json})
        return _FakeResponse(self._responses[len(self.requests) - 1])


def test_mint_jwt_signed_with_right_claims() -> None:
    session = _FakeSession([])
    client = GitHubAppClient(app_id="12345", private_key_b64=_PRIVATE_KEY_B64, session=session)
    token = client._mint_jwt()
    decoded = jwt.decode(token, _PUBLIC_KEY, algorithms=["RS256"])
    assert decoded["iss"] == "12345"
    assert decoded["exp"] - decoded["iat"] <= 10 * 60


async def test_installation_token_cached_and_reused() -> None:
    session = _FakeSession(
        [
            {"id": 999},  # GET installation
            {"token": "tok-1"},  # POST access_tokens
        ]
    )
    client = GitHubAppClient(app_id="12345", private_key_b64=_PRIVATE_KEY_B64, session=session)
    token1 = await client._installation_token("owner/repo")
    token2 = await client._installation_token("owner/repo")
    assert token1 == token2 == "tok-1"
    assert len(session.requests) == 2  # second call served from cache, no new requests


async def test_installation_token_reminted_after_expiry() -> None:
    session = _FakeSession(
        [
            {"id": 999},
            {"token": "tok-1"},
            {"id": 999},
            {"token": "tok-2"},
        ]
    )
    client = GitHubAppClient(app_id="12345", private_key_b64=_PRIVATE_KEY_B64, session=session)
    token1 = await client._installation_token("owner/repo")
    client._tokens["owner/repo"] = (token1, time.time() - 1)  # force expiry
    token2 = await client._installation_token("owner/repo")
    assert token2 == "tok-2"
    assert len(session.requests) == 4


async def test_token_value_never_appears_in_log_output(caplog) -> None:
    session = _FakeSession([{"id": 999}, {"token": "super-secret-token"}])
    client = GitHubAppClient(app_id="12345", private_key_b64=_PRIVATE_KEY_B64, session=session)
    with caplog.at_level(logging.DEBUG):
        await client._installation_token("owner/repo")
    assert "super-secret-token" not in caplog.text


_SANDBOX_PERMS = {"contents": "write", "pull_requests": "write", "metadata": "read"}


def _access_token_body(token: str = "ghs_minted") -> dict:
    return {
        "token": token,
        "expires_at": "2026-10-11T13:00:00Z",
        "permissions": dict(_SANDBOX_PERMS),
        "repositories": [{"name": "repo", "full_name": "owner/repo"}],
    }


async def test_mint_repo_token_narrows_to_one_repo_and_rights() -> None:
    session = _FakeSession([{"id": 999}, _access_token_body()])
    client = GitHubAppClient(app_id="12345", private_key_b64=_PRIVATE_KEY_B64, session=session)
    minted = await client.mint_repo_token("owner/repo", _SANDBOX_PERMS)

    post = session.requests[1]
    assert post["url"] == "https://api.github.com/app/installations/999/access_tokens"
    assert post["json"] == {"repositories": ["repo"], "permissions": _SANDBOX_PERMS}
    assert minted.token == "ghs_minted"
    assert minted.repositories == ["repo"]
    assert minted.permissions == _SANDBOX_PERMS
    assert minted.expires_at == "2026-10-11T13:00:00Z"


async def test_mint_repo_token_bypasses_cache() -> None:
    session = _FakeSession(
        [{"id": 999}, _access_token_body("ghs_one"), {"id": 999}, _access_token_body("ghs_two")]
    )
    client = GitHubAppClient(app_id="12345", private_key_b64=_PRIVATE_KEY_B64, session=session)
    first = await client.mint_repo_token("owner/repo", _SANDBOX_PERMS)
    second = await client.mint_repo_token("owner/repo", _SANDBOX_PERMS)
    assert (first.token, second.token) == ("ghs_one", "ghs_two")
    assert len(session.requests) == 4
    assert client._tokens == {}


async def test_minted_token_repr_hides_the_token() -> None:
    session = _FakeSession([{"id": 999}, _access_token_body("ghs_hidden_value")])
    client = GitHubAppClient(app_id="12345", private_key_b64=_PRIVATE_KEY_B64, session=session)
    minted = await client.mint_repo_token("owner/repo", _SANDBOX_PERMS)
    assert "ghs_hidden_value" not in repr(minted)
    assert "ghs_hidden_value" not in str(minted)


class _ErrorResponse(_FakeResponse):
    def __init__(self, status: int) -> None:
        super().__init__({})
        self.status = status

    def raise_for_status(self) -> None:
        raise aiohttp.ClientResponseError(None, (), status=self.status)


async def test_mint_repo_token_http_error_raises_client_response_error() -> None:
    session = _FakeSession([{"id": 999}])
    session.post = lambda url, headers, timeout=None, json=None: _ErrorResponse(422)
    client = GitHubAppClient(app_id="12345", private_key_b64=_PRIVATE_KEY_B64, session=session)
    with pytest.raises(aiohttp.ClientResponseError) as excinfo:
        await client.mint_repo_token("owner/repo", _SANDBOX_PERMS)
    assert excinfo.value.status == 422
