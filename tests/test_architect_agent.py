"""Tests for harness/architect-agent/agent.py. All `subprocess`/`gh`/`git`
and `query()` calls are mocked — no real GitHub or model network access.
Every test asserts a structural property (a tool binding, a prompt's
contents, process env state, a validation rejection), per tasks.md's
Notes section.
"""
import asyncio
import json
import os
import subprocess
from pathlib import Path

import pytest

from conftest import architect_agent as arch


# --- Helpers ---------------------------------------------------------------

def _envelope_text(**fields) -> str:
    return json.dumps(fields)


def _make_query(responses):
    """Returns a fake `query()` that yields one string response per call,
    in order, and records every call's (prompt, options)."""
    calls = []
    it = iter(responses)

    async def fake_query(*, prompt, options=None):
        calls.append({"prompt": prompt, "options": options})
        yield next(it)

    fake_query.calls = calls
    return fake_query


def _candidate_envelope(angle="some-angle", plan="plan body", tasks="tasks body", adrs=None):
    return _envelope_text(angle=angle, plan_md=plan, tasks_md=tasks, adrs=adrs or [])


SC_IDS = [("SC-001", "first"), ("SC-002", "second"), ("SC-003", "third")]


# --- T015: _no_git_credentials ----------------------------------------------

def test_no_git_credentials_pops_and_restores(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "tok-a")
    monkeypatch.setenv("GITHUB_TOKEN", "tok-b")

    with arch._no_git_credentials():
        assert "GH_TOKEN" not in os.environ
        assert "GITHUB_TOKEN" not in os.environ

    assert os.environ["GH_TOKEN"] == "tok-a"
    assert os.environ["GITHUB_TOKEN"] == "tok-b"


def test_no_git_credentials_restores_on_exception(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "tok-a")
    monkeypatch.setenv("GITHUB_TOKEN", "tok-b")

    with pytest.raises(RuntimeError):
        with arch._no_git_credentials():
            assert "GH_TOKEN" not in os.environ
            raise RuntimeError("boom")

    assert os.environ["GH_TOKEN"] == "tok-a"
    assert os.environ["GITHUB_TOKEN"] == "tok-b"


# --- T016: _load_sc_ids ------------------------------------------------------

def test_load_sc_ids_returns_id_text_pairs(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text(
        "## Success Criteria\n\n"
        "### Measurable Outcomes\n\n"
        "- **SC-001**: first criterion\n"
        "- **SC-002**: second criterion that\n  wraps across lines\n"
        "- **SC-003**: third criterion\n"
    )
    result = arch._load_sc_ids(spec)
    assert result == [
        ("SC-001", "first criterion"),
        ("SC-002", "second criterion that wraps across lines"),
        ("SC-003", "third criterion"),
    ]


def test_load_sc_ids_raises_without_measurable_outcomes(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text("## Success Criteria\n\nno subsection here\n")
    with pytest.raises(ValueError):
        arch._load_sc_ids(spec)


# --- T017a: no token anywhere in the checkout -------------------------------

def _init_bare_repo_with_commit(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    (path / "README.md").write_text("hello")
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(path), "-c", "user.email=t@t.com", "-c", "user.name=t",
         "commit", "-q", "-m", "init"],
        check=True,
    )


def test_clone_leaves_no_token_in_checkout(tmp_path, monkeypatch):
    origin = tmp_path / "origin"
    origin.mkdir()
    _init_bare_repo_with_commit(origin)
    (origin / "specs").mkdir()
    (origin / "specs" / "004-x").mkdir()
    (origin / "specs" / "004-x" / "spec.md").write_text("# spec\n")
    subprocess.run(["git", "-C", str(origin), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(origin), "-c", "user.email=t@t.com", "-c", "user.name=t",
         "commit", "-q", "-m", "spec"],
        check=True,
    )
    subprocess.run(["git", "-C", str(origin), "branch", "-M", "main"], check=True)

    sentinel = "sentinel-token-value"
    work_root = tmp_path / "work"
    work_root.mkdir()
    checkout = work_root / "checkout"
    subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", "main", str(origin), str(checkout)],
        check=True, capture_output=True,
    )
    # Simulate what a token-embedded clone URL would have written, since a
    # local fixture repo can't serve https:// credentials.
    subprocess.run(
        ["git", "-C", str(checkout), "remote", "set-url", "origin",
         f"https://x-access-token:{sentinel}@github.com/some/repo.git"],
        check=True,
    )
    git_config = checkout / ".git" / "config"
    assert sentinel in git_config.read_text()

    arch._run(
        ["git", "remote", "set-url", "origin", "https://github.com/some/repo.git"],
        cwd=checkout,
    )
    arch._run(["git", "config", "--local", "credential.helper", ""], cwd=checkout)

    for path in checkout.rglob("*"):
        if path.is_file():
            content = path.read_bytes()
            assert sentinel.encode() not in content, f"token leaked into {path}"

    remote_url = arch._run(["git", "remote", "get-url", "origin"], cwd=checkout)
    assert sentinel not in remote_url


