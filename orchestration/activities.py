"""Temporal activities (§3.5) wrapping the SWE agent (Harness/Runtime, §3.2),
the Eval-Gate (§3.6), and Register/Deploy (§3.7).
"""
import importlib.util
import json
import os
import re
import shlex
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import asyncio

import yaml
from e2b import AsyncSandbox
from temporalio import activity
from temporalio.exceptions import ApplicationError

# Mirrors harness/swe-agent/agent.py's own _REPO_RE/_BRANCH_RE: repo/branch
# are workflow inputs threaded into a shell command run inside the sandbox
# (`shlex.join`), so they must be rejected here too before ever reaching a
# shell — this is a shell-injection surface that the host argv-list
# subprocess calls in agent.py don't have.
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./-]*$")

# E2B template built from sandbox/swe-agent/Dockerfile (§3.3); id is
# sandbox/swe-agent/e2b.toml's `template_id`.
_SANDBOX_TEMPLATE = "swe-agent-sandbox"
_SANDBOX_TIMEOUT_SECONDS = 900

# Deterministic head branches, so a replayed/retried activity finds its own
# already-open PR (see _open_factory_pr) instead of stacking duplicates.
_REGISTRY_BRANCH_PREFIX = "registry/promote-"
_PROMOTE_BRANCH_PREFIX = "registry/promote-active-"

# Registry commits are attributed to the factory, not to whichever GH_TOKEN
# identity happens to be in the worker's env.
_GIT_IDENTITY = (
    "-c", "user.email=swe-agent@agentic-factory",
    "-c", "user.name=agentic-factory",
)


def _validate_target(repo: str, branch: str) -> None:
    if not _REPO_RE.match(repo):
        raise ValueError(f"Refusing to use unexpected repo value: {repo!r}")
    if not _BRANCH_RE.match(branch) or branch.startswith("-"):
        raise ValueError(f"Refusing to use unexpected branch value: {branch!r}")


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"{' '.join(cmd)} failed ({result.returncode}): "
            f"{result.stderr or result.stdout}"
        )
    return result.stdout.strip()


def _clone_url(repo: str) -> str:
    token = os.environ.get("GH_TOKEN")
    credential = f"x-access-token:{token}@" if token else ""
    return f"https://{credential}github.com/{repo}.git"


@activity.defn
async def run_swe_agent_activity(repo: str, branch: str, feedback: str | None = None) -> str:
    """Build + Sandbox Test collapsed (§3.2 + §3.3). Not idempotent —
    may already have pushed/opened a PR on partial failure.
    Workflow sets maximum_attempts=1."""
    _validate_target(repo, branch)

    sandbox = await AsyncSandbox.create(
        template=_SANDBOX_TEMPLATE,
        timeout=_SANDBOX_TIMEOUT_SECONDS,
        envs={
            "ANTHROPIC_PLATFORM_API_KEY": os.environ["ANTHROPIC_PLATFORM_API_KEY"],
            "GH_TOKEN": os.environ["GH_TOKEN"],
        },
    )
    try:
        argv = ["python3", "/app/agent.py", repo, branch]
        if feedback:
            argv.append(feedback)
        result = await sandbox.commands.run(shlex.join(argv))
        if result.exit_code != 0:
            raise RuntimeError(
                f"sandbox run failed ({result.exit_code}): "
                f"{result.stderr or result.stdout}"
            )
        return result.stdout.strip().splitlines()[-1]  # agent.py prints PR url last
    finally:
        await sandbox.kill()


