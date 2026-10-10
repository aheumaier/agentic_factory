"""swe-agent's seat protocol (specs/009-credential-pool-handoff, US2,
contracts/seat-guard-and-agent-protocol.md): resume shortcut, checkpoint
push on a seat outcome, the seat_status line, exit codes 75/77, the force
hook, and the unchanged no-token path.

The model is the claude_agent_sdk stub from conftest (monkeypatched per
test); git is real, against a local bare repo standing in for GitHub, so
"pushed" means the commit is actually on origin's branch.
"""
import asyncio
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import claude_agent_sdk as sdk
import pytest

from conftest import swe_agent

BRANCH = "feat-x"
TOKEN = "sk-ant-oat01-test-only-not-a-real-token"
GH = "ghs_test_only_not_a_real_token"
OPEN_TASKS = "# Tasks\n\n- [X] T001 done\n- [ ] T002 open\n"
DONE_TASKS = "# Tasks\n\n- [X] T001 done\n- [X] T002 done\n"


def _git(*args, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch):
    # No host git config (signing, hooks, default branch) leaks into the test.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for var in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(var, "test")
    for var in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(var, "test@example.invalid")
    for var in ("CLAUDE_CODE_OAUTH_TOKEN", "GH_TOKEN",
                "SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS",
                # set when run from inside a git hook; would redirect cwd= git calls
                "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def origin(tmp_path, monkeypatch):
    """A bare origin with `feat-x` holding specs/001-x/tasks.md, and
    clone_and_checkout pointed at it. `.bare` is the origin path,
    `.seed(text)` replaces tasks.md on origin's branch."""
    bare = tmp_path / "origin.git"
    _git("init", "--bare", "-b", "main", str(bare), cwd=tmp_path)
    seed = tmp_path / "seed"
    _git("clone", str(bare), str(seed), cwd=tmp_path)

    def seed_tasks(text: str) -> None:
        tasks = seed / "specs" / "001-x" / "tasks.md"
        tasks.parent.mkdir(parents=True, exist_ok=True)
        tasks.write_text(text)
        _git("checkout", "-B", BRANCH, cwd=seed)
        _git("add", "-A", cwd=seed)
        _git("commit", "-m", "seed", cwd=seed)
        _git("push", "-f", "origin", BRANCH, cwd=seed)

    seed_tasks(OPEN_TASKS)

    def fake_clone(repo, branch, work_root):
        _git("clone", str(bare), str(work_root), cwd=tmp_path)
        _git("checkout", branch, cwd=work_root)
        return work_root

    monkeypatch.setattr(swe_agent, "clone_and_checkout", fake_clone)
    return SimpleNamespace(bare=bare, seed=seed_tasks)


def _origin_head(bare: Path) -> str:
    return _git("rev-parse", BRANCH, cwd=bare)


def _commit(cwd: Path, name: str) -> None:
    (cwd / name).write_text(name)
    _git("add", "-A", cwd=cwd)
    _git("commit", "-m", name, cwd=cwd)


def _fake_query(*steps, raise_at_end=None, calls=None):
    """Each step is ("commit", name) — make a commit then yield a message —
    or a message to yield as-is."""
    async def fake(*, prompt, options=None):
        if calls is not None:
            calls.append({"prompt": prompt, "options": options})
        for step in steps:
            if isinstance(step, tuple) and step[0] == "commit":
                _commit(Path(options.cwd), step[1])
                yield f"committed {step[1]}"
            else:
                yield step
        if raise_at_end is not None:
            raise raise_at_end
    return fake


def _rejected(resets_at=1791655200):
    raw = {"unifiedWindows": {"five_hour": {"utilization": 1.0}}}
    return sdk.RateLimitEvent(
        sdk.RateLimitInfo(status="rejected", resets_at=resets_at, raw=raw)
    )


def _stub_pr(monkeypatch, calls: list | None = None):
    def fake_push_and_open_pr(checkout, repo, branch, title):
        if calls is not None:
            calls.append(branch)
        return "created"
    monkeypatch.setattr(swe_agent, "push_and_open_pr", fake_push_and_open_pr)
    monkeypatch.setattr(
        swe_agent, "verify_pr_exists", lambda repo, branch: "https://github.com/o/r/pull/7",
    )


def _main(*argv) -> int:
    return asyncio.run(swe_agent.main(["o/r", BRANCH, *argv]))


def _last_line(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


# --- has_open_tasks (T022) ---------------------------------------------------

def _tasks(root: Path, slug: str, text: str) -> None:
    path = root / "specs" / slug / "tasks.md"
    path.parent.mkdir(parents=True)
    path.write_text(text)


def test_has_open_tasks_true_and_false(tmp_path):
    _tasks(tmp_path, "001-x", OPEN_TASKS)
    assert swe_agent.has_open_tasks(tmp_path)
    (tmp_path / "specs" / "001-x" / "tasks.md").write_text(DONE_TASKS)
    assert not swe_agent.has_open_tasks(tmp_path)


def test_has_open_tasks_any_of_several_spec_dirs(tmp_path):
    _tasks(tmp_path, "001-a", DONE_TASKS)
    _tasks(tmp_path, "002-b", "- [x] lower-case done\n  - [ ] nested open\n")
    assert swe_agent.has_open_tasks(tmp_path)


def test_feature_tasks_md_wins_over_older_specs(tmp_path):
    # An older spec's leftover open box must not block the all-done shortcut.
    _tasks(tmp_path, "001-old", OPEN_TASKS)
    _tasks(tmp_path, BRANCH, DONE_TASKS)
    assert not swe_agent.has_open_tasks(tmp_path, BRANCH)
    assert swe_agent.all_tasks_done(tmp_path, BRANCH)
    assert swe_agent.has_open_tasks(tmp_path, "no-such-spec-dir")  # glob fallback


def test_tasks_md_without_checklist_is_not_done(tmp_path):
    _tasks(tmp_path, "001-x", "# Tasks\n\nImplement the thing.\n")
    assert not swe_agent.all_tasks_done(tmp_path)


def test_has_open_tasks_ignores_prose_mention(tmp_path):
    _tasks(tmp_path, "001-x", DONE_TASKS + "- [X] T3 true if a `- [ ]` line exists\n")
    assert not swe_agent.has_open_tasks(tmp_path)


# --- all-done shortcut (T022) ------------------------------------------------

def test_all_done_skips_implement_and_opens_pr(origin, monkeypatch, capsys):
    origin.seed(DONE_TASKS)
    pr_calls: list = []
    _stub_pr(monkeypatch, pr_calls)

    async def must_not_run(*args, **kwargs):
        raise AssertionError("run_implement called with no open tasks")
    monkeypatch.setattr(swe_agent, "run_implement", must_not_run)

    assert _main() == 0
    assert pr_calls == [BRANCH]
    assert capsys.readouterr().out.strip().splitlines()[-1] == "https://github.com/o/r/pull/7"


def test_gate_feedback_retry_still_implements(origin, monkeypatch):
    # Every task is [X] after attempt 1, but Gate feedback must still be acted on.
    origin.seed(DONE_TASKS)
    _stub_pr(monkeypatch)
    calls: list = []
    monkeypatch.setattr(swe_agent, "query", _fake_query(("commit", "fix"), calls=calls))

    assert _main("coverage too low") == 0
    assert "coverage too low" in calls[0]["prompt"]


# --- seat outcomes in __main__ (T023) ---------------------------------------

def test_exhausted_pushes_commits_prints_status_last_exits_75(origin, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    before = _origin_head(origin.bare)
    monkeypatch.setattr(swe_agent, "query", _fake_query(("commit", "t002"), _rejected()))

    assert _main() == swe_agent.EXIT_SEAT_EXHAUSTED == 75
    assert _origin_head(origin.bare) != before  # the commit reached origin
    status = _last_line(capsys)
    assert status["seat_status"] == "exhausted"
    assert status["resets_at"] == 1791655200
    assert status["utilization"] == 1.0
    assert status["rate_limit_type"] == "five_hour"


def test_exhausted_without_new_commits_skips_push(origin, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    # An unreachable origin proves no push is attempted.
    monkeypatch.setattr(swe_agent, "query", _fake_query(_rejected()))
    real_clone = swe_agent.clone_and_checkout

    def clone_then_break_origin(repo, branch, work_root):
        checkout = real_clone(repo, branch, work_root)
        _git("remote", "set-url", "origin", "/nonexistent/origin.git", cwd=checkout)
        return checkout
    monkeypatch.setattr(swe_agent, "clone_and_checkout", clone_then_break_origin)

    assert _main() == 75
    assert _last_line(capsys)["seat_status"] == "exhausted"


def test_invalid_pushes_and_exits_77(origin, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    before = _origin_head(origin.bare)
    error = sdk.ResultError("auth", data={"api_error_status": 401, "result": "bad"})
    monkeypatch.setattr(
        swe_agent, "query", _fake_query(("commit", "t002"), raise_at_end=error),
    )

    assert _main() == swe_agent.EXIT_SEAT_INVALID == 77
    assert _origin_head(origin.bare) != before
    status = _last_line(capsys)
    assert status["seat_status"] == "invalid"
    assert "resets_at" not in status


def test_push_failure_exits_1_without_status_line_and_scrubs_token(
    origin, monkeypatch, capsys,
):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    monkeypatch.setenv("GH_TOKEN", GH)
    monkeypatch.setattr(swe_agent, "query", _fake_query(("commit", "t002"), _rejected()))
    real_clone = swe_agent.clone_and_checkout

    def clone_then_break_origin(repo, branch, work_root):
        checkout = real_clone(repo, branch, work_root)
        # Shaped like the real clone URL: the token sits in the remote.
        _git("remote", "set-url", "origin", f"/nonexistent/{GH}/r.git", cwd=checkout)
        return checkout
    monkeypatch.setattr(swe_agent, "clone_and_checkout", clone_then_break_origin)

    # Uncaught -> the interpreter exits 1 (never 75/77), traceback on stderr.
    with pytest.raises(subprocess.CalledProcessError) as exc:
        _main()
    assert GH not in repr(exc.value) + str(exc.value.stderr)
    assert "***" in exc.value.stderr  # the token was there, and was redacted
    assert "seat_status" not in capsys.readouterr().out


# --- force hook (T022) -------------------------------------------------------

def test_force_hook_exhausts_after_n_commits(origin, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    monkeypatch.setenv("SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS", "2")
    before = _origin_head(origin.bare)
    monkeypatch.setattr(swe_agent, "query", _fake_query(
        ("commit", "one"), ("commit", "two"), ("commit", "three"),
    ))

    assert _main() == 75
    assert _git("rev-list", "--count", f"{before}..{BRANCH}", cwd=origin.bare) == "2"
    assert _last_line(capsys)["resets_at"] is None


# --- seat-mode success and the no-token path --------------------------------

def test_seat_success_prints_ok_line_before_pr_url(origin, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    _stub_pr(monkeypatch)
    calls: list = []
    monkeypatch.setattr(swe_agent, "query", _fake_query(("commit", "t002"), calls=calls))

    assert _main() == 0
    *_, status_line, url = capsys.readouterr().out.strip().splitlines()
    assert json.loads(status_line)["seat_status"] == "ok"
    assert url == "https://github.com/o/r/pull/7"
    assert calls[0]["options"].env["CLAUDE_CODE_OAUTH_TOKEN"] == TOKEN
    assert calls[0]["options"].env["ANTHROPIC_API_KEY"] == ""


def test_no_token_uses_plain_query_without_seat_env(origin, monkeypatch, capsys):
    _stub_pr(monkeypatch)
    calls: list = []
    monkeypatch.setattr(swe_agent, "query", _fake_query(("commit", "t002"), calls=calls))

    def must_not_guard(*args, **kwargs):
        raise AssertionError("guarded_query used without a seat token")
    monkeypatch.setattr(swe_agent, "guarded_query", must_not_guard)

    assert _main() == 0
    assert calls[0]["options"].env == {}
    out = capsys.readouterr().out
    assert "seat_status" not in out
    assert out.strip().splitlines()[-1] == "https://github.com/o/r/pull/7"


def test_prompt_carries_resume_and_checkpoint_rules():
    prompt = swe_agent.IMPLEMENT_PROMPT
    assert prompt.startswith("/speckit-implement")
    assert "`[X]`" in prompt and "skip them" in prompt
    assert "git add -A && git commit" in prompt
    assert "do not run `git push`" in " ".join(prompt.split())


def test_checkpoint_push_follows_branch_not_head(origin, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    before = _origin_head(origin.bare)

    async def commit_then_detach(*, prompt, options=None):
        _commit(Path(options.cwd), "t002")
        _git("checkout", "--detach", "HEAD~1", cwd=Path(options.cwd))
        yield _rejected()
    monkeypatch.setattr(swe_agent, "query", commit_then_detach)

    assert _main() == 75
    assert _git("rev-list", "--count", f"{before}..{BRANCH}", cwd=origin.bare) == "1"


def test_checkpoint_push_never_targets_main(tmp_path):
    with pytest.raises(RuntimeError, match="Refusing to checkpoint-push to 'main'"):
        swe_agent.checkpoint_push(tmp_path, "main", "abc123")
