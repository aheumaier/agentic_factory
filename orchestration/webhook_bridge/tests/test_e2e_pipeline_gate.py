"""End-to-end test chaining 002 (webhook_bridge) and 003 (pm-agent's
review_spec()): a real HTTP POST through the real BridgeApp, a real
Temporal connection/signal round-trip, and a real review_spec() call
(with git/gh/model doubled at the same subprocess/query boundary
tests/test_pm_agent.py already uses) — the same combination proved out
manually per specs/002-webhook-trigger-bridge/tasks.md T046, now asserted
automatically.

specs/002's and specs/003's own Assumptions are explicit that turning a
PM writeup into a pm_approved/pm_rejected:<feedback> decision comment is
a human step, out of scope for either feature. This test's "glue" line
(deriving that decision from the real writeup text) stands in for that
human — it is not part of either feature's implementation.

Skips like test_integration.py if Temporal isn't reachable at
localhost:7233 (needs `make up`). No real GitHub, model, or git network
access: github_client is a MagicMock, agent.query and agent.subprocess.run
are patched.
"""
import asyncio
import json
import sys
import types
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from temporalio.client import Client
from temporalio.worker import Worker

# --- Make harness/pm-agent/agent.py importable under orchestration's venv
# (no claude_agent_sdk/dotenv installed there — confirmed via
# `uv run python -c "import dotenv"` raising ModuleNotFoundError; braintrust
# IS really installed here but is stubbed anyway so agent.py's module-level
# braintrust.init_logger(...) call never needs BRAINTRUST_API_KEY/network).
PM_AGENT_DIR = Path(__file__).resolve().parents[3] / "harness" / "pm-agent"
sys.path.insert(0, str(PM_AGENT_DIR))

if "claude_agent_sdk" not in sys.modules:
    _sdk_stub = types.ModuleType("claude_agent_sdk")

    class ClaudeAgentOptions:
        def __init__(self, **kwargs):
            self.tools = kwargs.get("tools")
            self.allowed_tools = kwargs.get("allowed_tools", [])
            self.permission_mode = kwargs.get("permission_mode")
            self.setting_sources = kwargs.get("setting_sources")
            self.cwd = kwargs.get("cwd")
            self.env = kwargs.get("env", {})

    async def _stub_query(*, prompt, options=None):
        raise RuntimeError("claude_agent_sdk.query stub called directly — patch agent.query")
        yield  # pragma: no cover - keeps this an async generator

    _sdk_stub.ClaudeAgentOptions = ClaudeAgentOptions
    _sdk_stub.query = _stub_query
    sys.modules["claude_agent_sdk"] = _sdk_stub

if "dotenv" not in sys.modules:
    _dotenv_stub = types.ModuleType("dotenv")
    _dotenv_stub.load_dotenv = lambda *a, **k: False
    sys.modules["dotenv"] = _dotenv_stub

if "braintrust" not in sys.modules:
    _bt_stub = types.ModuleType("braintrust")

    class _StubLogger:
        def flush(self):
            pass

    _bt_stub.init_logger = lambda project=None: _StubLogger()
    _bt_stub.auto_instrument = lambda: None
    sys.modules["braintrust"] = _bt_stub

import agent  # noqa: E402 - path/stub setup above must run first

from webhook_bridge import temporal_client  # noqa: E402
from webhook_bridge.server import BridgeApp  # noqa: E402

from webhook_bridge.tests._pipeline_workflow_stub import AgentPipelineWorkflow  # noqa: E402

SECRET = "s3cr3t"
REPO = "owner/repo"


async def _connect_or_skip() -> Client:
    try:
        return await Client.connect("localhost:7233")
    except Exception as exc:  # noqa: BLE001 - environment-dependent skip
        pytest.skip(f"Temporal not reachable at localhost:7233: {exc}")


def _sign(body: bytes) -> str:
    import hashlib
    import hmac

    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


async def _post(bridge: BridgeApp, payload: dict, delivery_id: str) -> "web.Response":
    app = web.Application()
    app.router.add_post("/webhook", bridge.handle_webhook)
    async with TestClient(TestServer(app)) as client:
        body = json.dumps(payload).encode()
        headers = {
            "X-Hub-Signature-256": _sign(body),
            "X-GitHub-Event": "issue_comment",
            "X-GitHub-Delivery": delivery_id,
        }
        return await client.post("/webhook", data=body, headers=headers)


def _payload(pr_number: int, comment_id: int, body: str) -> dict:
    return {
        "action": "created",
        "repository": {"full_name": REPO},
        "issue": {"number": pr_number, "pull_request": {}},
        "comment": {
            "id": comment_id,
            "body": body,
            "author_association": "OWNER",
            "user": {"login": "alice"},
        },
    }


