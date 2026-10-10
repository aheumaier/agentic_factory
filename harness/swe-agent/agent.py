"""SWE agent (§3.2) — implement-only. Implements a feature branch whose
spec/plan/tasks were already produced upstream (Spec/Intake, §3.1, done
manually) — one model session per open task (specs/011 F7-a), or one
GitHub Spec Kit /speckit-implement session — then opens a PR. See SKILL.md
for what's deliberately deferred this pass.
"""
import asyncio
import contextlib
import glob
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import braintrust
from claude_agent_sdk import ClaudeAgentOptions, query

# Sibling module, not a package: agent.py runs as a script (/app in the E2B
# sandbox), so its own directory is on sys.path. specs/009.
from seat_guard import (
    SeatExhausted,
    SeatInvalid,
    force_exhaust_after_commits,
    guarded_query,
    seat_options_env,
)

# Observability (§3.8): same project as eval/braintrust/eval.config.py, so a
# run's trace and its Eval-Gate score land side by side.
BRAINTRUST_PROJECT = os.environ.get("BRAINTRUST_PROJECT", "agent-factory-pilot")

logger = braintrust.init_logger(project=BRAINTRUST_PROJECT)
braintrust.auto_instrument()

IMPLEMENT_PROMPT = """/speckit-implement

This branch may already hold work from an earlier run that was cut off \
(specs/009: a run can hand off mid-task to another seat). Tasks already \
marked `[X]` in tasks.md are done — skip them and continue with the first \
task still marked `[ ]`. Mark each task `[X]` in tasks.md as soon as you \
finish it — one task at a time, never several at once at the end. Each \
time a task is marked done, a checkpoint commit is saved for you, so \
finished work survives an interruption.

After implementing, run this repo's existing tests/verification locally \
to confirm the change works. Then commit your changes locally with \
`git add -A && git commit` — including if local verification doesn't \
fully pass, in which case say why in the commit message; a human \
reviews the result either way. When you are done, STOP: do not run \
`git push` and do not open a pull request. A separate step outside \
this conversation handles pushing and opening the PR."""

# specs/011 F7-a: one session per open task, so a seat outcome cuts off at
# most the task in progress even when the model would batch its ticks. Not
# /speckit-implement: that skill works through the whole list. "Do not
# commit": the force hook counts commits, so a model commit before the tick
# would fire it with the task still open (research R10).
TASK_PROMPT = """Implement only task {task} from {tasks_md}. First read \
the spec.md and plan.md next to it (and any other design docs there) for \
context. Tasks marked `[X]` are already done — an earlier run may have \
been cut off (specs/009) — so do not redo them, and do not start any task \
after {task}.

When {task} is implemented, run this repo's existing tests/verification \
for it, then mark {task} `[X]` in {tasks_md} and STOP. Do not commit: a \
checkpoint commit is saved for you when the task is marked done. Do not \
run `git push` and do not open a pull request. A separate step outside \
this conversation handles pushing and opening the PR."""

FEEDBACK_PROMPT_SUFFIX = """

The previous attempt on this branch failed the Eval-Gate. Feedback:
{feedback}

Address this feedback before re-running verification and committing."""

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


# Real checklist lines, anchored at line start: prose that merely mentions
# "- [ ]" mid-sentence (as specs/009's own tasks.md does) must not count.
_OPEN_TASK_RE = re.compile(r"^\s*- \[ \]", re.MULTILINE)
_DONE_TASK_RE = re.compile(r"^\s*- \[[xX]\]", re.MULTILINE)


def _task_files(checkout: Path, branch: str | None) -> list[Path]:
    """The feature's own tasks.md (Spec Kit: spec dir == branch name) when it
    exists — older specs on the branch may keep open boxes forever — else
    every specs/*/tasks.md."""
    if branch:
        own = checkout / "specs" / branch / "tasks.md"
        if own.is_file():
            return [own]
    return [Path(p) for p in glob.glob(str(checkout / "specs" / "*" / "tasks.md"))]


def has_open_tasks(checkout: Path, branch: str | None = None) -> bool:
    """True if the feature's tasks.md still has an unchecked task (specs/009
    resume: a predecessor seat may already have finished every task)."""
    return any(_OPEN_TASK_RE.search(f.read_text()) for f in _task_files(checkout, branch))


def all_tasks_done(checkout: Path, branch: str | None = None) -> bool:
    """At least one checked task and none open. A tasks.md with no checklist
    at all is not "done" — it was never in Spec Kit form, so implement."""
    files = _task_files(checkout, branch)
    return (
        any(_DONE_TASK_RE.search(f.read_text()) for f in files)
        and not has_open_tasks(checkout, branch)
    )


