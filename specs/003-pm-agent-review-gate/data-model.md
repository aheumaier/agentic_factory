# Phase 1 Data Model: PM-Agent Issue-Shaping and Spec-Review Gate

**Revision note**: Updated after a first senior-architect review (2026-09-03) —
`PmAttemptsExhausted` is removed (attempt-budget ownership moved to
`specs/005-pipeline-mode-signals-escalation/`, see `research.md` Unknown 3),
and Spec-Review Writeup now documents its idempotency marker (`research.md`
Unknown 5). Updated again after a second review the same day: the `pr_url`
cross-spec gap section gains two siblings below (a spec-path resolution bug
found in `orchestration/activities.py`, and an unresolved cross-stage SHA-pin
gap), per `research.md` Unknowns 3, 7.

No database or persisted store — every entity below lives in GitHub (an
issue, a PR comment) or is a plain function argument/return value, per the
spec's own Key Entities section. This document maps each spec entity to its
concrete representation in `harness/pm-agent/agent.py`.

## Raw Issue / Shaped Issue

**Representation**: A GitHub issue's `title`/`body` fields, read via
`gh issue view <n> --json title,body,closedByPullRequestsReferences` and
written via `gh issue edit <n> --title ... --body ...`. Not modeled as a
local class — `shape_issue()` passes the fetched `dict` straight into the
model's prompt as text and writes back whatever text the model returns.

**Fields** (as returned by `gh issue view --json`):
| Field | Type | Notes |
|---|---|---|
| `number` | int | Issue number, caller-supplied to `shape_issue()` |
| `title` | str | Rewritten in place |
| `body` | str | Rewritten in place — the no-gold-plating note is appended/blended into this text |
| `closedByPullRequestsReferences` | list | Used only for the linked-PR check below, never surfaced to the model; `pullRequest` is **not** a valid `gh issue view --json` field (`research.md` Unknown 8) |

**Validation rules**:
- `shape_issue()` MUST refuse (raise) if `gh issue view`'s
  `closedByPullRequestsReferences` is non-empty — this job only acts on raw
  issues with no linked pull request (Edge Case in spec.md; "linked" means
  linked via a closing reference, per `research.md` Unknown 8).
- No branch, spec file, or pipeline run may be created as a side effect
  (FR-002) — enforced structurally by binding zero tools to the model (see
  `research.md` Unknown 1), not by a runtime check.

**State transitions**: Raw Issue → Shaped Issue is one-way and terminal;
Shaped Issue has no further states within this feature (a human's later,
separate decision to write `spec.md` is out of scope, per spec Assumptions).

## Spec-Review Writeup

**Representation**: A plain string (Markdown) returned by the model in
`review_spec()`, posted via `gh pr comment <pr_url> --body ...` (code, not
the model). Its first line is a hidden idempotency marker, `<!--
pm-agent:review attempt=<N> -->` (see `research.md` Unknown 5) — not
persisted anywhere else; the PR comment thread is the artifact's home, per
`docs/70-multi-agent-pipeline-design.md` §8.

**Fields** (conceptual, all folded into the one Markdown string — no
structured schema is required by any FR):
| Field | Notes |
|---|---|
| Idempotency marker | `<!-- pm-agent:review attempt=<N> -->`, first line; checked before posting to avoid a double-post on retry |
| Rightness-of-scope assessment | FR-005: is this the right thing to build |
| Scope/gold-plating flag | FR-005: explicit no-gold-plating note |
| Attempt number | Also included in human-visible text so a reader can tell which re-review this is |

**`review_spec()`'s return value**: `{"writeup": str, "attempt": int}` — a
plain dict, not a bare string and not an exception on any business outcome
(see `PmAttemptsExhausted`, removed, below). Mirrors
`eval/braintrust/eval.config.py::run_eval`'s dict-return convention for gate
outcomes.

## PM Approval Decision

