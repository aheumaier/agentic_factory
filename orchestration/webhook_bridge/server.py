"""aiohttp app, POST /webhook route (contracts/webhook-http-contract.md).

Binds 127.0.0.1 only (A11) — the smee relay is the only intended path in,
GitHub never calls this port directly. Fails closed (refuses to start) if
GH_WEBHOOK_SECRET is empty/unset or the initial Temporal connect fails
(never "accept unsigned" or "start anyway, fail per-request").
"""
import asyncio
import logging
import os
import signal
from dataclasses import dataclass
from typing import Any

import aiohttp
from aiohttp import web

from . import audit, temporal_client
from .auth import is_authorized, verify_signature
from .dedup import DeliveryCache
from .github_app import GitHubAppClient
from .grammar import GateCommand, RunCommand, parse

_MAX_BODY_BYTES = 1024 * 1024  # 1MB (research.md/L4)
_MODE_NOT_SUPPORTED_REASON = "mode value not supported pre-005"

logger = logging.getLogger("webhook_bridge.server")


@dataclass
class WebhookDelivery:
    delivery_id: str | None
    signature: str | None
    raw_body: bytes
    is_pull_request: bool
    author_association: str
    author_login: str
    comment_body: str
    repo: str
    pr_number: int
    comment_id: int


def extract_delivery(request: web.Request, raw_body: bytes, payload: dict) -> WebhookDelivery:
    issue = payload.get("issue", {})
    comment = payload.get("comment", {})
    return WebhookDelivery(
        delivery_id=request.headers.get("X-GitHub-Delivery"),
        signature=request.headers.get("X-Hub-Signature-256"),
        raw_body=raw_body,
        is_pull_request=issue.get("pull_request") is not None,
        author_association=comment.get("author_association", ""),
        author_login=comment.get("user", {}).get("login", ""),
        comment_body=comment.get("body", ""),
        repo=payload.get("repository", {}).get("full_name", ""),
        pr_number=issue.get("number", 0),
        comment_id=comment.get("id", 0),
    )