def _load_module_by_path(name: str, path: Path) -> ModuleType:
    """Import a module the normal `import` statement can't reach — here a
    filename with dots in it (`eval.config.py`)."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_eval_config = _load_module_by_path(
    "eval_config",
    Path(__file__).resolve().parent.parent / "eval" / "braintrust" / "eval.config.py",
)

_architect_agent = _load_module_by_path(
    "architect_agent",
    Path(__file__).resolve().parent.parent / "harness" / "architect-agent" / "agent.py",
)

# Coarse heartbeat for architect_stage_activity: run_architect_stage() has no
# internal heartbeat hook (it's one in-process call, not a sandboxed run), so
# this timer is the only way Temporal can tell a slow N-candidate fan-out
# apart from a hung one.
_HEARTBEAT_INTERVAL_SECONDS = 30


@activity.defn
async def eval_gate_activity(repo: str, branch: str, sandbox_trace: dict) -> dict:
    """Eval-Gate (§3.6). Read-only — clones just enough of `branch` to read
    its spec.md, no push side effects. Retryable (transient Braintrust API
    failures are the only expected failure mode)."""
    _validate_target(repo, branch)
    with tempfile.TemporaryDirectory() as td:
        checkout = Path(td)
        _run(
            [
                "git", "clone", "--depth", "1", "--branch", branch,
                _clone_url(repo), str(checkout),
            ]
        )
        specs = sorted(checkout.glob("specs/*/spec.md"))
        if not specs:
            return {
                "passed": False,
                "criteria": [],
                "reason": "no specs/*/spec.md found on branch",
            }
        return _eval_config.run_eval(str(specs[0]), sandbox_trace)


@activity.defn
async def ensure_target_pr_activity(repo: str, branch: str) -> str:
    """Opens (or finds) the PR on the *target* repo (`repo`) that the
    architect stage and Build both need to agree on one `pr_url` for.
    Precondition: `branch` already exists and is pushed on `repo` — Spec
    Intake (§3.1, manual today) is what puts specs/*/spec.md there.
    Idempotent — safe to retry, and safe for harness/swe-agent/agent.py's
    later `gh pr create` to run again afterward, since that call already
    tolerates an "already exists" failure and reuses the PR."""
    _validate_target(repo, branch)
    existing = _open_pr_url(repo, branch)
    if existing:
        return existing
    try:
        return _run(
            [
                "gh", "pr", "create",
                "--repo", repo,
                "--head", branch,
                "--title", f"[{branch}] automated pipeline run",
                "--body", "Opened by ensure_target_pr_activity ahead of the architect stage.",
            ]
        )
    except RuntimeError:
        existing = _open_pr_url(repo, branch)
        if existing:
            return existing
        raise


@activity.defn
async def architect_stage_activity(
    repo: str, branch: str, pr_url: str, attempt: int, feedback: str | None = None,
) -> dict:
    """Architect fan-out/judge stage (004), run in-process — no E2B sandbox
    for this stage, per its own design carve-out (§6.1). Maps the two
    exception cases run_architect_stage() can raise onto typed,
    non-retryable ApplicationErrors so the workflow can branch on `.type`
    instead of string-matching a caught exception itself:
      - MalformedRetriesExhausted: all fan-out candidates came back
        malformed even after a retry (CO-3) — must NOT charge the caller's
        plan-attempt budget.
      - PlanDeterministicFailure: any other ValueError/RuntimeError from
        the stage (CO-2) — the caller charges its plan-attempt budget.
    Anything else (e.g. a transient git/gh CalledProcessError) propagates
    raw for the workflow's _TRANSIENT_RETRY policy to retry."""
    _validate_target(repo, branch)

    async def _heartbeat() -> None:
        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL_SECONDS)
            activity.heartbeat()

    heartbeat_task = asyncio.ensure_future(_heartbeat())
    try:
        return await _architect_agent.run_architect_stage(
            repo, branch, pr_url, attempt, feedback=feedback,
        )
    except RuntimeError as e:
        if "malformed" in str(e).lower():
            raise ApplicationError(
                str(e), type="MalformedRetriesExhausted", non_retryable=True
            ) from e
        raise ApplicationError(
            str(e), type="PlanDeterministicFailure", non_retryable=True
        ) from e
    except ValueError as e:
        raise ApplicationError(
            str(e), type="PlanDeterministicFailure", non_retryable=True
        ) from e
    finally:
        heartbeat_task.cancel()


def _factory_repo() -> str:
    return os.environ.get("FACTORY_REPO") or _run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"]
    )


def _open_pr_url(factory_repo: str, branch: str) -> str | None:
    """Url of the open PR whose head is `branch`, if there is one."""
    prs = json.loads(
        _run(["gh", "pr", "list", "--repo", factory_repo, "--head", branch, "--json", "url"])
        or "[]"
    )
    return prs[0]["url"] if prs else None


def _open_factory_pr(
    branch: str,
    commit_message: str,
    title: str,
    body: str,
    edit_checkout: Callable[[Path], None],
) -> str:
    """Clone the factory repo onto a fresh `branch`, let `edit_checkout`
    rewrite files in it, then commit/push and open the PR — returning the
    url of the PR already open on `branch` instead, if there is one. That
    existing-PR check is what makes the Register/Deploy activities safe to
    retry, rather than the "already exists" string-match in
    harness/swe-agent/agent.py::push_and_open_pr.
    """
    factory_repo = _factory_repo()
    existing = _open_pr_url(factory_repo, branch)
    if existing:
        return existing

    with tempfile.TemporaryDirectory() as td:
        checkout = Path(td)
        _run(["git", "clone", _clone_url(factory_repo), str(checkout)])
        _run(["git", "checkout", "-b", branch], cwd=checkout)
        edit_checkout(checkout)
        _run(["git", "add", "-A"], cwd=checkout)
        _run(["git", *_GIT_IDENTITY, "commit", "-m", commit_message], cwd=checkout)
        _run(["git", "push", "-u", "origin", branch], cwd=checkout)

        # Written after the commit, so the body file stays untracked.
        body_path = checkout / ".pr-body.md"
        body_path.write_text(body)
        try:
            return _run(
                [
                    "gh", "pr", "create",
                    "--repo", factory_repo,
                    "--head", branch,
                    "--title", title,
                    "--body-file", str(body_path),
                ],
                cwd=checkout,
            )
        except RuntimeError:
            # `gh pr create` also fails when a PR appeared on this branch
            # since the check above (concurrent run) — reuse it.
            existing = _open_pr_url(factory_repo, branch)
            if existing:
                return existing
            raise


@activity.defn
async def register_activity(repo: str, agent_name: str, version: str, eval_result: dict) -> str:
    """Register (§3.7). Opens a PR against the factory repo itself (not
    `repo`, the target implementation repo) adding/updating
    registry/agents/<agent_name>/manifest.yaml + versions/<version>.yaml."""

    def write_registry_entry(checkout: Path) -> None:
        agent_dir = checkout / "registry" / "agents" / agent_name
        versions_dir = agent_dir / "versions"
        versions_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = agent_dir / "manifest.yaml"
        manifest: dict = (
            yaml.safe_load(manifest_path.read_text())
            if manifest_path.exists()
            else {"name": agent_name}
        )
        manifest["current_version"] = version
        manifest["eval_gate_passed"] = bool(eval_result.get("passed"))
        manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))

        (versions_dir / f"{version}.yaml").write_text(
            yaml.safe_dump(
                {"version": version, "source_repo": repo, "eval_gate": eval_result},
                sort_keys=False,
            )
        )

    return _open_factory_pr(
        branch=f"{_REGISTRY_BRANCH_PREFIX}{agent_name}-{version}",
        commit_message=f"register {agent_name} {version}",
        title=f"registry: {agent_name} {version}",
        body=(
            f"Automated registry update for {agent_name} {version}."
            f"\n\nEval-Gate: {eval_result}"
        ),
        edit_checkout=write_registry_entry,
    )


@activity.defn
async def promote_agent_activity(agent_name: str, version: str) -> str:
    """Deploy (§3.7) status flip. Runs once the registry PR opened by
    register_activity is merged (signaled to RegistryPromotionWaiterWorkflow).
    Opens a follow-up PR against the factory repo setting
    manifest.yaml.status: experimental -> active — kept as a separately
    auditable git event from Register, per registry/README.md's ops table."""

    def flip_status_to_active(checkout: Path) -> None:
        manifest_path = checkout / "registry" / "agents" / agent_name / "manifest.yaml"
        manifest: dict = yaml.safe_load(manifest_path.read_text())
        manifest["status"] = "active"
        manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))

    return _open_factory_pr(
        branch=f"{_PROMOTE_BRANCH_PREFIX}{agent_name}-{version}",
        commit_message=f"deploy: promote {agent_name} {version} to active",
        title=f"deploy: promote {agent_name} {version}",
        body=f"Registry PR for {agent_name} {version} merged — promoting to active.",
        edit_checkout=flip_status_to_active,
    )
