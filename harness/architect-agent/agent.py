"""Architect agent — fan-out, judge, and completeness-critic. One stage
entrypoint, `run_architect_stage()`, sequencing five independently
callable capability functions: fan out N candidate plans from distinct
architectural angles, score each for SC-NNN coverage plus a 1-5
internal-consistency rating, synthesize exactly one plan/tasks/ADR set
from a deterministically computed winner, run an independent
completeness-critic pass, and post one combined, idempotent-per-attempt
PR comment. See SKILL.md for the design source and this pass's
deviations.
"""
import asyncio
import contextlib
import importlib.util
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import braintrust
from claude_agent_sdk import ClaudeAgentOptions, query
from dotenv import load_dotenv


def _load_sibling(name: str, filename: str):
    """Load a module next to this file by path. The worker loads this
    agent.py by path, so its directory is not on sys.path and a plain
    `import seat_guard` would not resolve."""
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parent / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# specs/009: subscription-seat guard, byte-identical to swe-agent's copy.
seat_guard = _load_sibling("architect_agent_seat_guard", "seat_guard.py")
SeatExhausted = seat_guard.SeatExhausted
SeatInvalid = seat_guard.SeatInvalid

# Load this repo's own root .env (never the developer's shell profile),
# without overriding a value already present in the process environment.
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

BRAINTRUST_PROJECT = os.environ.get("BRAINTRUST_PROJECT", "agent-factory-pilot")

logger = braintrust.init_logger(project=BRAINTRUST_PROJECT)
braintrust.auto_instrument()

LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "http://localhost:4000")
LITELLM_API_KEY = os.environ.get("LITELLM_MASTER_KEY", "sk-local-master")

# repo/branch are caller-supplied, ultimately threaded into git/gh argv.
# Mirrors harness/pm-agent/agent.py::_REPO_RE/_BRANCH_RE exactly.
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./-]*$")

# Registry commits from this stage are attributed to the factory, not to
# whichever GH_TOKEN identity happens to be in the worker's env — mirrors
# orchestration/activities.py::_GIT_IDENTITY.
_GIT_IDENTITY = (
    "-c", "user.email=architect-agent@agentic-factory",
    "-c", "user.name=agentic-factory",
)

# --- Module constants (contracts/architect-agent-interface.md) -----------

MIN_CANDIDATES = 3
MAX_CANDIDATES = 6
MAX_MALFORMED_RETRIES = 1
_COMMENT_LIMIT = 60000

CANDIDATE_CONCURRENCY = 3
CANDIDATE_TIMEOUT_S = 600
MAX_PLAN_CHARS = 40000
MAX_TASKS_CHARS = 20000

ANGLES = [
    "minimal-diff-first",
    "clean-architecture-first",
    "risk/security-first",
    "test-and-observability-first",
    "data-and-contract-first",
    "operability-and-rollback-first",
]

MODEL = "claude-sonnet-5"


def _validate_repo(repo: str) -> None:
    if not _REPO_RE.match(repo):
        raise ValueError(f"Refusing to use unexpected repo value: {repo!r}")


def _validate_branch(branch: str) -> None:
    if not _BRANCH_RE.match(branch) or branch.startswith("-"):
        raise ValueError(f"Refusing to use unexpected branch value: {branch!r}")


def _scrubbed(
    error: subprocess.CalledProcessError, secret: str
) -> subprocess.CalledProcessError:
    """Copy of `error` with `secret` redacted everywhere it could surface."""

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


def _model_env(seat_token: str | None) -> dict[str, str]:
    """LiteLLM-routed by default (§3.4). A seat-backed run goes direct to
    Anthropic with the seat's OAuth token as its only credential — the
    documented §3.4 deviation for subscription seats (specs/009, research
    R4: LiteLLM can't pool OAuth tokens)."""
    if seat_token:
        return seat_guard.seat_options_env(seat_token)
    return {"ANTHROPIC_BASE_URL": LITELLM_BASE_URL, "ANTHROPIC_API_KEY": LITELLM_API_KEY}


def _judge_options(seat_token: str | None = None) -> ClaudeAgentOptions:
    """Options for the tool-less score/synthesis/critic calls."""
    return ClaudeAgentOptions(
        tools=[], setting_sources=[], permission_mode="default", model=MODEL,
        env=_model_env(seat_token),
    )


async def _model_text(
    prompt: str, options: ClaudeAgentOptions, usage: dict | None = None,
) -> str:
    """Run `query()` and return only the model's final text result. With
    `usage` (seat mode) the stream goes through seat_guard, which records
    the seat's last-seen usage there and raises SeatExhausted/SeatInvalid."""
    stream = (
        seat_guard.guarded_query(prompt, options, usage, query_fn=query)
        if usage is not None
        else query(prompt=prompt, options=options)
    )
    text: str | None = None
    async with contextlib.aclosing(stream) as messages:
        async for message in messages:
            if isinstance(message, str):
                text = message  # test doubles yield plain strings directly
            else:
                result = getattr(message, "result", None)
                if result is not None:
                    text = result
    if text is None:
        raise RuntimeError(f"Model call produced no usable text result for prompt: {prompt!r}")
    return text