def test_clone_spec_branch_scrubs_token_on_failure(tmp_path, monkeypatch):
    token = "secret-token-xyz"
    monkeypatch.setenv("GH_TOKEN", token)

    def fake_run(cmd, cwd=None):
        raise subprocess.CalledProcessError(
            1, cmd, output=f"cloning with {token}", stderr=f"failed with {token}"
        )

    monkeypatch.setattr(arch, "_run", fake_run)

    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        arch._clone_spec_branch("owner/repo", "main", "specs/x", str(tmp_path))

    e = exc_info.value
    assert token not in str(e.cmd)
    assert token not in (e.output or "")
    assert token not in (e.stderr or "")
    assert token not in str(e.args)


# --- T018: _parse_json_envelope ---------------------------------------------

def test_parse_json_envelope_extracts_object():
    assert arch._parse_json_envelope('prose {"a": 1} more prose') == {"a": 1}


def test_parse_json_envelope_raises_on_no_json():
    with pytest.raises(ValueError):
        arch._parse_json_envelope("no json here")


# --- T020/T021/T022: candidate_count / angles_for ---------------------------

def test_candidate_count_properties():
    assert arch.candidate_count(["SC-001"] * 3) >= arch.MIN_CANDIDATES
    for n in range(0, 30):
        assert arch.candidate_count(["SC-001"] * n) <= arch.MAX_CANDIDATES
    counts = [arch.candidate_count(["SC-001"] * n) for n in range(0, 20)]
    assert counts == sorted(counts)
    assert arch.candidate_count(["SC-001"] * 20) > arch.candidate_count(["SC-001"] * 5)


def test_candidate_count_override():
    assert arch.candidate_count([], n_override=1) == 1
    assert arch.candidate_count([], n_override=99) == arch.MAX_CANDIDATES


def test_angles_for():
    assert arch.angles_for(3) == arch.ANGLES[:3]
    assert len(set(arch.angles_for(6))) == 6
    with pytest.raises(ValueError):
        arch.angles_for(arch.MAX_CANDIDATES + 1)


# --- T023: generate_candidates isolation ------------------------------------

def test_generate_candidates_isolation(tmp_path, monkeypatch):
    angles = arch.angles_for(3)
    responses = [
        _candidate_envelope(angle=a, plan=f"plan-for-{a}", tasks=f"tasks-for-{a}")
        for a in angles
    ]
    fake = _make_query(responses)
    monkeypatch.setattr(arch, "query", fake)

    results = asyncio.run(arch.generate_candidates(tmp_path, "specs/x", angles))

    assert len(fake.calls) == len(angles)
    all_texts = [f"plan-for-{a}" for a in angles]
    for i, call in enumerate(fake.calls):
        prompt = call["prompt"]
        assert angles[i] in prompt
        for j, text in enumerate(all_texts):
            if j != i:
                assert text not in prompt
        assert "synthesized_plan" not in prompt.lower() or "SYNTHESIZED PLAN" not in prompt
    assert all(r["valid"] for r in results)


# --- T024: concurrent credential scrub --------------------------------------

def test_generate_candidates_scrubs_credentials_for_every_call(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "live-token")
    seen = []

    async def fake_query(*, prompt, options=None):
        seen.append(os.environ.get("GH_TOKEN"))
        yield _candidate_envelope()

    monkeypatch.setattr(arch, "query", fake_query)
    angles = arch.angles_for(3)

    with arch._no_git_credentials():
        asyncio.run(arch.generate_candidates(tmp_path, "specs/x", angles))

    assert seen
    assert all(v is None for v in seen)


# --- T025: tool binding ------------------------------------------------------

