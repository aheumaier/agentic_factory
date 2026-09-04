# Feature Specification: Architect Fan-Out, Judge, and Completeness-Critic

**Feature Branch**: `004-architect-fanout-judge`

**Created**: 2026-09-02

**Status**: Draft

**Input**: User description: "Architect stage for the multi-agent SDLC pipeline (docs/70-multi-agent-pipeline-design.md §2's Architect-agent subsection). New registry/agents/architect-agent/ entry covering: (1) N concurrent architect candidates (default 3: minimal-diff-first, clean-architecture-first, risk/security-first — a tunable knob scaling with spec complexity/budget), each producing an independent plan.md/tasks.md/ADR set from a distinct angle for the same spec.md, run as plain agent calls with no execution sandbox since their output is prose/markdown only; (2) one judge/synthesis pass scoring all N candidates against the spec's measurable outcomes and each candidate's own internal consistency check, producing a single synthesized plan.md/tasks.md that picks a winner and grafts strong ideas from runners-up; (3) one completeness-critic pass over the synthesized plan asking whether every measurable outcome is addressed and whether an architectural angle none of the N candidates tried was missed — on no gap found, posts a short note and the plan proceeds; on a gap found, triggers exactly one additional targeted candidate on that gap and a re-synthesis, counted against the same bounded re-plan attempt budget as an ordinary human rejection (MAX_PLAN_ATTEMPTS=3), not a separate budget. Candidate plans, judge rationale, and the critic's note are posted to the target-repo PR thread for human visibility/challenge; only the synthesized plan is committed to the spec directory. This spec covers the fan-out/judge/critic agents' own behavior and registry entry — it does NOT cover the human plan_approved/plan_rejected gate's signal delivery (separate feature) or the workflow's own orchestration sequencing beyond invoking this stage and waiting on its gate signal."

## Clarifications

### Session 2026-09-03

- Q: All N candidates come back malformed/empty (edge case only covered "a candidate", not "every candidate") — what should the stage do? → A: Fail the stage attempt and count it against the same bounded re-plan attempt budget (MAX_PLAN_ATTEMPTS=3) used for gap-triggered/rejection retries.
- Q: What does the gap-triggered additional candidate see as input? → A: The gap description plus the full synthesized plan, so its output slots into the existing plan rather than being a disconnected alternative.
- Q: How should candidate plans, judge rationale, and the completeness note be posted to the target-repo PR thread? → A: As a single combined PR comment per plan-attempt containing all three.

### Session 2026-09-04 (spec-review revision)

- Revises the 2026-09-03 malformed-candidates answer: the all-malformed/empty failure no longer shares `MAX_PLAN_ATTEMPTS` with gap-triggered/rejection retries. Rationale: sharing one retry budget across transient/infra failures and human-content iteration is a documented anti-pattern in resilience-engineering practice (retry-budget-pattern / circuit-breaker literature) — an API or parsing hiccup shouldn't consume the same budget a human needs for legitimate plan iteration. New: a separate `MAX_MALFORMED_RETRIES` (default 1) governs this failure class; see FR-013.
- Revises the 2026-09-03 PR-comment answer: the single combined comment stays, but it no longer posts every candidate in full on every attempt. Rationale: dumping N full alternatives — and re-dumping them on every retry — is a documented reviewer cognitive-overload/decision-fatigue anti-pattern; progressive disclosure (synthesized plan as the primary reading surface, candidates collapsed/linked, retries showing only the delta) is the established fix. See FR-014.

### Session 2026-09-04 (clarify)

- Q: What governs a synthesis-step or completeness-critic-step call itself failing/erroring (not malformed candidate output, but e.g. an API/timeout error in the judge or critic call)? → A: Falls to `MAX_PLAN_ATTEMPTS` — a synthesis- or critic-step error consumes the ordinary plan-attempt budget, not `MAX_MALFORMED_RETRIES`. `MAX_MALFORMED_RETRIES` (FR-013) stays scoped strictly to "every candidate in the set is malformed/empty." **Subsequently narrowed**: this answer is right for a *deterministic* failure (schema-validation rejection, dangling reference, unparseable envelope) and wrong for a *transient* one — as written it routes an API/timeout error to the human's iteration budget, which is exactly what the 2026-09-03 revision two bullets above split `MAX_MALFORMED_RETRIES` off to prevent. The split now lands in FR-013a (deterministic → `MAX_PLAN_ATTEMPTS`) and FR-013b (transient → orchestration-level retry).
- Q: FR-005/Key Entities mention a per-candidate "internal-consistency rating" consumed by synthesis, but its scale was unspecified. What granularity should it have? → A: Ordinal scale (e.g. 1-5), not binary or free-text.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Explore multiple architectural angles instead of committing to one (Priority: P1)

