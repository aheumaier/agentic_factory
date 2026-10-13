"""Tests for the Claude Code hook scripts in .claude/hooks/ (feature 010).

Each test drives the real bash scripts through subprocess with a synthetic
JSON payload on stdin, inside a throwaway git repo with the hooks copied in.
The scripts take their repo root from their own path (012 R2), so the copies
judge the tmp repo; CLAUDE_PROJECT_DIR is still set, as Claude Code sets it.
`uv` is a stub placed first on PATH: it logs its argv and returns the exit
code/output a test sets per tool, so "suite red"/"suite green" need no
network and no real suite. `timeout` is a stub too. `git` and `jq` are real.
The hook code has no test-only switches.

Layout under tmp_path: repo/ (the git repo), bin/uv and bin/timeout (the
stubs), uv-calls.log, timeout-calls.log, timeout.rc, and <tool>.rc /
<tool>.out for tool in ruff, pytest.
"""
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"
DENY_FORMAT = re.compile(r"^\[AF-[A-Z]+\] .+\. To proceed: .+$")

# Uses only bash builtins, so it still works on the trimmed PATH of the
# missing-tool tests. "run", --locked, --frozen and --directory <d> are
# skipped; the next word picks the tool.
_UV_STUB = """#!/bin/bash
T='{tmp}'
(IFS=$'\\t'; printf '%s\\n' "$*") >> "$T/uv-calls.log"
while [ $# -gt 0 ]; do
  case "$1" in
    run|--locked|--frozen) shift ;;
    --directory) shift 2 ;;
    *) break ;;
  esac
done
case "${{1:-}}" in
  ruff|pytest) tool="$1" ;;
  *) exit 0 ;;
esac
[ -f "$T/$tool.out" ] && printf '%s' "$(< "$T/$tool.out")"
rc=0
[ -f "$T/$tool.rc" ] && rc="$(< "$T/$tool.rc")"
exit "$rc"
"""

# Stands in for GNU timeout/gtimeout (012 R3): logs its argv, then exits with
# timeout.rc when a test set one (124 = timed out, 137 = killed), otherwise
# runs the command and returns its exit code. Bash builtins only, as above.
_TIMEOUT_STUB = """#!/bin/bash
T='{tmp}'
(IFS=$'\\t'; printf '%s\\n' "$*") >> "$T/timeout-calls.log"
[ -f "$T/timeout.rc" ] && exit "$(< "$T/timeout.rc")"
case "${{1:-}}" in --kill-after=*) shift ;; esac
shift
"$@"
"""


def _clean_env() -> dict[str, str]:
    # Keep the operator's shell out of the fixture: a GIT_DIR from a git
    # hook would retarget every git call, and a launch-time
    # AF_SPEC_EXCEPTION or AF_GATE_LIMIT would change the hooks' verdicts.
    return {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("GIT_")
        and k not in ("AF_SPEC_EXCEPTION", "AF_GATE_LIMIT", "CLAUDE_PROJECT_DIR")
    }


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True, env=_clean_env(),
    ).stdout


@pytest.fixture
def harness_repo(tmp_path: Path) -> Path:
    return _make_harness_repo(tmp_path)


