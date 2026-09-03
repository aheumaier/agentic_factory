---
name: pm-agent
description: >-
  PM agent (Harness/Runtime, agent-factory-architecture.md §3.2) backing
  two capabilities: Issue-Shaping (rewrites a raw issue for scope
  clarity before it becomes a spec) and Spec-Review (posts a
  value-judgment review of a spec to a target-repo PR).
---

# PM agent

Portable copy of `harness/pm-agent/SKILL.md` — the registry entry per
`CLAUDE.md`'s portability boundary. Keep the two in sync.

Design source: `specs/003-pm-agent-review-gate/` (spec, plan, research,
data-model, contracts, quickstart — third senior-architect revision).
Two independently callable, async functions in `harness/pm-agent/agent.py`:
`shape_issue(repo, issue_number)` and `review_spec(repo, branch, pr_url,
attempt, feedback=None, spec_dir=None)`.

## Issue-Shaping — `shape_issue()`

Rewrites an issue's title/body for scope clarity and an explicit
no-gold-plating note. Refuses (raises `RuntimeError`) if the issue
already has a linked pull request
(`closedByPullRequestsReferences` non-empty).

**Structural guarantee**: the model is called with `ClaudeAgentOptions(
tools=[])` — no tools bound at all, not merely `allowed_tools=[]` (which
only suppresses auto-approval prompting for tools that *are* bound, and
is already the SDK's default). `tools=[]` is what actually disables
tool binding — there is nothing for the model to invoke a branch, spec,
or pipeline run with (FR-002/FR-003). The `gh issue edit` mutation runs
from code, after the model call returns, mirroring
`harness/swe-agent/agent.py::push_and_open_pr`'s "the model must not do
X, so code does X instead" pattern.

**Preservation step** (FR-002a): before overwriting, the original
title/body is posted as a `gh issue comment`. This is a model-authored,
one-way overwrite on a **target** repo with no other human checkpoint in
this job's path — the comment is the sole recovery mechanism.

**Direct-to-Anthropic deviation**: this capability runs on a target
repo's GitHub-hosted Actions runner (see the trigger below), which
cannot reach this repo's self-hosted LiteLLM proxy on `localhost:4000`.
This is a *network-reachability* deviation from `CLAUDE.md`'s "model
calls never take a provider key directly" convention — distinct from,
and not to be conflated with, `harness/swe-agent`'s deviation, which is
about needing Claude Code's own skill discovery for `/speckit-implement`.
Nothing here invokes a Spec-Kit skill command.

**`ANTHROPIC_PLATFORM_API_KEY`, not `ANTHROPIC_API_KEY`**: this repo's
own Anthropic key is deliberately named `ANTHROPIC_PLATFORM_API_KEY` so
it doesn't collide with a developer's own ambient `ANTHROPIC_API_KEY`
(e.g. an enterprise Claude subscription used for Claude Code itself).
But the vendored `claude_agent_sdk`'s CLI subprocess only ever reads the
literal `ANTHROPIC_API_KEY` env var — it has no notion of the renamed
key. Both `shape_issue()` and `review_spec()` therefore pass
`ANTHROPIC_PLATFORM_API_KEY`'s value through explicitly as an `env=`
override under the SDK's fixed name (`ClaudeAgentOptions.env={
"ANTHROPIC_API_KEY": ...}`), which also shadows any ambient personal
`ANTHROPIC_API_KEY`, since `options.env` merges on top of `os.environ`
in the SDK's subprocess launcher. Found and fixed while validating this
feature end-to-end against a real scratch repo.

**Trigger**: `.github/workflows/pm-agent-shape.yml` (reusable) +
`pm-agent-shape-trigger.yml` (the ~10-line per-repo caller), mirroring
`swe-agent-build.yml`/`swe-agent-trigger.yml`'s split — a target repo
copies only the trigger file and comments `@pm-agent shape` on a
qualifying issue.

## Spec-Review — `review_spec()`

Posts a value-judgment review (rightness of scope, explicit
gold-plating flag, and — if `feedback` is given — whether it's
addressed) of `<spec_dir>/spec.md` (default `specs/<branch>`, override
for a branch that doesn't follow that convention) to a target-repo PR.

**No trigger of its own in this feature** — it is a directly callable,
importable function, invoked today only by hand (see `quickstart.md`);
a future orchestration caller (a Temporal activity, out of scope this
pass) wires it into the pipeline.

**FR-007's no-push/no-mutate guarantee holds at three independent
layers**, none of which depends on execution environment:
1. `tools=["Read", "Grep", "Glob"]` — no `Bash`, no `Write`/`Edit`; no
   tool with shell-execution or GitHub-mutation capability is bound at
   all. `/speckit-analyze` is dropped from v1 scope because it needed
   `Bash`.
2. `setting_sources=[]` — no `.claude/settings.json` hook committed to
   the branch **under review** can auto-execute in the CLI subprocess.
   This is independent of (1): the SDK's default `setting_sources=None`
   loads project settings (including hooks) from wherever `cwd` points
   regardless of which tools are bound to the model.
3. `GH_TOKEN`/`GITHUB_TOKEN` are popped from the **parent process's**
   `os.environ` before the model call and restored in a `finally` block
   afterward — not passed via `ClaudeAgentOptions.env`, which only
   *overrides* `os.environ` in the SDK's subprocess launcher and so
   cannot remove an inherited value. `GH_CONFIG_DIR` (pointed at an
   empty directory) and `GIT_TERMINAL_PROMPT=0` remain valid `env=`
   overrides, since those are additions, not removals. The checkout's
   git credential helper is also disabled immediately after clone.

**LiteLLM-routed** (`LITELLM_BASE_URL`/`ANTHROPIC_BASE_URL`), matching
this repo's default convention: this capability runs on the
orchestration worker host, which can reach the proxy — unlike
Issue-Shaping's target-repo runner. Dropping `Bash`/`/speckit-analyze`
(point 1 above) is what removed the reason a prior revision needed
direct-to-Anthropic here.

**Idempotent per `attempt`**: the posted writeup's first line is a
hidden marker, `<!-- pm-agent:review attempt=<N> spec=<sha> -->`.
Before doing anything else (before even cloning), `review_spec()` checks
the PR's existing comments for that exact `attempt=<N>` marker and
returns the existing body unchanged if found — a retry never burns a
model call or double-posts. `attempt` MUST be strictly increasing per
distinct review request; reusing an `attempt` with different `feedback`
is caller error, not something this function detects.

**No attempt cap**: `review_spec()` never raises on any business
outcome — it takes `attempt`/`feedback` purely as writeup content and
returns `{"writeup": str, "attempt": int}` every time. Enforcing a
bounded retry budget and escalating on exhaustion belongs entirely to
`specs/005-pipeline-mode-signals-escalation/`'s workflow-level tracking.

## Known gaps

- **No producer of a target-repo PR exists yet.** `review_spec()`'s
  `pr_url` parameter is caller-supplied per its contract, but nothing in
  this repo (or any adjacent `specs/*/`) creates or verifies that a PR
  exists at that URL before the PM stage runs. Whoever wires
  `review_spec()` as a Temporal activity must also ensure this — see
  `specs/003-pm-agent-review-gate/data-model.md`'s `pr_url` section.
- **Cross-stage spec-version gap.** Nothing yet carries the reviewed
  spec's commit SHA (recorded in the idempotency marker, for human
  legibility) forward into a structured field the later Eval-Gate stage
  could compare against. If a human edits `spec.md` between PM approval
  and Eval-Gate's later read, the two stages can silently score
  different versions. See `data-model.md`'s "Cross-stage spec version"
  section.
- **`orchestration/activities.py::eval_gate_activity`'s spec-path glob
  bug is a blocking dependency for this feature's own gate score being
  reachable at all**, not just an adjacent nuisance: it globs
  `specs/*/spec.md` and takes `sorted(...)[0]` unconditionally, which
  resolves to `001-agent-spec-schema-test` on any checkout of this repo
  with more than one spec directory (true today, 001 through 007). This
  bug is not introduced by, and not fixed by, this feature — see
  `data-model.md`'s "Spec-path resolution" section — but until it's
  fixed, `eval/braintrust/eval.config.py`'s coverage gate cannot score
  this feature's own `spec.md` correctly on this repo's own checkout.
