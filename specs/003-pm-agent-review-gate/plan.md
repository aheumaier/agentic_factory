# Implementation Plan: PM-Agent Issue-Shaping and Spec-Review Gate

**Branch**: `003-pm-agent-review-gate` | **Date**: 2026-09-02 (revised 2026-09-03, third pass) | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-pm-agent-review-gate/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

**Revision note**: First revised after a senior-architect review (2026-09-03)
that found the original design's FR-007 guarantee did not hold as specified,
its Issue-Shaping trigger had no delivery path on target repos, and it
created a second, conflicting owner of the PM re-review attempt cap. A
**second** senior-architect pass the same day found that first revision's
FR-007 fix still incomplete (closed git's credential path, not `gh` CLI's
separate one), its LiteLLM routing incompatible with its own revised
trigger design, and two new correctness bugs (an unresolved spec-path
lookup, an invalid `gh --json` field). A **third** pass, also the same day,
found that both prior passes corrected *rationale* without checking it
against the `claude-agent-sdk` actually vendored in this repo: `tools=`
(not `allowed_tools=`) is what disables tool binding; `ClaudeAgentOptions.env`
only overrides `os.environ`, it does not remove an inherited credential;
and the SDK's default `setting_sources=None` loads hooks from the branch
under review regardless of which tools are bound. See `research.md`'s
per-Unknown Rationale sections for the full reasoning; this Summary
reflects the third revision.

One new registry entry, `registry/agents/pm-agent/`, backing two independently
callable capabilities implemented in `harness/pm-agent/agent.py`:

1. **Issue-Shaping** — the model receives an existing issue's title/body as
   plain prompt context and returns rewritten text (scope clarity + a
   no-gold-plating note) with **zero tool access** — the actual `gh issue
   edit` mutation happens in Python code after the model call returns, never
   left to the model. This is the structural guarantee behind FR-002/FR-003:
   there is nothing to invoke a branch, spec, or pipeline run with, because
   `tools=[]` disables tool binding entirely (`allowed_tools=[]`, used in the
   first two revisions, only suppresses permission prompting for tools that
   *are* bound and is already the SDK's default — it asserts nothing on its
   own; `research.md` Unknown 1, corrected). Before the `gh issue edit`
   mutation, the original title/body is posted as a preserving `gh issue
   comment` (FR-002a) — a model-authored overwrite with no other human
   checkpoint in this job's path needs a recovery trail. Goes
   **direct-to-Anthropic**, not LiteLLM-routed — a target repo's
   GitHub-hosted runner (where this capability actually runs, per Unknown 4)
   cannot reach the self-hosted LiteLLM proxy on `localhost:4000`
   (`research.md` Unknown 1). The "no linked PR" precondition check uses
   `closedByPullRequestsReferences`, the only valid `gh --json` field for
   that check (`research.md` Unknown 8).
2. **Spec-Review** — the model gets `Read`/`Grep`/`Glob` (no `Bash`, and no
   `/speckit-analyze` — dropped this revision, see below) against a shallow
   clone of the branch, resolved as `<spec_dir>/spec.md` where `spec_dir`
   defaults to `specs/<branch>` but is caller-overridable for branches that
   don't follow that convention (not a glob — a checkout of this repo alone
   has seven `specs/*/` directories, and a first-sorted-match glob would
   silently review the wrong one; `research.md` Unknown 7). FR-007's no-push
   guarantee is enforced by three independent layers: (a) no tool with
   shell-execution or GitHub-mutation capability is bound to the model at
   all (`tools=["Read","Grep","Glob"]`); (b) `setting_sources=[]` prevents
   any `.claude/settings.json` hook committed to the branch under review
   from auto-executing in the CLI subprocess — a risk that exists
   regardless of (a), since hooks run in the subprocess itself, not through
   a model-invoked tool; (c) `GH_TOKEN`/`GITHUB_TOKEN` are popped from the
   **parent process's** `os.environ` before the model call and restored in
   a `finally` block afterward — not passed via `ClaudeAgentOptions.env`,
   which only overrides `os.environ` in the SDK's subprocess launcher and
   so cannot remove an inherited value (`research.md` Unknown 2, corrected).
   `GH_CONFIG_DIR` pointed at an empty directory remains a valid `env=`
   override (so `gh` has no `hosts.yml` fallback either), and the checkout's
   git credential helper is disabled. Dropping `Bash`/`/speckit-analyze`
   also removes the reason Spec-Review needed to stay direct-to-Anthropic:
   it now goes **through LiteLLM** like the rest of this repo, since it runs
   on the Temporal worker host (reachable) rather than a target-repo runner,
   and no longer needs Claude Code's own skill discovery (`research.md`
   Unknown 1, reversed; Unknown 9). The writeup is posted via `gh pr comment`
   from code, using the restored token, with a hidden per-`(attempt, spec
   SHA)` marker so a retried post doesn't duplicate and `attempt` is defined
   as the strictly-increasing idempotency key (`research.md` Unknown 5,
   extended). `attempt`/`feedback` are content for the writeup only — the
   function returns `{"writeup": str, "attempt": int}` and does **not**
   enforce or raise on any attempt cap; that ownership belongs entirely to
   `specs/005-pipeline-mode-signals-escalation/`'s workflow-level tracking
   (`research.md` Unknown 3).

