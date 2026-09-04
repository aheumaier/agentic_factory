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
- What happens if every candidate in the set is malformed or empty (zero valid candidates)? The stage fails that attempt and the failure is counted against the same bounded re-plan attempt budget (`MAX_PLAN_ATTEMPTS=3`) as a gap-triggered retry or human rejection, not a separate failure path.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST produce multiple independent candidate plans for the same approved spec, each from a distinct, explicitly stated architectural angle.
- **FR-002**: System MUST default to 3 candidates and MUST support scaling that number up based on the spec's complexity (e.g. number of measurable outcomes) or an allotted budget.
- **FR-003**: Each candidate MUST be produced with no visibility into any other candidate's output.
- **FR-004**: System MUST produce exactly one synthesized plan and task breakdown from the full set of candidates, choosing a winning approach and incorporating strong ideas from the others where applicable.
- **FR-005**: The synthesis MUST evaluate each candidate against the spec's measurable outcomes and against that candidate's own internal consistency.
- **FR-006**: System MUST make all candidate plans and the synthesis rationale visible to a human reviewer alongside the synthesized plan.
- **FR-007**: System MUST run a completeness check on the synthesized plan that determines whether every measurable outcome is addressed and whether an architectural angle none of the candidates tried appears to have been missed.
- **FR-008**: On finding no gap, the completeness check MUST produce a short confirmation note and allow the synthesized plan to proceed to the human decision unchanged.
- **FR-009**: On finding a gap, the completeness check MUST trigger exactly one additional targeted candidate addressing that specific gap, followed by a re-synthesis that folds it in. This targeted candidate MUST receive the gap description and the full synthesized plan as input (unlike the original N candidates, which have no visibility into each other or into any synthesized plan).
- **FR-010**: Any gap-triggered additional attempt MUST be counted against the same bounded overall re-plan attempt budget (default: 3) used for human-rejection retries — not tracked as a separate, unbounded allowance.
- **FR-011**: Only the final synthesized plan (and its supporting ADRs) MUST be persisted to the spec's directory — individual candidate plans are not committed as separate artifacts there.
- **FR-012**: System MUST register this capability (candidates, judge/synthesis, completeness-critic) as a single named agent entry.
- **FR-013**: If every candidate in a set is malformed or empty (zero valid candidates), the stage MUST fail that attempt and count it against the same bounded re-plan attempt budget as FR-010, rather than defining a separate failure/retry path.
- **FR-014**: System MUST post the candidate plans, judge/synthesis rationale, and completeness note to the target-repo PR thread together as a single combined comment per plan-attempt, not as separate comments.

### Key Entities

- **Architect Candidate**: One independently produced plan/task/ADR set addressing the spec from one stated angle, with no knowledge of other candidates.
- **Synthesis Result**: The single chosen plan/task/ADR set, plus a rationale explaining which candidate most influenced it and what was drawn from the others.
- **Completeness Note**: The short output of the coverage check — either a confirmation of no gap, or a description of the specific gap that triggered one more candidate.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every architecture-stage run on an approved spec produces more than one independent candidate before any synthesis happens.
- **SC-002**: Every completed candidate set results in exactly one synthesized plan with a visible rationale, never zero and never more than one.
- **SC-003**: Every synthesized plan is checked for coverage gaps before reaching a human, and any gap found results in exactly one additional targeted attempt, never an unbounded chain of attempts.
- **SC-004**: 100% of candidate plans and the synthesis rationale are visible to the human reviewer at decision time, alongside the synthesized plan.
- **SC-005**: The number of candidates produced for a spec scales with that spec's stated complexity or budget rather than staying fixed regardless of size.

## Assumptions

- The bounded re-plan attempt budget defaults to 3 (`MAX_PLAN_ATTEMPTS=3`), matching the pipeline design doc's stated default, and is shared between gap-triggered retries and ordinary human-rejection retries.
- The exact function mapping spec complexity/budget to a candidate count is left to be defined at implementation time; this feature only requires that the count is not hardcoded regardless of spec size.
- The human plan_approved/plan_rejected decision's delivery mechanism (e.g. a parsed PR comment routed through a separate trigger bridge) is a dependency of this feature, not part of it.
- The orchestration sequencing that invokes this stage inside a larger pipeline run, and waits on its gate, is a dependency of this feature, not something this feature implements itself.
- Because every candidate, the judge, and the completeness-critic only ever produce and consume text/markdown, none of them require a code-execution environment — this is treated as an inherent property of the stage's inputs/outputs, not an implementation choice this spec mandates.
