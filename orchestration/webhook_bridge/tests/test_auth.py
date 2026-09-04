import hashlib
import hmac

import pytest

from webhook_bridge.auth import is_authorized, verify_signature

SECRET = "s3cr3t"


def _sign(body: bytes, secret: str = SECRET) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_verify_signature_valid() -> None:
    body = b'{"hello": "world"}'
    assert verify_signature(body, _sign(body), SECRET) is True


def test_verify_signature_invalid() -> None:
    body = b'{"hello": "world"}'
    assert verify_signature(body, _sign(body, secret="wrong"), SECRET) is False


def test_verify_signature_missing() -> None:
    body = b'{"hello": "world"}'
    assert verify_signature(body, None, SECRET) is False


def test_verify_signature_wrong_prefix() -> None:
    body = b'{"hello": "world"}'
    assert verify_signature(body, "sha1=deadbeef", SECRET) is False


class _FakeGitHubClient:
    def __init__(self, permission: str) -> None:
        self.permission = permission
        self.calls = 0

    async def get_permission(self, repo: str, username: str) -> str:
        self.calls += 1
        return self.permission


@pytest.mark.parametrize("permission,expected", [("write", True), ("admin", True), ("read", False), ("none", False)])
async def test_is_authorized_permission_levels(permission: str, expected: bool) -> None:
    client = _FakeGitHubClient(permission)
    result = await is_authorized(client, "owner/repo", "someone", "CONTRIBUTOR")
    assert result is expected
    assert client.calls == 1


async def test_is_authorized_owner_fast_path_skips_api_call() -> None:
    client = _FakeGitHubClient("read")
    result = await is_authorized(client, "owner/repo", "the-owner", "OWNER")
    assert result is True
    assert client.calls == 0
