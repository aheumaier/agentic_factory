---
name: architect-agent
description: >-
  Architect agent (Harness/Runtime, agent-factory-architecture.md §3.2)
  backing one stage entrypoint, run_architect_stage(): fan-out N
  candidate plans, score + synthesize one winner, and an independent
  completeness-critic pass.
---

# Architect agent

Portable copy of `harness/architect-agent/SKILL.md` — the registry
entry per `CLAUDE.md`'s portability boundary. Keep the two in sync.

Design source: `specs/004-architect-fanout-judge/` (spec, plan,
research, data-model, contracts, quickstart). One stage entrypoint plus
five independently callable capability functions in
`harness/architect-agent/agent.py`: `generate_candidate()` /
`generate_candidates()`, `score_candidates()` / `pick_winner()`,
`synthesize()`, `check_completeness()`, `persist_synthesized()` /
`push_synthesized()`, `post_stage_comment()`, sequenced by
`run_architect_stage(repo, branch, pr_url, attempt, feedback=None,
spec_dir=None, n_candidates=None, push=True, sc_loader=None)`.

## Three roles, three distinct tool bindings

- **Candidates (fan-out and gap-targeted)** — `tools=["Read", "Grep",
  "Glob"]`, `setting_sources=[]`, `cwd` set to a shallow clone of the
  branch under review. No `Write`/`Edit`/`Bash` anywhere — a candidate's
  plan cannot reach the filesystem, which is what makes FR-011
  structural rather than a promise about commit contents. Each fan-out
  candidate's `query()` is its own CLI subprocess with its own context:
  FR-003's "no visibility into any other candidate" holds because there
  is no shared conversation to leak through, not because a prompt says
  so.
- **Scoring, synthesis, and the completeness-critic** — `tools=[]`, no
  filesystem access at all; they reason over structured text passed in
  the prompt (candidate plans, validated scores, or the synthesized
  plan), never over a live checkout.
- **All three roles pin the same model id**, `claude-sonnet-5` — the
  only id `litellm/config.yaml` guarantees resolves, since the Agent SDK
  CLI requests it by default.

## §6.1 no-sandbox carve-out

No E2B sandbox for any of the three roles
(`docs/70-multi-agent-pipeline-design.md` §6.1): candidates, judge, and
critic only ever produce and consume markdown, so there is nothing to
execute. Unlike `harness/swe-agent`, which its callers always run inside
an E2B sandbox.

## LiteLLM-routed

Goes through LiteLLM (`LITELLM_BASE_URL`/`ANTHROPIC_BASE_URL`), matching
this repo's default convention and `pm-agent`'s `review_spec()` — this
stage runs on the Temporal worker host, which can reach the self-hosted
proxy, unlike `pm-agent`'s `shape_issue()` on a target-repo runner.

## Deviation from `docs/70-multi-agent-pipeline-design.md` §2

The design doc's Architect step 2 has the judge consume each
candidate's own `/speckit-analyze` consistency result. This feature
does not: FR-005 replaced that with a model-produced ordinal 1-5
internal-consistency rating, computed by the scoring call and validated
in Python. `/speckit-analyze` needs `Bash`, and `Bash` is exactly the
tool `003-pm-agent-review-gate` dropped from `review_spec()` to keep the
stage LiteLLM-routed and free of the branch-under-review's own hooks.
Binding `Bash` to N concurrent candidates to recover a consistency
number would reintroduce that whole surface N times over.

## The credential-scrub window is process-wide, not per-call