def _parse_json_envelope(text: str) -> dict:
    """Extract and parse the single JSON object embedded in a model
    response (which may wrap it in prose or a fenced code block)."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in model response: {text!r}")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise ValueError(f"Model response is not valid JSON: {text!r}") from e


@contextlib.contextmanager
def _no_git_credentials():
    """Pop GH_TOKEN/GITHUB_TOKEN from the parent process's os.environ for
    the duration of the `with` block, restoring both on exit — including
    on the exception path. One window per stage, entered once, not once
    per model call: under `asyncio.gather`, a per-call pop/restore would
    let one candidate's `finally` hand a live token to a sibling still
    spawning (research.md Unknown 1).
    """
    saved_gh_token = os.environ.pop("GH_TOKEN", None)
    saved_github_token = os.environ.pop("GITHUB_TOKEN", None)
    try:
        yield
    finally:
        if saved_gh_token is not None:
            os.environ["GH_TOKEN"] = saved_gh_token
        if saved_github_token is not None:
            os.environ["GITHUB_TOKEN"] = saved_github_token


def _load_sc_ids(spec_path: Path) -> list[tuple[str, str]]:
    """Default `sc_loader` for `run_architect_stage()`: loads
    `eval/braintrust/eval.config.py` by path (its filename has dots, so a
    plain `import` can't reach it) and calls its
    `load_success_criteria_ids`. Loaded lazily, inside this function —
    `eval.config.py` does `import braintrust` at module scope, and a
    module-scope shim here would drag the eval layer's import into every
    architect import and test collection (research.md Unknown 2).
    """
    eval_config = importlib.util.spec_from_file_location(
        "eval_config",
        Path(__file__).resolve().parent.parent.parent / "eval" / "braintrust" / "eval.config.py",
    )
    assert eval_config is not None and eval_config.loader is not None
    module = importlib.util.module_from_spec(eval_config)
    eval_config.loader.exec_module(module)
    return module.load_success_criteria_ids(str(spec_path))


def _clone_spec_branch(
    repo: str, branch: str, spec_dir: str, work_root: str
) -> tuple[Path, Path, str | None]:
    """Shallow-clone `branch` of `repo` into `work_root`, then strip the
    embedded credential from the checkout before returning. Returns
    `(checkout, spec_path, token)`.

    `git remote set-url origin` (removing the credential) is
    security-critical, not tidiness: `git clone
    https://x-access-token:<token>@...` writes the token into the
    checkout's `.git/config` as the `origin` URL, and
    `credential.helper ""` does nothing about that — it only stops *new*
    prompts. Candidates are bound `Read` with `cwd=checkout`, and their
    `plan_md` is posted verbatim into a PR comment, so without this
    rewrite a candidate that reads `.git/config` publishes a GitHub App
    installation token (FR-015). This runs before the
    `_no_git_credentials()` window, since it needs the token.
    """
    token = os.environ.get("GH_TOKEN")
    credential = f"x-access-token:{token}@" if token else ""
    clone_url = f"https://{credential}github.com/{repo}.git"
    checkout = Path(work_root) / "checkout"
    try:
        _run(["git", "clone", "--depth", "1", "--branch", branch, clone_url, str(checkout)])
    except subprocess.CalledProcessError as e:
        if not token:
            raise
        raise _scrubbed(e, token) from None

    _run(["git", "remote", "set-url", "origin", f"https://github.com/{repo}.git"], cwd=checkout)
    _run(["git", "config", "--local", "credential.helper", ""], cwd=checkout)

    spec_path = checkout / spec_dir / "spec.md"
    if not spec_path.is_file():
        raise RuntimeError(
            f"No {spec_dir}/spec.md found on checked-out branch {branch!r} "
            f"of {repo} — pass spec_dir explicitly if this branch doesn't "
            "follow the specs/<branch>/ convention."
        )
    return checkout, spec_path, token


# --- User Story 1: fan-out -------------------------------------------------

CANDIDATE_PROMPT = """You are one of several independent architects, \
each asked to produce a candidate implementation plan for the same spec \
from your own distinct angle. You have no visibility into any other \
architect's plan — do not reference or assume one exists.

Your assigned angle: {angle}

Read {spec_dir}/spec.md in this checkout (you have Read/Grep/Glob only — \
you cannot execute anything or mutate this repository). Produce a \
complete implementation plan and task breakdown from your angle.

Respond with exactly one JSON object, nothing else, with this shape:
{{
  "angle": "{angle}",
  "plan_md": "<the full plan, as markdown>",
  "tasks_md": "<the full task breakdown, as markdown>",
  "adrs": [{{"title": "<ADR title>", "body": "<ADR body, as markdown>"}}]
}}

"adrs" may be an empty list if your angle needs no architecture decision \
records. Both "plan_md" and "tasks_md" must be non-empty."""

GAP_CANDIDATE_PROMPT = """You are an architect asked to fill one \
specific gap in an already-synthesized implementation plan. You are not \
proposing an alternative to the plan below — you are producing one \
targeted addition that slots into it.

Gap to address: {gap}

The existing synthesized plan:
--- SYNTHESIZED PLAN ---
{synthesized_plan}
--- END SYNTHESIZED PLAN ---

Read {spec_dir}/spec.md in this checkout (you have Read/Grep/Glob only — \
you cannot execute anything or mutate this repository).

Respond with exactly one JSON object, nothing else, with this shape:
{{
  "angle": "{gap}",
  "plan_md": "<a plan addressing the gap, as markdown>",
  "tasks_md": "<a task breakdown for the addition, as markdown>",
  "adrs": [{{"title": "<ADR title>", "body": "<ADR body, as markdown>"}}]
}}

"adrs" may be an empty list. Both "plan_md" and "tasks_md" must be \
non-empty."""


def _candidate_options(checkout: Path, seat_token: str | None = None) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        cwd=str(checkout),
        tools=["Read", "Grep", "Glob"],
        setting_sources=[],
        permission_mode="default",
        model=MODEL,
        env=_model_env(seat_token),
    )


async def generate_candidate(
    checkout: Path,
    spec_dir: str,
    angle: str,
    *,
    gap: str | None = None,
    synthesized_plan: dict | None = None,
    seat_token: str | None = None,
    usage: dict | None = None,
) -> dict:
    """Produce one Architect Candidate. Exactly one of "both `gap` and
    `synthesized_plan` set" (gap-targeted, FR-009) or "both `None`"
    (fan-out, FR-003) is legal — a partially-populated call is caller
    error, so a gap candidate cannot silently degrade into a blind one.
    """
    if (gap is None) != (synthesized_plan is None):
        raise ValueError(
            "generate_candidate() requires both gap and synthesized_plan "
            "set (gap mode) or both None (fan-out mode), got "
            f"gap={gap!r}, synthesized_plan={'<set>' if synthesized_plan else None!r}"
        )

    if gap is None:
        prompt = CANDIDATE_PROMPT.format(angle=angle, spec_dir=spec_dir)
    else:
        prompt = GAP_CANDIDATE_PROMPT.format(
            gap=gap,
            synthesized_plan=synthesized_plan.get("plan_md", ""),
            spec_dir=spec_dir,
        )

    options = _candidate_options(checkout, seat_token)

    result: dict = {"angle": angle, "valid": False, "plan_md": "", "tasks_md": "", "adrs": []}
    try:
        text = await _model_text(prompt, options, usage)
        envelope = _parse_json_envelope(text)
        plan_md = (envelope.get("plan_md") or "").strip()
        tasks_md = (envelope.get("tasks_md") or "").strip()
        adrs = envelope.get("adrs") or []
        if not plan_md or not tasks_md:
            result["error"] = "empty plan_md or tasks_md"
        elif len(plan_md) > MAX_PLAN_CHARS:
            result["error"] = f"plan_md exceeds MAX_PLAN_CHARS ({len(plan_md)} > {MAX_PLAN_CHARS})"
        elif len(tasks_md) > MAX_TASKS_CHARS:
            result["error"] = f"tasks_md exceeds MAX_TASKS_CHARS ({len(tasks_md)} > {MAX_TASKS_CHARS})"
        else:
            result.update(
                {"valid": True, "error": None, "plan_md": plan_md, "tasks_md": tasks_md, "adrs": adrs}
            )
    # SeatExhausted/SeatInvalid subclass Exception directly, so they pass
    # through here untouched (specs/009 FR-011).
    except (ValueError, RuntimeError) as e:
        result["error"] = str(e)

    return result


def candidate_count(sc_ids: list, n_override: int | None = None) -> int:
    """FR-002 / SC-005. Pure; no I/O, no model call."""
    if n_override is not None:
        return max(1, min(n_override, MAX_CANDIDATES))
    return min(MAX_CANDIDATES, MIN_CANDIDATES + max(0, (len(sc_ids) - 5) // 3))


def angles_for(n: int) -> list[str]:
    if n > MAX_CANDIDATES:
        raise ValueError(f"n={n} exceeds MAX_CANDIDATES={MAX_CANDIDATES} — no curated angle left")
    return ANGLES[:n]


async def generate_candidates(
    checkout: Path, spec_dir: str, angles: list[str],
    *, seat_token: str | None = None, usage: dict | None = None,
) -> list[dict]:
    """An `asyncio.TaskGroup` over `generate_candidate()` in fan-out mode,
    one call per angle, bounded by `CANDIDATE_CONCURRENCY` in-flight CLI
    subprocesses and a `CANDIDATE_TIMEOUT_S` per-call timeout. Must be
    called inside the stage's single `_no_git_credentials()` window —
    this function does not manipulate `os.environ` itself.

    Any error escaping a candidate cancels its siblings (unlike the old
    `asyncio.gather`, which left them running). For a seat outcome that is
    the point (specs/009 FR-013): siblings would only keep spending an
    exhausted or dead seat, and the whole stage re-runs on the next seat.
    """
    semaphore = asyncio.Semaphore(CANDIDATE_CONCURRENCY)

    async def _bounded(angle: str) -> dict:
        async with semaphore:
            try:
                return await asyncio.wait_for(
                    generate_candidate(
                        checkout, spec_dir, angle, seat_token=seat_token, usage=usage,
                    ),
                    CANDIDATE_TIMEOUT_S,
                )
            except TimeoutError:
                return {
                    "angle": angle, "valid": False, "error": "timeout",
                    "plan_md": "", "tasks_md": "", "adrs": [],
                }

    try:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(_bounded(angle)) for angle in angles]
    except BaseExceptionGroup as group_error:
        raise _unwrap_fanout_error(group_error) from None
    results = [task.result() for task in tasks]
    for index, result in enumerate(results):
        result["index"] = index
    return results


def _unwrap_fanout_error(group_error: BaseExceptionGroup) -> BaseException:
    """The one exception a fan-out failure surfaces as, never the group (whose
    "unhandled errors in a TaskGroup" text would hide the cause): a seat
    outcome first (SeatInvalid before SeatExhausted — a dead token is the
    more definite verdict), else the first error, as `asyncio.gather` did.
    The others are kept as notes on it."""
    errors = group_error.exceptions
    chosen = next(
        (e for kind in (SeatInvalid, SeatExhausted) for e in errors if isinstance(e, kind)),
        errors[0],
    )
    for other in errors:
        if other is not chosen:
            chosen.add_note(f"also raised by a sibling candidate: {type(other).__name__}: {other}")
    return chosen


# --- User Story 2: score, synthesize, persist, post -----------------------

SCORING_PROMPT = """You are judging a set of independently produced \
candidate implementation plans against a spec's success criteria.

Success criteria:
{criteria}

Candidates (in randomized order — do not infer anything from this order):
{candidates}

For each candidate, determine:
- coverage: for every success-criterion id listed above, true if this
  candidate's plan addresses it, false otherwise. Every id above must
  appear as a key — do not invent ids and do not omit any.
- internal_consistency: an integer 1-5 rating of how internally
  consistent and coherent this candidate's plan and tasks are with each
  other (1 = incoherent, 5 = fully consistent).
- notes: brief free-form reasoning for this candidate only.

Respond with exactly one JSON object, nothing else, with this shape:
{{
  "scores": [
    {{"candidate_label": "<label>", "coverage": {{"SC-001": true, ...}}, \
"internal_consistency": 3, "notes": "..."}}
  ]
}}"""

SYNTHESIS_PROMPT = """You are synthesizing exactly one implementation \
plan from a set of independently produced candidates and their \
validated scores. Candidate {winner_index} was computed (not chosen by \
you) as the strongest by coverage and consistency — use it as your \
primary basis, grafting in specific ideas from other candidates where \
they clearly improve on it.

Candidates:
{candidates}

Validated scores (coverage map and 1-5 consistency ratings — not prose):
{scores}
{feedback_section}
Respond with exactly one JSON object, nothing else, with this shape:
{{
  "plan_md": "<the synthesized plan, as markdown>",
  "tasks_md": "<the synthesized task breakdown, as markdown>",
  "adrs": [{{"title": "...", "body": "..."}}],
  "grafted_from": [<candidate indices whose ideas were pulled in>],
  "rationale": "<why this synthesis, referencing the winner and any grafts>"
}}"""

CRITIC_PROMPT = """You are an independent completeness critic reviewing \
an already-synthesized implementation plan. You have not seen how it was \
produced, and you should not defer to it — determine independently \
whether it addresses every success criterion, and whether any \
reasonable architectural angle was missed.

Success criteria:
{criteria}

Angles already tried by the candidate panel: {angles_tried}

The synthesized plan:
{plan_md}

Respond with exactly one JSON object, nothing else, with this shape:
{{
  "uncovered": ["<SC-NNN ids this plan does not address>"],
  "missed_angle": "<a specific architectural angle none of the tried \
angles covered, or null if you found none>",
  "note": "<a short human-facing summary of this assessment>"
}}"""


def _format_criteria(sc_ids: list[tuple[str, str]]) -> str:
    return "\n".join(f"- {id_}: {text}" for id_, text in sc_ids)


def _format_candidates_for_prompt(candidates: list[dict], *, labeled: bool = False) -> str:
    parts = []
    for c in candidates:
        label = f"Candidate {c['index']}" if not labeled else f"Candidate (label {c.get('_label')})"
        adrs = "\n".join(f"  ADR: {a['title']}\n{a['body']}" for a in c.get("adrs", []))
        parts.append(
            f"--- {label} (angle: {c['angle']}) ---\n"
            f"PLAN:\n{c['plan_md']}\n\nTASKS:\n{c['tasks_md']}\n{adrs}"
        )
    return "\n\n".join(parts)


async def score_candidates(
    candidates: list[dict], sc_ids: list[tuple[str, str]],
    *, seat_token: str | None = None, usage: dict | None = None,
) -> list[dict]:
    """FR-005. One model call over all valid candidates. Strict, total
    Python validation of the returned coverage/consistency structure.
    Candidate presentation order is randomised to mitigate position bias;
    the returned list stays in candidate-index order.
    """
    import random

    id_set = {id_ for id_, _ in sc_ids}
    shuffled = list(candidates)
    random.shuffle(shuffled)
    for i, c in enumerate(shuffled):
        c["_label"] = i

    prompt = SCORING_PROMPT.format(
        criteria=_format_criteria(sc_ids),
        candidates=_format_candidates_for_prompt(shuffled, labeled=True),
    )
    text = await _model_text(prompt, _judge_options(seat_token), usage)
    envelope = _parse_json_envelope(text)

    raw_scores = envelope.get("scores") or []
    if len(raw_scores) != len(candidates):
        raise ValueError(
            f"Scoring returned {len(raw_scores)} scores for {len(candidates)} candidates"
        )

    scores_by_index: dict[int, dict] = {}
    for i, raw in enumerate(raw_scores):
        # Map back by position in the (label-order) response, since the
        # model echoes candidates in the order it was given them.
        candidate = shuffled[i]
        coverage = raw.get("coverage")
        if not isinstance(coverage, dict) or set(coverage.keys()) != id_set:
            raise ValueError(
                f"Candidate {candidate['index']}'s coverage keys {set((coverage or {}).keys())} "
                f"do not exactly match the SC-NNN id set {id_set}"
            )
        consistency = raw.get("internal_consistency")
        if not isinstance(consistency, int) or isinstance(consistency, bool) or not (1 <= consistency <= 5):
            raise ValueError(
                f"Candidate {candidate['index']}'s internal_consistency {consistency!r} "
                "is not an int in 1..5"
            )
        scores_by_index[candidate["index"]] = {
            "candidate_index": candidate["index"],
            "angle": candidate["angle"],
            "coverage": dict(coverage),
            "internal_consistency": consistency,
            "notes": raw.get("notes", ""),
        }

    return [scores_by_index[c["index"]] for c in candidates]


def pick_winner(scores: list[dict]) -> int:
    """FR-005a. Pure Python, no model call. Highest coverage-true count,
    then highest internal_consistency, then lowest candidate_index."""

    def key(score: dict) -> tuple[int, int, int]:
        true_count = sum(1 for v in score["coverage"].values() if v)
        return (-true_count, -score["internal_consistency"], score["candidate_index"])

    return min(scores, key=key)["candidate_index"]


async def synthesize(
    candidates: list[dict], scores: list[dict], winner_index: int, feedback: str | None = None,
    *, seat_token: str | None = None, usage: dict | None = None,
) -> dict:
    """FR-004, FR-005a. One model call, distinct from `score_candidates()`.
    Returns exactly one Synthesis Result or raises."""
    valid_indices = {c["index"] for c in candidates}

    feedback_section = ""
    if feedback:
        feedback_section = (
            f"\nThis is a re-synthesis after prior human feedback:\n{feedback}\n"
        )

    prompt = SYNTHESIS_PROMPT.format(
        winner_index=winner_index,
        candidates=_format_candidates_for_prompt(candidates),
        scores=json.dumps(
            [
                {"candidate_index": s["candidate_index"], "coverage": s["coverage"],
                 "internal_consistency": s["internal_consistency"]}
                for s in scores
            ],
            indent=2,
        ),
        feedback_section=feedback_section,
    )
    text = await _model_text(prompt, _judge_options(seat_token), usage)
    envelope = _parse_json_envelope(text)

    plan_md = (envelope.get("plan_md") or "").strip()
    tasks_md = (envelope.get("tasks_md") or "").strip()
    if not plan_md or not tasks_md:
        raise ValueError("Synthesis returned empty plan_md or tasks_md")

    grafted_from = envelope.get("grafted_from") or []
    for idx in grafted_from:
        if idx not in valid_indices:
            raise ValueError(f"Synthesis grafted_from references invalid candidate index {idx!r}")

    return {
        "plan_md": plan_md,
        "tasks_md": tasks_md,
        "adrs": envelope.get("adrs") or [],
        "winner_index": winner_index,
        "grafted_from": list(grafted_from),
        "rationale": envelope.get("rationale", ""),
    }


async def check_completeness(
    synthesized: dict, sc_ids: list[tuple[str, str]], angles_tried: list[str],
    *, seat_token: str | None = None, usage: dict | None = None,
) -> dict:
    """FR-007a, FR-007b. One model call with a fresh context, withholding
    the judge's rationale, the score records, and every candidate's plan
    text. `gap_found` is derived in Python, never taken from the model's
    own boolean.
    """
    id_set = {id_ for id_, _ in sc_ids}
    prompt = CRITIC_PROMPT.format(
        criteria=_format_criteria(sc_ids),
        angles_tried=", ".join(angles_tried),
        plan_md=synthesized["plan_md"],
    )
    text = await _model_text(prompt, _judge_options(seat_token), usage)
    envelope = _parse_json_envelope(text)

    uncovered = envelope.get("uncovered") or []
    for id_ in uncovered:
        if id_ not in id_set:
            raise ValueError(f"check_completeness's uncovered id {id_!r} is not in the SC-NNN id set")

    missed_angle = envelope.get("missed_angle")
    note = envelope.get("note", "")
    if missed_angle is None:
        note = note or "No additional angle was identified."

    return {
        "uncovered": list(uncovered),
        "missed_angle": missed_angle,
        "note": note,
        "gap_found": bool(uncovered) or missed_angle is not None,
    }


def persist_synthesized(checkout: Path, spec_dir: str, synthesized: dict) -> str:
    """FR-011. Pure subprocess/filesystem code — no model call. Writes
    plan.md, tasks.md, and one ADR-NNN-<slug>.md per ADR, then makes one
    commit with an explicit committer identity (this runs code-side on a
    worker host that may have no global git config). Returns the new
    commit SHA.
    """
    target_dir = checkout / spec_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "plan.md").write_text(synthesized["plan_md"])
    (target_dir / "tasks.md").write_text(synthesized["tasks_md"])

    for i, adr in enumerate(synthesized.get("adrs") or [], start=1):
        slug = re.sub(r"[^a-z0-9]+", "-", adr["title"].lower()).strip("-")
        (target_dir / f"ADR-{i:03d}-{slug}.md").write_text(adr["body"])

    _run(["git", "add", "-A"], cwd=checkout)
    _run(
        ["git", *_GIT_IDENTITY, "commit", "-m", "architect-agent: synthesized plan"],
        cwd=checkout,
    )
    return _run(["git", "rev-parse", "HEAD"], cwd=checkout)


def push_synthesized(checkout: Path, branch: str, token: str | None = None) -> None:
    """Pushes `branch` from the clone. `_clone_spec_branch` stripped the
    credential from `origin`, so this builds the credentialed URL in argv
    rather than relying on the remote — the credentialed URL never goes
    back into `.git/config`.
    """
    if token:
        remote = _run(["git", "remote", "get-url", "origin"], cwd=checkout)
        repo_url = remote.split("github.com/", 1)[-1]
        push_url = f"https://x-access-token:{token}@github.com/{repo_url}"
        try:
            _run(["git", "push", push_url, f"HEAD:refs/heads/{branch}"], cwd=checkout)
        except subprocess.CalledProcessError as e:
            raise _scrubbed(e, token) from None
    else:
        _run(["git", "push", "origin", f"HEAD:refs/heads/{branch}"], cwd=checkout)


def _existing_stage_comment(repo: str, pr_url: str, attempt: int) -> str | None:
    marker = f"<!-- architect-agent:stage attempt={attempt} "
    raw = _run(["gh", "pr", "view", pr_url, "--repo", repo, "--json", "comments"])
    for comment in json.loads(raw).get("comments", []):
        body = comment.get("body", "")
        if body.startswith(marker):
            return body
    return None


def post_stage_comment(
    repo: str,
    pr_url: str,
    attempt: int,
    *,
    synthesized: dict,
    scores: list[dict],
    candidates: list[dict],
    completeness: dict,
    delta: str | None,
    sha: str,
) -> str:
    """FR-006, FR-014. Assembles the body in data-model.md's fixed
    section order, honours the `_COMMENT_LIMIT` size budget, and prefixes
    the hidden idempotency marker.
    """
    marker = f"<!-- architect-agent:stage attempt={attempt} spec={sha} -->"

    sections: list[str] = [marker]
    if delta is not None:
        sections.append(f"**Delta:** {delta}")

    sections.append(f"## Synthesized plan\n\n{synthesized['plan_md']}")
    sections.append(f"## Synthesized tasks\n\n{synthesized['tasks_md']}")

    grafted = ", ".join(str(i) for i in synthesized.get("grafted_from", [])) or "none"
    sections.append(
        f"## Judge rationale\n\nWinner: candidate {synthesized['winner_index']}. "
        f"Grafted from: {grafted}.\n\n{synthesized['rationale']}"
    )

    header = "| Criterion | " + " | ".join(f"C{s['candidate_index']}" for s in scores) + " |"
    sep = "| --- | " + " | ".join("---" for _ in scores) + " |"
    all_ids = sorted({id_ for s in scores for id_ in s["coverage"]})
    rows = [
        "| " + id_ + " | " + " | ".join("✅" if s["coverage"].get(id_) else "❌" for s in scores) + " |"
        for id_ in all_ids
    ]
    coverage_table = "\n".join([header, sep, *rows])

    completeness_note = f"## Completeness check\n\n{completeness['note']}"

    invalid = [c for c in candidates if not c.get("valid")]
    invalid_section = ""
    if invalid:
        lines = [f"- Candidate {c['index']} ({c['angle']}): {c.get('error')}" for c in invalid]
        invalid_section = "## Invalid candidates\n\n" + "\n".join(lines)

    fixed_sections = [s for s in [
        "\n\n".join(sections),
        "## Coverage map\n\n" + coverage_table,
        completeness_note,
        invalid_section,
    ] if s]

    fixed_body = "\n\n".join(fixed_sections)

    valid_candidates = [c for c in candidates if c.get("valid")]
    if valid_candidates and len(fixed_body) < _COMMENT_LIMIT:
        # Reserve room for each block's own markup and truncation notice so
        # the assembled total actually lands under _COMMENT_LIMIT, rather
        # than overshooting by exactly that overhead and falling through
        # to the last-resort branch below (which trims the wrong section).
        notice = f"\n\n…[truncated — full candidate text in the Braintrust span for attempt {attempt}]"
        overhead = len(notice) + len("<details><summary>Candidate  ()</summary>\n\n\n\n</details>") + 40
        remaining = _COMMENT_LIMIT - len(fixed_body)
        share = max(0, remaining // max(1, len(valid_candidates)) - overhead)
        details_blocks = []
        for c in valid_candidates:
            content = f"### Plan\n{c['plan_md']}\n\n### Tasks\n{c['tasks_md']}"
            if len(content) > share:
                content = content[:share] + notice
            details_blocks.append(
                f"<details><summary>Candidate {c['index']} ({c['angle']})</summary>\n\n{content}\n\n</details>"
            )
        details = "\n\n".join(details_blocks)
        body = fixed_body + "\n\n" + details
    elif valid_candidates:
        body = fixed_body + "\n\n_Candidate details omitted — sections 1-7 alone exceed the comment size budget._"
    else:
        body = fixed_body

    if len(body) > _COMMENT_LIMIT:
        # Last resort: truncate the synthesized plan/tasks section inline,
        # pointing at the committed copy — by this point the full text is
        # already on the branch (persist_synthesized ran before this).
        overage = len(body) - _COMMENT_LIMIT
        truncated_intro = "\n\n".join(sections)
        pointer = f"\n\n…[truncated — full plan committed at {sha} in this branch's spec dir]"
        keep = max(0, len(truncated_intro) - overage - len(pointer))
        truncated_intro = truncated_intro[:keep] + pointer
        rest = "\n\n".join([
            "## Coverage map\n\n" + coverage_table,
            completeness_note,
            invalid_section,
        ])
        body = truncated_intro + "\n\n" + rest

    _run(["gh", "pr", "comment", pr_url, "--repo", repo, "--body", body])
    return body


def _derive_delta(
    attempt: int, feedback: str | None, gap_round_ran: bool, completeness: dict, sha: str
) -> str | None:
    if attempt == 1:
        return None
    if feedback is not None:
        first_line = feedback.strip().splitlines()[0][:200] if feedback.strip() else ""
        return f"Revised after: {first_line}"
    if gap_round_ran:
        return f"Re-synthesized after gap round: {completeness.get('note', '')[:200]}"
    return f"Re-ran attempt {attempt} against spec {sha}."


async def run_architect_stage(
    repo: str,
    branch: str,
    pr_url: str,
    attempt: int,
    feedback: str | None = None,
    spec_dir: str | None = None,
    n_candidates: int | None = None,
    push: bool = True,
    sc_loader=None,
    seat_token: str | None = None,
) -> dict:
    """The stage entrypoint. See
    contracts/architect-agent-interface.md for the full sequence.

    `seat_token` (specs/009): run every model call on that subscription
    seat, direct to Anthropic. A seat outcome raises SeatExhausted /
    SeatInvalid before anything is persisted, pushed or posted; on success
    the result carries the seat's last-seen usage under `_seat_usage`."""
    _validate_repo(repo)
    _validate_branch(branch)
    if attempt < 1:
        raise ValueError(f"attempt must be >= 1, got {attempt!r}")
    spec_dir = spec_dir or f"specs/{branch}"
    sc_loader = sc_loader or _load_sc_ids

    existing = _existing_stage_comment(repo, pr_url, attempt)
    if existing is not None:
        return {"attempt": attempt, "comment_body": existing, "idempotent_hit": True}

    with tempfile.TemporaryDirectory() as work_root:
        checkout, spec_path, token = _clone_spec_branch(repo, branch, spec_dir, work_root)
        sc_ids = sc_loader(spec_path)
        if not sc_ids:
            raise ValueError(f"No SC-NNN success criteria found in {spec_path}")

        malformed_retries_used = 0
        gap_round_ran = False
        # Seat mode only: shared by every model call of this stage, so it
        # ends holding the seat's last-seen usage (seat_guard updates it).
        usage: dict | None = {} if seat_token else None
        seat = {"seat_token": seat_token, "usage": usage}

        with _no_git_credentials():
            n = candidate_count([id_ for id_, _ in sc_ids], n_override=n_candidates)
            angles = angles_for(n)
            candidates = await generate_candidates(checkout, spec_dir, angles, **seat)

            while not any(c["valid"] for c in candidates):
                if malformed_retries_used >= MAX_MALFORMED_RETRIES:
                    raise RuntimeError(
                        f"All {len(candidates)} candidates were malformed after "
                        f"{malformed_retries_used} retries"
                    )
                malformed_retries_used += 1
                candidates = await generate_candidates(checkout, spec_dir, angles, **seat)

            valid_candidates = [c for c in candidates if c["valid"]]
            scores = await score_candidates(valid_candidates, sc_ids, **seat)
            winner_index = pick_winner(scores)
            synthesized = await synthesize(
                valid_candidates, scores, winner_index, feedback, **seat,
            )

            completeness = await check_completeness(
                synthesized, sc_ids, [c["angle"] for c in valid_candidates], **seat,
            )

            if completeness["gap_found"] and not gap_round_ran:
                gap_text = completeness["missed_angle"] or ", ".join(completeness["uncovered"])
                gap_candidate = await generate_candidate(
                    checkout, spec_dir, gap_text, gap=gap_text, synthesized_plan=synthesized,
                    **seat,
                )
                gap_candidate["index"] = len(candidates)
                candidates = candidates + [gap_candidate]
                gap_round_ran = True

                if gap_candidate["valid"]:
                    valid_candidates = [c for c in candidates if c["valid"]]
                    scores = await score_candidates(valid_candidates, sc_ids, **seat)
                    winner_index = pick_winner(scores)
                    synthesized = await synthesize(
                        valid_candidates, scores, winner_index, feedback, **seat,
                    )

        persist_synthesized(checkout, spec_dir, synthesized)
        commit_sha = _run(["git", "rev-parse", "HEAD"], cwd=checkout)
        if push:
            push_synthesized(checkout, branch, token)

        delta = _derive_delta(attempt, feedback, gap_round_ran, completeness, commit_sha)
        comment_body = post_stage_comment(
            repo, pr_url, attempt,
            synthesized=synthesized, scores=scores, candidates=candidates,
            completeness=completeness, delta=delta, sha=commit_sha,
        )

    invalid_candidates = [
        {"angle": c["angle"], "error": c.get("error")} for c in candidates if not c["valid"]
    ]

    result = {
        "attempt": attempt,
        "plan_md": synthesized["plan_md"],
        "tasks_md": synthesized["tasks_md"],
        "adrs": synthesized["adrs"],
        "winner_index": synthesized["winner_index"],
        "grafted_from": synthesized["grafted_from"],
        "rationale": synthesized["rationale"],
        "scores": scores,
        "completeness": completeness,
        "gap_round_ran": gap_round_ran,
        "invalid_candidates": invalid_candidates,
        "malformed_retries_used": malformed_retries_used,
        "commit_sha": commit_sha,
        "comment_body": comment_body,
    }
    if usage is not None:
        result["_seat_usage"] = usage
    return result


if __name__ == "__main__":
    import sys

    async def _main() -> None:
        cmd = sys.argv[1]
        if cmd == "architect-stage":
            repo, branch, pr_url, attempt = sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])
            feedback = sys.argv[6] if len(sys.argv) > 6 else None
            print(await run_architect_stage(repo, branch, pr_url, attempt, feedback))
        else:
            raise SystemExit(f"Unknown command: {cmd!r} (expected architect-stage)")

    asyncio.run(_main())
    logger.flush()