_DONE_LINE_RE = re.compile(r"^\s*- \[[xX]\]\s*(.*)$", re.MULTILINE)
_OPEN_LINE_RE = re.compile(r"^\s*- \[ \]\s*(.*)$", re.MULTILINE)
_TASK_ID_RE = re.compile(r"T\d+\b")  # "T001a" is no ID


def _open_task_ids(tasks_md: Path) -> list[str] | None:
    """Open task IDs of one tasks.md, in file order; None when an open line
    has no ID — no task to name a session after (specs/011 F7-a)."""
    ids = []
    for text in _OPEN_LINE_RE.findall(tasks_md.read_text()):
        match = _TASK_ID_RE.match(text)
        if not match:
            return None
        ids.append(match.group(0))
    return ids


def _task_open(tasks_md: Path, task: str) -> bool:
    """False too when tasks.md is gone (the model moved it): the remaining
    tasks are skipped instead of crashing the run."""
    try:
        text = tasks_md.read_text()
    except OSError:
        return False
    return re.search(rf"^\s*- \[ \]\s*{task}\b", text, re.MULTILINE) is not None


def _done_task_keys(checkout: Path, branch: str | None) -> list[tuple[str, str]]:
    """Done checklist lines of the feature's tasks.md, in file order, each
    keyed by (file, task ID) (Spec Kit: `- [X] T001 [P] ...`) or else
    (file, its text). Per file: in the every-specs/*/tasks.md fallback, an
    older spec's ticked T001 must not hide this feature's T001."""
    keys: list[tuple[str, str]] = []
    for path in _task_files(checkout, branch):
        for text in _DONE_LINE_RE.findall(path.read_text()):
            match = _TASK_ID_RE.match(text)
            key = (str(path), match.group(0) if match else text.strip())
            if key not in keys:
                keys.append(key)
    return keys


def _git_identity(checkout: Path) -> list[str]:
    """`git -c` fallbacks when no identity is configured — the sandbox image
    sets none, and a harness commit can come before the model's first one
    (specs/011 research R7). A configured identity always wins."""
    configured = subprocess.run(
        ["git", "config", "user.email"], cwd=checkout, capture_output=True, text=True,
    ).stdout.strip()
    if configured:
        return []
    return ["-c", "user.name=swe-agent", "-c", "user.email=swe-agent@users.noreply.github.com"]


class TaskCheckpointer:
    """Deterministic per-task checkpoints (specs/011 F1): called after every
    streamed message, it commits the tree as `checkpoint: <IDs>` once the
    feature's done-task set grows — finished work no longer depends on the
    model remembering to commit. A clean tree (the model committed itself)
    only records the IDs. A failed commit (e.g. index.lock while the model
    commits at the same moment) is retried on the next message."""

    def __init__(self, checkout: Path, branch: str) -> None:
        self.checkout = checkout
        self.branch = branch
        # A predecessor seat's [X] tasks are already on the branch.
        self.saved = set(_done_task_keys(checkout, branch))

    def __call__(self) -> None:
        try:
            keys = _done_task_keys(self.checkout, self.branch)
        except OSError:  # tasks.md mid-rewrite: try again on the next message
            return
        new = [key for key in keys if key not in self.saved]
        if not new:
            return
        ids = [task for _, task in new if _TASK_ID_RE.fullmatch(task)]
        if self._commit("checkpoint: " + (" ".join(ids) or "tasks")):
            self.saved.update(new)

    def finish(self, what: str = "run") -> None:
        """After a normal stream end (of the run, or of one task's session):
        checkpoint new ticks, then commit any edits made after the last one
        (verification fixes) as `checkpoint: end of <what>`."""
        self()
        self._commit(f"checkpoint: end of {what}")

    def _commit(self, message: str) -> bool:
        """Commit everything if the tree is dirty. True once nothing is left
        uncommitted; a failure goes to stderr (stdout is the seat protocol)."""
        try:
            if not _run(["git", "status", "--porcelain"], cwd=self.checkout):
                return True
            _run(["git", "add", "-A"], cwd=self.checkout)
            _run(["git", *_git_identity(self.checkout), "commit", "-m", message],
                 cwd=self.checkout)
            return True
        except subprocess.CalledProcessError as e:
            print(f"checkpoint commit failed, will retry: {e.stderr}", file=sys.stderr)
            return False