Both capabilities remain plain Claude Agent SDK calls with no sandbox
provisioning inside `agent.py` itself, matching `harness/swe-agent/agent.py`'s
own split (the agent module doesn't know whether it's running on a host or
inside E2B — that's the caller's concern). This is not justified by the
Architect fan-out's §6.1 "text-only, never executes anything" carve-out —
Spec-Review still reads and reasons over content from the branch under
review, so §6.1 does not actually apply to it. Its FR-007 guarantee instead
holds at the tool-binding, setting-source, and credential level regardless
of execution environment (see point 2 above); a future orchestration caller
running it inside an E2B sandbox, the way
`orchestration/activities.py::run_swe_agent_activity` already does for
Build, remains recommended defense-in-depth but is that caller's decision,
out of scope here per the spec's own Assumptions about orchestration
sequencing.

## Technical Context

**Language/Version**: Python 3.11 (matches `harness/swe-agent`)

**Primary Dependencies**: `claude-agent-sdk`, `braintrust` (same observability
project as `eval/braintrust/eval.config.py` and `harness/swe-agent`), GitHub
CLI (`gh`, invoked via `subprocess`, not a bound model tool, for the actual
issue/PR mutations)

**Storage**: N/A — all state lives in GitHub (issue body, PR comments) or is
passed in as function arguments (attempt count, feedback); nothing persisted
by this feature itself

**Testing**: `uv run pytest` from repo root (root `pyproject.toml`/`uv.lock`),
new tests under `tests/`, mocking `subprocess`/`gh` calls — no real GitHub
network access in tests

**Target Platform**: Execution-environment-agnostic, like
`harness/swe-agent/agent.py` itself — `agent.py` does not provision a
sandbox and runs identically on a host process or inside an E2B sandbox.
(Note: `CLAUDE.md` records that no host-tempdir *path* remains for
swe-agent's own production trigger — both its triggers now run inside E2B.
That doesn't mean `agent.py`'s code depends on E2B; it means production
callers chose to sandbox it. Spec-Review's FR-007 guarantee is designed to
hold either way, per Summary point 2, precisely because this feature cannot
mandate its future caller's sandboxing choice.)

**Project Type**: Single agent harness + registry entry, following the
existing `harness/<agent>/` + `registry/agents/<agent>/` pattern

**Performance Goals**: N/A — not a latency- or throughput-sensitive path;
each capability runs once per human-driven event (an issue comment or a
pipeline stage attempt)

**Constraints**:
- Issue-Shaping: model has `tools=[]` — no bound tools at all, not merely
  `allowed_tools=[]` (which only suppresses auto-approval prompting and is
  already the SDK default); the `gh issue edit` mutation is code, not
  model-invoked (FR-002, FR-003); the original title/body is preserved via
  a `gh issue comment` before the overwrite (FR-002a); goes
  direct-to-Anthropic (`ANTHROPIC_PLATFORM_API_KEY`), a documented deviation from
  this repo's default LiteLLM-routing convention — justified by network
  reachability (runs on a target repo's GitHub-hosted runner, which cannot
  reach the self-hosted proxy), not by the skill-discovery reason
  `harness/swe-agent` documents (`research.md` Unknown 1)
- Issue-Shaping's "no linked PR" precondition checks
  `closedByPullRequestsReferences`, not a `pullRequest` field (which does
  not exist on `gh issue view --json`) (`research.md` Unknown 8)
- Spec-Review: `tools=["Read","Grep","Glob"]` — no `Bash`, no `Write`/`Edit`,
  and `/speckit-analyze` is dropped from v1 scope (it needed `Bash`);
  `setting_sources=[]` is set explicitly so no `.claude/settings.json` hook
  committed to the branch under review can execute in the CLI subprocess,
  independent of the model's own tool access (`research.md` Unknown 2,
  corrected). `GH_TOKEN`/`GITHUB_TOKEN` are popped from the **parent
  process's** `os.environ` before the model call and restored in a
  `finally` block afterward — `ClaudeAgentOptions.env` cannot remove an
  inherited value, it only overrides on top of `os.environ`, so it is used
  only for `GH_CONFIG_DIR` (pointed at an empty directory, so `gh`'s own
  `hosts.yml` fallback has nothing to read) and `GIT_TERMINAL_PROMPT=0`; the
  checkout's git credential helper is also disabled before the model call
  (FR-007; `research.md` Unknown 2). Because `/speckit-analyze` is dropped,
  Spec-Review no longer needs Claude Code's own skill discovery and instead
  goes **through LiteLLM** (`LITELLM_BASE_URL`), matching this repo's
  default convention — it runs on the Temporal worker host, which can reach
  the proxy, unlike Issue-Shaping's target-repo runner (`research.md`
  Unknown 1, reversed; Unknown 9)
