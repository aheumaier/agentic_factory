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
                "SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS", "SEAT_HANDOFF_INDEX",
                # set when run from inside a git hook; would redirect cwd= git calls
                "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def origin(tmp_path, monkeypatch):
    """A bare origin with `feat-x` holding specs/001-x/tasks.md, and
    clone_and_checkout pointed at it. `.bare` is the origin path,
    `.seed(text, extra)` replaces tasks.md (plus any `extra` repo-relative
    files) on origin's branch."""
    bare = tmp_path / "origin.git"
    _git("init", "--bare", "-b", "main", str(bare), cwd=tmp_path)
    seed = tmp_path / "seed"
    _git("clone", str(bare), str(seed), cwd=tmp_path)

    def seed_tasks(text: str, extra: dict[str, str] | None = None) -> None:
        tasks = seed / "specs" / "001-x" / "tasks.md"
        tasks.parent.mkdir(parents=True, exist_ok=True)
        tasks.write_text(text)
        for rel, content in (extra or {}).items():
            (seed / rel).parent.mkdir(parents=True, exist_ok=True)
            (seed / rel).write_text(content)
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


# --- specs/011 F1: deterministic per-task checkpoints --------------------------

THREE_TASKS = "# Tasks\n\n- [ ] T001 one\n- [ ] T002 two\n- [ ] T003 three\n"


def _edit(cwd: Path, name: str) -> None:
    (cwd / name).write_text(name)


def _tick(cwd: Path, *ids: str) -> None:
    tasks = cwd / "specs" / "001-x" / "tasks.md"
    text = tasks.read_text()
    for task_id in ids:
        text = text.replace(f"- [ ] {task_id} ", f"- [X] {task_id} ")
    tasks.write_text(text)


def _scripted(*steps):
    """Each step is a callable(cwd) run before yielding one message, or a
    message (e.g. a RateLimitEvent) yielded as-is."""
    async def fake(*, prompt, options=None):
        cwd = Path(options.cwd)
        for step in steps:
            if callable(step):
                step(cwd)
                yield "tool result"
            else:
                yield step
    return fake


def _capture_log(monkeypatch) -> list:
    """Stubs the PR step; records the subjects of the commits made in the
    checkout (oldest first) at the moment it would push."""
    subjects: list = []

    def fake_push_and_open_pr(checkout, repo, branch, title):
        log = _git("log", "--reverse", "--format=%s", f"origin/{branch}..HEAD", cwd=checkout)
        subjects.extend(log.splitlines())
        return "created"
    monkeypatch.setattr(swe_agent, "push_and_open_pr", fake_push_and_open_pr)
    monkeypatch.setattr(
        swe_agent, "verify_pr_exists", lambda repo, branch: "https://github.com/o/r/pull/7",
    )
    return subjects


def _origin_subjects(bare: Path, before: str) -> list[str]:
    return _git("log", "--reverse", "--format=%s", f"{before}..{BRANCH}", cwd=bare).splitlines()


def test_harness_checkpoints_each_tick_when_the_model_never_commits(origin, monkeypatch):
    origin.seed(THREE_TASKS)
    subjects = _capture_log(monkeypatch)
    monkeypatch.setattr(swe_agent, "query", _scripted(
        lambda cwd: _edit(cwd, "a.py"), lambda cwd: _tick(cwd, "T001"),
        lambda cwd: _edit(cwd, "b.py"), lambda cwd: _tick(cwd, "T002"),
        lambda cwd: _edit(cwd, "fixup.py"),  # after the last tick: end-of-run commit
    ))

    assert _main() == 0
    assert subjects == ["checkpoint: T001", "checkpoint: T002", "checkpoint: end of run"]


def test_model_commit_is_recorded_not_duplicated(origin, monkeypatch):
    origin.seed(THREE_TASKS)
    subjects = _capture_log(monkeypatch)

    def model_finishes_t001(cwd):
        _edit(cwd, "a.py")
        _tick(cwd, "T001")
        _git("add", "-A", cwd=cwd)
        _git("commit", "-m", "model: T001", cwd=cwd)

    monkeypatch.setattr(swe_agent, "query", _scripted(model_finishes_t001, lambda cwd: None))

    assert _main() == 0
    assert subjects == ["model: T001"]