def _make_harness_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    git(repo, "init", "-q", "-b", "010-x")
    git(repo, "config", "user.name", "harness-test")
    git(repo, "config", "user.email", "harness-test@example.invalid")
    git(repo, "config", "commit.gpgsign", "false")
    (repo / "pkg" / "clean.py").write_text("VALUE = 1\n")
    (repo / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0"\n')
    (repo / "uv.lock").write_text("version = 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")

    hooks = repo / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    for script in HOOKS_DIR.glob("*.sh"):
        shutil.copy2(script, hooks / script.name)

    (tmp_path / "bin").mkdir()
    for name, body in (("uv", _UV_STUB), ("timeout", _TIMEOUT_STUB)):
        stub = tmp_path / "bin" / name
        stub.write_text(body.format(tmp=tmp_path))
        stub.chmod(0o755)
    return repo


def run_hook(
    repo: Path,
    script: str,
    args: list[str],
    payload: dict | str,  # a str is sent as raw stdin
    env_extra: dict[str, str] | None = None,
    path: str | None = None,
) -> subprocess.CompletedProcess:
    env = _clean_env()
    env["PATH"] = path if path is not None else f"{repo.parent / 'bin'}{os.pathsep}{env['PATH']}"
    env["CLAUDE_PROJECT_DIR"] = str(repo)
    env.update(env_extra or {})
    return subprocess.run(
        ["/bin/bash", str(repo / ".claude" / "hooks" / script), *args],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True, text=True, env=env, timeout=60,
    )


def gate_limit(repo: Path) -> list[str]:
    """The <n> of each logged `timeout --kill-after=5 <n>s <cmd…>` call."""
    log = repo.parent / "timeout-calls.log"
    if not log.exists():
        return []
    return [line.split("\t")[1].removesuffix("s") for line in log.read_text().splitlines()]


def uv_calls(repo: Path) -> list[list[str]]:
    log = repo.parent / "uv-calls.log"
    if not log.exists():
        return []
    return [line.split("\t") for line in log.read_text().splitlines()]


def set_stub(repo: Path, tool: str, rc: int, out: str = "") -> None:
    (repo.parent / f"{tool}.rc").write_text(str(rc))
    (repo.parent / f"{tool}.out").write_text(out)


def state_dir(repo: Path) -> Path:
    d = Path(git(repo, "rev-parse", "--git-path", "claude-harness").strip())
    return d if d.is_absolute() else repo / d


def _tool(call: list[str]) -> str:
    """The tool a logged uv argv dispatched to (mirrors the stub's skipping)."""
    i = 0
    while i < len(call):
        if call[i] in ("run", "--locked", "--frozen"):
            i += 1
        elif call[i] == "--directory":
            i += 2
        else:
            return call[i]
    return ""


def calls_for(repo: Path, tool: str) -> list[list[str]]:
    return [c for c in uv_calls(repo) if _tool(c) == tool]


def turn_start(repo: Path, session: str = "s1") -> subprocess.CompletedProcess:
    return run_hook(repo, "py-check.sh", ["turn-start"], {"session_id": session})


def stop(repo: Path, session: str = "s1", active: bool = False) -> subprocess.CompletedProcess:
    return run_hook(
        repo, "py-check.sh", ["stop"], {"session_id": session, "stop_hook_active": active}
    )


def snapshot(repo: Path, session: str = "s1") -> Path:
    return state_dir(repo) / f"turn-{session}.tsv"


# ---------------------------------------------------------------------------
# US1: a turn is judged only on what it changed (T012)
# ---------------------------------------------------------------------------


def test_preexisting_dirty_file_is_not_judged(harness_repo):
    repo = harness_repo
    (repo / "pkg" / "bad.py").write_text("x = undefined_name\n")
    turn_start(repo)
    (repo / "pkg" / "clean.py").write_text("VALUE = 2\n")

    result = stop(repo)

    assert result.returncode == 0, result.stderr
    [ruff] = calls_for(repo, "ruff")
    assert "pkg/clean.py" in ruff
    assert "pkg/bad.py" not in ruff


def test_shell_made_file_is_judged_and_named(harness_repo):
    repo = harness_repo
    turn_start(repo)
    (repo / "pkg" / "new.py").write_text("x = undefined_name\n")  # no edit hook ran
    set_stub(repo, "ruff", 1, "pkg/new.py:1:5: F821 undefined name\n")

    result = stop(repo)

    assert result.returncode == 2
    [ruff] = calls_for(repo, "ruff")
    assert "pkg/new.py" in ruff
    assert "pkg/new.py" in result.stderr
    assert "F821" in result.stderr


@pytest.mark.parametrize("name", ["pyproject.toml", "uv.lock"])
def test_config_only_change_runs_suites_without_file_lint(harness_repo, name):
    repo = harness_repo
    turn_start(repo)
    (repo / name).write_text((repo / name).read_text() + "# changed\n")

    result = stop(repo)

    assert result.returncode == 0, result.stderr
    assert calls_for(repo, "ruff") == []
    dirs = sorted(c[c.index("--directory") + 1] for c in calls_for(repo, "pytest"))
    assert dirs == [str(repo), str(repo / "orchestration")]


def test_no_change_runs_nothing_and_clears_snapshot(harness_repo):
    repo = harness_repo
    turn_start(repo)
    assert snapshot(repo).exists()

    result = stop(repo)

    assert result.returncode == 0, result.stderr
    assert uv_calls(repo) == []
    assert not snapshot(repo).exists()


def test_deleted_file_runs_suites_but_is_not_linted(harness_repo):
    repo = harness_repo
    turn_start(repo)
    (repo / "pkg" / "clean.py").unlink()

    result = stop(repo)

    assert result.returncode == 0, result.stderr
    assert len(calls_for(repo, "pytest")) == 2
    assert calls_for(repo, "ruff") == []


def test_mid_turn_prompt_keeps_the_original_snapshot(harness_repo):
    repo = harness_repo
    turn_start(repo)
    before = snapshot(repo).read_bytes()
    (repo / "pkg" / "clean.py").write_text("VALUE = 2\n")

    turn_start(repo)  # a second prompt in the same turn (FR-001)

    assert snapshot(repo).read_bytes() == before
    stop(repo)
    [ruff] = calls_for(repo, "ruff")
    assert "pkg/clean.py" in ruff


@pytest.mark.parametrize("corrupt", [False, True])
def test_missing_or_corrupt_snapshot_falls_back_to_head(harness_repo, corrupt):
    repo = harness_repo
    # Unchanged since HEAD: a garbage snapshot taken as usable would put it in
    # the changed set; the HEAD fallback doesn't.
    (repo / "pkg" / "other.py").write_text("OTHER = 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "other")
    if corrupt:
        turn_start(repo)
        snapshot(repo).write_text("garbage line\n")
    (repo / "pkg" / "clean.py").write_text("VALUE = 2\n")

    result = stop(repo)

    assert result.returncode == 0, result.stderr
    [ruff] = calls_for(repo, "ruff")
    assert "pkg/clean.py" in ruff
    assert "pkg/other.py" not in ruff
    assert len(calls_for(repo, "pytest")) == 2


def test_files_outside_the_repo_are_never_linted(harness_repo, tmp_path_factory):
    repo = harness_repo
    outside = tmp_path_factory.mktemp("outside") / "stray.py"
    turn_start(repo)
    outside.write_text("x = undefined_name\n")

    edit = run_hook(repo, "py-check.sh", ["edit"], {"tool_input": {"file_path": str(outside)}})
    result = stop(repo)

    assert edit.returncode == 0
    assert result.returncode == 0
    assert all(str(outside) not in arg for c in uv_calls(repo) for arg in c)


# ---------------------------------------------------------------------------
# US1: gate behaviour (T013)
# ---------------------------------------------------------------------------


def _suite_block(stderr: str, label: str) -> list[str]:
    lines = stderr.splitlines()
    start = lines.index(f"=== {label} FAILED ===") + 1
    block = []
    for line in lines[start:]:
        if line.startswith("=== "):
            break
        block.append(line)
    while block and not block[-1]:
        block.pop()
    return block


def test_red_blocks_once_then_lets_go_with_a_notice(harness_repo):
    repo = harness_repo
    turn_start(repo)
    (repo / "pkg" / "clean.py").write_text("VALUE = 2\n")
    set_stub(repo, "pytest", 1, "FAILED tests/test_x.py::test_a - boom\n")

    first = stop(repo, active=False)
    assert first.returncode == 2
    assert snapshot(repo).exists()

    second = stop(repo, active=True)
    assert second.returncode == 0
    assert "still RED" in json.loads(second.stdout)["systemMessage"]
    assert not snapshot(repo).exists()


def test_every_failing_test_id_survives_trimming(harness_repo):
    repo = harness_repo
    turn_start(repo)
    (repo / "pkg" / "clean.py").write_text("VALUE = 2\n")
    ids = [f"tests/test_x.py::test_{n}" for n in (1, 2, 3)]
    traceback = "".join(f"    frame {n}\n" for n in range(300))
    set_stub(repo, "pytest", 1, traceback + "".join(f"FAILED {i} - boom\n" for i in ids))

    result = stop(repo)

    assert result.returncode == 2
    block = _suite_block(result.stderr, "pytest tests/")
    assert len(block) <= 60
    for test_id in ids:
        assert any(test_id in line for line in block)


def test_failing_test_ids_before_a_long_tail_survive_trimming(harness_repo):
    # A plain `tail -n 60` would cut these; only FAILED-first keeps them.
    repo = harness_repo
    turn_start(repo)
    (repo / "pkg" / "clean.py").write_text("VALUE = 2\n")
    ids = [f"tests/test_x.py::test_{n}" for n in (1, 2, 3)]
    warnings = "".join(f"  warning {n}\n" for n in range(300))
    set_stub(repo, "pytest", 1, "".join(f"FAILED {i} - boom\n" for i in ids) + warnings)

    result = stop(repo)

    assert result.returncode == 2
    block = _suite_block(result.stderr, "pytest tests/")
    assert len(block) <= 60
    assert block[:3] == [f"FAILED {i} - boom" for i in ids]


def test_edit_lints_only_the_edited_python_file(harness_repo, tmp_path_factory):
    repo = harness_repo
    target = repo / "pkg" / "clean.py"

    result = run_hook(repo, "py-check.sh", ["edit"], {"tool_input": {"file_path": str(target)}})

    assert result.returncode == 0, result.stderr
    [call] = uv_calls(repo)
    assert _tool(call) == "ruff"
    assert "pkg/clean.py" in call

    outside = tmp_path_factory.mktemp("outside") / "stray.py"
    outside.write_text("x = 1\n")
    for path in (repo / "README.md", outside):
        run_hook(repo, "py-check.sh", ["edit"], {"tool_input": {"file_path": str(path)}})
    assert len(uv_calls(repo)) == 1


def test_edit_reports_ruff_findings(harness_repo):
    repo = harness_repo
    set_stub(repo, "ruff", 1, "pkg/clean.py:1:1: F401 unused\n")

    result = run_hook(
        repo, "py-check.sh", ["edit"],
        {"tool_input": {"file_path": str(repo / "pkg" / "clean.py")}},
    )

    assert result.returncode == 2
    assert "ruff failed after editing pkg/clean.py" in result.stderr
    assert calls_for(repo, "pytest") == []


def test_uv_never_runs_unlocked_and_lockfile_is_untouched(harness_repo):
    repo = harness_repo
    lock_before = (repo / "uv.lock").read_bytes()
    run_hook(
        repo, "py-check.sh", ["edit"],
        {"tool_input": {"file_path": str(repo / "pkg" / "clean.py")}},
    )
    turn_start(repo)
    (repo / "pkg" / "clean.py").write_text("VALUE = 2\n")
    stop(repo)

    edit_call, *gate_calls = uv_calls(repo)
    assert "--frozen" in edit_call and "--locked" not in edit_call
    assert len(gate_calls) == 3  # ruff + two suites
    assert all("--locked" in c for c in gate_calls)
    assert (repo / "uv.lock").read_bytes() == lock_before


_PATH_TOOLS = (
    "git", "jq", "dirname", "cat", "mktemp", "mv", "rm", "mkdir", "find", "ls", "tr",
    "paste", "sort", "comm", "sed", "cut", "grep", "awk", "tail", "head", "touch",
)


def _path_without(tmp_path: Path, repo: Path, missing: str) -> str:
    """A PATH with the stub uv and the real tools the hooks use, minus one."""
    bin_dir = tmp_path / f"no{missing}-bin"
    bin_dir.mkdir()
    if missing != "uv":
        (bin_dir / "uv").symlink_to(repo.parent / "bin" / "uv")
    for tool in _PATH_TOOLS:
        if tool == missing:
            continue
        found = shutil.which(tool)
        assert found, tool
        (bin_dir / tool).symlink_to(found)
    return str(bin_dir)


def test_missing_jq_fails_closed_except_turn_start(harness_repo, tmp_path_factory):
    repo = harness_repo
    path = _path_without(tmp_path_factory.mktemp("path"), repo, "jq")
    edit_payload = {"tool_input": {"file_path": str(repo / "pkg" / "clean.py")}}

    for args, payload in ((["edit"], edit_payload), (["stop"], {"session_id": "s1"})):
        result = run_hook(repo, "py-check.sh", args, payload, path=path)
        assert result.returncode == 2, args
        assert "jq is required" in result.stderr

    start = run_hook(repo, "py-check.sh", ["turn-start"], {"session_id": "s1"}, path=path)
    assert start.returncode == 0
    assert start.stdout == ""


def test_missing_uv_fails_closed_only_where_uv_runs(harness_repo, tmp_path_factory):
    """Contract: `uv` is checked only on paths that run it."""
    repo = harness_repo
    path = _path_without(tmp_path_factory.mktemp("path"), repo, "uv")

    def edit(name: str) -> subprocess.CompletedProcess:
        payload = {"tool_input": {"file_path": str(repo / name)}}
        return run_hook(repo, "py-check.sh", ["edit"], payload, path=path)

    def stop_no_uv() -> subprocess.CompletedProcess:
        return run_hook(repo, "py-check.sh", ["stop"], {"session_id": "s1"}, path=path)

    assert edit("notes.md").returncode == 0
    py = edit("pkg/clean.py")
    assert py.returncode == 2
    assert "uv is required" in py.stderr

    turn_start(repo)
    assert stop_no_uv().returncode == 0  # nothing changed this turn

    turn_start(repo)
    (repo / "pkg" / "new.py").write_text("x = 1\n")
    changed = stop_no_uv()
    assert changed.returncode == 2
    assert "uv is required" in changed.stderr


def test_session_id_is_sanitised_into_the_state_dir(harness_repo):
    repo = harness_repo

    result = turn_start(repo, session="../x y")

    assert result.returncode == 0
    sd = state_dir(repo)
    assert [p.name for p in sd.iterdir()] == ["turn-xy.tsv"]
    assert list(sd.parent.glob("turn-*")) == []


# ---------------------------------------------------------------------------
# US1: snapshot adoption across /clear and session_id changes (T014)
# ---------------------------------------------------------------------------

DAY = 24 * 60 * 60


def _age(path: Path, seconds: float) -> None:
    t = time.time() - seconds
    os.utime(path, (t, t))


def test_clear_after_interrupted_turn_adopts_the_pending_snapshot(harness_repo):
    repo = harness_repo
    turn_start(repo, "A")
    original = snapshot(repo, "A").read_bytes()
    (repo / "pkg" / "new.py").write_text("x = undefined_name\n")
    set_stub(repo, "ruff", 1, "pkg/new.py:1:5: F821 undefined name\n")
    # Interrupted: no stop for A. /clear starts session B.

    turn_start(repo, "B")

    assert snapshot(repo, "B").read_bytes() == original
    assert not snapshot(repo, "A").exists()
    result = stop(repo, "B")
    assert result.returncode == 2
    assert "pkg/new.py" in result.stderr


def test_session_id_change_mid_turn_is_adopted_at_stop(harness_repo):
    repo = harness_repo
    (repo / "pkg" / "bad.py").write_text("x = undefined_name\n")  # in A's baseline
    turn_start(repo, "A")
    (repo / "pkg" / "clean.py").write_text("VALUE = 2\n")

    result = stop(repo, "B")  # no turn-start for B

    assert result.returncode == 0, result.stderr
    [ruff] = calls_for(repo, "ruff")
    assert "pkg/clean.py" in ruff
    assert "pkg/bad.py" not in ruff  # the HEAD fallback would have included it


def test_week_old_snapshot_is_pruned_not_adopted(harness_repo):
    repo = harness_repo
    turn_start(repo, "A")
    (repo / "pkg" / "clean.py").write_text("VALUE = 2\n")  # changed before B's turn
    _age(snapshot(repo, "A"), 8 * DAY)

    turn_start(repo, "B")

    assert not snapshot(repo, "A").exists()
    assert snapshot(repo, "B").exists()
    result = stop(repo, "B")
    assert result.returncode == 0, result.stderr
    assert uv_calls(repo) == []


def test_oldest_pending_snapshot_wins_and_the_rest_are_dropped(harness_repo):
    repo = harness_repo
    turn_start(repo, "A")
    original = snapshot(repo, "A").read_bytes()
    newer = snapshot(repo, "C")
    newer.write_text(f"{'0' * 40}\tpkg/clean.py\n")
    _age(snapshot(repo, "A"), 2 * DAY)
    _age(newer, 1 * DAY)

    turn_start(repo, "B")

    assert snapshot(repo, "B").read_bytes() == original
    assert not snapshot(repo, "A").exists()
    assert not newer.exists()


def test_own_pending_snapshot_short_circuits_adoption(harness_repo):
    repo = harness_repo
    turn_start(repo, "B")
    own = snapshot(repo, "B").read_bytes()
    other = snapshot(repo, "A")
    other.write_text(f"{'0' * 40}\tpkg/clean.py\n")
    _age(other, 1 * DAY)

    turn_start(repo, "B")

    assert snapshot(repo, "B").read_bytes() == own
    assert other.read_text() == f"{'0' * 40}\tpkg/clean.py\n"


# ---------------------------------------------------------------------------
# US2: policy.sh — AF-SECRET, AF-SPEC, AF-COMMIT (T027-T030)
# ---------------------------------------------------------------------------


def policy(repo: Path, payload: dict | str, **kwargs) -> subprocess.CompletedProcess:
    return run_hook(repo, "policy.sh", [], payload, **kwargs)


def bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def assert_denied(result: subprocess.CompletedProcess, rule: str) -> str:
    """The deny reason, after checking the decision and its first line."""
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse"
    assert out["permissionDecision"] == "deny"
    reason = out["permissionDecisionReason"]
    first = reason.splitlines()[0]
    # 012 data-model validation (T009): every deny shares one first-line format.
    assert DENY_FORMAT.match(first), reason
    assert first.startswith(f"[{rule}] "), reason
    return reason


def deny_line(result: subprocess.CompletedProcess) -> str:
    """The first non-empty stderr line, where exit-2 denies put their message."""
    return next((line for line in result.stderr.splitlines() if line.strip()), "")


def assert_no_decision(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def switch(repo: Path, branch: str, tasks: bool = False) -> None:
    git(repo, "switch", "-q", "-c", branch)
    if tasks:
        spec = repo / "specs" / branch.removeprefix("worktree-")
        spec.mkdir(parents=True, exist_ok=True)
        (spec / "tasks.md").write_text("- [ ] T001 x\n")


_SECRET_DENIED = [
    ("Read", {"file_path": "{repo}/.env"}),
    ("Read", {"file_path": "{repo}/.env.braintrust"}),
    ("Grep", {"pattern": "KEY", "path": "{repo}/.env"}),
    ("Grep", {"pattern": "KEY", "glob": ".env"}),
    ("Glob", {"pattern": ".env"}),
    # Basename in any directory and any case; a glob that can name one.
    ("Read", {"file_path": "{repo}/pkg/../.env"}),
    ("Read", {"file_path": "{repo}/.ENV"}),
    ("Read", {"file_path": "/elsewhere/.env"}),
    ("Grep", {"pattern": "KEY", "glob": ".env*"}),
    ("Glob", {"pattern": "**/.env{,.braintrust}"}),
    *[("Bash", {"command": c}) for c in (
        "cat .env", "grep KEY .env", "cat ./.env", "cat .env*",
        "cat .env{,.braintrust}", "source .env", "x=$(<.env)",
    )],
]
_SECRET_ALLOWED = [
    ("Read", {"file_path": "{repo}/.env.example"}),
    ("Glob", {"pattern": "**/.env.example"}),
    ("Grep", {"pattern": ".env", "glob": "*.py"}),
    *[("Bash", {"command": c}) for c in ("cat .env.example", "echo $HOME", "ls")],
]


def _tool_payload(repo: Path, tool: str, tool_input: dict) -> dict:
    return {
        "tool_name": tool,
        "tool_input": {k: v.replace("{repo}", str(repo)) for k, v in tool_input.items()},
    }


@pytest.mark.parametrize(("tool", "tool_input"), _SECRET_DENIED)
def test_secret_reads_are_denied(harness_repo, tool, tool_input):
    repo = harness_repo

    result = policy(repo, _tool_payload(repo, tool, tool_input))

    assert_denied(result, "AF-SECRET")
    assert uv_calls(repo) == []


@pytest.mark.parametrize(("tool", "tool_input"), _SECRET_ALLOWED)
def test_non_secret_reads_are_allowed(harness_repo, tool, tool_input):
    repo = harness_repo

    assert_no_decision(policy(repo, _tool_payload(repo, tool, tool_input)))


def _edit(repo: Path, rel: str, tool: str = "Edit") -> dict:
    key = "notebook_path" if tool == "NotebookEdit" else "file_path"
    return {"tool_name": tool, "tool_input": {key: str(repo / rel)}}


@pytest.mark.parametrize(
    ("branch", "tool", "rel"),
    [
        ("scratch", "Edit", "harness/a.py"),
        ("042-x", "Edit", "harness/a.py"),  # no specs/042-*/tasks.md
        (None, "Edit", "harness/a.py"),  # detached HEAD
        ("scratch", "Write", "orchestration/x.py"),
        ("scratch", "NotebookEdit", "eval/n.ipynb"),
    ],
)
def test_guarded_code_without_a_planned_feature_is_denied(harness_repo, branch, tool, rel):
    repo = harness_repo
    if branch is None:
        git(repo, "switch", "-q", "--detach")
    else:
        switch(repo, branch)

    reason = assert_denied(policy(repo, _edit(repo, rel, tool)), "AF-SPEC")

    assert f"branch: {branch or '(detached)'}" in reason.splitlines()[1:]


@pytest.mark.parametrize("branch", ["042-x", "worktree-042-x"])
def test_feature_branch_with_tasks_may_edit_guarded_code(harness_repo, branch):
    repo = harness_repo
    switch(repo, branch, tasks=True)

    assert_no_decision(policy(repo, _edit(repo, "harness/a.py")))


@pytest.mark.parametrize(
    "rel", ["docs/a.md", "specs/a.md", ".claude/hooks/x.sh", "CLAUDE.md", "README.md", "tests/a.py"]
)
def test_unguarded_paths_need_no_feature(harness_repo, rel):
    repo = harness_repo
    switch(repo, "scratch")

    assert_no_decision(policy(repo, _edit(repo, rel)))


@pytest.mark.parametrize("spelling", ["absolute", "relative"])
def test_root_comes_from_the_script_not_the_env(harness_repo, tmp_path_factory, spelling):
    # FR-002 (R2): a CLAUDE_PROJECT_DIR naming another checkout must not decide
    # which branch AF-SPEC judges; the repo the scripts live in does. With ROOT
    # taken from the env, the relative path was judged on B's planned branch
    # and allowed, and the absolute one lay outside B and got no decision.
    a = harness_repo
    switch(a, "main")
    b = _make_harness_repo(tmp_path_factory.mktemp("b"))
    switch(b, "042-x", tasks=True)
    payload = _edit(a, "harness/x.py")
    if spelling == "relative":
        payload["tool_input"]["file_path"] = "harness/x.py"

    result = policy(a, payload, env_extra={"CLAUDE_PROJECT_DIR": str(b)})

    reason = assert_denied(result, "AF-SPEC")
    assert "branch: main" in reason.splitlines()[1:]


def test_no_hook_script_reads_claude_project_dir():
    # FR-002 (R2): only the launcher reads CLAUDE_PROJECT_DIR. A script that
    # reads it again would judge the launch worktree instead of its own.
    assert [p.name for p in HOOKS_DIR.glob("*.sh") if "CLAUDE_PROJECT_DIR" in p.read_text()] == []


def test_paths_outside_the_repo_are_ignored(harness_repo, tmp_path_factory):
    repo = harness_repo
    switch(repo, "scratch")
    outside = tmp_path_factory.mktemp("outside") / "harness" / "a.py"

    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(outside)}}
    assert_no_decision(policy(repo, payload))


def test_spec_exception_allows_and_announces_once(harness_repo):
    repo = harness_repo
    switch(repo, "scratch")
    payload = {"session_id": "s1", **_edit(repo, "harness/a.py")}
    env = {"AF_SPEC_EXCEPTION": "hotfix"}

    first = policy(repo, payload, env_extra=env)
    second = policy(repo, payload, env_extra=env)

    assert first.returncode == 0, first.stderr
    out = json.loads(first.stdout)
    assert "hookSpecificOutput" not in out
    assert "exception active" in out["systemMessage"]
    assert "hotfix" in out["systemMessage"]
    assert (state_dir(repo) / "exception-s1.notified").exists()
    assert_no_decision(second)


def test_spec_exception_never_bypasses_secret_or_commit(harness_repo):
    repo = harness_repo
    switch(repo, "scratch")
    env = {"AF_SPEC_EXCEPTION": "hotfix"}
    read_env = {"session_id": "s1", "tool_name": "Read",
                "tool_input": {"file_path": str(repo / ".env")}}
    set_stub(repo, "pytest", 1, "FAILED tests/test_x.py::test_a - boom\n")

    assert_denied(policy(repo, read_env, env_extra=env), "AF-SECRET")
    commit = {"session_id": "s1", **bash("git commit -m x")}
    assert_denied(policy(repo, commit, env_extra=env), "AF-COMMIT")


def test_green_commit_runs_the_whole_gate_locked(harness_repo):
    repo = harness_repo

    assert_no_decision(policy(repo, bash("git commit -m x")))

    [ruff] = calls_for(repo, "ruff")
    assert ruff[-2:] == ["concise", "."] and "check" in ruff
    dirs = sorted(c[c.index("--directory") + 1] for c in calls_for(repo, "pytest"))
    assert dirs == [str(repo), str(repo / "orchestration")]
    assert len(uv_calls(repo)) == 3
    assert all("--locked" in c for c in uv_calls(repo))


def test_red_commit_is_denied_with_the_failing_test(harness_repo):
    repo = harness_repo
    set_stub(repo, "pytest", 1, "FAILED tests/test_x.py::test_a - boom\n")

    reason = assert_denied(policy(repo, bash("git commit -m x")), "AF-COMMIT")

    assert "tests/test_x.py::test_a" in reason


@pytest.mark.parametrize(
    "command",
    ["git -C /x commit -m y", "cd a && git commit --amend", "git add . && git commit", "git  commit"],
)
def test_commit_shapes_are_gated(harness_repo, command):
    repo = harness_repo
    set_stub(repo, "pytest", 1, "FAILED tests/test_x.py::test_a - boom\n")

    assert_denied(policy(repo, bash(command)), "AF-COMMIT")


@pytest.mark.parametrize(
    "command",
    # FR-005: `echo rebase` added (a verb without the word git). `git log
    # --grep=merge` is gated by the 012 contract table (`=` is a word boundary),
    # so it is in test_commit_making_verbs_are_gated instead.
    ["git status", "git log --grep=committee", "echo gitcommit", "echo rebase"],
)
def test_non_commit_commands_run_no_gate(harness_repo, command):
    repo = harness_repo

    assert_no_decision(policy(repo, bash(command)))
    assert uv_calls(repo) == []


def test_commit_without_uv_fails_closed(harness_repo, tmp_path_factory):
    repo = harness_repo
    path = _path_without(tmp_path_factory.mktemp("path"), repo, "uv")

    commit = policy(repo, bash("git commit -m x"), path=path)
    status = policy(repo, bash("git status"), path=path)

    assert commit.returncode == 2
    assert "uv is required" in commit.stderr
    assert_no_decision(status)


def test_secret_rule_runs_before_the_commit_gate(harness_repo):
    repo = harness_repo

    assert_denied(policy(repo, bash("cat .env && git commit")), "AF-SECRET")
    assert uv_calls(repo) == []


# ---------------------------------------------------------------------------
# 012 US1: gate time limit (FR-003, R3), input check (FR-004, R4), git verbs
# (FR-005, R5)
# ---------------------------------------------------------------------------


def _stop_after_a_change(repo: Path, path: str | None = None) -> subprocess.CompletedProcess:
    turn_start(repo)
    (repo / "pkg" / "new.py").write_text("x = 1\n")
    return run_hook(repo, "py-check.sh", ["stop"], {"session_id": "s1"}, path=path)


@pytest.mark.parametrize(
    ("value", "limit"),
    [(None, "240"), ("1000", "240"), ("abc", "240"), ("0", "240"), ("-5", "240"), ("30", "30")],
)
def test_gate_limit_is_clamped(harness_repo, value, limit):
    repo = harness_repo
    env = {} if value is None else {"AF_GATE_LIMIT": value}

    assert_no_decision(policy(repo, bash("git commit -m x"), env_extra=env))

    # FR-003: SECONDS counts whole seconds, so a clock tick between the gate's
    # start and its first step may hand that step one second less.
    first = [int(n) for n in gate_limit(repo)[:1]]
    assert first in ([int(limit)], [int(limit) - 1])


def test_gate_steps_share_one_deadline(harness_repo):
    repo = harness_repo
    # FR-003: each step takes over a second, so a shared deadline must hand each
    # later step strictly less time; a limit reset per step would not.
    stub = repo.parent / "bin" / "timeout"
    stub.write_text(stub.read_text().replace("\n[ -f", "\nsleep 1.1\n[ -f", 1))

    assert_no_decision(policy(repo, bash("git commit -m x"), env_extra={"AF_GATE_LIMIT": "30"}))

    limits = [int(n) for n in gate_limit(repo)]
    assert len(limits) == 3  # ruff + two suites
    assert limits[0] in (29, 30)  # FR-003: a SECONDS tick may take one second
    assert limits[0] > limits[1] > limits[2] >= 1


@pytest.mark.parametrize("rc", [124, 137])
def test_gate_timeout_denies_the_commit(harness_repo, rc):
    repo = harness_repo
    (repo.parent / "timeout.rc").write_text(str(rc))

    reason = assert_denied(policy(repo, bash("git commit -m x")), "AF-COMMIT")

    assert "timed out after" in reason.splitlines()[0]
    assert len(gate_limit(repo)) == 1  # the gate stops at the first timed-out step
    stopped = _stop_after_a_change(repo)
    assert stopped.returncode == 2
    assert "TIMED OUT" in stopped.stderr and "timed out" in stopped.stderr


def test_gate_without_a_timeout_tool_denies(harness_repo, tmp_path_factory):
    repo = harness_repo
    # _PATH_TOOLS has neither timeout nor gtimeout, so this PATH has no runner.
    path = _path_without(tmp_path_factory.mktemp("path"), repo, "timeout")

    # The contract keeps AF-COMMIT a JSON deny; only AF-HOOKS goes to stderr.
    reason = assert_denied(policy(repo, bash("git commit -m x"), path=path), "AF-COMMIT")

    assert "brew install coreutils" in reason.splitlines()[0]
    assert uv_calls(repo) == []
    stopped = _stop_after_a_change(repo, path=path)
    assert stopped.returncode == 2
    assert "brew install coreutils" in stopped.stderr


@pytest.mark.parametrize("payload", ["", "{not json", "[]", '"x"', {}, {"tool_name": 3}])
def test_policy_denies_empty_or_invalid_input(harness_repo, payload):
    repo = harness_repo

    result = policy(repo, payload)

    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "[AF-HOOKS] The repo policy hook got no valid input" in result.stderr
    assert DENY_FORMAT.match(deny_line(result)), result.stderr
    assert uv_calls(repo) == []


@pytest.mark.parametrize(
    "command",
    [
        "git revert HEAD",
        "git cherry-pick abc",
        "git merge x",
        "git am p.patch",
        "git rebase main",
        "git pull",
        "git pull --rebase",
        "git rebase --skip",
        "git rebase --continue",
        "git -c a=b merge x",
        "git pull --ff-only; git commit",
        "git pull --ff-only $(x)",
        "git com\\\nmit",
        # every "gated" row of the contract's AF-COMMIT table
        "git commit -m x",
        'git commit -m "allow git rebase --abort"',
        'git merge topic -m "see --abort"',
        "git rebase --abort && git commit -m x",
        "git cherry-pick --skip",
        "git merge --no-ff topic",
        "git -c pull.rebase=true pull --ff-only",
        "git pull --ff-only -r",
        "git pull --ff-only --no-ff",
        "git -C $(git${IFS}commit${IFS}-qam${IFS}x) rebase --abort",
        "git rebase --abort 2>/dev/null",
        "git status && git am x.patch",
        "git log --grep=merge",
        "echo commit; git status",
        "for v in commit; do git $v; done",
        # an exempt shape needs exactly one verb word
        "git -C merge merge --abort",
        # quotes and backslashes are meta: the shell strips them, so a quoted
        # option is still an option (FR-005)
        'git pull --ff-only "--no-ff"',
        "git pull --ff-only '--rebase'",
        r"git pull --ff-only \--no-ff",
        'git pull --ff-only ""--no-ff',
        "git pull --ff-only '-r'",
        # brace and glob characters are meta too: the shell expands them into
        # an option after the check (FR-005)
        "git pull --ff-only {--no-ff,}",
        "git pull --ff-only {--no-ff,origin}",
        "git pull --ff-only [-]-no-ff",
        "git pull --ff-only ?-no-ff",
        "git pull --ff-only *",
    ],
)
def test_commit_making_verbs_are_gated(harness_repo, command):
    repo = harness_repo
    set_stub(repo, "pytest", 1, "FAILED tests/test_x.py::test_a - boom\n")

    assert_denied(policy(repo, bash(command)), "AF-COMMIT")


@pytest.mark.parametrize(
    ("command", "pull_rebase"),
    [
        ("git rebase --abort", None),
        ("git -C /x merge --quit", None),
        ("git -C ../wt merge --quit", None),
        ("git cherry-pick --abort", None),
        ("git revert --quit", None),
        ("git am --abort", None),
        ("git pull --ff-only", None),
        ("git pull --ff-only", "false"),
        ("git pull --ff-only origin main", None),
    ],
)
def test_exempt_verbs_run_no_gate(harness_repo, command, pull_rebase):
    repo = harness_repo
    if pull_rebase is not None:
        git(repo, "config", "pull.rebase", pull_rebase)
    # The developer's own git config must not decide the pull verdict.
    env = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}

    assert_no_decision(policy(repo, bash(command), env_extra=env))
    assert uv_calls(repo) == []


