import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from webhook_bridge import server as server_module
from webhook_bridge.server import BridgeApp

SECRET = "s3cr3t"
REPO = "owner/repo"


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def _payload(**overrides) -> dict:
    payload = {
        "action": "created",
        "repository": {"full_name": REPO},
        "issue": {"number": 7, "pull_request": {}},
        "comment": {
            "id": 555,
            "body": "@pipeline-agent run mode=full agent=widget-export version=3",
            "author_association": "OWNER",
            "user": {"login": "alice"},
        },
    }
    payload.update(overrides)
    return payload


def _make_client(github_client, temporal_client_obj=None) -> BridgeApp:
    return BridgeApp(
        client=temporal_client_obj or MagicMock(),
        github_client=github_client,
        secret=SECRET,
        allowed_repos={REPO.lower()},
    )


async def _post(bridge: BridgeApp, payload: dict, event: str = "issue_comment", delivery_id: str | None = "d-1"):
    app = web.Application()
    app.router.add_post("/webhook", bridge.handle_webhook)
    async with TestClient(TestServer(app)) as client:
        body = json.dumps(payload).encode()
        headers = {
            "X-Hub-Signature-256": _sign(body),
            "X-GitHub-Event": event,
        }
        if delivery_id is not None:
            headers["X-GitHub-Delivery"] = delivery_id
        return await client.post("/webhook", data=body, headers=headers)


async def test_invalid_signature_returns_401() -> None:
    bridge = _make_client(MagicMock())
    app = web.Application()
    app.router.add_post("/webhook", bridge.handle_webhook)
    async with TestClient(TestServer(app)) as client:
        body = json.dumps(_payload()).encode()
        resp = await client.post(
            "/webhook",
            data=body,
            headers={"X-Hub-Signature-256": "sha256=deadbeef", "X-GitHub-Event": "issue_comment", "X-GitHub-Delivery": "d-1"},
        )
        assert resp.status == 401


async def test_missing_delivery_header_is_malformed() -> None:
    bridge = _make_client(MagicMock())
    resp = await _post(bridge, _payload(), delivery_id=None)
    assert resp.status == 202


async def test_non_pr_comment_ignored() -> None:
    bridge = _make_client(MagicMock())
    resp = await _post(bridge, _payload(issue={"number": 7, "pull_request": None}))
    assert resp.status == 202


async def test_repo_not_allowed_returns_202_no_reaction() -> None:
    github_client = MagicMock()
    github_client.post_reaction = AsyncMock()
    bridge = BridgeApp(client=MagicMock(), github_client=github_client, secret=SECRET, allowed_repos={"other/repo"})
    resp = await _post(bridge, _payload())
    assert resp.status == 202
    github_client.post_reaction.assert_not_awaited()


async def test_repo_allowlist_case_and_whitespace_insensitive() -> None:
    github_client = MagicMock()
    github_client.get_pull_request = AsyncMock(return_value={"branch": "feat", "is_cross_repository": False})
    github_client.post_reaction = AsyncMock()
    temporal_client_obj = MagicMock()
    temporal_client_obj.start_workflow = AsyncMock()
    bridge = BridgeApp(
        client=temporal_client_obj, github_client=github_client, secret=SECRET, allowed_repos={" Owner/Repo ".strip().lower()}
    )
    resp = await _post(bridge, _payload())
    assert resp.status == 202
    github_client.get_pull_request.assert_awaited()


async def test_fork_pr_rejected() -> None:
    github_client = MagicMock()
    github_client.get_pull_request = AsyncMock(return_value={"branch": "feat", "is_cross_repository": True})
    github_client.post_reaction = AsyncMock()
    bridge = _make_client(github_client)
    resp = await _post(bridge, _payload())
    assert resp.status == 202
    github_client.post_reaction.assert_awaited_once_with(REPO, 555, "confused")


async def test_mode_vibe_rejected_pre_005() -> None:
    github_client = MagicMock()
    github_client.get_pull_request = AsyncMock(return_value={"branch": "feat", "is_cross_repository": False})
    github_client.post_reaction = AsyncMock()
    bridge = _make_client(github_client)
    payload = _payload()
    payload["comment"]["body"] = "@pipeline-agent run mode=vibe agent=x version=1"
    resp = await _post(bridge, payload)
    assert resp.status == 202
    github_client.post_reaction.assert_awaited_once_with(REPO, 555, "confused")