def test_batched_ticks_make_one_checkpoint_naming_both(origin, monkeypatch):
    origin.seed(THREE_TASKS)
    subjects = _capture_log(monkeypatch)
    monkeypatch.setattr(swe_agent, "query", _scripted(
        lambda cwd: (_edit(cwd, "a.py"), _tick(cwd, "T001", "T002")),
    ))

    assert _main() == 0
    assert subjects == ["checkpoint: T001 T002"]


def test_failed_checkpoint_is_retried_on_the_next_message(origin, monkeypatch, capsys):
    origin.seed(THREE_TASKS)
    subjects = _capture_log(monkeypatch)

    def tick_while_model_holds_the_index(cwd):
        _edit(cwd, "a.py")
        _tick(cwd, "T001")
        (cwd / ".git" / "index.lock").write_text("")

    monkeypatch.setattr(swe_agent, "query", _scripted(
        tick_while_model_holds_the_index,
        lambda cwd: (cwd / ".git" / "index.lock").unlink(),
    ))

    assert _main() == 0
    assert subjects == ["checkpoint: T001"]
    assert "checkpoint commit failed, will retry" in capsys.readouterr().err


def test_predecessor_ticks_are_not_checkpointed_again(origin, monkeypatch):
    origin.seed(THREE_TASKS.replace("- [ ] T001", "- [X] T001"))
    subjects = _capture_log(monkeypatch)
    monkeypatch.setattr(swe_agent, "query", _scripted(
        lambda cwd: (_edit(cwd, "b.py"), _tick(cwd, "T002")),
    ))

    assert _main() == 0
    assert subjects == ["checkpoint: T002"]


def test_tick_without_task_id_gets_a_generic_checkpoint(origin, monkeypatch):
    origin.seed("# Tasks\n\n- [ ] write the docs\n- [ ] ship it\n")
    subjects = _capture_log(monkeypatch)

    def tick_docs(cwd):
        tasks = cwd / "specs" / "001-x" / "tasks.md"
        tasks.write_text(tasks.read_text().replace("- [ ] write", "- [X] write"))
        _edit(cwd, "docs.md")

    monkeypatch.setattr(swe_agent, "query", _scripted(tick_docs))

    assert _main() == 0
    assert subjects == ["checkpoint: tasks"]


def test_forced_exhaustion_fires_right_after_the_first_checkpoint(origin, monkeypatch, capsys):
    """SC-002 / FR-005: exhaust-after-1-commit counts the harness checkpoint
    of the same message, so T002 never starts and origin holds T001."""
    origin.seed(THREE_TASKS)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    monkeypatch.setenv("SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS", "1")
    before = _origin_head(origin.bare)
    started: list = []
    monkeypatch.setattr(swe_agent, "query", _scripted(
        lambda cwd: (_edit(cwd, "a.py"), _tick(cwd, "T001")),
        lambda cwd: (started.append("T002"), _edit(cwd, "b.py"), _tick(cwd, "T002")),
    ))

    assert _main() == 75
    assert _origin_subjects(origin.bare, before) == ["checkpoint: T001"]
    assert started == []
    assert _last_line(capsys)["seat_status"] == "exhausted"


def test_seat_outcome_checkpoints_a_tick_the_consumer_never_saw(origin, monkeypatch):
    """The tick lands, then the seat is rejected before another message:
    the except branch's checkpoint still saves T001 before the push."""
    origin.seed(THREE_TASKS)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    before = _origin_head(origin.bare)

    async def tick_then_rejected(*, prompt, options=None):
        cwd = Path(options.cwd)
        _edit(cwd, "a.py")
        _tick(cwd, "T001")
        yield _rejected()
    monkeypatch.setattr(swe_agent, "query", tick_then_rejected)

    assert _main() == 75
    assert _origin_subjects(origin.bare, before) == ["checkpoint: T001"]


def test_seat_outcome_leaves_unticked_edits_uncommitted(origin, monkeypatch):
    origin.seed(THREE_TASKS)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    before = _origin_head(origin.bare)
    monkeypatch.setattr(swe_agent, "query", _scripted(
        lambda cwd: _edit(cwd, "half-done.py"), _rejected(),
    ))

    assert _main() == 75
    assert _origin_subjects(origin.bare, before) == []