def test_pull_ff_only_is_gated_when_pull_rebase_is_set(harness_repo):
    repo = harness_repo
    git(repo, "config", "pull.rebase", "true")
    set_stub(repo, "pytest", 1, "FAILED tests/test_x.py::test_a - boom\n")

    assert_denied(policy(repo, bash("git pull --ff-only")), "AF-COMMIT")


def test_af_commit_message_names_the_verbs(harness_repo):
    repo = harness_repo
    set_stub(repo, "pytest", 1, "FAILED tests/test_x.py::test_a - boom\n")

    first = assert_denied(policy(repo, bash("git merge x")), "AF-COMMIT").splitlines()[0]

    assert re.match(r"^\[AF-COMMIT\] .+\. To proceed: .+$", first), first
    for verb in ("commit", "revert", "cherry-pick", "merge", "am", "rebase", "pull"):
        assert re.search(rf"\b{verb}\b", first), verb


# ---------------------------------------------------------------------------
# US4: context warning in turn-start (T034, SC-008)
# ---------------------------------------------------------------------------


def _assistant(total: int) -> dict:
    """A main-thread assistant entry whose usage splits `total` over the three fields."""
    inp, created = total // 4, total // 4
    return {"type": "assistant", "message": {"usage": {
        "input_tokens": inp,
        "cache_creation_input_tokens": created,
        "cache_read_input_tokens": total - inp - created,
        "output_tokens": 500,
    }}}


