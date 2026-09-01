"""SWE agent (§3.2) — implement-only. Runs GitHub Spec Kit's
/speckit-implement against a feature branch whose spec/plan/tasks were
already produced upstream (Spec/Intake, §3.1, done manually), then opens
a PR. See SKILL.md for what's deliberately deferred this pass.
"""
import glob
import os
import re
import subprocess
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query

IMPLEMENT_PROMPT = """/speckit-implement

After implementing, run this repo's existing tests/verification locally \
to confirm the change works. Then commit your changes locally with \
`git add -A && git commit` — including if local verification doesn't \
fully pass, in which case say why in the commit message; a human \
reviews the result either way. When you are done, STOP: do not run \
`git push` and do not open a pull request. A separate step outside \
this conversation handles pushing and opening the PR."""

# repo/branch are workflow inputs (ultimately caller-supplied) threaded
# straight into git/gh argv. Reject anything not shaped like a plain
# "owner/name" repo slug or git ref, so a value like "--upload-pack=..."
# can't be parsed as a flag by git/gh (argument injection) instead of a
# positional repo/branch name.
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


def clone_and_checkout(repo: str, branch: str, work_root: Path) -> Path:
    _validate_repo(repo)
    _validate_branch(branch)
    # git clone via an explicit https URL, not `gh repo clone` — the
    # latter defers to the local gh CLI's configured git_protocol
    # (per-host in ~/.config/gh/hosts.yml), which may be set to ssh with
    # no working key, as it was on this machine.
    #
    # GH_TOKEN (e.g. a GitHub App installation token minted by the caller)
    # is embedded in the clone URL so this works with no ambient `gh`/git
    # credential helper — required inside an ephemeral E2B sandbox, which
    # has neither. Unset falls back to the unauthenticated URL, keeping the
    # host-CLI path (which does have a credential helper) unchanged.
    token = os.environ.get("GH_TOKEN")
    credential = f"x-access-token:{token}@" if token else ""
    clone_url = f"https://{credential}github.com/{repo}.git"
    try:
        _run(["git", "clone", clone_url, str(work_root)])
    except subprocess.CalledProcessError as e:
        # Never let the embedded credential reach a log or PR comment.
        if not token:
            raise
        raise _scrubbed(e, token) from None

    _run(["git", "fetch", "origin", branch], cwd=work_root)
    _run(["git", "checkout", branch], cwd=work_root)
    return work_root


def verify_spec_exists(checkout: Path) -> None:
    if not glob.glob(str(checkout / "specs" / "*" / "tasks.md")):
        raise RuntimeError(
            f"No specs/*/tasks.md found on checked-out branch at {checkout} "
            "— /speckit-specify -> /speckit-plan -> /speckit-tasks must run "
            "upstream before this agent."
        )


def build_options(cwd: Path) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        cwd=str(cwd),
        allowed_tools=["Bash", "Read", "Edit", "Write", "Grep", "Glob"],
        permission_mode="bypassPermissions",
        # NOTE: setting_sources deliberately left at its default (loads
        # user/project/local settings, matching CLI defaults) — that's
        # also what makes /speckit-implement discoverable at all
        # (verified live: setting_sources=[] makes the CLI report
        # "Unknown command: /speckit-implement", since project-level
        # skill discovery is gated by the same "project" source as
        # settings.json). A hook committed to the checkout's own
        # .claude/settings*.json could therefore auto-execute in this
        # session — but that's not a new risk on top of the already
        # unsandboxed, full-Bash-access "Known gap" in SKILL.md; a
        # malicious branch can already make the model run anything via
        # Bash without needing a hook.
    )


async def run_implement(checkout: Path) -> str:
    transcript: list[str] = []
    async for message in query(prompt=IMPLEMENT_PROMPT, options=build_options(checkout)):
        transcript.append(str(message))
    return "\n".join(transcript)


def verify_left_main(checkout: Path, branch: str) -> None:
    head = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=checkout)
    if head in ("main", "master"):
        raise RuntimeError(
            f"Agent left HEAD on '{head}' instead of '{branch}' — aborting "
            "before any push."
        )


def _head_sha(checkout: Path) -> str:
    return _run(["git", "rev-parse", "HEAD"], cwd=checkout)


def verify_new_commit(checkout: Path, sha_before: str) -> None:
    if _head_sha(checkout) == sha_before:
        raise RuntimeError(
            "Agent made no new commit — nothing to push. It may have "
            "produced only uncommitted changes (or none at all); rerun "
            "with the prompt's commit instruction, or inspect manually."
        )


def _pr_body_from_spec(checkout: Path) -> str:
    spec_files = glob.glob(str(checkout / "specs" / "*" / "spec.md"))
    if not spec_files:
        return "(no specs/*/spec.md found to source a description from)"
    return Path(spec_files[0]).read_text()


def push_and_open_pr(checkout: Path, repo: str, branch: str, title: str) -> str:
    pr_body = _pr_body_from_spec(checkout)
    _run(["git", "push", "-u", "origin", branch], cwd=checkout)
    body_path = checkout / ".pr-body.md"
    body_path.write_text(pr_body)
    try:
        return _run(
            [
                "gh", "pr", "create",
                "--repo", repo,
                "--head", branch,
                "--title", title,
                "--body-file", str(body_path),
            ],
            cwd=checkout,
        )
    except subprocess.CalledProcessError as e:
        if "already exists" in (e.stderr or ""):
            return e.stderr.strip()
        raise
    finally:
        body_path.unlink(missing_ok=True)


def verify_pr_exists(repo: str, branch: str) -> str:
    out = _run(
        ["gh", "pr", "list", "--repo", repo, "--head", branch, "--json", "url"],
    )
    if not out or out == "[]":
        raise RuntimeError(f"No PR found for {repo}#{branch} after push_and_open_pr.")
    import json

    urls = [pr["url"] for pr in json.loads(out)]
    return urls[0]


async def run(repo: str, branch: str, work_root: Path) -> str:
    checkout = clone_and_checkout(repo, branch, work_root)
    verify_spec_exists(checkout)
    sha_before = _head_sha(checkout)
    await run_implement(checkout)
    verify_left_main(checkout, branch)
    verify_new_commit(checkout, sha_before)
    title = f"Implement {branch}"
    push_and_open_pr(checkout, repo, branch, title)
    return verify_pr_exists(repo, branch)


if __name__ == "__main__":
    import asyncio
    import sys
    import tempfile

    async def _main() -> None:
        repo, branch = sys.argv[1], sys.argv[2]
        with tempfile.TemporaryDirectory() as td:
            pr_url = await run(repo, branch, Path(td))
            print(pr_url)

    asyncio.run(_main())
