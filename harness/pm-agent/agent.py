"""PM agent — Issue-Shaping and Spec-Review Gate. Two independently
callable capabilities: `shape_issue()` rewrites a raw GitHub issue's
title/body for scope clarity before it becomes a spec; `review_spec()`
posts a value-judgment writeup (right thing to build? right scope? any
gold-plating?) to a target-repo PR, read-only against the branch under
review. See SKILL.md for the design source and this pass's deviations.
"""
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import braintrust
from claude_agent_sdk import ClaudeAgentOptions, query
from dotenv import load_dotenv

# Load this repo's own root .env (never the developer's shell profile),
# without overriding a value already present in the process environment
# — a var exported ambiently (e.g. CI secrets, or a developer's own
# shell export) still wins over the repo-local file.
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

# Observability (§3.8): same project as eval/braintrust/eval.config.py and
# harness/swe-agent/agent.py, so a run's trace lands beside the gate score.
BRAINTRUST_PROJECT = os.environ.get("BRAINTRUST_PROJECT", "agent-factory-pilot")

logger = braintrust.init_logger(project=BRAINTRUST_PROJECT)
braintrust.auto_instrument()

LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "http://localhost:4000")
LITELLM_API_KEY = os.environ.get("LITELLM_MASTER_KEY", "sk-local-master")

# This repo's own Anthropic key is named ANTHROPIC_PLATFORM_API_KEY, not
# ANTHROPIC_API_KEY, specifically to avoid colliding with a developer's
# own ambient ANTHROPIC_API_KEY (e.g. an enterprise Claude subscription
# used for Claude Code itself). The vendored claude_agent_sdk's CLI
# subprocess only ever reads the literal "ANTHROPIC_API_KEY" env var
# (see _internal/session_resume.py) — it has no notion of this repo's
# renamed key. Both direct-to-Anthropic calls in this module must
# therefore pass this value through explicitly as an `env=` override
# under the SDK's fixed name, which also shadows (takes precedence
# over) any ambient personal ANTHROPIC_API_KEY the developer's shell
# already has set, since ClaudeAgentOptions.env merges on top of
# os.environ in the SDK's subprocess launcher.
ANTHROPIC_PLATFORM_API_KEY = os.environ.get("ANTHROPIC_PLATFORM_API_KEY", "")

SHAPE_ISSUE_PROMPT = """You are shaping a raw GitHub issue before it \
becomes a spec. You will be given the issue's current title and body as \
plain text below — you have no tools, so act only on this text.

Rewrite the title and body so that:
- The scope is clear and unambiguous — a reader should know exactly what
  is and is not being asked for.
- The body ends with an explicit note flagging anything that looks like
  gold-plating (asks beyond the issue's actual need) so a reviewer can
  push back on it before work starts.
- The original intent is preserved — you are clarifying scope, not
  changing what is being asked for.

Respond with exactly this format, nothing else:

TITLE: <rewritten title>
BODY:
<rewritten body>

--- ORIGINAL TITLE ---
{title}

--- ORIGINAL BODY ---
{body}
"""

SPEC_REVIEW_PROMPT = """You are reviewing a spec for value and scope \
before build work starts on it. Read {spec_dir}/spec.md in this \
checkout (you have Read/Grep/Glob only — you cannot execute anything or \
mutate this repository).

Write a value-judgment review covering:
- Rightness of scope: is this the right thing to build, and is the scope
  right — not too narrow, not too broad?
- An explicit gold-plating flag: call out anything in the spec that goes
  beyond what's actually needed, or say plainly that you found none.

Be direct and specific, citing the spec's own language where useful."""

FEEDBACK_PROMPT_SUFFIX = """

This is attempt {attempt} at reviewing this spec. A previous review \
raised feedback that should have been addressed since:
{feedback}

Explicitly say whether and how the spec now addresses this feedback."""

# repo/branch are caller-supplied, ultimately threaded into git/gh argv.
# Reject anything not shaped like a plain "owner/name" repo slug or git
# ref, so a value like "--upload-pack=..." can't be parsed as a flag by
# git/gh (argument injection) instead of a positional repo/branch name.
# Mirrors harness/swe-agent/agent.py::_REPO_RE/_BRANCH_RE exactly — one
# shared regex would reject a plain branch name like this feature's own
# ("003-pm-agent-review-gate", no slash).
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./-]*$")