def test_generate_candidate_tool_binding(tmp_path, monkeypatch):
    fake = _make_query([_candidate_envelope()])
    monkeypatch.setattr(arch, "query", fake)

    asyncio.run(arch.generate_candidate(tmp_path, "specs/x", "some-angle"))

    options = fake.calls[0]["options"]
    assert options.tools == ["Read", "Grep", "Glob"]
    assert options.setting_sources == []
    assert options.cwd == str(tmp_path)
    assert "ANTHROPIC_BASE_URL" in options.env
    assert "ANTHROPIC_API_KEY" in options.env


# --- T026: validity + mode legality -----------------------------------------

def test_generate_candidate_validity_and_mode_legality(tmp_path, monkeypatch):
    fake = _make_query(["not json at all"])
    monkeypatch.setattr(arch, "query", fake)
    result = asyncio.run(arch.generate_candidate(tmp_path, "specs/x", "angle"))
    assert result["valid"] is False

    fake = _make_query([_candidate_envelope(plan="", tasks="tasks")])
    monkeypatch.setattr(arch, "query", fake)
    result = asyncio.run(arch.generate_candidate(tmp_path, "specs/x", "angle"))
    assert result["valid"] is False

    fake = _make_query([_candidate_envelope(angle="model-said-this")])
    monkeypatch.setattr(arch, "query", fake)
    result = asyncio.run(arch.generate_candidate(tmp_path, "specs/x", "caller-angle"))
    assert result["angle"] == "caller-angle"

    with pytest.raises(ValueError):
        asyncio.run(arch.generate_candidate(tmp_path, "specs/x", "angle", gap="g"))
    with pytest.raises(ValueError):
        asyncio.run(
            arch.generate_candidate(
                tmp_path, "specs/x", "angle", synthesized_plan={"plan_md": "p"}
            )
        )


# --- T028a: bounds -----------------------------------------------------------

def test_generate_candidates_bounds(tmp_path, monkeypatch):
    concurrent = []
    peak = [0]
    lock_count = [0]

    async def fake_query(*, prompt, options=None):
        lock_count[0] += 1
        peak[0] = max(peak[0], lock_count[0])
        await asyncio.sleep(0.01)
        lock_count[0] -= 1
        yield _candidate_envelope()

    monkeypatch.setattr(arch, "query", fake_query)
    angles = arch.angles_for(6)
    results = asyncio.run(arch.generate_candidates(tmp_path, "specs/x", angles))
    assert peak[0] <= arch.CANDIDATE_CONCURRENCY
    assert len(results) == 6

    monkeypatch.setattr(arch, "CANDIDATE_TIMEOUT_S", 0.01)

    async def hanging_query(*, prompt, options=None):
        await asyncio.sleep(10)
        yield _candidate_envelope()
        return

    monkeypatch.setattr(arch, "query", hanging_query)
    results = asyncio.run(arch.generate_candidates(tmp_path, "specs/x", arch.angles_for(1)))
    assert results[0]["valid"] is False
    assert results[0]["error"] == "timeout"


def test_generate_candidate_rejects_oversize_plan(tmp_path, monkeypatch):
    fake = _make_query([_candidate_envelope(plan="x" * (arch.MAX_PLAN_CHARS + 1))])
    monkeypatch.setattr(arch, "query", fake)
    result = asyncio.run(arch.generate_candidate(tmp_path, "specs/x", "angle"))
    assert result["valid"] is False


# --- T029/T030: score_candidates validation ---------------------------------

def _valid_candidates(n=2):
    return [
        {"index": i, "angle": f"angle-{i}", "plan_md": "p", "tasks_md": "t", "adrs": [], "valid": True}
        for i in range(n)
    ]


def test_score_candidates_rejects_bad_coverage(monkeypatch):
    candidates = _valid_candidates(2)

    bad_invented = json.dumps({"scores": [
        {"coverage": {"SC-001": True, "SC-002": True, "SC-999": False}, "internal_consistency": 3},
        {"coverage": {"SC-001": True, "SC-002": True, "SC-003": True}, "internal_consistency": 3},
    ]})
    monkeypatch.setattr(arch, "query", _make_query([bad_invented]))
    with pytest.raises(ValueError):
        asyncio.run(arch.score_candidates(candidates, SC_IDS))

    bad_missing = json.dumps({"scores": [
        {"coverage": {"SC-001": True}, "internal_consistency": 3},
        {"coverage": {"SC-001": True, "SC-002": True, "SC-003": True}, "internal_consistency": 3},
    ]})
    monkeypatch.setattr(arch, "query", _make_query([bad_missing]))
    with pytest.raises(ValueError):
        asyncio.run(arch.score_candidates(candidates, SC_IDS))

    bad_key = json.dumps({"scores": [
        {"coverage": {"SC-001": True, "SC-002": True, "not-an-id": True}, "internal_consistency": 3},
        {"coverage": {"SC-001": True, "SC-002": True, "SC-003": True}, "internal_consistency": 3},
    ]})
    monkeypatch.setattr(arch, "query", _make_query([bad_key]))
    with pytest.raises(ValueError):
        asyncio.run(arch.score_candidates(candidates, SC_IDS))


