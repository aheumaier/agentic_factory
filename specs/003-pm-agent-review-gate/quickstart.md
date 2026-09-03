# Quickstart: PM-Agent Issue-Shaping and Spec-Review Gate

**Revision note**: Updated after three senior-architect review passes on
2026-09-03. First pass: `review_spec()` now returns a dict and is never
expected to raise on attempt exhaustion (Unknown 3); a credential-scrub
check replaces the old clone-URL-string check for FR-007 (Unknown 2);
Issue-Shaping is validated via its real trigger shape (Unknown 4). Second
pass: both capabilities now go direct-to-Anthropic, not LiteLLM (Unknown
1); the FR-007 verification step also checks `GH_CONFIG_DIR` (Unknown 2,
revised again); Issue-Shaping's linked-PR edge case checks
`closedByPullRequestsReferences` (Unknown 8). **Third pass**: the
credential-scrub verification step now checks `os.environ` state, not an
`env=` dict shape (Unknown 2, corrected); a no-`Bash`/no-hooks check
replaces the old "inspect the environment via `Bash`" step, since
Spec-Review no longer binds `Bash` at all; Spec-Review now goes through
LiteLLM, not direct-to-Anthropic (Unknown 9); Issue-Shaping's edit step now
has a preceding preservation-comment check (FR-002a).

## Prerequisites

- `gh` CLI authenticated (ambient credential helper, or `GH_TOKEN` set for
  Issue-Shaping's issue-edit call)
- `harness/pm-agent/` dependencies installed: `cd harness/pm-agent && uv sync`
- `ANTHROPIC_PLATFORM_API_KEY` set for Issue-Shaping — a documented deviation from
  this repo's default LiteLLM-routing convention, justified by network
  reachability from a target repo's GitHub-hosted runner (`research.md`
  Unknown 1). `BRAINTRUST_API_KEY` set for both capabilities (Braintrust
  tracing, per `plan.md`'s Foundational setup).
- `LITELLM_BASE_URL`/`LITELLM_MASTER_KEY` set for Spec-Review — it is
  LiteLLM-routed, matching this repo's default convention, since it runs
  on the orchestration worker host (reachable) and no longer needs Claude
  Code's own skill discovery (`research.md` Unknown 9). Not used by
  Issue-Shaping.
- For the Issue-Shaping trigger on an opted-in **target** repo: the
  `pm-agent`-scoped GitHub App installed with `issues: write`, and
  `ANTHROPIC_PLATFORM_API_KEY`/`BRAINTRUST_API_KEY` available to that repo's Actions
  secrets (`secrets: inherit` does not create secrets that don't already
  exist there).

## Validate User Story 1 — Issue-Shaping

1. File a test issue with vague scope on a scratch repo, no linked PR.
2. Run (from `harness/pm-agent/`, so `agent` resolves without a `PYTHONPATH`
   override):
   ```
   cd harness/pm-agent && uv run python -c \
     "import asyncio; from agent import shape_issue; \
      print(asyncio.run(shape_issue('<owner>/<repo>', <issue_number>)))"
   ```
3. **Expected**: `gh issue view <issue_number>` shows an edited title/body
   with added scope clarity and an explicit no-gold-plating note, and a
   preceding comment on the issue containing the original, pre-shaping
   title/body (FR-002a — the only recovery path for this overwrite).
4. **Verify no side effects** (SC-001): `git branch -a` and `specs/` on the
   scratch repo are unchanged; no Temporal workflow was started (nothing in
   this feature can start one — see the interface contract's postcondition).
5. **Edge case**: repeat against an issue whose
   `closedByPullRequestsReferences` is non-empty (i.e. a PR closes it) —
   expect a `RuntimeError`, no edit performed.
6. **Trigger, end-to-end** (once `.github/workflows/pm-agent-shape.yml` +
   `pm-agent-shape-trigger.yml` are deployed, per `research.md` Unknown 4):
   copy `pm-agent-shape-trigger.yml` into a scratch target repo, comment
   `@pm-agent shape` on a qualifying issue there, and confirm the same
   edit happens without `harness/pm-agent/` being checked out into that
   repo ahead of time (the reusable workflow's `actions/checkout` step
   pulls it from `agentic_factory` at trigger time).

## Validate User Story 2 — Spec-Review

1. On a scratch repo/branch, ensure `specs/NNN-slug/spec.md` already exists
   and a PR is open for that branch (this feature does not create that PR —
   see `data-model.md`'s "`pr_url`" section; create one manually for this
   quickstart).
2. Run (from `harness/pm-agent/`, so `agent` resolves without a
   `PYTHONPATH` override):
   ```
   cd harness/pm-agent && uv run python -c \
     "import asyncio; from agent import review_spec; \
      print(asyncio.run(review_spec('<owner>/<repo>', '<branch>', \
      '<pr_url>', attempt=1)))"
   ```
3. **Expected** (SC-002): the call returns `{"writeup": ..., "attempt": 1}`,
   and a value-judgment writeup appears as a new comment on `<pr_url>`,
   addressing scope/rightness and flagging any apparent gold-plating, with
   a leading `<!-- pm-agent:review attempt=1 spec=<sha> -->` marker.
4. **Verify no tool-execution or credential surface, structurally**
   (FR-007): via a test double (not the model — it has no `Bash` to run a
   shell check with), confirm the `ClaudeAgentOptions` passed to `query()`
   has `tools == ["Read", "Grep", "Glob"]` and `setting_sources == []`, and
   inspect `os.environ` for the duration of the model call — `GH_TOKEN`/
   `GITHUB_TOKEN` must be absent (popped from the parent process, not
   merely omitted from an `env=` dict), the `env=` override must point
   `GH_CONFIG_DIR` at an empty directory, and `git config --local --get
   credential.helper` in the checkout must return empty. Then, separately,
   confirm `git log origin/<branch>` on the real remote shows no new commit
   from this run.
5. **Re-review with feedback** (SC-004): call again with
   `attempt=2, feedback="<some correction>"` — expect a fresh writeup
   comment that visibly addresses the feedback text, and a `{"writeup":
   ..., "attempt": 2}` return.
6. **Idempotent re-post**: call again with the exact same `attempt=2` (no
   new feedback) — expect the *same* comment body returned, and confirm no
   second comment was posted to the PR.
7. **No attempt cap here**: calling with `attempt=99` does **not** raise —
   it posts (or returns the idempotent) writeup for attempt 99 like any
   other call. Enforcing a cap and escalating on exhaustion is validated by
   `specs/005-pipeline-mode-signals-escalation/`'s own quickstart, not this
   one.

## What this quickstart does not cover

Per the spec's Assumptions, out of scope for this feature (and therefore
this quickstart):
- Delivering a human's `pm_approved`/`pm_rejected: <feedback>` decision from
  a GitHub PR comment into a call to `review_spec()` — that's
  `specs/002-webhook-trigger-bridge/`.
- Wiring `review_spec()` as an actual Temporal activity inside
  `AgentPipelineWorkflow`, including provisioning any execution sandbox for
  it — that's the orchestration-layer work
  `docs/70-multi-agent-pipeline-design.md` describes but leaves unbuilt.
- Tracking the PM re-review attempt budget and escalating on exhaustion —
  `specs/005-pipeline-mode-signals-escalation/`.
- Ensuring a target-repo PR exists before this stage runs — an unresolved
  gap across the whole multi-agent pipeline design, recorded in
  `data-model.md`, not resolved by any spec yet.