def test_checkpoint_uses_fallback_identity_when_none_is_configured(origin, monkeypatch):
    origin.seed(THREE_TASKS)
    for var in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.delenv(var, raising=False)
    authors: list = []

    def fake_push_and_open_pr(checkout, repo, branch, title):
        authors.append(_git("log", "-1", "--format=%an <%ae>", cwd=checkout))
        return "created"
    monkeypatch.setattr(swe_agent, "push_and_open_pr", fake_push_and_open_pr)
    monkeypatch.setattr(swe_agent, "verify_pr_exists", lambda repo, branch: "u")
    monkeypatch.setattr(swe_agent, "query", _scripted(
        lambda cwd: (_edit(cwd, "a.py"), _tick(cwd, "T001")),
    ))

    assert _main() == 0
    assert authors == ["swe-agent <swe-agent@users.noreply.github.com>"]


def test_prompt_asks_for_one_tick_per_task():
    prompt = " ".join(swe_agent.IMPLEMENT_PROMPT.split())
    assert "one task at a time" in prompt
    assert "checkpoint commit is saved for you" in prompt


# --- specs/011 F5: a successor seat skips the "no new commit" check ------------

def test_successor_feedback_retry_without_new_commit_reaches_pr(origin, monkeypatch):
    origin.seed(DONE_TASKS)
    monkeypatch.setenv("SEAT_HANDOFF_INDEX", "1")
    pr_calls: list = []
    _stub_pr(monkeypatch, pr_calls)
    monkeypatch.setattr(swe_agent, "query", _scripted(lambda cwd: None))

    assert _main("coverage too low") == 0
    assert pr_calls == [BRANCH]


def test_first_seat_feedback_retry_without_new_commit_still_fails(origin, monkeypatch):
    origin.seed(DONE_TASKS)
    monkeypatch.setenv("SEAT_HANDOFF_INDEX", "0")
    _stub_pr(monkeypatch)
    monkeypatch.setattr(swe_agent, "query", _scripted(lambda cwd: None))

    with pytest.raises(RuntimeError, match="made no new commit"):
        _main("coverage too low")


# --- specs/011 F2: the reading's own reset time travels in the status line -----

def test_ok_line_carries_the_readings_window_reset(origin, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    _stub_pr(monkeypatch)
    raw = {"unifiedWindows": {
        "five_hour": {"utilization": 0.2, "resetsAt": 1791655200},
        "seven_day": {"utilization": 0.4, "resetsAt": 1791831600},
    }}
    event = sdk.RateLimitEvent(sdk.RateLimitInfo(status="allowed", resets_at=1791655200, raw=raw))
    monkeypatch.setattr(swe_agent, "query", _fake_query(event, ("commit", "t002")))

    assert _main() == 0
    status = json.loads(capsys.readouterr().out.strip().splitlines()[-2])
    assert status["utilization"] == 0.4
    assert status["utilization_resets_at"] == 1791831600


def test_successor_with_open_tasks_and_no_commit_still_fails(origin, monkeypatch):
    """F5 is scoped to "nothing left to do": a successor that leaves tasks
    open and commits nothing did no work, and the Eval-Gate would not notice.
    (The fixture's default tasks.md has T002 open.)"""
    monkeypatch.setenv("SEAT_HANDOFF_INDEX", "1")
    _stub_pr(monkeypatch)
    monkeypatch.setattr(swe_agent, "query", _scripted(lambda cwd: None))

    with pytest.raises(RuntimeError, match="made no new commit"):
        _main()


def test_older_specs_ticked_ids_do_not_hide_this_features_ticks(origin, monkeypatch):
    """Fallback mode (no specs/<branch>/tasks.md): every Spec Kit tasks.md
    starts at T001, so done-task keys are per file."""
    origin.seed(THREE_TASKS, {"specs/000-old/tasks.md": "# Tasks\n\n- [X] T001 old\n"})
    subjects = _capture_log(monkeypatch)
    monkeypatch.setattr(swe_agent, "query", _scripted(
        lambda cwd: (_edit(cwd, "a.py"), _tick(cwd, "T001")),
        lambda cwd: _edit(cwd, "b.py"),
    ))

    assert _main() == 0
    assert subjects == ["checkpoint: T001", "checkpoint: end of run"]