_FILLER = {"type": "user", "message": {"role": "user", "content": "x"}}


def write_transcript(path: Path, entries: list[int | dict | str]) -> Path:
    """JSONL: an int is an assistant entry of that many tokens, a dict is
    written as JSON, a str is a raw line (e.g. a truncated one)."""
    lines = [
        e if isinstance(e, str) else json.dumps(_assistant(e) if isinstance(e, int) else e)
        for e in entries
    ]
    path.write_text("\n".join(lines) + "\n")
    return path


def ctx_start(repo: Path, transcript: Path | None) -> dict | None:
    """Run turn-start, check the never-block contract, return the notice if any."""
    payload: dict = {"session_id": "s1"}
    if transcript is not None:
        payload["transcript_path"] = str(transcript)
    result = run_hook(repo, "py-check.sh", ["turn-start"], payload)
    assert result.returncode == 0, result.stderr
    assert snapshot(repo).exists()
    return json.loads(result.stdout) if result.stdout else None


def ctx_marker(repo: Path) -> Path:
    return state_dir(repo) / "ctx-s1.level"


def test_context_below_warn_is_silent(harness_repo):
    repo = harness_repo
    t = write_transcript(repo.parent / "t.jsonl", [100_000])

    assert ctx_start(repo, t) is None
    assert not ctx_marker(repo).exists()