- Spec-Review resolves its target spec as `<spec_dir>/spec.md`, where
  `spec_dir` defaults to `specs/<branch>` but is caller-overridable, never a
  glob over `specs/*/spec.md` (`research.md` Unknown 7)
- Spec-Review clones via a token-embedded URL
  (`https://x-access-token:<token>@github.com/<repo>.git`) so private
  target repos can be cloned; this happens before the credential scrub
  above, so it does not weaken FR-007 (`research.md` Unknown 2)
- Spec-Review's idempotency marker includes the spec's commit SHA
  (`<!-- pm-agent:review attempt=<N> spec=<sha> -->`); `attempt` MUST be
  strictly increasing per distinct review request and is the sole
  idempotency key — a caller reusing an `attempt` with different `feedback`
  is caller error, resolving FR-010/FR-011's apparent conflict
  (`research.md` Unknown 5, extended)
- `review_spec()` does not bound or track `MAX_PM_ATTEMPTS` — that budget and
  its escalation-on-exhaustion behavior belong to
  `specs/005-pipeline-mode-signals-escalation/` (FR-010/FR-011 there); this
  feature's function is attempt-oblivious beyond including the number in the
  writeup for human legibility (`research.md` Unknown 3)
- Posting the writeup is idempotent per `attempt` via a hidden marker
  comment, so a retried call doesn't double-post (`research.md` Unknown 5)

**Scale/Scope**: One registry entry, two capability functions, no new
external services

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is still the unfilled placeholder template
(no principles have been ratified for this repo) — there are no gates to
check against. No violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/003-pm-agent-review-gate/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
harness/pm-agent/
├── agent.py            # shape_issue(), review_spec(), _validate_repo,
│                        # _validate_branch, _run (mirrors
│                        # harness/swe-agent/agent.py's pattern);
│                        # SHAPE_ISSUE_PROMPT/SPEC_REVIEW_PROMPT/
│                        # FEEDBACK_PROMPT_SUFFIX hardcoded as module-level
│                        # constants (mirrors IMPLEMENT_PROMPT there) — no
│                        # runtime-loaded prompts/pm-agent.json
├── SKILL.md             # design source + deviations, mirrors
│                        # harness/swe-agent/SKILL.md
└── pyproject.toml        # own runtime deps: claude-agent-sdk, braintrust

registry/agents/pm-agent/
├── manifest.yaml         # mirrors registry/agents/swe-agent/manifest.yaml
├── versions/
│   └── v1.yaml
└── SKILL.md              # registry-side copy — CLAUDE.md's portability
                          # boundary requires this live under
                          # registry/agents/<name>/, not just harness/
                          # (the original plan omitted this copy)

