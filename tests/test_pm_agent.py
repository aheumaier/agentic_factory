"""Unit tests for harness/pm-agent/agent.py — no real GitHub network
access or model call: `subprocess.run` is faked via `agent.subprocess.run`
and the model call via `agent.query`. See conftest.py for how `agent`
becomes importable with no `claude-agent-sdk`/`braintrust` installed in
the root venv.
"""
import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import agent


# ---------------------------------------------------------------------------
# Issue-Shaping (User Story 1)
# ---------------------------------------------------------------------------


def _issue_view_result(title="Raw title", body="Raw body", linked_pr=False):
    payload = {
        "title": title,
        "body": body,
        "closedByPullRequestsReferences": [{"number": 5}] if linked_pr else [],
    }
    return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")


def _make_issue_fake_run(calls, *, linked_pr=False, title="Raw title", body="Raw body"):
    def fake_run(cmd, cwd=None, **kwargs):
        calls.append(cmd)
        if cmd[:3] == ["gh", "issue", "view"]:
            return _issue_view_result(title=title, body=body, linked_pr=linked_pr)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    return fake_run


def _make_shape_fake_query(captured, response_text):
    async def fake_query(*, prompt, options):
        captured["prompt"] = prompt
        captured["options"] = options
        yield response_text

    return fake_query


def test_shape_issue_rejects_linked_pr():
    calls = []
    fake_run = _make_issue_fake_run(calls, linked_pr=True)

    async def fake_query(*, prompt, options):
        raise AssertionError("model must not be called when a PR is linked")
        yield  # pragma: no cover

    with patch.object(agent.subprocess, "run", fake_run), patch.object(
        agent, "query", fake_query
    ):
        try:
            asyncio.run(agent.shape_issue("owner/repo", 42))
            raise AssertionError("expected RuntimeError")
        except RuntimeError:
            pass

    assert not any(c[:3] == ["gh", "issue", "edit"] for c in calls)


def test_shape_issue_zero_tools():
    calls = []
    fake_run = _make_issue_fake_run(calls)
    captured = {}
    fake_query = _make_shape_fake_query(captured, "TITLE: New\nBODY:\nNew body")

    with patch.object(agent.subprocess, "run", fake_run), patch.object(
        agent, "query", fake_query
    ):
        asyncio.run(agent.shape_issue("owner/repo", 42))

    assert captured["options"].tools == []
    assert captured["options"].permission_mode != "bypassPermissions"


def test_shape_issue_direct_to_anthropic():
    calls = []
    fake_run = _make_issue_fake_run(calls)
    captured = {}
    fake_query = _make_shape_fake_query(captured, "TITLE: New\nBODY:\nNew body")

    with patch.object(agent.subprocess, "run", fake_run), patch.object(
        agent, "query", fake_query
    ):
        asyncio.run(agent.shape_issue("owner/repo", 42))

    assert "ANTHROPIC_BASE_URL" not in captured["options"].env
    assert captured["options"].env == {"ANTHROPIC_API_KEY": agent.ANTHROPIC_PLATFORM_API_KEY}


def test_shape_issue_edits_issue():
    calls = []
    fake_run = _make_issue_fake_run(calls, title="Raw title", body="Raw body")
    fake_query = _make_shape_fake_query({}, "TITLE: New Title\nBODY:\nNew body text")

    with patch.object(agent.subprocess, "run", fake_run), patch.object(
        agent, "query", fake_query
    ):
        result = asyncio.run(agent.shape_issue("owner/repo", 42))

    edit_calls = [c for c in calls if c[:3] == ["gh", "issue", "edit"]]
    assert len(edit_calls) == 1
    edit_cmd = edit_calls[0]
    assert "New Title" in edit_cmd
    assert "New body text" in edit_cmd
    assert result == {"number": 42, "title": "New Title", "body": "New body text"}


def test_shape_issue_preserves_original():
    calls = []
    fake_run = _make_issue_fake_run(calls, title="Original title", body="Original body")
    fake_query = _make_shape_fake_query({}, "TITLE: New Title\nBODY:\nNew body text")

    with patch.object(agent.subprocess, "run", fake_run), patch.object(
        agent, "query", fake_query
    ):
        asyncio.run(agent.shape_issue("owner/repo", 42))

    kinds = [c[:3] for c in calls]
    comment_idx = kinds.index(["gh", "issue", "comment"])
    edit_idx = kinds.index(["gh", "issue", "edit"])
    assert comment_idx < edit_idx

    comment_cmd = calls[comment_idx]
    comment_body = comment_cmd[comment_cmd.index("--body") + 1]
    assert "Original title" in comment_body
    assert "Original body" in comment_body