**Representation**: Not produced or consumed by this feature's code at all
— per the spec's Assumptions, the mechanism that delivers a human's
`pm_approved`/`pm_rejected: <feedback>` decision back to a caller is a
dependency (the webhook bridge, `specs/002-webhook-trigger-bridge/`), not
part of this feature. `review_spec()`'s only awareness of a prior decision
is the `feedback: str | None` argument a caller passes in on a re-review
call — there is no `PmApprovalDecision` type in this codebase. Likewise, the
bounded-attempt count and escalation-on-exhaustion behavior the spec's
FR-011 describes at the system level is owned by
`specs/005-pipeline-mode-signals-escalation/` (FR-010/FR-011 there,
explicitly naming "PM review"), not by this feature's function — see
`research.md` Unknown 3.

## `pr_url` — an unresolved cross-spec precondition (new)

**Status**: `review_spec()`'s `pr_url` parameter is caller-supplied per its
contract, but no producer of a target-repo PR *before* the PM stage runs
exists anywhere in `specs/002-webhook-trigger-bridge/`,
`specs/004-architect-fanout-judge/`, `specs/005-pipeline-mode-signals-escalation/`,
`specs/006-quality-gate/`, or `specs/007-automated-security-review/` — the
`ensure_target_pr_activity` referenced in
`docs/70-multi-agent-pipeline-design.md` is not implemented or specified by
any of them. This feature does not resolve that gap (it is squarely an
orchestration-sequencing concern per this spec's own Assumptions), but it is
recorded here — and added to `spec.md`'s Assumptions — so it is not silently
assumed away: **whoever wires `review_spec()` as a Temporal activity must
also ensure a target-repo PR exists first**, e.g. by implementing
`ensure_target_pr_activity` (naturally a fit for `specs/002-webhook-trigger-bridge/`
or `specs/005-pipeline-mode-signals-escalation/`, not this feature).

## Spec-path resolution — a bug found adjacent to, but outside, this feature

**Status**: `review_spec()` resolves its target spec as `specs/<branch>/spec.md`
directly from its own `branch` argument (`research.md` Unknown 7), not a
glob — this feature's own code does not have the bug described below. But
the review that found the need for that fix also found that
`orchestration/activities.py`'s `eval_gate_activity` (lines ~128-135) globs
`specs/*/spec.md` and takes `sorted(...)[0]` unconditionally, which resolves
to `001-agent-spec-schema-test` on any checkout with more than one spec
directory — true of this repo today (001 through 007). This is a real,
pre-existing bug, not introduced by this feature, and not this feature's to
fix (it lives entirely inside `orchestration/`, outside `harness/pm-agent/`
and this feature's Project Structure). Recorded here, next to the
`pr_url` gap below, so it is not lost: whoever next touches
`eval_gate_activity` should fix it the same way — derive the path from the
branch being evaluated, not a glob.

## Cross-stage spec version — an unresolved cross-spec gap (new)

**Status**: Nothing in this feature, or in `specs/002-webhook-trigger-bridge/`
or `specs/005-pipeline-mode-signals-escalation/`, pins the exact commit SHA
of `spec.md` that a `pm_approved` decision was granted against. Spec-Review
re-reviews "the spec as it stands" on each attempt by design (see
`spec.md`'s Edge Cases, third bullet) — that is correct and intentional for
*this* feature's own re-review loop. But once approved, nothing carries that
approved SHA forward to the later Eval-Gate stage, which independently
re-reads `spec.md` off the same branch when it runs
(`eval/braintrust/eval.config.py::load_success_criteria`). If a human edits
`spec.md` between PM approval and Eval-Gate's later read — plausible, since
`pm_rejected: <feedback>` naturally invites editing the spec — the two
stages can score different versions of it with no record of the mismatch.
This is not a defect in this feature (it has no Eval-Gate-facing
responsibility per its Assumptions) but is recorded here as an open gap for
whoever next touches `specs/002-webhook-trigger-bridge/` or
`specs/005-pipeline-mode-signals-escalation/`, alongside the `pr_url` gap
above, since both are "no producer of X exists yet" gaps of the same shape.

## `PmAttemptsExhausted` — removed (was: new, this feature)

Removed in this revision. Attempt-count enforcement and escalation-on-
exhaustion now belong entirely to the calling workflow
(`specs/005-pipeline-mode-signals-escalation/` FR-010/FR-011), per
`research.md` Unknown 3. `review_spec()` no longer raises on any business
outcome; `attempt`/`feedback` are content for the writeup only.