.github/workflows/
├── pm-agent-shape.yml         # reusable workflow (on: workflow_call),
│                              # lives here — mirrors swe-agent-build.yml:
│                              # author-association gate, mints a GitHub
│                              # App token, checks out agentic_factory@main
│                              # onto the *target* repo's runner (no Bash
│                              # is bound in shape_issue(), so this carries
│                              # none of Spec-Review's Bash-isolation
│                              # concerns), invokes shape_issue(); also
│                              # (added this revision, matching
│                              # swe-agent-build.yml's own conventions it
│                              # had drifted from): an explicit
│                              # `permissions: {issues: write}` block; an
│                              # `astral-sh/setup-uv` step before `uv run`
│                              # (ubuntu-latest has no `uv` preinstalled);
│                              # issue title/body passed via `env:` and
│                              # referenced as `"$VAR"` in `run:`, never
│                              # interpolated via `${{ }}` — title/body are
│                              # this feature's most attacker-shapeable
│                              # input and flow into a prompt and a
│                              # `gh issue edit` argv; a failure comment
│                              # posted back to the issue, mirroring
│                              # swe-agent-build.yml:100-119
└── pm-agent-shape-trigger.yml # ~10-line per-repo caller (`on: issue_comment`,
                              # `uses: aheumaier/agentic_factory/.github/
                              # workflows/pm-agent-shape.yml@main`), mirrors
                              # swe-agent-trigger.yml — this is the file each
                              # opted-in target repo actually copies

tests/
└── test_pm_agent.py      # unit tests: credential-scrubbing during the
                          # model call, tool-set assertions, gh-command
                          # construction, idempotent-post behavior —
                          # subprocess calls mocked, no real GitHub network
                          # access
```

**Structure Decision**: Follows the existing `harness/<agent>/` +
`registry/agents/<agent>/` single-project pattern established by
`harness/swe-agent/` — no new top-level project boundary is introduced.
Still out of scope per the spec's Assumptions: Spec-Review's Temporal-
activity wiring (`orchestration/activities.py`,
`orchestration/workflows/pipeline_workflow.py`), the `pm_approved`/
`pm_rejected` decision-delivery mechanism (`specs/002-webhook-trigger-bridge/`),
attempt-budget tracking and escalation
(`specs/005-pipeline-mode-signals-escalation/`), and — newly documented
rather than silently assumed — ensuring a target-repo PR exists before this
stage runs (`data-model.md`'s "`pr_url`" section). This feature ends at two
directly callable, testable functions plus the Issue-Shaping trigger that
can invoke one of them from a target repo; Spec-Review has no trigger of its
own in this feature (it is invoked by a future Temporal activity).

`pm-agent-shape.yml`'s `uses: aheumaier/agentic_factory/.github/workflows/
pm-agent-shape.yml@main` reference tracks a moving branch, not a pinned
SHA/tag, matching `swe-agent-trigger.yml`'s existing `@main` convention in
this repo — accepted as-is (not a new deviation this feature introduces),
but documented here rather than described as "pinned," which it is not.

FR-012 ("distinguishing the two jobs' distinct triggers and tool access" in
one registry entry) is satisfied by `harness/pm-agent/SKILL.md` and
`registry/agents/pm-agent/SKILL.md`'s prose, not by a registry manifest
schema field — `registry/agents/swe-agent/manifest.yaml`'s schema (`name`/
`owner`/`current_version`/`status`/`eval_gate_passed`/
`requires_human_supervision`/`description`/`design_docs`) has no
capability/trigger field to extend, and this feature does not add one. No
Success Criterion covers FR-012, since `eval/braintrust/eval.config.py`'s
binary coverage gate does not (and is not extended by this feature to)
score documentation completeness.

Separately: `eval/braintrust/eval.config.py`'s SC-NNN-scoring premise (see
`spec.md`'s revision note) is itself currently unreachable for this
feature specifically, not just in the abstract — `orchestration/
activities.py::eval_gate_activity`'s `sorted(glob("specs/*/spec.md"))[0]`
resolves to `001-agent-spec-schema-test` on any checkout of this repo as it
exists today (`specs/001` through `specs/007` all present). This is a
pre-existing bug outside this feature's Project Structure (see
`data-model.md`'s "Spec-path resolution" section) and this feature does not
fix it, but it is called out here explicitly: **until that bug is fixed,
this feature's own gate score is not reachable**, which is a blocking
dependency for treating this feature as gate-passed, not merely a
nice-to-have cleanup.

## Complexity Tracking

*No Constitution Check violations — this section is not applicable.*