async def test_mode_unrecognized_value_rejected() -> None:
    github_client = MagicMock()
    github_client.get_pull_request = AsyncMock(return_value={"branch": "feat", "is_cross_repository": False})
    github_client.post_reaction = AsyncMock()
    bridge = _make_client(github_client)
    payload = _payload()
    payload["comment"]["body"] = "@pipeline-agent run mode=turbo agent=x version=1"
    resp = await _post(bridge, payload)
    assert resp.status == 202
    github_client.post_reaction.assert_awaited_once_with(REPO, 555, "confused")


async def test_permission_denied_rejected() -> None:
    github_client = MagicMock()
    github_client.get_permission = AsyncMock(return_value="read")
    github_client.post_reaction = AsyncMock()
    bridge = _make_client(github_client)
    payload = _payload()
    payload["comment"]["author_association"] = "CONTRIBUTOR"
    resp = await _post(bridge, payload)
    assert resp.status == 202
    github_client.post_reaction.assert_awaited_once_with(REPO, 555, "confused")


async def test_malformed_comment_no_reaction() -> None:
    github_client = MagicMock()
    github_client.post_reaction = AsyncMock()
    bridge = _make_client(github_client)
    payload = _payload()
    payload["comment"]["body"] = "just chatting here"
    resp = await _post(bridge, payload)
    assert resp.status == 202
    github_client.post_reaction.assert_not_awaited()


async def test_duplicate_delivery_short_circuits() -> None:
    github_client = MagicMock()
    github_client.get_pull_request = AsyncMock(return_value={"branch": "feat", "is_cross_repository": False})
    github_client.post_reaction = AsyncMock()
    temporal_client_obj = MagicMock()
    temporal_client_obj.start_workflow = AsyncMock()
    bridge = _make_client(github_client, temporal_client_obj)

    resp1 = await _post(bridge, _payload(), delivery_id="dupe-1")
    resp2 = await _post(bridge, _payload(), delivery_id="dupe-1")

    assert resp1.status == 202
    assert resp2.status == 202
    assert temporal_client_obj.start_workflow.await_count == 1


async def test_build_app_refuses_to_start_without_secret(monkeypatch) -> None:
    monkeypatch.delenv("GH_WEBHOOK_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        await server_module.build_app()


async def test_build_app_refuses_to_start_if_temporal_connect_fails(monkeypatch) -> None:
    monkeypatch.setenv("GH_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("SWE_AGENT_APP_ID", "1")
    monkeypatch.setenv("SWE_AGENT_APP_PRIVATE_KEY", "notreallyakey")
    monkeypatch.setenv("BRIDGE_ALLOWED_REPOS", REPO)

    async def _fail_connect():
        raise RuntimeError("temporal unreachable")

    monkeypatch.setattr(server_module.temporal_client, "connect", _fail_connect)
    with pytest.raises(RuntimeError):
        await server_module.build_app()


def test_body_size_limit_matches_contract() -> None:
    assert server_module._MAX_BODY_BYTES == 1024 * 1024


async def test_main_binds_loopback_only(monkeypatch) -> None:
    monkeypatch.setenv("GH_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("SWE_AGENT_APP_ID", "1")
    monkeypatch.setenv("SWE_AGENT_APP_PRIVATE_KEY", "notreallyakey")
    monkeypatch.setenv("BRIDGE_ALLOWED_REPOS", REPO)

    fake_app = web.Application()
    monkeypatch.setattr(server_module, "build_app", AsyncMock(return_value=(fake_app, MagicMock())))

    bind_calls = []

    class _FakeSite:
        def __init__(self, runner, host, port):
            bind_calls.append((host, port))

        async def start(self):
            pass

    monkeypatch.setattr(server_module.web, "TCPSite", _FakeSite)

    import asyncio

    async def _immediate_wait(self):
        return None

    # main() would otherwise block forever waiting for SIGTERM/SIGINT.
    monkeypatch.setattr(asyncio.Event, "wait", _immediate_wait)

    await server_module.main()

    assert bind_calls == [("127.0.0.1", 3000)]