`_no_git_credentials()` pops `GH_TOKEN`/`GITHUB_TOKEN` from the parent
process's `os.environ` **once**, wrapping every model call in one
`run_architect_stage()` invocation — not once per candidate. A per-call
pop/restore (`pm-agent`'s pattern, correct for a sequential caller) is a
race under `asyncio.gather`: candidate A's `finally` would restore
`GH_TOKEN` while candidate B is still mid-`query()`.

## The clone's `origin` URL is rewritten immediately after clone

`_clone_spec_branch()` clones with a token-embedded URL, then
immediately `git remote set-url origin` to the token-free form and
disables the checkout's credential helper. This is separate from, and
in addition to, the credential-scrub window: `git clone
https://x-access-token:<token>@...` writes the token into the
checkout's `.git/config`, and `credential.helper ""` does nothing about
that. Candidates are bound `Read` with `cwd=checkout`, and their
`plan_md` is posted verbatim into a PR comment — so without this
rewrite, a candidate that reads `.git/config` publishes a GitHub App
installation token (FR-015).

## Deviation from the contract: `post_stage_comment()` takes a `sha` parameter

`contracts/architect-agent-interface.md`'s `post_stage_comment()`
signature has no `sha` parameter, but the idempotency marker it emits
(`<!-- architect-agent:stage attempt=<N> spec=<sha> -->`) requires one,
and the function is given no checkout to derive it from. `agent.py`
adds a required keyword-only `sha: str` argument; `run_architect_stage()`
passes the commit SHA from `persist_synthesized()`.

## Temporal wiring (narrow slice of 005)

`orchestration/activities.py::architect_stage_activity` wraps
`run_architect_stage()` in-process (no E2B sandbox, per the carve-out
above), mapping its two named exception cases onto typed, non-retryable
`ApplicationError`s so the workflow branches on `.type` rather than
string-matching: `MalformedRetriesExhausted` (CO-3 — never charges the
plan-attempt budget) and `PlanDeterministicFailure` (CO-2 — always
charges it). `ensure_target_pr_activity` opens the target-repo PR ahead of
this stage (see "No standalone `pr_url` producer" below). `AgentPipelineWorkflow`
(`orchestration/workflows/pipeline_workflow.py`) runs this stage ahead of
Build behind a `workflow.patched("architect-stage-v1")` guard, gated by
real `plan_approved`/`plan_rejected(feedback)` signals, and discharges
CO-1/CO-2/CO-3/CO-4 against a `MAX_PLAN_ATTEMPTS=3` budget. Covered by
`orchestration/tests/test_pipeline_workflow.py`.

Still deliberately out of scope, left for a full
`specs/005-pipeline-mode-signals-escalation/` pass: the `mode` param and
`vibe` mode itself, PM Spec-Review's own activity/signal wiring, the
security-clearance signal, and the generic `escalation_resume`/
`escalation_abandon(reason)` pair — this slice's budget exhaustion still
raises a bare `ApplicationError`, exactly like the existing Build loop's,
not yet generalized into that pair. The full FR-015 re-sequence (Setup +
PM gate + Architect + Completeness-Critic all ahead of Build) also isn't
done — only the Architect stage moved.

## Known gaps

- **`MAX_PLAN_ATTEMPTS` charging is duplicated, not shared, across
  gated stages** — deliberately, for now. The plan-review loop above
  enforces its own `MAX_PLAN_ATTEMPTS=3` budget; a generic, cross-stage
  escalation mechanism (`escalation_resume`/`escalation_abandon`) that
  the PM and Security stages would also plug into is still
  `specs/005-pipeline-mode-signals-escalation/`'s job.
- **No `vibe` mode.** `candidate_count()` accepts an `n_override`, the
  seam a future `vibe` caller uses, but this feature does not add the
  mode itself.
- **No standalone `pr_url` producer.** `run_architect_stage()` itself
  still just takes `pr_url` as an argument, unchanged. The narrow
  Temporal slice above provides one via `ensure_target_pr_activity`, but
  `review_spec()` (pm-agent) has no equivalent yet.
- **This stage is not automatically gated.** See
  `registry/agents/architect-agent/manifest.yaml`'s `eval_gate` field and
  `specs/004-architect-fanout-judge/plan.md`'s "This stage is not
  automatically gated" section: the coverage map scores the candidates,
  not the shipped synthesized plan, and the completeness-critic is
  advisory with exactly one retry, never blocking.
- **SC-007 was narrowed to the per-attempt correlation marker only** —
  see `plan.md`'s "SC-007, and what was deliberately moved out of it".
  The decision-capture half belongs to
  `specs/005-pipeline-mode-signals-escalation/`.
- **`orchestration/activities.py::eval_gate_activity`'s
  `sorted(glob("specs/*/spec.md"))[0]` bug is inherited, not fixed
  here** — it resolves to `001-agent-spec-schema-test` on any checkout
  of this repo, so this feature's own Eval-Gate score stays unreachable,
  the same as `003-pm-agent-review-gate`'s.