# ---------------------------------------------------------------------------
# Spec-Review (User Story 2)
# ---------------------------------------------------------------------------


def _make_review_fake_run(
    calls,
    *,
    create_spec=True,
    spec_relpath="specs/003-pm-agent-review-gate/spec.md",
    existing_comments=None,
    sha="abc1234",
):
    existing_comments = existing_comments if existing_comments is not None else []

    def fake_run(cmd, cwd=None, **kwargs):
        calls.append(cmd)
        if cmd[:2] == ["git", "clone"]:
            target = Path(cmd[-1])
            target.mkdir(parents=True, exist_ok=True)
            if create_spec:
                spec_file = target / spec_relpath
                spec_file.parent.mkdir(parents=True, exist_ok=True)
                spec_file.write_text("# Spec\n")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[:2] == ["git", "config"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[:3] == ["git", "rev-parse", "--short"]:
            return SimpleNamespace(returncode=0, stdout=sha, stderr="")
        if cmd[:3] == ["gh", "pr", "view"]:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"comments": existing_comments}),
                stderr="",
            )
        if cmd[:3] == ["gh", "pr", "comment"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    return fake_run


def _make_review_fake_query(captured, response_text="A value-judgment review."):
    async def fake_query(*, prompt, options):
        captured["prompt"] = prompt
        captured["options"] = options
        captured["env_during_call"] = dict(agent.os.environ)
        gh_config_dir = Path(options.env["GH_CONFIG_DIR"])
        captured["gh_config_dir_is_empty_dir"] = (
            gh_config_dir.is_dir() and list(gh_config_dir.iterdir()) == []
        )
        yield response_text

    return fake_query


def test_review_spec_env_scrubbed(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "secret-token")
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")
    calls = []
    fake_run = _make_review_fake_run(calls)
    captured = {}
    fake_query = _make_review_fake_query(captured)

    with patch.object(agent.subprocess, "run", fake_run), patch.object(
        agent, "query", fake_query
    ):
        asyncio.run(
            agent.review_spec("owner/repo", "003-pm-agent-review-gate", "pr-url", attempt=1)
        )

    assert "GH_TOKEN" not in captured["env_during_call"]
    assert "GITHUB_TOKEN" not in captured["env_during_call"]
    assert agent.os.environ["GH_TOKEN"] == "secret-token"
    assert agent.os.environ["GITHUB_TOKEN"] == "secret-token"

    env_override = captured["options"].env
    assert env_override["GIT_TERMINAL_PROMPT"] == "0"
    assert captured["gh_config_dir_is_empty_dir"]


def test_review_spec_no_bash_no_hooks():
    calls = []
    fake_run = _make_review_fake_run(calls)
    captured = {}
    fake_query = _make_review_fake_query(captured)

    with patch.object(agent.subprocess, "run", fake_run), patch.object(
        agent, "query", fake_query
    ):
        asyncio.run(
            agent.review_spec("owner/repo", "003-pm-agent-review-gate", "pr-url", attempt=1)
        )

    assert captured["options"].tools == ["Read", "Grep", "Glob"]
    assert captured["options"].setting_sources == []


def test_review_spec_litellm_routed():
    calls = []
    fake_run = _make_review_fake_run(calls)
    captured = {}
    fake_query = _make_review_fake_query(captured)

    with patch.object(agent.subprocess, "run", fake_run), patch.object(
        agent, "query", fake_query
    ):
        asyncio.run(
            agent.review_spec("owner/repo", "003-pm-agent-review-gate", "pr-url", attempt=1)
        )

    env_override = captured["options"].env
    assert env_override["ANTHROPIC_BASE_URL"] == agent.LITELLM_BASE_URL
    assert env_override["ANTHROPIC_API_KEY"] == agent.LITELLM_API_KEY


def test_review_spec_credential_helper_disabled():
    calls = []
    fake_run = _make_review_fake_run(calls)
    fake_query = _make_review_fake_query({})

    with patch.object(agent.subprocess, "run", fake_run), patch.object(
        agent, "query", fake_query
    ):
        asyncio.run(
            agent.review_spec("owner/repo", "003-pm-agent-review-gate", "pr-url", attempt=1)
        )

    clone_idx = next(i for i, c in enumerate(calls) if c[:2] == ["git", "clone"])
    config_idx = next(i for i, c in enumerate(calls) if c[:2] == ["git", "config"])
    assert clone_idx < config_idx
    assert calls[config_idx] == [
        "git", "config", "--local", "credential.helper", "",
    ]


def test_review_spec_no_attempt_cap():
    calls = []
    fake_run = _make_review_fake_run(calls)
    fake_query = _make_review_fake_query({})

    with patch.object(agent.subprocess, "run", fake_run), patch.object(
        agent, "query", fake_query
    ):
        result = asyncio.run(
            agent.review_spec("owner/repo", "003-pm-agent-review-gate", "pr-url", attempt=99)
        )

    assert result["attempt"] == 99


def test_review_spec_idempotent_post():
    existing_body = (
        "<!-- pm-agent:review attempt=2 spec=deadbeef -->\n\nAlready posted."
    )
    calls = []
    fake_run = _make_review_fake_run(
        calls, existing_comments=[{"body": existing_body}]
    )

    async def fake_query(*, prompt, options):
        raise AssertionError("model must not be called on an idempotent retry")
        yield  # pragma: no cover

    with patch.object(agent.subprocess, "run", fake_run), patch.object(
        agent, "query", fake_query
    ):
        result = asyncio.run(
            agent.review_spec("owner/repo", "003-pm-agent-review-gate", "pr-url", attempt=2)
        )

    assert result == {"writeup": existing_body, "attempt": 2}
    assert not any(c[:3] == ["gh", "pr", "comment"] for c in calls)


def test_review_spec_marker_includes_spec_sha():
    calls = []
    fake_run = _make_review_fake_run(calls, sha="deadbee")
    fake_query = _make_review_fake_query({}, "A review.")

    with patch.object(agent.subprocess, "run", fake_run), patch.object(
        agent, "query", fake_query
    ):
        asyncio.run(
            agent.review_spec("owner/repo", "003-pm-agent-review-gate", "pr-url", attempt=3)
        )

    comment_cmd = next(c for c in calls if c[:3] == ["gh", "pr", "comment"])
    body = comment_cmd[comment_cmd.index("--body") + 1]
    assert re.match(r"^<!-- pm-agent:review attempt=3 spec=deadbee -->", body)


def test_review_spec_writeup_includes_attempt_and_feedback():
    calls = []
    fake_run = _make_review_fake_run(calls)
    captured = {}

    async def fake_query(*, prompt, options):
        captured["prompt"] = prompt
        yield "Feedback addressed: fix the typo in section 2."

    with patch.object(agent.subprocess, "run", fake_run), patch.object(
        agent, "query", fake_query
    ):
        result = asyncio.run(
            agent.review_spec(
                "owner/repo",
                "003-pm-agent-review-gate",
                "pr-url",
                attempt=2,
                feedback="fix the typo in section 2",
            )
        )

    assert "fix the typo in section 2" in captured["prompt"]
    assert "attempt=2" in result["writeup"]
    assert "fix the typo in section 2" in result["writeup"]


def test_review_spec_spec_path_default_and_override():
    calls = []
    fake_run = _make_review_fake_run(
        calls, spec_relpath="specs/some-branch/spec.md"
    )
    fake_query = _make_review_fake_query({})

    with patch.object(agent.subprocess, "run", fake_run), patch.object(
        agent, "query", fake_query
    ):
        result = asyncio.run(
            agent.review_spec("owner/repo", "some-branch", "pr-url", attempt=1)
        )
    assert result["attempt"] == 1

    calls2 = []
    fake_run2 = _make_review_fake_run(
        calls2, spec_relpath="specs/other-slug/spec.md"
    )
    fake_query2 = _make_review_fake_query({})

    with patch.object(agent.subprocess, "run", fake_run2), patch.object(
        agent, "query", fake_query2
    ):
        result2 = asyncio.run(
            agent.review_spec(
                "owner/repo",
                "main",
                "pr-url",
                attempt=1,
                spec_dir="specs/other-slug",
            )
        )
    assert result2["attempt"] == 1


def test_review_spec_missing_spec_raises():
    calls = []
    fake_run = _make_review_fake_run(calls, create_spec=False)
    fake_query = _make_review_fake_query({})

    with patch.object(agent.subprocess, "run", fake_run), patch.object(
        agent, "query", fake_query
    ):
        try:
            asyncio.run(
                agent.review_spec(
                    "owner/repo", "003-pm-agent-review-gate", "pr-url", attempt=1
                )
            )
            raise AssertionError("expected RuntimeError")
        except RuntimeError:
            pass