async def _resolve_or_fail(client: Client, pr_number: int, wf_id: str):
    """Search-attribute visibility is eventually consistent (as in
    test_integration.py) — poll briefly rather than assuming an immediate
    read-after-write.
    """
    for _ in range(25):
        resolution = await temporal_client.resolve_gate_target(client, REPO, pr_number)
        if resolution.handle is not None:
            assert resolution.handle.id == wf_id
            return
        await asyncio.sleep(0.2)
    raise AssertionError("workflow never became visible to resolve_gate_target")


# ---------------------------------------------------------------------------
# pm-agent review_spec() fixtures (trimmed/adapted from tests/test_pm_agent.py)
# ---------------------------------------------------------------------------


def _make_review_fake_run(calls, *, existing_comments=None, sha="abc1234"):
    existing_comments = existing_comments if existing_comments is not None else []

    def fake_run(cmd, cwd=None, **kwargs):
        calls.append(cmd)
        if cmd[:2] == ["git", "clone"]:
            target = Path(cmd[-1])
            branch = cmd[cmd.index("--branch") + 1]
            spec_file = target / "specs" / branch / "spec.md"
            spec_file.parent.mkdir(parents=True, exist_ok=True)
            spec_file.write_text("# Spec\n")
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[:2] == ["git", "config"]:
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[:3] == ["git", "rev-parse", "--short"]:
            return types.SimpleNamespace(returncode=0, stdout=sha, stderr="")
        if cmd[:3] == ["gh", "pr", "view"]:
            return types.SimpleNamespace(
                returncode=0, stdout=json.dumps({"comments": existing_comments}), stderr=""
            )
        if cmd[:3] == ["gh", "pr", "comment"]:
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    return fake_run


def _make_review_fake_query(response_text: str):
    async def fake_query(*, prompt, options):
        yield response_text

    return fake_query


def _decision_from_writeup(writeup: str) -> str:
    # The human-in-the-loop step 002/003 both explicitly leave out of
    # scope: this test makes it deterministic instead of a person reading
    # the PR and posting a comment.
    if "reject" in writeup.lower():
        first_line = writeup.strip().splitlines()[-1]
        return f"pm_rejected: {first_line}"
    return "pm_approved"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_pm_approval_writeup_drives_real_bridge_signal():
    client = await _connect_or_skip()

    run_id = uuid.uuid4().hex[:8]
    branch = f"e2e-pm-approve-{run_id}"
    pr_number = uuid.uuid4().int % 1_000_000
    agent_name = f"demo-widget-{run_id}"
    version = "1"
    wf_id = temporal_client.workflow_id(REPO, agent_name, version)

    github_client = MagicMock()
    github_client.get_pull_request = AsyncMock(
        return_value={"branch": branch, "is_cross_repository": False}
    )
    github_client.post_reaction = AsyncMock()

    bridge = BridgeApp(client, github_client, SECRET, allowed_repos={REPO.lower()})
    pr_url = "https://github.com/owner/repo/pull/9"

    async with Worker(
        client, task_queue=temporal_client.TASK_QUEUE, workflows=[AgentPipelineWorkflow]
    ):
        handle = None
        try:
            resp = await _post(
                bridge,
                _payload(
                    pr_number, 1,
                    f"@pipeline-agent run mode=full agent={agent_name} version={version}",
                ),
                delivery_id=f"d-run-{run_id}",
            )
            assert resp.status == 202
            github_client.post_reaction.assert_awaited_with(REPO, 1, "rocket")

            handle = client.get_workflow_handle(wf_id)
            assert await handle.query(AgentPipelineWorkflow.stage) == "pm"

            calls = []
            fake_run = _make_review_fake_run(calls)
            fake_query = _make_review_fake_query("A value-judgment review. Looks good.")
            with patch.object(agent.subprocess, "run", fake_run), patch.object(
                agent, "query", fake_query
            ):
                result = await agent.review_spec(REPO, branch, pr_url, attempt=1)

            assert result["attempt"] == 1
            comment_cmd = next(c for c in calls if c[:3] == ["gh", "pr", "comment"])
            comment_body = comment_cmd[comment_cmd.index("--body") + 1]
            assert comment_body.startswith("<!-- pm-agent:review attempt=1 spec=abc1234 -->")

            decision = _decision_from_writeup(result["writeup"])
            assert decision == "pm_approved"

            await _resolve_or_fail(client, pr_number, wf_id)
            resp = await _post(
                bridge, _payload(pr_number, 2, decision), delivery_id=f"d-gate-{run_id}"
            )
            assert resp.status == 202
            github_client.post_reaction.assert_awaited_with(REPO, 2, "eyes")

            assert await handle.query(AgentPipelineWorkflow.stage) == "plan"
        finally:
            if handle is not None:
                try:
                    await handle.terminate()
                except Exception:  # noqa: BLE001 - best-effort cleanup only
                    pass