Once a spec has been approved, several independent architectural approaches to the same spec are produced at once from distinct angles (e.g. minimal-diff, clean-architecture, risk-first), so no single, possibly biased first attempt becomes the only option considered.

**Why this priority**: This is the core value of the stage — a single-answer architecture step would just be a plan-writer, not a panel. Every other story in this feature builds on having multiple candidates to work with.

**Independent Test**: Given an approved spec, verify that multiple independent candidate plans are produced, each from a distinct stated angle, and that no candidate is influenced by another candidate's output.

**Acceptance Scenarios**:

1. **Given** an approved spec, **When** the architecture stage runs, **Then** a set of independent candidate plans is produced, each addressing the same spec from a distinct architectural angle.
2. **Given** the candidates are being produced, **When** one candidate is generated, **Then** it has no visibility into any other candidate's output.
3. **Given** a spec with a larger number of measurable outcomes or a larger allotted budget, **When** the architecture stage runs, **Then** more candidates are produced than for a small, simple spec.

---

### User Story 2 - Synthesize one actionable plan from the candidates (Priority: P1)

The multiple candidate plans are reduced to a single plan and task breakdown that a human can approve and that the build stage can consume — picking the strongest overall candidate and pulling in good ideas from the others, with the reasoning made visible.

**Why this priority**: Build can only consume one plan. Without synthesis, having multiple candidates produces no forward progress — this is what turns exploration into a decision.

**Independent Test**: Given a completed set of candidate plans, verify a single synthesized plan and task breakdown is produced, that it references which candidate most influenced it, and that the rationale is visible to a human reviewer.

**Acceptance Scenarios**:

1. **Given** a completed set of candidate plans, **When** synthesis runs, **Then** exactly one plan and task breakdown is produced, along with a rationale explaining the choice.
2. **Given** the synthesized plan is ready, **When** a human reviews it, **Then** all candidate plans and the synthesis rationale are visible for them to compare against the chosen plan.

---

### User Story 3 - Catch coverage gaps the candidate panel missed (Priority: P2)

Before a human is asked to approve the synthesized plan, a fresh check looks for any measurable outcome the synthesized plan doesn't address, or an architectural angle none of the candidates tried, and — if it finds one — triggers one more targeted attempt to cover it before the plan reaches the human.

**Why this priority**: A fixed set of candidate angles only ever explores what it was prompted to explore. This story exists to catch what a fixed-angle panel would otherwise silently miss, but the panel and synthesis (Stories 1–2) are functional without it, hence P2.

**Independent Test**: Given a synthesized plan that omits a measurable outcome, verify the check identifies the gap and triggers exactly one additional targeted attempt before the plan is presented to a human; given a synthesized plan with no gaps, verify the check passes through with a short note and no extra attempt.

**Acceptance Scenarios**:

1. **Given** a synthesized plan that leaves a measurable outcome unaddressed, **When** the coverage check runs, **Then** it identifies the specific gap and triggers exactly one additional targeted candidate addressing it, followed by a re-synthesis.
2. **Given** a synthesized plan with no identifiable gap, **When** the coverage check runs, **Then** a short confirmation note is produced and the plan proceeds to the human decision without any extra attempt.
3. **Given** a gap-triggered extra attempt has already occurred for this plan revision, **When** the resulting re-synthesized plan is checked again, **Then** any further attempts count against the same bounded overall re-plan budget as an ordinary rejection, not a separate allowance.

### Edge Cases