def _validate_repo(repo: str) -> None:
    if not _REPO_RE.match(repo):
        raise ValueError(f"Refusing to use unexpected repo value: {repo!r}")


def _validate_branch(branch: str) -> None:
    if not _BRANCH_RE.match(branch) or branch.startswith("-"):
        raise ValueError(f"Refusing to use unexpected branch value: {branch!r}")


def _scrubbed(
    error: subprocess.CalledProcessError, secret: str
) -> subprocess.CalledProcessError:
    """Copy of `error` with `secret` redacted everywhere it could surface.

    Rebuilding rather than mutating in place also covers `args`, which
    `repr()` prints and which keeps a reference to the *original* cmd
    list even after `error.cmd` is reassigned.
    """

    def redact(value: str | None) -> str:
        return (value or "").replace(secret, "***")

    return subprocess.CalledProcessError(
        error.returncode,
        [redact(arg) for arg in error.cmd],
        output=redact(error.output),
        stderr=redact(error.stderr),
    )


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd, output=result.stdout, stderr=result.stderr
        )
    return result.stdout.strip()


async def _model_text(prompt: str, options: ClaudeAgentOptions) -> str:
    """Run `query()` and return only the model's final text — not a
    join of every SDK message's `str()` (hook events, system init,
    per-turn assistant messages, ...), which is what the raw async
    generator yields and is not itself the model's response text.
    """
    text: str | None = None
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, str):
            text = message  # test doubles yield plain strings directly
        else:
            result = getattr(message, "result", None)
            if result is not None:
                text = result
    if text is None:
        raise RuntimeError(f"Model call produced no usable text result for prompt: {prompt!r}")
    return text


def _parse_shaped_response(text: str) -> tuple[str, str]:
    match = re.search(r"TITLE:\s*(.*?)\s*\nBODY:\s*\n(.*)", text, re.DOTALL)
    if not match:
        raise RuntimeError(
            f"Model response did not match the expected TITLE/BODY format: {text!r}"
        )
    return match.group(1).strip(), match.group(2).strip()


async def shape_issue(repo: str, issue_number: int) -> dict:
    """Rewrite `issue_number`'s title/body for scope clarity (FR-001–
    FR-003, FR-002a). Refuses if the issue has a linked PR. The model has
    zero bound tools (`tools=[]`) — the only mutation happens in code,
    after the model returns, and only after the original content is
    preserved as a comment.
    """
    _validate_repo(repo)

    raw = _run(
        [
            "gh", "issue", "view", str(issue_number),
            "--repo", repo,
            "--json", "title,body,closedByPullRequestsReferences",
        ]
    )
    issue = json.loads(raw)
    if issue.get("closedByPullRequestsReferences"):
        raise RuntimeError(
            f"Issue {repo}#{issue_number} already has a linked pull request "
            "— shape_issue() only acts on raw issues with no linked PR."
        )

    original_title = issue["title"]
    original_body = issue["body"]

    prompt = SHAPE_ISSUE_PROMPT.format(title=original_title, body=original_body)
    options = ClaudeAgentOptions(
        tools=[],
        permission_mode="default",
        env={"ANTHROPIC_API_KEY": ANTHROPIC_PLATFORM_API_KEY},
    )
    response_text = await _model_text(prompt, options)
    new_title, new_body = _parse_shaped_response(response_text)

    _run(
        [
            "gh", "issue", "comment", str(issue_number),
            "--repo", repo,
            "--body",
            "Original issue content, preserved before PM-agent shaping:\n\n"
            f"**Title:** {original_title}\n\n{original_body}",
        ]
    )
    _run(
        [
            "gh", "issue", "edit", str(issue_number),
            "--repo", repo,
            "--title", new_title,
            "--body", new_body,
        ]
    )
    return {"number": issue_number, "title": new_title, "body": new_body}


def _existing_review_comment(repo: str, pr_url: str, attempt: int) -> str | None:
    marker = f"<!-- pm-agent:review attempt={attempt} "
    raw = _run(["gh", "pr", "view", pr_url, "--repo", repo, "--json", "comments"])
    for comment in json.loads(raw).get("comments", []):
        body = comment.get("body", "")
        if body.startswith(marker):
            return body
    return None