@pytest.mark.parametrize("rating", [0, 6, "high", 3.5])
def test_score_candidates_rejects_bad_consistency_rating(monkeypatch, rating):
    candidates = _valid_candidates(1)
    envelope = json.dumps({"scores": [
        {"coverage": {"SC-001": True, "SC-002": True, "SC-003": True}, "internal_consistency": rating},
    ]})
    monkeypatch.setattr(arch, "query", _make_query([envelope]))
    with pytest.raises(ValueError):
        asyncio.run(arch.score_candidates(candidates, SC_IDS))


@pytest.mark.parametrize("rating", [1, 2, 3, 4, 5])
def test_score_candidates_accepts_valid_consistency_rating(monkeypatch, rating):
    candidates = _valid_candidates(1)
    envelope = json.dumps({"scores": [
        {"coverage": {"SC-001": True, "SC-002": True, "SC-003": True}, "internal_consistency": rating},
    ]})
    monkeypatch.setattr(arch, "query", _make_query([envelope]))
    scores = asyncio.run(arch.score_candidates(candidates, SC_IDS))
    assert scores[0]["internal_consistency"] == rating


# --- T031: synthesis receives scores, not prose -----------------------------

def test_synthesize_receives_scores_not_prose(monkeypatch):
    candidates = _valid_candidates(2)
    scores = [
        {"candidate_index": 0, "angle": "angle-0", "coverage": {"SC-001": True, "SC-002": True, "SC-003": False},
         "internal_consistency": 4, "notes": "aggregate reasoning prose that must not leak"},
        {"candidate_index": 1, "angle": "angle-1", "coverage": {"SC-001": True, "SC-002": True, "SC-003": True},
         "internal_consistency": 5, "notes": "other notes"},
    ]
    synth_envelope = json.dumps({"plan_md": "final plan", "tasks_md": "final tasks", "adrs": [], "grafted_from": []})
    fake = _make_query([synth_envelope])
    monkeypatch.setattr(arch, "query", fake)

    asyncio.run(arch.synthesize(candidates, scores, winner_index=1))

    prompt = fake.calls[0]["prompt"]
    assert "SC-001" in prompt and "true" in prompt.lower()
    assert "aggregate reasoning prose that must not leak" not in prompt


def test_scoring_and_synthesis_are_two_distinct_calls(monkeypatch):
    candidates = _valid_candidates(1)
    score_envelope = json.dumps({"scores": [
        {"coverage": {"SC-001": True, "SC-002": True, "SC-003": True}, "internal_consistency": 3},
    ]})
    synth_envelope = json.dumps({"plan_md": "p", "tasks_md": "t", "adrs": [], "grafted_from": []})
    fake = _make_query([score_envelope, synth_envelope])
    monkeypatch.setattr(arch, "query", fake)

    scores = asyncio.run(arch.score_candidates(candidates, SC_IDS))
    winner = arch.pick_winner(scores)
    asyncio.run(arch.synthesize(candidates, scores, winner))
    assert len(fake.calls) == 2


# --- T032: cardinality + references -----------------------------------------

def test_synthesize_cardinality_and_references(monkeypatch):
    candidates = _valid_candidates(2)
    scores = [
        {"candidate_index": 0, "angle": "a0", "coverage": {"SC-001": True, "SC-002": True, "SC-003": True},
         "internal_consistency": 3, "notes": ""},
    ]

    good = json.dumps({"plan_md": "p", "tasks_md": "t", "adrs": [], "grafted_from": [0]})
    monkeypatch.setattr(arch, "query", _make_query([good]))
    result = asyncio.run(arch.synthesize(candidates, scores, winner_index=0))
    assert isinstance(result, dict)

    bad_ref = json.dumps({"plan_md": "p", "tasks_md": "t", "adrs": [], "grafted_from": [999]})
    monkeypatch.setattr(arch, "query", _make_query([bad_ref]))
    with pytest.raises(ValueError):
        asyncio.run(arch.synthesize(candidates, scores, winner_index=0))