async def test_pm_rejection_feedback_drives_reject_signal_and_rereview():
    client = await _connect_or_skip()

    run_id = uuid.uuid4().hex[:8]
    branch = f"e2e-pm-reject-{run_id}"
    pr_number = uuid.uuid4().int % 1_000_000
    agent_name = f"demo-widget-2-{run_id}"
    version = "1"
    wf_id = temporal_client.workflow_id(REPO, agent_name, version)

    github_client = MagicMock()
    github_client.get_pull_request = AsyncMock(
        return_value={"branch": branch, "is_cross_repository": False}
    )
    github_client.post_reaction = AsyncMock()

    bridge = BridgeApp(client, github_client, SECRET, allowed_repos={REPO.lower()})
    pr_url = "https://github.com/owner/repo/pull/10"

    async with Worker(
        client, task_queue=temporal_client.TASK_QUEUE, workflows=[AgentPipelineWorkflow]
    ):
        handle = None
        try:
            resp = await _post(
                bridge,
                _payload(
                    pr_number, 1,
                    f"@pipeline-agent run mode=full agent={agent_name} version={version}",
                ),
                delivery_id=f"d-run-{run_id}",
            )
            assert resp.status == 202

            handle = client.get_workflow_handle(wf_id)
            assert await handle.query(AgentPipelineWorkflow.stage) == "pm"

            # Attempt 1: model flags scope, real review_spec() call.
            calls1 = []
            fake_run1 = _make_review_fake_run(calls1)
            fake_query1 = _make_review_fake_query(
                "This spec is over-scoped and should reject the extra feature."
            )
            with patch.object(agent.subprocess, "run", fake_run1), patch.object(
                agent, "query", fake_query1
            ):
                result1 = await agent.review_spec(REPO, branch, pr_url, attempt=1)

            decision1 = _decision_from_writeup(result1["writeup"])
            assert decision1.startswith("pm_rejected:")

            await _resolve_or_fail(client, pr_number, wf_id)
            resp = await _post(
                bridge, _payload(pr_number, 2, decision1), delivery_id=f"d-gate1-{run_id}"
            )
            assert resp.status == 202
            github_client.post_reaction.assert_awaited_with(REPO, 2, "eyes")

            state = await handle.query(AgentPipelineWorkflow.state)
            assert "pm" in state["rejected"]
            assert await handle.query(AgentPipelineWorkflow.stage) == "pm"

            # Real re-review (FR-010): attempt=2 with feedback, different
            # model output.
            calls2 = []
            fake_run2 = _make_review_fake_run(calls2)
            fake_query2 = _make_review_fake_query(
                "Feedback addressed: scope trimmed as requested. Looks good now."
            )
            with patch.object(agent.subprocess, "run", fake_run2), patch.object(
                agent, "query", fake_query2
            ):
                result2 = await agent.review_spec(
                    REPO, branch, pr_url, attempt=2, feedback="see writeup"
                )

            assert result2["writeup"] != result1["writeup"]
            assert "Feedback addressed" in result2["writeup"]

            # Idempotency (FR-011): a second attempt=2 call must not
            # re-invoke the model or re-post a comment.
            calls3 = []
            fake_run3 = _make_review_fake_run(
                calls3, existing_comments=[{"body": result2["writeup"]}]
            )

            async def _fail_if_called(*, prompt, options):
                raise AssertionError("model must not be called on an idempotent retry")
                yield  # pragma: no cover

            with patch.object(agent.subprocess, "run", fake_run3), patch.object(
                agent, "query", _fail_if_called
            ):
                result2_again = await agent.review_spec(
                    REPO, branch, pr_url, attempt=2, feedback="see writeup"
                )
            assert result2_again["writeup"] == result2["writeup"]
            assert not any(c[:3] == ["gh", "pr", "comment"] for c in calls3)

            decision2 = _decision_from_writeup(result2["writeup"])
            assert decision2 == "pm_approved"

            resp = await _post(
                bridge, _payload(pr_number, 3, decision2), delivery_id=f"d-gate2-{run_id}"
            )
            assert resp.status == 202

            assert await handle.query(AgentPipelineWorkflow.stage) == "plan"
        finally:
            if handle is not None:
                try:
                    await handle.terminate()
                except Exception:  # noqa: BLE001 - best-effort cleanup only
                    pass