async def review_spec(
    repo: str,
    branch: str,
    pr_url: str,
    attempt: int,
    feedback: str | None = None,
    spec_dir: str | None = None,
) -> dict:
    """Post a value-judgment review of `spec_dir`/spec.md (default
    `specs/<branch>`) to `pr_url` (FR-004–FR-011). Read-only against the
    branch under review: no `Bash`, no hook-loading `setting_sources`, and
    the ambient `GH_TOKEN`/`GITHUB_TOKEN` are scrubbed from the parent
    process for the duration of the model call (FR-007). Idempotent per
    `attempt`, which MUST be strictly increasing per distinct review
    request; no attempt cap is enforced here (that budget belongs to
    `specs/005-pipeline-mode-signals-escalation/`).
    """
    _validate_repo(repo)
    _validate_branch(branch)
    if attempt < 1:
        raise ValueError(f"attempt must be >= 1, got {attempt!r}")
    spec_dir = spec_dir or f"specs/{branch}"

    existing = _existing_review_comment(repo, pr_url, attempt)
    if existing is not None:
        return {"writeup": existing, "attempt": attempt}

    with tempfile.TemporaryDirectory() as work_root:
        checkout = Path(work_root) / "checkout"
        token = os.environ.get("GH_TOKEN")
        credential = f"x-access-token:{token}@" if token else ""
        clone_url = f"https://{credential}github.com/{repo}.git"
        try:
            _run(["git", "clone", "--depth", "1", "--branch", branch, clone_url, str(checkout)])
        except subprocess.CalledProcessError as e:
            if not token:
                raise
            raise _scrubbed(e, token) from None
        _run(["git", "config", "--local", "credential.helper", ""], cwd=checkout)

        spec_path = checkout / spec_dir / "spec.md"
        if not spec_path.is_file():
            raise RuntimeError(
                f"No {spec_dir}/spec.md found on checked-out branch {branch!r} "
                f"of {repo} — pass spec_dir explicitly if this branch doesn't "
                "follow the specs/<branch>/ convention."
            )

        prompt = SPEC_REVIEW_PROMPT.format(spec_dir=spec_dir)
        if feedback:
            prompt += FEEDBACK_PROMPT_SUFFIX.format(attempt=attempt, feedback=feedback)

        gh_config_dir = Path(work_root) / "empty-gh-config"
        gh_config_dir.mkdir()
        options = ClaudeAgentOptions(
            cwd=str(checkout),
            tools=["Read", "Grep", "Glob"],
            setting_sources=[],
            permission_mode="default",
            env={
                "GH_CONFIG_DIR": str(gh_config_dir),
                "GIT_TERMINAL_PROMPT": "0",
                "ANTHROPIC_BASE_URL": LITELLM_BASE_URL,
                "ANTHROPIC_API_KEY": LITELLM_API_KEY,
            },
        )

        saved_gh_token = os.environ.pop("GH_TOKEN", None)
        saved_github_token = os.environ.pop("GITHUB_TOKEN", None)
        try:
            review = await _model_text(prompt, options)
        finally:
            if saved_gh_token is not None:
                os.environ["GH_TOKEN"] = saved_gh_token
            if saved_github_token is not None:
                os.environ["GITHUB_TOKEN"] = saved_github_token

        sha = _run(["git", "rev-parse", "--short", "HEAD"], cwd=checkout)

    marker = f"<!-- pm-agent:review attempt={attempt} spec={sha} -->"
    writeup = f"{marker}\n\n{review}"
    _run(["gh", "pr", "comment", pr_url, "--repo", repo, "--body", writeup])
    return {"writeup": writeup, "attempt": attempt}


if __name__ == "__main__":
    import asyncio
    import sys

    async def _main() -> None:
        cmd = sys.argv[1]
        if cmd == "shape-issue":
            repo, issue_number = sys.argv[2], int(sys.argv[3])
            print(await shape_issue(repo, issue_number))
        elif cmd == "review-spec":
            repo, branch, pr_url, attempt = sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])
            feedback = sys.argv[6] if len(sys.argv) > 6 else None
            print(await review_spec(repo, branch, pr_url, attempt, feedback))
        else:
            raise SystemExit(f"Unknown command: {cmd!r} (expected shape-issue|review-spec)")

    asyncio.run(_main())
    logger.flush()