# --- T033: partial + total malformed candidates -----------------------------

def test_partial_malformed_candidate_reported_not_dropped(tmp_path, monkeypatch):
    angles = arch.angles_for(3)
    responses = [
        _candidate_envelope(angle=angles[0]),
        "not valid json",
        _candidate_envelope(angle=angles[2]),
    ]
    monkeypatch.setattr(arch, "query", _make_query(responses))
    results = asyncio.run(arch.generate_candidates(tmp_path, "specs/x", angles))
    invalid = [c for c in results if not c["valid"]]
    assert len(invalid) == 1
    assert invalid[0]["angle"] == angles[1]
    assert invalid[0]["error"] is not None


def test_all_malformed_retries_once_then_raises(tmp_path, monkeypatch):
    angles = arch.angles_for(3)
    call_count = [0]

    async def always_bad(*, prompt, options=None):
        call_count[0] += 1
        yield "not json"

    monkeypatch.setattr(arch, "query", always_bad)
    first = asyncio.run(arch.generate_candidates(tmp_path, "specs/x", angles))
    assert not any(c["valid"] for c in first)

    retries_used = 0
    candidates = first
    while not any(c["valid"] for c in candidates):
        if retries_used >= arch.MAX_MALFORMED_RETRIES:
            break
        retries_used += 1
        candidates = asyncio.run(arch.generate_candidates(tmp_path, "specs/x", angles))
    assert retries_used == arch.MAX_MALFORMED_RETRIES


# --- T034: comment format + budget -------------------------------------------

def _synthesized(plan="synth plan", tasks="synth tasks"):
    return {
        "plan_md": plan, "tasks_md": tasks, "adrs": [],
        "winner_index": 0, "grafted_from": [], "rationale": "because reasons",
    }


def _scores(n=1):
    return [
        {"candidate_index": i, "angle": f"a{i}", "coverage": {"SC-001": True, "SC-002": False},
         "internal_consistency": 3, "notes": ""}
        for i in range(n)
    ]


def test_post_stage_comment_format_and_budget(monkeypatch):
    posted = {}

    def fake_run(cmd, cwd=None):
        if cmd[:2] == ["gh", "pr"]:
            posted["body"] = cmd[cmd.index("--body") + 1]
            return ""
        raise AssertionError(f"unexpected _run call: {cmd}")

    monkeypatch.setattr(arch, "_run", fake_run)

    candidates = [
        {"index": 0, "angle": "a0", "plan_md": "p0", "tasks_md": "t0", "adrs": [], "valid": True},
    ]
    completeness = {"uncovered": [], "missed_angle": None, "note": "no additional angle was identified", "gap_found": False}

    body = arch.post_stage_comment(
        "owner/repo", "https://github.com/owner/repo/pull/1", 2,
        synthesized=_synthesized(), scores=_scores(1), candidates=candidates,
        completeness=completeness, delta="Revised after: fix it", sha="abc123",
    )

    marker_idx = body.find("<!-- architect-agent:stage attempt=2 spec=abc123 -->")
    delta_idx = body.find("Revised after: fix it")
    plan_idx = body.find("synth plan")
    rationale_idx = body.find("because reasons")
    coverage_idx = body.find("Coverage map")
    completeness_idx = body.find("no additional angle was identified")
    details_idx = body.find("<details>")

    assert marker_idx == 0
    assert -1 < marker_idx < delta_idx < plan_idx < rationale_idx < coverage_idx < completeness_idx < details_idx
    assert len(body) <= arch._COMMENT_LIMIT
    assert posted["body"] == body


def test_post_stage_comment_truncates_oversize_candidate(monkeypatch):
    def fake_run(cmd, cwd=None):
        return ""

    monkeypatch.setattr(arch, "_run", fake_run)

    candidates = [
        {"index": 0, "angle": "a0", "plan_md": "x" * 100000, "tasks_md": "t", "adrs": [], "valid": True},
    ]
    completeness = {"uncovered": [], "missed_angle": None, "note": "no additional angle was identified", "gap_found": False}
    body = arch.post_stage_comment(
        "owner/repo", "https://github.com/owner/repo/pull/1", 1,
        synthesized=_synthesized(), scores=_scores(1), candidates=candidates,
        completeness=completeness, delta=None, sha="abc123",
    )
    assert "…[truncated" in body
    assert "synth plan" in body
    assert len(body) <= arch._COMMENT_LIMIT