class BridgeApp:
    def __init__(
        self,
        client,
        github_client: GitHubAppClient,
        secret: str,
        allowed_repos: set[str],
    ) -> None:
        self.client = client
        self.github_client = github_client
        self.secret = secret
        self.allowed_repos = allowed_repos
        self.cache = DeliveryCache()

    async def handle_webhook(self, request: web.Request) -> web.Response:
        raw_body = await request.read()

        if not verify_signature(raw_body, request.headers.get("X-Hub-Signature-256"), self.secret):
            return web.Response(status=401)

        if request.headers.get("X-GitHub-Event") != "issue_comment":
            return web.Response(status=202)

        payload = await request.json()
        if payload.get("action") != "created":
            return web.Response(status=202)

        delivery = extract_delivery(request, raw_body, payload)

        if not delivery.delivery_id:
            audit.log_entry(
                author=delivery.author_login,
                comment=delivery.comment_body,
                reason="missing X-GitHub-Delivery header",
                outcome="malformed",
            )
            return web.Response(status=202)

        if not delivery.is_pull_request:
            return web.Response(status=202)

        repo_allowed = delivery.repo.strip().lower() in self.allowed_repos
        if not repo_allowed:
            audit.log_entry(
                author=delivery.author_login,
                comment=delivery.comment_body,
                reason=f"repo not in BRIDGE_ALLOWED_REPOS: {delivery.repo}",
                outcome="repo_not_allowed",
            )
            return web.Response(status=202)

        authorized = await is_authorized(
            self.github_client, delivery.repo, delivery.author_login, delivery.author_association
        )
        if not authorized:
            audit.log_entry(
                author=delivery.author_login,
                comment=delivery.comment_body,
                reason=f"permission_denied: author={delivery.author_login}",
                outcome="permission_denied",
            )
            await self._react(delivery, "confused")
            return web.Response(status=202)

        command = parse(delivery.comment_body)

        if not self.cache.reserve(delivery.delivery_id):
            audit.log_entry(
                author=delivery.author_login,
                comment=delivery.comment_body,
                reason="duplicate delivery",
                outcome="duplicate_ignored",
            )
            return web.Response(status=202)

        if isinstance(command, RunCommand):
            await self._dispatch_run(delivery, command)
        elif isinstance(command, GateCommand):
            await self._dispatch_gate(delivery, command)
        else:
            audit.log_entry(
                author=delivery.author_login,
                comment=delivery.comment_body,
                reason="no grammar match",
                outcome="malformed",
            )

        return web.Response(status=202)

    async def _dispatch_run(self, delivery: WebhookDelivery, command: RunCommand) -> None:
        try:
            pr_info = await self.github_client.get_pull_request(delivery.repo, delivery.pr_number)
        except Exception as exc:  # noqa: BLE001 - fail closed on branch/fork resolution errors
            audit.log_entry(
                author=delivery.author_login,
                comment=delivery.comment_body,
                reason=f"branch/fork resolution failed: {exc}",
                outcome="signal_failed",
            )
            await self._react(delivery, "confused")
            return

        if pr_info["is_cross_repository"]:
            audit.log_entry(
                author=delivery.author_login,
                comment=delivery.comment_body,
                reason="fork PR",
                outcome="fork_rejected",
            )
            await self._react(delivery, "confused")
            return

        if command.mode not in ("full", "vibe"):
            audit.log_entry(
                author=delivery.author_login,
                comment=delivery.comment_body,
                reason=f"unrecognized mode value: {command.mode}",
                outcome="mode_not_supported",
            )
            await self._react(delivery, "confused")
            return

        if command.mode == "vibe":
            audit.log_entry(
                author=delivery.author_login,
                comment=delivery.comment_body,
                reason=_MODE_NOT_SUPPORTED_REASON,
                outcome="mode_not_supported",
            )
            await self._react(delivery, "confused")
            return

        result = await temporal_client.start_run(
            self.client,
            delivery.repo,
            delivery.pr_number,
            pr_info["branch"],
            command.agent_name,
            command.version,
        )
        audit.log_entry(
            author=delivery.author_login,
            comment=delivery.comment_body,
            reason=f"workflow_id={result.workflow_id} started={result.started}",
            outcome="started",
        )
        await self._react(delivery, "rocket")

    async def _dispatch_gate(self, delivery: WebhookDelivery, command: GateCommand) -> None:
        await temporal_client.signal_gate(
            self.client,
            delivery.repo,
            delivery.pr_number,
            command.gate,
            command.decision,
            command.feedback,
            delivery.comment_id,
            delivery.author_login,
            delivery.comment_body,
            self.github_client,
        )

    async def _react(self, delivery: WebhookDelivery, content: str) -> None:
        try:
            await self.github_client.post_reaction(delivery.repo, delivery.comment_id, content)
        except Exception:  # noqa: BLE001 - a reaction failure must never mask the real outcome
            logger.warning("reaction POST failed for comment_id=%s", delivery.comment_id)


def _parse_allowed_repos(raw: str) -> set[str]:
    return {entry.strip().lower() for entry in raw.split(",") if entry.strip()}


async def build_app() -> tuple[web.Application, Any]:
    secret = os.environ.get("GH_WEBHOOK_SECRET", "")
    if not secret:
        raise RuntimeError("GH_WEBHOOK_SECRET is empty/unset — refusing to start (fail closed)")

    client = await temporal_client.connect()

    session = aiohttp.ClientSession()
    github_client = GitHubAppClient(
        app_id=os.environ["SWE_AGENT_APP_ID"],
        private_key_b64=os.environ["SWE_AGENT_APP_PRIVATE_KEY"],
        session=session,
    )
    allowed_repos = _parse_allowed_repos(os.environ.get("BRIDGE_ALLOWED_REPOS", ""))

    bridge = BridgeApp(client, github_client, secret, allowed_repos)

    app = web.Application(client_max_size=_MAX_BODY_BYTES)
    app.router.add_post("/webhook", bridge.handle_webhook)

    async def _on_cleanup(_app: web.Application) -> None:
        await session.close()

    app.on_cleanup.append(_on_cleanup)
    return app, client


async def main() -> None:
    app, _ = await build_app()
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("BRIDGE_PORT", "3000"))
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    logger.info("webhook_bridge listening on 127.0.0.1:%s", port)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    await stop_event.wait()
    logger.info("webhook_bridge shutting down")
    await runner.cleanup()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