def _handoff_index() -> int:
    """This seat's position within the Build invocation (SEAT_HANDOFF_INDEX,
    specs/011 F5); 0 when unset, e.g. on the GitHub-comment path."""
    value = os.environ.get("SEAT_HANDOFF_INDEX", "").strip()
    return int(value) if value.isdigit() else 0


def _seat_token() -> str | None:
    """The subscription-seat OAuth token, when this run is seat-backed
    (Temporal path, specs/009). Unset on the GitHub-comment path
    (swe-agent-build.yml), which still authenticates with an API key — seat
    mode and its exit protocol stay off there."""
    return os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or None


def build_options(cwd: Path, seat_token: str | None = None) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        cwd=str(cwd),
        allowed_tools=["Bash", "Read", "Edit", "Write", "Grep", "Glob"],
        permission_mode="bypassPermissions",
        # Seat mode: the seat token must be the only credential the CLI sees
        # (an inherited API key/base URL would otherwise win, research R1).
        env=seat_options_env(seat_token) if seat_token else {},
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


async def run_implement(
    checkout: Path, feedback: str | None = None, usage: dict | None = None,
    force_check: Callable[[], bool] | None = None,
    on_message: Callable[[], None] | None = None,
    prompt: str = IMPLEMENT_PROMPT,
) -> str:
    """Run one model session on `prompt` (/speckit-implement by default,
    TASK_PROMPT per task — specs/011 F7-a). In seat mode the stream goes through
    seat_guard, which records last-seen usage into `usage` and raises
    SeatExhausted/SeatInvalid on a seat outcome (specs/009). `force_check`
    is seat_guard's test hook (SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS).
    `on_message` runs after every message — before seat_guard polls
    `force_check` for it, so the hook counts that message's checkpoint."""
    if feedback:
        prompt += FEEDBACK_PROMPT_SUFFIX.format(feedback=feedback)
    seat_token = _seat_token()
    options = build_options(checkout, seat_token)
    stream = (
        guarded_query(
            prompt, options, usage if usage is not None else {},
            query_fn=query, force_check=force_check,
        )
        if seat_token
        else query(prompt=prompt, options=options)
    )
    transcript: list[str] = []
    # aclosing: an exception mid-stream tears the CLI subprocess down now,
    # not whenever the generator happens to be garbage-collected.
    async with contextlib.aclosing(stream) as messages:
        async for message in messages:
            transcript.append(str(message))
            if on_message is not None:
                # Off the event loop: git (and a target repo's commit hooks)
                # must not stall the SDK's stream readers. Still awaited, so
                # it finishes before seat_guard resumes and polls force_check.
                await asyncio.to_thread(on_message)
    return "\n".join(transcript)


async def run_per_task(
    checkout: Path, tasks_md: Path, task_ids: list[str], usage: dict | None,
    force_check: Callable[[], bool] | None, checkpointer: TaskCheckpointer,
) -> None:
    """One model session per open task, in file order (specs/011 F7-a). A
    task ticked ahead in an earlier session is skipped. After each session
    its leftover edits are committed, so the next session's seat outcome
    can't lose them. A session that leaves its task open ends the loop: a
    later task likely builds on it (research R10). Seat outcomes propagate."""
    rel = tasks_md.relative_to(checkout)
    for task in task_ids:
        if not _task_open(tasks_md, task):
            continue
        await run_implement(
            checkout, None, usage, force_check, checkpointer,
            prompt=TASK_PROMPT.format(task=task, tasks_md=rel),
        )
        checkpointer.finish(task)
        if _task_open(tasks_md, task):
            print(f"task {task} left open, stopping the per-task loop", file=sys.stderr)
            return


def verify_left_main(checkout: Path, branch: str) -> None:
    head = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=checkout)
    if head in ("main", "master"):
        raise RuntimeError(
            f"Agent left HEAD on '{head}' instead of '{branch}' — aborting "
            "before any push."
        )


def _head_sha(checkout: Path) -> str:
    return _run(["git", "rev-parse", "HEAD"], cwd=checkout)


def commits_since(checkout: Path, sha: str, ref: str = "HEAD") -> int:
    return int(_run(["git", "rev-list", "--count", f"{sha}..{ref}"], cwd=checkout))