# --- T035: persist_synthesized -----------------------------------------------

def test_persist_synthesized_writes_only_synthesized(tmp_path):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)

    spec_dir = "specs/004-x"
    (checkout / spec_dir).mkdir(parents=True)
    (checkout / spec_dir / "plan.md").write_text("old plan")

    synthesized = {
        "plan_md": "new plan", "tasks_md": "new tasks",
        "adrs": [{"title": "Use X", "body": "because Y"}],
    }
    calls = []
    real_run = arch._run

    def spying_run(cmd, cwd=None):
        calls.append(cmd)
        return real_run(cmd, cwd=cwd)

    import unittest.mock
    with unittest.mock.patch.object(arch, "_run", spying_run):
        sha = arch.persist_synthesized(checkout, spec_dir, synthesized)

    assert (checkout / spec_dir / "plan.md").read_text() == "new plan"
    assert (checkout / spec_dir / "tasks.md").read_text() == "new tasks"
    adr_files = list((checkout / spec_dir).glob("ADR-*.md"))
    assert len(adr_files) == 1

    commit_calls = [c for c in calls if "commit" in c]
    assert commit_calls
    commit_argv = commit_calls[0]
    assert "-c" in commit_argv
    assert any(a.startswith("user.email=") for a in commit_argv)
    assert any(a.startswith("user.name=") for a in commit_argv)
    assert sha

    for path in (checkout / spec_dir).rglob("*"):
        if path.is_file():
            assert "candidate" not in path.name.lower()


# --- T036: idempotency --------------------------------------------------------

def test_run_architect_stage_idempotent_per_attempt(tmp_path, monkeypatch):
    async def failing_query(*, prompt, options=None):
        raise AssertionError("query() must not be called on an idempotent hit")
        yield  # pragma: no cover

    monkeypatch.setattr(arch, "query", failing_query)
    monkeypatch.setattr(arch, "_existing_stage_comment", lambda repo, pr_url, attempt: "existing body")

    result = asyncio.run(
        arch.run_architect_stage("owner/repo", "004-x", "https://github.com/owner/repo/pull/1", 2)
    )
    assert result == {"attempt": 2, "comment_body": "existing body", "idempotent_hit": True}
    assert set(result.keys()) == {"attempt", "comment_body", "idempotent_hit"}


# --- T037: scrub-window scope -------------------------------------------------

def test_run_architect_stage_scrub_window_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "the-token")
    events = []

    monkeypatch.setattr(arch, "_existing_stage_comment", lambda *a, **k: None)

    def fake_clone(repo, branch, spec_dir, work_root):
        checkout = Path(work_root) / "checkout"
        checkout.mkdir()
        subprocess.run(["git", "init", "-q", str(checkout)], check=True)
        (checkout / spec_dir).mkdir(parents=True)
        return checkout, checkout / spec_dir / "spec.md", os.environ.get("GH_TOKEN")

    monkeypatch.setattr(arch, "_clone_spec_branch", fake_clone)
    monkeypatch.setattr(arch, "_load_sc_ids", lambda p: SC_IDS)

    async def fake_query(*, prompt, options=None):
        events.append(("model_call", os.environ.get("GH_TOKEN")))
        if "coverage" in prompt.lower() and "candidate" in prompt.lower() and "plan_md" not in prompt:
            yield json.dumps({"scores": [
                {"coverage": {i: True for i, _ in SC_IDS}, "internal_consistency": 3}
                for _ in arch.angles_for(3)
            ]})
        elif "you are synthesizing" in prompt.lower():
            yield json.dumps({"plan_md": "p", "tasks_md": "t", "adrs": [], "grafted_from": []})
        elif "completeness critic" in prompt.lower():
            yield json.dumps({"uncovered": [], "missed_angle": None, "note": "no additional angle was identified"})
        else:
            yield _candidate_envelope()

    monkeypatch.setattr(arch, "query", fake_query)

    def fake_persist(checkout, spec_dir, synthesized):
        events.append(("persist", os.environ.get("GH_TOKEN")))
        return "sha123"

    def fake_push(checkout, branch, token=None):
        events.append(("push", os.environ.get("GH_TOKEN"), token))

    def fake_post(*args, **kwargs):
        events.append(("post", os.environ.get("GH_TOKEN")))
        return "posted body"

    monkeypatch.setattr(arch, "persist_synthesized", fake_persist)
    monkeypatch.setattr(arch, "push_synthesized", fake_push)
    monkeypatch.setattr(arch, "post_stage_comment", fake_post)
    monkeypatch.setattr(arch, "_run", lambda cmd, cwd=None: "sha123")

    asyncio.run(
        arch.run_architect_stage("owner/repo", "004-x", "https://github.com/owner/repo/pull/1", 1)
    )

    model_events = [e for e in events if e[0] == "model_call"]
    assert model_events and all(e[1] is None for e in model_events)

    persist_events = [e for e in events if e[0] == "persist"]
    assert persist_events and persist_events[0][1] == "the-token"

    push_events = [e for e in events if e[0] == "push"]
    assert push_events and push_events[0][1] == "the-token" and push_events[0][2] == "the-token"

    post_events = [e for e in events if e[0] == "post"]
    assert post_events and post_events[0][1] == "the-token"