def test_context_warns_once_per_level_and_rearms(harness_repo):
    repo = harness_repo
    t = repo.parent / "t.jsonl"

    notice = ctx_start(repo, write_transcript(t, [100_000, 125_000]))
    assert notice is not None
    assert "125k" in notice["systemMessage"]
    assert "150k" in notice["systemMessage"]
    assert notice["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert notice["hookSpecificOutput"]["additionalContext"]
    assert ctx_marker(repo).read_text().strip() == "warn"

    assert ctx_start(repo, write_transcript(t, [140_000])) is None

    notice = ctx_start(repo, write_transcript(t, [152_000]))
    assert notice is not None
    assert "at or over" in notice["systemMessage"]
    assert ctx_marker(repo).read_text().strip() == "budget"
    assert ctx_start(repo, write_transcript(t, [155_000])) is None

    assert ctx_start(repo, write_transcript(t, [40_000])) is None
    assert not ctx_marker(repo).exists()
    notice = ctx_start(repo, write_transcript(t, [121_000]))
    assert notice is not None
    assert "121k of 150k" in notice["systemMessage"]


@pytest.mark.parametrize(
    "entries",
    [
        None,  # no transcript_path in the payload
        "missing",  # a path that doesn't exist
        [{"type": "user", "message": {"usage": {"input_tokens": 130_000}}}],
        [{**_assistant(130_000), "isSidechain": True}],
        [{"type": "assistant", "message": {"usage": {"input_tokens": "lots"}}}],
        # jq's + concatenates strings: "130000", then a leading-zero (octal) value.
        [{"type": "assistant", "message": {"usage": {
            "input_tokens": "13", "cache_read_input_tokens": "0000", "cache_creation_input_tokens": ""
        }}}],
        [{"type": "assistant", "message": {"usage": {
            "input_tokens": "0", "cache_read_input_tokens": "9", "cache_creation_input_tokens": "99999"
        }}}],
    ],
    ids=["no-path", "nonexistent", "user-only", "sidechain-only", "non-numeric",
         "digit-strings", "leading-zero-strings"],
)
def test_context_unreadable_input_is_silent(harness_repo, entries):
    repo = harness_repo
    t = repo.parent / "t.jsonl"
    if isinstance(entries, list):
        write_transcript(t, entries)

    assert ctx_start(repo, None if entries is None else t) is None
    assert not ctx_marker(repo).exists()


def test_context_partial_last_line_uses_the_last_whole_entry(harness_repo):
    repo = harness_repo
    t = write_transcript(
        repo.parent / "t.jsonl", [130_000, '{"type":"assistant","message":{"usage":{"input_tok']
    )

    notice = ctx_start(repo, t)

    assert notice is not None
    assert "130k" in notice["systemMessage"]


@pytest.mark.parametrize(
    ("entries", "warned"),
    [([_FILLER] * 5000 + [130_000], True), ([130_000] + [_FILLER] * 300, False)],
    ids=["entry-in-tail", "entry-before-tail"],
)
def test_context_reads_only_the_transcript_tail(harness_repo, entries, warned):
    repo = harness_repo
    t = write_transcript(repo.parent / "t.jsonl", entries)

    assert (ctx_start(repo, t) is not None) is warned


# ---------------------------------------------------------------------------
# US4: continuity context after /compact or /clear (T035, SC-009)
# ---------------------------------------------------------------------------

_RULES = ("AF-SPEC", "AF-SECRET", "AF-COMMIT", "AF-REGISTRY", "AF-HARNESS")


def session_context(repo: Path, source: str, **kwargs) -> str:
    """The injected block, or "" — after checking the never-block contract."""
    result = run_hook(repo, "session-context.sh", [], {"source": source}, **kwargs)
    assert result.returncode == 0, result.stderr
    if not result.stdout:
        return ""
    out = json.loads(result.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "SessionStart"
    return out["additionalContext"]


def feature(repo: Path, branch: str, tasks: list[str] | None) -> None:
    """Switch to `branch` and give it a spec dir, with these tasks.md lines if any."""
    git(repo, "switch", "-q", "-c", branch)
    spec = repo / "specs" / branch.removeprefix("worktree-")
    spec.mkdir(parents=True)
    (spec / "spec.md").write_text("# spec\n")
    if tasks is not None:
        (spec / "tasks.md").write_text("# Tasks\n\n" + "".join(f"{t}\n" for t in tasks))


_TASKS = ["- [x] T001 done", *(f"- [ ] T00{i} open {i}" for i in range(2, 7))]


@pytest.mark.parametrize("branch", ["042-x", "worktree-042-x"])
def test_compact_on_a_feature_branch_injects_where_to_resume(harness_repo, branch):
    repo = harness_repo
    feature(repo, branch, _TASKS)

    ctx = session_context(repo, "compact")

    assert "compacted" in ctx
    assert f"- branch: {branch}\n" in ctx
    assert "specs/042-x/" in ctx
    found = re.findall(r"T00\d", ctx)
    assert found == ["T002", "T003", "T004"]
    assert all(rule in ctx for rule in _RULES)


def test_clear_says_cleared(harness_repo):
    repo = harness_repo
    feature(repo, "042-x", _TASKS)

    assert "cleared" in session_context(repo, "clear")


def test_continuity_reports_a_pending_turn_snapshot(harness_repo):
    repo = harness_repo
    feature(repo, "042-x", _TASKS)

    assert "- turn gate: clear" in session_context(repo, "compact")
    (state_dir(repo) / "turn-x.tsv").write_text("")
    assert "- turn gate: snapshot pending" in session_context(repo, "compact")


@pytest.mark.parametrize(
    ("branch", "spec", "source"),
    [
        ("main", False, "compact"),
        ("043-y", False, "compact"),
        ("042-x", True, "startup"),
        ("042-x", True, "resume"),
        ("042-x", True, ""),
    ],
    ids=["main", "no-spec-dir", "startup", "resume", "no-source"],
)
def test_continuity_is_silent_off_feature_or_on_other_sources(harness_repo, branch, spec, source):
    repo = harness_repo
    if spec:
        feature(repo, branch, _TASKS)
    else:
        git(repo, "switch", "-q", "-c", branch)

    assert session_context(repo, source) == ""


def test_continuity_is_silent_on_a_detached_head(harness_repo):
    repo = harness_repo
    feature(repo, "042-x", _TASKS)
    git(repo, "switch", "-q", "--detach")

    assert session_context(repo, "compact") == ""


def test_continuity_is_silent_without_jq(harness_repo, tmp_path_factory):
    repo = harness_repo
    feature(repo, "042-x", _TASKS)
    path = _path_without(tmp_path_factory.mktemp("path"), repo, "jq")

    assert session_context(repo, "compact", path=path) == ""


def test_spec_dir_without_tasks_says_so(harness_repo):
    repo = harness_repo
    feature(repo, "042-x", None)

    assert "- next tasks: no tasks.md" in session_context(repo, "compact")


def test_long_task_lines_are_cut_to_160_characters(harness_repo):
    repo = harness_repo
    line = "- [ ] T001 " + "a" * 289
    assert len(line) == 300
    feature(repo, "042-x", [line])

    lines = session_context(repo, "compact").splitlines()

    assert "  " + line[:160] in lines
    assert not any(line[:161] in entry for entry in lines)


# ---------------------------------------------------------------------------
# Never-block and fail-closed contracts across scripts (T036 review)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", ["not-json", "empty-stdin", "no-lib", "no-git"])
@pytest.mark.parametrize(
    ("script", "args"),
    [("py-check.sh", ["turn-start"]), ("session-context.sh", [])],
    ids=["turn-start", "session-context"],
)
def test_turn_start_and_session_context_never_fail(
    harness_repo, tmp_path_factory, script, args, case
):
    repo = harness_repo
    feature(repo, "042-x", _TASKS)  # session-context would speak on a good payload
    payload: dict | str = {"session_id": "s1", "source": "compact"}
    path = None
    if case == "not-json":
        payload = "{not json"
    elif case == "empty-stdin":
        payload = ""
    elif case == "no-lib":
        (repo / ".claude" / "hooks" / "lib.sh").unlink()
    else:
        path = _path_without(tmp_path_factory.mktemp("path"), repo, "git")

    result = run_hook(repo, script, args, payload, path=path)

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize(
    ("script", "args", "payload", "missing"),
    [
        ("py-check.sh", ["stop"], {"session_id": "s1"}, "git"),
        ("policy.sh", [], bash("git status"), "git"),
        ("policy.sh", [], bash("git status"), "jq"),
    ],
    ids=["stop-no-git", "policy-no-git", "policy-no-jq"],
)
def test_stop_and_policy_fail_closed_without_tools(
    harness_repo, tmp_path_factory, script, args, payload, missing
):
    repo = harness_repo
    path = _path_without(tmp_path_factory.mktemp("path"), repo, missing)

    result = run_hook(repo, script, args, payload, path=path)

    assert result.returncode == 2
    assert f"{missing} is required" in result.stderr


def _run_without_root(repo: Path, script: str, args: list[str]) -> subprocess.CompletedProcess:
    """Run a hook copy from its own dir with the repo dir at mode 0, so the
    script's `cd <script dir>/../..` fails. bash's own startup warnings
    (shell-init:, chdir:), caused by that cwd, are dropped from stderr."""
    switch(repo, "main")
    env = _clean_env()
    env["PATH"] = f"{repo.parent / 'bin'}{os.pathsep}{env['PATH']}"
    run = 'r=$1 s=$2; shift 2; chmod 0 "$r" && exec /bin/bash "./$s" "$@"'
    try:
        result = subprocess.run(
            ["/bin/sh", "-c", run, "sh", str(repo), script, *args],
            cwd=repo / ".claude" / "hooks", input=json.dumps(_edit(repo, "harness/x.py")),
            capture_output=True, text=True, env=env, timeout=60,
        )
    finally:
        repo.chmod(0o755)
    lines = result.stderr.splitlines(keepends=True)
    result.stderr = "".join(s for s in lines if not s.startswith(("shell-init:", "chdir:")))
    return result


_NEEDS_DIR_PERMISSIONS = pytest.mark.skipif(
    os.geteuid() == 0, reason="root ignores directory permissions, so chmod 0 cannot make cd fail"
)


@_NEEDS_DIR_PERMISSIONS
@pytest.mark.parametrize(("script", "args"), [("policy.sh", []), ("py-check.sh", ["edit"])])
def test_policy_and_edit_fail_closed_without_a_root(harness_repo, script, args):
    # FR-002 (R2), 012 fix round: ROOT comes from `cd <script dir>/../..`. If
    # that cd fails, an empty ROOT makes every absolute path look outside the
    # repo, so AF-SPEC and the edit lint would pass the call unchecked.
    result = _run_without_root(harness_repo, script, args)

    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "cannot resolve the repo root" in result.stderr


@_NEEDS_DIR_PERMISSIONS
def test_policy_without_a_root_is_an_af_hooks_deny(harness_repo):
    # FR-002 + data-model validation: policy.sh's exit-2 refusal is an AF-HOOKS
    # deny, so its first line names the rule and a way to proceed.
    first = deny_line(_run_without_root(harness_repo, "policy.sh", []))

    assert DENY_FORMAT.match(first), first
    assert first.startswith("[AF-HOOKS] "), first


@_NEEDS_DIR_PERMISSIONS
def test_turn_start_without_a_root_keeps_the_prompt(harness_repo):
    # FR-002, 012 fix round: turn-start always exits 0 (an exit 2 from
    # UserPromptSubmit erases the operator's prompt), as with a lib.sh failure.
    result = _run_without_root(harness_repo, "py-check.sh", ["turn-start"])

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# US2 + US4: the real .claude/settings.json wiring and permission rules (T038)
# ---------------------------------------------------------------------------

_DENY = ["Read(/.env)", "Read(/.env.braintrust)"]
_ASK = [
    "Edit(/registry/agents/*/manifest.yaml)",
    "Edit(/registry/agents/*/versions/**)",
    "Edit(/.claude/settings.json)",
    "Edit(/.claude/settings.local.json)",
    "Edit(/.claude/hooks/**)",
]


@pytest.fixture(scope="module")
def settings() -> dict:
    return json.loads((REPO_ROOT / ".claude" / "settings.json").read_text())


def _rule_covers(rule: str, tool: str, rel: str) -> bool:
    """Gitignore-style match: `*` stays within one segment, `**` crosses `/`,
    and a single leading `/` anchors the pattern at the project root (`./` would
    anchor it at the session's start directory, `//` at the filesystem root)."""
    m = re.fullmatch(r"(\w+)\(/([^/].*)\)", rule)
    assert m, rule
    parts = re.split(r"(\*\*|\*)", m.group(2))
    regex = "".join(
        ".*" if p == "**" else "[^/]*" if p == "*" else re.escape(p) for p in parts
    )
    return m.group(1) == tool and re.fullmatch(regex, rel) is not None


def _command(settings: dict, event: str, matcher: str | None = None) -> str:
    entries = [e for e in settings["hooks"][event] if e.get("matcher") == matcher]
    assert len(entries) == 1, (event, matcher)
    return entries[0]["hooks"][0]["command"]


def test_settings_lists_every_permission_rule(settings):
    assert set(_DENY) <= set(settings["permissions"]["deny"])
    assert set(_ASK) <= set(settings["permissions"]["ask"])


@pytest.mark.parametrize(
    ("kind", "tool", "rel", "covered"),
    [
        # AF-REGISTRY
        ("ask", "Edit", "registry/agents/swe-agent/manifest.yaml", True),
        ("ask", "Edit", "registry/agents/pm-agent/versions/0.1.0.yaml", True),
        ("ask", "Edit", "registry/agents/swe-agent/SKILL.md", False),
        # AF-HARNESS
        ("ask", "Edit", ".claude/settings.json", True),
        ("ask", "Edit", ".claude/settings.local.json", True),
        ("ask", "Edit", ".claude/hooks/policy.sh", True),
        ("ask", "Edit", ".claude/agents/py-codereviewer.md", False),
        # AF-SECRET (permission layer)
        ("deny", "Read", ".env", True),
        ("deny", "Read", ".env.braintrust", True),
        ("deny", "Read", ".env.example", False),
    ],
)
def test_permission_rules_cover_exactly_the_intended_paths(
    settings, kind, tool, rel, covered
):
    rules = settings["permissions"][kind]
    assert any(_rule_covers(r, tool, rel) for r in rules) is covered


# FR-001: replaces test_settings_wire_every_hook. Every command is now the 012
# launcher, so the old `.endswith("py-check.sh stop")` checks no longer hold.
_PRE_MATCHER = "Edit|Write|MultiEdit|NotebookEdit|Read|Grep|Glob|Bash"
_ENTRIES = [
    # (event, matcher, script, args, timeout; None = unchanged, not asserted)
    ("PreToolUse", _PRE_MATCHER, "policy.sh", "", 300),
    ("PostToolUse", "Edit|Write|MultiEdit", "py-check.sh", " edit", None),
    ("UserPromptSubmit", None, "py-check.sh", " turn-start", None),
    ("Stop", None, "py-check.sh", " stop", 300),
    ("SessionStart", "compact|clear", "session-context.sh", "", None),
]


def _hook(settings: dict, event: str, matcher: str | None) -> dict:
    entries = [e for e in settings["hooks"][event] if e.get("matcher") == matcher]
    assert len(entries) == 1, (event, matcher)
    return entries[0]["hooks"][0]


def test_policy_hook_covers_every_guarded_tool(settings):
    pre = [e for e in settings["hooks"]["PreToolUse"] if "policy.sh" in e["hooks"][0]["command"]]
    assert len(pre) == 1
    assert set(pre[0]["matcher"].split("|")) == {
        "Edit", "Write", "MultiEdit", "NotebookEdit", "Read", "Grep", "Glob", "Bash"
    }


@pytest.mark.parametrize(("event", "matcher", "script", "args", "timeout"), _ENTRIES)
def test_every_hook_uses_the_launcher(settings, event, matcher, script, args, timeout):
    hook = _hook(settings, event, matcher)
    cmd = hook["command"]
    if timeout is not None:
        assert hook["timeout"] == timeout

    assert "git rev-parse --show-cdup" in cmd
    assert "--show-toplevel" not in cmd
    assert '"$CLAUDE_PROJECT_DIR"' in cmd
    assert f'bash "$r/.claude/hooks/{script}"{args};' in cmd
    message = cmd[cmd.index("[AF-HOOKS]"):]
    message = message[: message.index("Claude Code.") + len("Claude Code.")]
    assert "'" not in message
    assert f"(.claude/hooks/{script})" in message
    syntax = subprocess.run(["/bin/sh", "-n", "-c", cmd], capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr
    if shutil.which("shellcheck"):
        lint = subprocess.run(
            ["shellcheck", "-s", "sh", "-"], input=cmd + "\n", capture_output=True, text=True
        )
        assert lint.returncode == 0, lint.stdout


def test_gate_limit_is_below_the_hook_timeouts(settings):
    lib = (HOOKS_DIR / "lib.sh").read_text()
    default = re.search(r"\$\{AF_GATE_LIMIT:-(\d+)\}", lib)
    assert default, "lib.sh sets no AF_GATE_LIMIT default"
    for event, matcher in (("PreToolUse", _PRE_MATCHER), ("Stop", None)):
        assert int(default.group(1)) + 10 < _hook(settings, event, matcher)["timeout"], event


def _launch(cmd: str, payload: dict, project_dir: Path) -> subprocess.CompletedProcess:
    """Run a settings.json hook command the way Claude Code does: /bin/sh -c."""
    env = _clean_env()
    env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    return subprocess.run(
        ["/bin/sh", "-c", cmd], input=json.dumps(payload),
        capture_output=True, text=True, env=env, timeout=60,
    )


@pytest.mark.parametrize(
    "case", ["cwd-wins", "cwd-over-project-dir", "project-dir-fallback", "symlinked-cwd"]
)
def test_launcher_finds_scripts(settings, harness_repo, tmp_path_factory, case):
    repo = harness_repo
    switch(repo, "main")
    cmd = _command(settings, "PreToolUse", _PRE_MATCHER)
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    gone = elsewhere / "removed-worktree"  # never created
    # (d): the cwd and file_path are spelled through a symlink to the repo. A
    # launcher built on --show-toplevel would get the physical root, and the
    # edit would fall outside it with no decision (012 fix round, 2026-10-13).
    link = elsewhere / "link"
    link.symlink_to(repo)
    # Both hold the scripts: the launch dir is on a planned feature, so its
    # policy.sh would see the edit outside its root and stay silent. Only the
    # cwd's copy denies (FR-002, lookup order).
    planned = _make_harness_repo(tmp_path_factory.mktemp("planned"))
    switch(planned, "042-x", tasks=True)
    root, cwd, project_dir = {
        "cwd-wins": (repo, repo, gone),
        "cwd-over-project-dir": (repo, repo, planned),
        "project-dir-fallback": (repo, elsewhere, repo),
        "symlinked-cwd": (link, link, gone),
    }[case]
    payload = {**_edit(root, "harness/x.py"), "cwd": str(cwd)}

    assert_denied(_launch(cmd, payload, project_dir), "AF-SPEC")


@pytest.mark.parametrize(("event", "matcher", "script", "args", "timeout"), _ENTRIES)
def test_launcher_without_scripts_fails_safe(
    settings, tmp_path_factory, event, matcher, script, args, timeout
):
    empty = tmp_path_factory.mktemp("noscripts")
    cmd = _command(settings, event, matcher)

    result = _launch(cmd, {"cwd": str(empty), "tool_name": "Bash"}, empty / "gone")

    expected = f"[AF-HOOKS] The repo hook scripts (.claude/hooks/{script}) were not found"
    if event == "PreToolUse":
        assert result.returncode == 2
        assert expected in result.stderr
        assert DENY_FORMAT.match(deny_line(result)), result.stderr
    else:
        assert result.returncode == 0, result.stderr
        message = json.loads(result.stdout)["systemMessage"]
        assert message.startswith(expected)
        assert DENY_FORMAT.match(message), message


def test_settings_wire_context_continuity_and_cap(settings):
    # FR-001: the session-context command check moved to
    # test_every_hook_uses_the_launcher.
    assert "PreCompact" not in settings["hooks"]

    lib = (HOOKS_DIR / "lib.sh").read_text()
    budget = re.search(r"^CTX_BUDGET=(\d+)$", lib, re.MULTILINE)
    assert budget
    assert settings["env"]["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] == budget.group(1)