- What happens when two or more candidates converge on effectively the same approach? Synthesis should still pick one winner and may note the convergence in its rationale; this is not an error condition.
- What happens when the coverage check identifies more than one gap at once? Only one additional targeted candidate is triggered per check per this feature's bounded design — covering multiple gaps in one pass, if needed, is not guaranteed.
- What happens when the number of candidates scales up for a complex spec but the allotted budget is exhausted before all of them complete? This feature does not define a fallback for a partial candidate set; that failure mode is a dependency on the surrounding orchestration, not defined here.
- What happens when a human rejects the synthesized plan for a reason unrelated to any gap the completeness-critic already checked? The rejection re-enters the fan-out/synthesis process with the human's feedback, consuming the same bounded attempt budget as a gap-triggered retry.
- What happens if a candidate's output does not resemble a usable plan/tasks/ADR set at all (e.g. empty or malformed)? Synthesis must still produce a single result from the remaining valid candidates rather than failing outright, provided at least one valid candidate exists.
- What happens if every candidate in the set is malformed or empty (zero valid candidates)? The stage fails that attempt and retries against a separate `MAX_MALFORMED_RETRIES` budget (default 1), distinct from the `MAX_PLAN_ATTEMPTS` budget used for gap-triggered retries or human rejection — an all-empty/malformed result is an infra/transient failure class, not a content decision.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST produce multiple independent candidate plans for the same approved spec, each from a distinct, explicitly stated architectural angle.
- **FR-002**: System MUST default to 3 candidates and MUST support scaling that number up based on the spec's complexity (e.g. number of measurable outcomes) or an allotted budget.
- **FR-003**: Each candidate MUST be produced with no visibility into any other candidate's output.
- **FR-004**: System MUST produce exactly one synthesized plan and task breakdown from the full set of candidates, choosing a winning approach and incorporating strong ideas from the others where applicable.
- **FR-005**: System MUST evaluate each candidate against the spec's measurable outcomes and against that candidate's own internal consistency as a distinct scoring step, producing structured per-candidate scores and a per-outcome coverage tag (see FR-005a, SC-006) rather than only free-form judge prose. The internal-consistency rating MUST be an ordinal scale (e.g. 1-5), not a binary flag or free-text list.
- **FR-005a**: A separate synthesis step MUST consume those structured scores — not the scoring step's free-form reasoning — to produce the single synthesized plan required by FR-004. Scoring and synthesis MUST be distinguishable steps (separate model calls, or clearly separated phases within one call), so an evaluation error is not silently baked into the generated artifact as if it were fact.
- **FR-006**: System MUST make all candidate plans and the synthesis rationale visible to a human reviewer alongside the synthesized plan.
- **FR-007a**: System MUST run a completeness check on the synthesized plan that determines, per measurable outcome, whether it is addressed. This is a closed-form, checkable determination.
- **FR-007b**: System MUST additionally check whether an architectural angle none of the candidates tried appears to have been missed. This check MUST run as an independent pass — not appended to the synthesis judge's own context — to reduce (not eliminate) the risk of the critic sharing the synthesis step's blind spots. Because detecting an untried angle is an open-ended, unknown-unknowns judgment rather than a closed-form check, a "no gap identified" result from this check MUST be treated as "no additional angle was identified," not as confidence that none exists.
- **FR-008**: On finding no gap under FR-007a and no angle identified under FR-007b, the completeness check MUST produce a short confirmation note and allow the synthesized plan to proceed to the human decision unchanged.
- **FR-009**: On finding a gap under FR-007a or an untried angle under FR-007b, the completeness check MUST trigger exactly one additional targeted candidate addressing that specific gap/angle, followed by a re-synthesis that folds it in. This targeted candidate MUST receive the gap description and the full synthesized plan as input (unlike the original N candidates, which have no visibility into each other or into any synthesized plan).
- **FR-010**: moved to the "Consumer obligations" subsection below — its charging is 005's to implement, not this module's.
- **FR-011**: Only the final synthesized plan (and its supporting ADRs) MUST be persisted to the spec's directory — individual candidate plans are not committed as separate artifacts there.
- **FR-012**: System MUST register this capability (candidates, judge/synthesis, completeness-critic) as a single named agent entry.
- **FR-013**: If every candidate in a set is malformed or empty (zero valid candidates), the stage MUST fail that attempt and retry, in-process, against a separate, smaller `MAX_MALFORMED_RETRIES` budget (default: 1) — not the `MAX_PLAN_ATTEMPTS` budget used by FR-010. This class is scoped by **where it is observable, not by why it happened**: "every candidate came back malformed or empty" is a fact only this module can see (candidates are validated here, never on the wire to a caller), regardless of whether the underlying cause was a content problem or an infra hiccup (e.g. a 429 that made every candidate call fail the same way). Exhausting `MAX_MALFORMED_RETRIES` MUST fail the stage rather than falling through to `MAX_PLAN_ATTEMPTS`, and MUST NOT be treated as a plain `MAX_PLAN_ATTEMPTS`-consuming failure — see FR-013's Consumer obligations note below. `MAX_MALFORMED_RETRIES` is scoped strictly to this "all candidates malformed/empty" case; it never governs a scoring-, synthesis-, or critic-step failure (FR-013a).
- **FR-013a**: A synthesis-step or completeness-critic-step call itself failing or erroring (as distinct from FR-013's "every candidate malformed" case, which is never routed here) MUST be classified as **deterministic** (a schema-validation rejection, a dangling candidate reference, an unparseable envelope) or **transient** (API 429/5xx, timeout, connection reset). A deterministic failure is a **consumer obligation**: this module propagates it as a plain exception, and it is the caller — not this module — that MUST consume the ordinary `MAX_PLAN_ATTEMPTS` budget (FR-010) for it, never `MAX_MALFORMED_RETRIES`. A transient failure MUST NOT consume `MAX_PLAN_ATTEMPTS` either; it MUST be retried at the orchestration layer instead, because the whole stage runs as one unit and charging a plan attempt would re-run the entire `N + 3`-call fan-out for one 429. **No task in this feature charges either budget** — like FR-010, both halves are consumer obligations this module cannot discharge on its own, since it deliberately does not name `MAX_PLAN_ATTEMPTS`. They land as `specs/005-pipeline-mode-signals-escalation/`'s FR-014, and as CO-2/CO-2a in `contracts/architect-agent-interface.md`'s Consumer obligations table.
- **FR-014**: System MUST post the synthesized plan, judge/synthesis rationale, and completeness note to the target-repo PR thread together as a single combined comment per plan-attempt, not as separate comments. The N candidate plans MUST be included in that same comment but collapsed (e.g. behind a details/summary disclosure) or linked, not inline in full, so the synthesized result is the primary reading surface. On any attempt after the first, the comment MUST lead with a short delta line describing what changed since the prior attempt (e.g. the rejection reason or gap addressed) rather than re-presenting everything as if it were the first attempt.
- **FR-015**: No artifact this stage produces or exposes to a model — a candidate prompt, a candidate's returned `plan_md`/`tasks_md`, the synthesis or critic prompt, or the posted PR comment — MUST contain the target repo's clone credential (the GitHub App installation token embedded in the clone URL). Structurally: the token MUST be stripped from the checkout's `origin` URL before any candidate, scoring, synthesis, or critic call runs, and MUST be re-attached only for the push step, in argv, never written back to the checkout's `.git/config`.

### Consumer obligations (owned and delivered by `specs/005-pipeline-mode-signals-escalation/`)

FR-010 and half of FR-013a/FR-013b describe budget rules this module states but cannot itself enforce, because this module deliberately never names or tracks `MAX_PLAN_ATTEMPTS` (see Assumptions). They are requirements of *this* feature's design — 004 is where they originate — but their implementation is 005's `run_architect_stage()` caller, per `contracts/architect-agent-interface.md`'s Consumer obligations table (CO-1 through CO-4) and `specs/005-pipeline-mode-signals-escalation/spec.md`'s FR-014.

- **FR-010**: Any gap-triggered additional attempt MUST be counted against the same bounded overall re-plan attempt budget (default: 3) used for human-rejection retries — not tracked as a separate, unbounded allowance. (Delivered by 005's FR-014, CO-1.)
- **FR-013a's deterministic half** (a scoring/synthesis/critic validation failure): charged to `MAX_PLAN_ATTEMPTS` by the caller. (Delivered by 005's FR-014, CO-2.)
- **FR-013b** (a scoring/synthesis/critic *transient* failure): retried at the orchestration layer, never charged to `MAX_PLAN_ATTEMPTS`. (Delivered by 005's FR-014, CO-2a.)

### Key Entities

- **Architect Candidate**: One independently produced plan/task/ADR set addressing the spec from one stated angle, with no knowledge of other candidates.
- **Synthesis Result**: The single chosen plan/task/ADR set, plus a rationale explaining which candidate most influenced it and what was drawn from the others.
- **Completeness Note**: The short output of the coverage check — either a confirmation of no gap, or a description of the specific gap that triggered one more candidate.
- **Candidate Score**: The structured, per-candidate output of the FR-005 scoring step — a per-measurable-outcome coverage tag plus an internal-consistency rating on an ordinal scale (e.g. 1-5) — consumed by the FR-005a synthesis step and by SC-006's coverage map.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every architecture-stage run on an approved spec produces more than one independent candidate before any synthesis happens.
- **SC-002**: Every completed candidate set results in exactly one synthesized plan with a visible rationale, never zero and never more than one.
- **SC-003**: Every synthesized plan is checked for coverage gaps before reaching a human, and any gap found results in exactly one additional targeted attempt, never an unbounded chain of attempts.
- **SC-004**: 100% of stage comments make the synthesized plan, judge/synthesis rationale, coverage map, and completeness note visible to the human reviewer in full, alongside every candidate plan **in full or via an explicit pointer to where its full text is recorded** (e.g. a Braintrust span) when the comment's size budget requires collapsing or truncating a candidate.

  *Narrowed from "100% of candidate plans … are visible … alongside the synthesized plan,"* which FR-014's own size-budget truncation (and its documented last-resort drop of the collapsed candidate section) makes unsatisfiable at scale — a success criterion this feature's own comment-assembly logic would violate by design is a spec defect, not an acceptable trade-off. The half above is what FR-014's truncation-with-notice behavior actually guarantees: the synthesized result is never dropped, and a truncated candidate is never *silently* lost, only made indirect.
- **SC-005**: The number of candidates produced for a spec scales with that spec's stated complexity or budget rather than staying fixed regardless of size.
- **SC-006**: Every synthesized plan's supporting judge output includes an explicit per-measurable-outcome coverage map (which candidate covers which outcome, yes/no) rather than free-text rationale alone — coverage is machine-checkable, not just non-empty.
- **SC-007**: Every stage comment carries an `attempt` + spec-sha marker sufficient to correlate a later human approve/reject decision back to the attempt that produced the plan.

  *Narrowed from "every human approve/reject decision is recorded as a plain fact against the PR."* Capturing the decision itself requires the gate that `specs/005-pipeline-mode-signals-escalation/` owns, which this feature does not ship — a success criterion this feature cannot satisfy by construction is a spec defect, not a documentation footnote, and it also distorts `candidate_count`, whose input is the SC count. The correlation half above is what 004 actually lands and is scoreable today; the decision-capture half belongs to 005.

## Assumptions

- The bounded re-plan attempt budget defaults to 3 (`MAX_PLAN_ATTEMPTS=3`), matching the pipeline design doc's stated default, and is shared between gap-triggered retries and ordinary human-rejection retries.
- The exact function mapping spec complexity/budget to a candidate count is left to be defined at implementation time; this feature only requires that the count is not hardcoded regardless of spec size.
- The human plan_approved/plan_rejected decision's delivery mechanism (e.g. a parsed PR comment routed through a separate trigger bridge) is a dependency of this feature, not part of it.
- The orchestration sequencing that invokes this stage inside a larger pipeline run, and waits on its gate, is a dependency of this feature, not something this feature implements itself.
- Because every candidate, the judge, and the completeness-critic only ever produce and consume text/markdown, none of them require a code-execution environment — this is treated as an inherent property of the stage's inputs/outputs, not an implementation choice this spec mandates.
- Defaulting to 3 candidates (FR-002) is not an arbitrary pick — multi-agent fan-out/synthesis literature (e.g. Mixture-of-Agents) cites 3 as a defensible sweet spot for this class of pattern.
- `MAX_MALFORMED_RETRIES` (FR-013) defaults to 1 and is deliberately kept separate from `MAX_PLAN_ATTEMPTS`, scoped by observability — an all-malformed candidate set is only detectable inside this module, regardless of whether the underlying cause was transient or content-related.
- The target repo's clone credential (FR-015) never appears in a checkout's `.git/config`, a model prompt, a model response, or a posted PR comment; it exists only in the clone/push argv and the parent process's popped-and-restored environment.
- SC-007 covers only the correlation marker this feature ships. The approve/reject logging it enables is a lightweight, non-scientific trend signal, not a validated quality metric — it requires no new eval harness, only that the gate decision `specs/005-pipeline-mode-signals-escalation/` introduces is retained as data against the marker.