# --- T038a/T038b: pick_winner ------------------------------------------------

def test_pick_winner_ordering_is_total():
    scores = [
        {"candidate_index": 0, "coverage": {"SC-001": True, "SC-002": False}, "internal_consistency": 5},
        {"candidate_index": 1, "coverage": {"SC-001": True, "SC-002": True}, "internal_consistency": 1},
    ]
    assert arch.pick_winner(scores) == 1  # coverage dominates

    scores = [
        {"candidate_index": 0, "coverage": {"SC-001": True, "SC-002": True}, "internal_consistency": 2},
        {"candidate_index": 1, "coverage": {"SC-001": True, "SC-002": True}, "internal_consistency": 4},
    ]
    assert arch.pick_winner(scores) == 1  # consistency breaks coverage tie

    scores = [
        {"candidate_index": 0, "coverage": {"SC-001": True}, "internal_consistency": 3},
        {"candidate_index": 1, "coverage": {"SC-001": True}, "internal_consistency": 3},
    ]
    assert arch.pick_winner(scores) == 0  # lowest index breaks full tie

    import random
    shuffled = list(scores)
    random.shuffle(shuffled)
    assert arch.pick_winner(shuffled) == arch.pick_winner(scores)


# --- T042a: delta line derivation --------------------------------------------

def test_delta_line_derivation():
    assert arch._derive_delta(1, None, False, {}, "sha1") is None
    assert arch._derive_delta(2, "please fix X", False, {}, "sha1").startswith("Revised after:")
    assert arch._derive_delta(2, None, True, {"note": "gap note"}, "sha1").startswith(
        "Re-synthesized after gap round:"
    )
    assert arch._derive_delta(2, None, False, {}, "sha1") == "Re-ran attempt 2 against spec sha1."


# --- T043: critic prompt independence ---------------------------------------

def test_check_completeness_prompt_independence(monkeypatch):
    envelope = json.dumps({"uncovered": [], "missed_angle": None, "note": "n/a"})
    fake = _make_query([envelope])
    monkeypatch.setattr(arch, "query", fake)

    synthesized = {"plan_md": "the synthesized plan text"}
    angles_tried = ["minimal-diff-first", "clean-architecture-first"]
    asyncio.run(arch.check_completeness(synthesized, SC_IDS, angles_tried))

    prompt = fake.calls[0]["prompt"]
    assert "the synthesized plan text" in prompt
    assert "SC-001" in prompt
    assert "minimal-diff-first" in prompt
    assert "rationale" not in prompt.lower()
    assert "aggregate" not in prompt.lower()


# --- T044: gap_found is derived, not trusted --------------------------------

def test_gap_found_is_derived_not_trusted(monkeypatch):
    envelope = json.dumps({"uncovered": [], "missed_angle": None, "note": "n"})
    monkeypatch.setattr(arch, "query", _make_query([envelope]))
    result = asyncio.run(arch.check_completeness({"plan_md": "p"}, SC_IDS, []))
    assert result["gap_found"] is False

    envelope2 = json.dumps({"uncovered": ["SC-002"], "missed_angle": None, "note": "n"})
    monkeypatch.setattr(arch, "query", _make_query([envelope2]))
    result2 = asyncio.run(arch.check_completeness({"plan_md": "p"}, SC_IDS, []))
    assert result2["gap_found"] is True

    envelope3 = json.dumps({"uncovered": ["SC-999"], "missed_angle": None, "note": "n"})
    monkeypatch.setattr(arch, "query", _make_query([envelope3]))
    with pytest.raises(ValueError):
        asyncio.run(arch.check_completeness({"plan_md": "p"}, SC_IDS, []))