def checkpoint_push(checkout: Path, branch: str, sha_before: str) -> None:
    """Push every commit made on `branch` before a seat outcome ends the run
    (specs/009 FR-008), so the successor seat resumes from it. Counts and
    pushes the branch ref, not HEAD — wherever the agent left HEAD. A push
    failure propagates (exit 1, never 75/77): a seat outcome must not hide
    lost work."""
    # Same invariant verify_left_main guards on the normal path: never push
    # the model's commits to the default branch.
    if branch in ("main", "master"):
        raise RuntimeError(f"Refusing to checkpoint-push to '{branch}'.")
    if commits_since(checkout, sha_before, ref=branch) == 0:
        return
    token = os.environ.get("GH_TOKEN")
    try:
        _run(["git", "push", "-u", "origin", branch], cwd=checkout)
    except subprocess.CalledProcessError as e:
        if not token:
            raise
        raise _scrubbed(e, token) from None


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


async def run(
    repo: str, branch: str, work_root: Path, feedback: str | None = None,
    usage: dict | None = None,
) -> str:
    checkout = clone_and_checkout(repo, branch, work_root)
    verify_spec_exists(checkout)
    sha_before = _head_sha(checkout)
    # All-done shortcut (specs/009 resume): a predecessor seat finished every
    # task but ran out before the PR step. Not on a Gate-feedback retry —
    # there every task is already [X] from the previous attempt, and the
    # feedback still has to be acted on.
    if feedback is None and all_tasks_done(checkout, branch):
        verify_left_main(checkout, branch)
    else:
        n = force_exhaust_after_commits()
        force_check = (lambda: commits_since(checkout, sha_before) >= n) if n is not None else None
        checkpointer = TaskCheckpointer(checkout, branch)
        # specs/011 F7-a: per task, unless there is Gate feedback (about the
        # whole change), an open task without an ID, or several task files
        # (older specs' open boxes must not get sessions of their own).
        files = _task_files(checkout, branch)
        task_ids = _open_task_ids(files[0]) if feedback is None and len(files) == 1 else None
        try:
            if task_ids:
                await run_per_task(checkout, files[0], task_ids, usage, force_check, checkpointer)
            else:
                await run_implement(checkout, feedback, usage, force_check, checkpointer)
        except (SeatExhausted, SeatInvalid):
            checkpointer()  # a tick the last message made, before pushing
            checkpoint_push(checkout, branch, sha_before)
            raise
        verify_left_main(checkout, branch)
        checkpointer.finish()
        # A successor seat (specs/011 F5) with every task done may find its
        # predecessor already committed and pushed this attempt's work — e.g.
        # a Gate-feedback fix. With tasks still open, no commit means no work:
        # fail as on the first seat (the Eval-Gate never looks at the diff).
        if _handoff_index() == 0 or has_open_tasks(checkout, branch):
            verify_new_commit(checkout, sha_before)
    title = f"Implement {branch}"
    push_and_open_pr(checkout, repo, branch, title)
    return verify_pr_exists(repo, branch)


# Seat protocol exit codes (contracts/seat-guard-and-agent-protocol.md),
# mapped by run_swe_agent_activity to typed ApplicationErrors.
EXIT_SEAT_EXHAUSTED = 75
EXIT_SEAT_INVALID = 77


def _seat_status_line(status: str, usage: dict, **extra) -> str:
    return json.dumps({
        "seat_status": status,
        **extra,
        "utilization": usage.get("utilization"),
        "rate_limit_type": usage.get("rate_limit_type"),
        # specs/011 F2: when this reading stops describing the seat.
        "utilization_resets_at": usage.get("utilization_resets_at"),
    })


async def main(argv: list[str]) -> int:
    """CLI entry: `agent.py <repo> <branch> [feedback]`. Returns the exit
    code. In seat mode the last stdout lines follow the seat protocol."""
    import tempfile

    repo, branch = argv[0], argv[1]
    feedback = argv[2] if len(argv) > 2 else None
    usage: dict = {}
    with tempfile.TemporaryDirectory() as td:
        try:
            pr_url = await run(repo, branch, Path(td), feedback, usage)
        except SeatExhausted as e:
            # e.resets_at, not usage["resets_at"]: the latter may belong to
            # an earlier allowed window (seat_guard sets None on purpose).
            print(_seat_status_line("exhausted", usage, resets_at=e.resets_at))
            return EXIT_SEAT_EXHAUSTED
        except SeatInvalid:
            print(_seat_status_line("invalid", usage))
            return EXIT_SEAT_INVALID
    if _seat_token():
        # seat_status line second-to-last, PR url stays last.
        print(_seat_status_line("ok", usage))
    print(pr_url)
    return 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main(sys.argv[1:]))
    finally:
        logger.flush()  # also on the exit-1 path, so its trace isn't lost
    sys.exit(code)