# --- T045/T046/T047: gap round wiring (integration-style, mocked) ----------

def _wire_full_stage(monkeypatch, gap_response):
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setattr(arch, "_existing_stage_comment", lambda *a, **k: None)

    def fake_clone(repo, branch, spec_dir, work_root):
        checkout = Path(work_root) / "checkout"
        checkout.mkdir()
        subprocess.run(["git", "init", "-q", str(checkout)], check=True)
        (checkout / spec_dir).mkdir(parents=True)
        return checkout, checkout / spec_dir / "spec.md", "tok"

    monkeypatch.setattr(arch, "_clone_spec_branch", fake_clone)
    monkeypatch.setattr(arch, "_load_sc_ids", lambda p: SC_IDS)
    monkeypatch.setattr(arch, "persist_synthesized", lambda *a, **k: "sha")
    monkeypatch.setattr(arch, "push_synthesized", lambda *a, **k: None)
    monkeypatch.setattr(arch, "post_stage_comment", lambda *a, **k: "posted")
    monkeypatch.setattr(arch, "_run", lambda cmd, cwd=None: "sha123")

    call_log = []

    async def fake_query(*, prompt, options=None):
        if "you are one of several independent architects" in prompt.lower():
            call_log.append("candidate")
            yield _candidate_envelope()
        elif "you are an architect asked to fill one" in prompt.lower():
            call_log.append("gap_candidate")
            yield _candidate_envelope(angle="gap-angle")
        elif "you are judging a set of independently" in prompt.lower():
            call_log.append("score")
            n = prompt.count("--- Candidate")
            yield json.dumps({"scores": [
                {"coverage": {i: True for i, _ in SC_IDS}, "internal_consistency": 3}
                for _ in range(n)
            ]})
        elif "you are synthesizing exactly one" in prompt.lower():
            call_log.append("synthesize")
            yield json.dumps({"plan_md": "p", "tasks_md": "t", "adrs": [], "grafted_from": []})
        elif "you are an independent completeness critic" in prompt.lower():
            call_log.append("critic")
            yield gap_response
        else:
            raise AssertionError(f"unrecognized prompt: {prompt[:80]}")

    monkeypatch.setattr(arch, "query", fake_query)
    return call_log


def test_no_gap_path(monkeypatch):
    no_gap = json.dumps({"uncovered": [], "missed_angle": None, "note": "no additional angle was identified"})
    call_log = _wire_full_stage(monkeypatch, no_gap)

    result = asyncio.run(
        arch.run_architect_stage("owner/repo", "004-x", "https://github.com/owner/repo/pull/1", 1)
    )

    assert result["gap_round_ran"] is False
    assert call_log.count("candidate") == arch.candidate_count([i for i, _ in SC_IDS])
    assert call_log.count("gap_candidate") == 0
    assert result["completeness"]["note"] == "no additional angle was identified"
    assert result["plan_md"] == "p"


def test_gap_path_runs_exactly_one_extra_round(monkeypatch):
    gap = json.dumps({"uncovered": ["SC-003"], "missed_angle": "security-first", "note": "found a gap"})
    call_log = _wire_full_stage(monkeypatch, gap)

    result = asyncio.run(
        arch.run_architect_stage("owner/repo", "004-x", "https://github.com/owner/repo/pull/1", 1)
    )

    assert result["gap_round_ran"] is True
    assert call_log.count("gap_candidate") == 1
    assert call_log.count("critic") == 1
    assert call_log.count("synthesize") == 2
    assert call_log.count("score") == 2


def test_gap_candidate_sees_synthesized_plan(monkeypatch):
    fake = _make_query([_candidate_envelope(plan="the synthesized plan text here")])
    monkeypatch.setattr(arch, "query", fake)

    asyncio.run(
        arch.generate_candidate(
            Path("/tmp"), "specs/x", "gap-desc",
            gap="gap-desc", synthesized_plan={"plan_md": "the synthesized plan text here"},
        )
    )
    prompt = fake.calls[0]["prompt"]
    assert "gap-desc" in prompt
    assert "the synthesized plan text here" in prompt
