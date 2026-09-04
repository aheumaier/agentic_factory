# Feature Specification: Automated-Review and Security-Review Wiring

**Feature Branch**: `007-automated-security-review`

**Created**: 2026-09-02

**Status**: Draft

**Input**: User description: "Automated-Review and Security-Review stages for the multi-agent SDLC pipeline (docs/70-multi-agent-pipeline-design.md §2/§4), positioned after Quality-Gate in the build loop. Automated-Review wraps a 5-subagent review bundle (code-reviewer, silent-failure-hunter, comment-analyzer, pr-test-analyzer, type-design-analyzer) run against the build's PR diff: in the pipeline's rigorous mode, code-reviewer and silent-failure-hunter findings are blocking while the other 3 are always advisory; in the relaxed mode all 5 are advisory only, nothing blocks. Security-Review wraps a security-focused review of the same diff and is always blocking in both modes — a safety control, never a speed/quality tradeoff, per the design doc's explicit statement that this is the one stage never relaxed by mode. Findings from both stages are posted to the target-repo PR as comments. Automated-Review's blocking findings route back to Build with the specific finding as feedback, sharing the same bounded retry budget as Eval-Gate/Quality-Gate. Security-Review is gated by an explicit human decision (security_cleared / security_rejected:<feedback>) rather than an automatic pass/fail threshold, and a rejection is a hard stop that re-enters the Build loop directly with no separate retry-around mechanism of its own — also sharing the same bounded budget, so a security rejection can exhaust it same as any other failure. This spec covers the wiring, pass/fail/advisory contract, and feedback routing for both stages — it does NOT cover the individual review subagents' own internal logic (pre-existing, reused as-is), the mode switch/shared retry budget/escalation mechanics (separate feature), or the exact severity threshold that should trigger security_rejected (explicitly left open per the design doc's own open questions, to be decided by the human reviewer using judgment until a concrete threshold is defined)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Catch code-quality and silent-failure problems before they ship, when rigor is on (Priority: P1)

After Quality-Gate passes, the build's diff is checked by a bundle of automated reviewers; in the pipeline's rigorous mode, two of them (general code review and a check for silently-swallowed failures) can block the run and send it back for another attempt, while the rest only ever add advisory notes.

**Why this priority**: This is the primary quality backstop before a human security reviewer ever sees the diff — catching a blocking-class issue here is cheaper than catching it later, and every other story in this feature depends on this pass/advisory split existing.

**Independent Test**: Given a diff with a code-reviewer-flagged blocking issue in rigorous mode, verify the run is sent back to Build with that finding as feedback; given a diff with only advisory-class findings, verify the run proceeds without blocking.

**Acceptance Scenarios**:

1. **Given** a build's diff has a finding from the code-review or silent-failure checks in rigorous mode, **When** Automated-Review runs, **Then** the run is sent back to Build with that specific finding as feedback, consuming one attempt from the shared retry budget.
2. **Given** a build's diff has only findings from the other three checks (comment quality, test coverage quality, type design) in rigorous mode, **When** Automated-Review runs, **Then** those findings are posted as advisory notes and the run proceeds without blocking.
3. **Given** a build's diff has no findings at all, **When** Automated-Review runs, **Then** the run proceeds with no notes posted beyond confirmation that the check ran clean.

---

### User Story 2 - Relax automated review without losing its visibility, in the fast mode (Priority: P2)

In the pipeline's relaxed mode, the same five automated reviewers still run and still post their findings, but none of them can block the run — every finding is advisory only.

**Why this priority**: This preserves the value of Story 1's visibility even when speed is prioritized, but it's a variant of already-established behavior rather than new capability, hence lower priority.

**Independent Test**: Given the identical diff and findings as a rigorous-mode run, but with the run started in relaxed mode, verify none of the five findings block the run, even ones that would have blocked in rigorous mode.

**Acceptance Scenarios**:

1. **Given** a build's diff has a code-review or silent-failure finding that would block in rigorous mode, **When** Automated-Review runs on a relaxed-mode run, **Then** the finding is posted as advisory and the run proceeds without blocking.

---

### User Story 3 - Require an explicit human sign-off on security, always (Priority: P1)

Regardless of the pipeline's mode, the build's diff is checked by a security-focused review, and the run cannot proceed past this point without an explicit human decision that the findings (if any) are acceptable — a rejection sends the run back to redo the work, and this never happens automatically based on a score.

**Why this priority**: This is the pipeline's one designated always-blocking safety control; it is equally critical in both modes and has no lesser-priority variant, so it sits at the top tier alongside Story 1.

**Independent Test**: Drive a run through Security-Review in both rigorous and relaxed mode and verify in both cases the run halts and waits for an explicit human decision, never proceeding on its own regardless of what findings (or lack of findings) were posted.

**Acceptance Scenarios**:

1. **Given** Security-Review has posted its findings (including the case of no findings at all) to the PR, **When** the stage completes, **Then** the run halts and waits for an explicit human decision rather than proceeding automatically.
2. **Given** a run is waiting on a Security-Review decision, **When** a clearance decision arrives, **Then** the run proceeds past this stage.
3. **Given** a run is waiting on a Security-Review decision, **When** a rejection decision with feedback arrives, **Then** the run is sent back to Build directly with that feedback, with no separate Security-Review-specific retry loop of its own, consuming one attempt from the shared retry budget.
4. **Given** a run in relaxed mode, **When** it reaches Security-Review, **Then** it is gated exactly the same way as a run in rigorous mode — no automatic proceed, no relaxed threshold.

### Edge Cases

- What happens when Automated-Review's blocking-class checks (in rigorous mode) find nothing but the advisory-class checks find several issues? The run proceeds; all advisory findings are still posted for visibility even though nothing blocked.
- What happens when a Security-Review rejection arrives after the shared retry budget has already been exhausted by earlier failures in the same run? Per this feature's design, a security rejection consumes from the same shared budget as any other stage — if the budget is already exhausted, this triggers the same escalation behavior as any other exhaustion (defined by a separate feature), not a special case.
- What happens if the same diff is re-submitted to Automated-Review or Security-Review after a Build retry with no actual change relevant to a prior finding? Each stage re-evaluates the current diff independently each attempt; a finding may recur and block/gate again.
- What happens when Security-Review posts zero findings? The run still halts and waits for an explicit human decision — absence of findings does not bypass the requirement for a human sign-off.
- What happens if a human's clearance or rejection decision references a diff revision that has since changed (e.g. Build pushed again before the decision arrived)? This feature does not define reconciliation logic for that race; the decision is assumed to apply to the run's current state when received.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST run the five-subagent Automated-Review bundle (code review, silent-failure detection, comment quality, test coverage quality, type design) against the build's diff after Quality-Gate.
- **FR-002**: In the pipeline's rigorous mode, findings from the code-review and silent-failure checks MUST be treated as blocking; findings from the other three checks MUST always be treated as advisory.
- **FR-003**: In the pipeline's relaxed mode, findings from all five checks MUST be treated as advisory only — none may block the run.
- **FR-004**: System MUST post all findings from Automated-Review (blocking and advisory) to the target-repo pull request as comments, regardless of mode.
- **FR-005**: On a blocking finding, system MUST route the run back to Build with that specific finding as feedback, and MUST consume one attempt from the shared build-loop retry budget.
- **FR-006**: System MUST run a security-focused review against the build's diff, independent of the pipeline's mode.
- **FR-007**: Security-Review MUST post its findings (or an explicit statement that none were found) to the target-repo pull request.
- **FR-008**: System MUST halt the run after Security-Review completes and MUST wait for an explicit human clearance-or-rejection decision before proceeding, in both pipeline modes, with no automatic threshold-based pass.
- **FR-009**: On a clearance decision, system MUST allow the run to proceed past Security-Review.
- **FR-010**: On a rejection decision (carrying feedback), system MUST route the run back to Build directly with that feedback, and MUST consume one attempt from the same shared build-loop retry budget used by Eval-Gate, Quality-Gate, and Automated-Review's blocking findings — Security-Review MUST NOT maintain a separate retry loop of its own.
- **FR-011**: System MUST NOT let Security-Review's blocking behavior be relaxed, skipped, or downgraded by the pipeline's mode choice under any circumstance.

### Key Entities

- **Automated-Review Finding**: One reported issue from one of the five bundled checks, tagged as blocking or advisory according to which check produced it and the run's mode.
- **Security-Review Finding**: One reported security-relevant issue (or the explicit absence of any) from the security-focused review.
- **Security Decision**: The human's explicit clearance-or-rejection outcome that gates progress past Security-Review.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of rigorous-mode runs with a code-review or silent-failure finding are sent back to Build with that finding as feedback; 100% of relaxed-mode runs with the same finding proceed without blocking.
- **SC-002**: 100% of Automated-Review findings, blocking or advisory, are posted to the PR regardless of mode.
- **SC-003**: 100% of runs, in both modes, halt at Security-Review and require an explicit human decision before proceeding — zero runs proceed automatically past this stage.
- **SC-004**: 100% of Security-Review rejections route back to Build directly with the rejection's feedback, consuming exactly one attempt from the shared retry budget, with zero cases of a separate Security-Review-specific retry loop being used.
- **SC-005**: Zero cases across either mode where Security-Review's blocking requirement is bypassed, relaxed, or auto-resolved.

## Assumptions

- The five automated-review subagents' own internal review logic is pre-existing and reused as-is; this feature only defines which of their outputs block versus advise, and how blocking findings route back to Build.
- The exact severity threshold that should trigger a `security_rejected` decision versus an advisory-only security note is left to human reviewer judgment for now, per the design doc's own stated open question — this feature does not define an automatic threshold.
- The mode switch itself, the shared retry budget's exhaustion/escalation behavior, and the decision-delivery mechanism (e.g. a parsed PR comment routed through a separate trigger bridge) are all dependencies of this feature, defined by separate features, not implemented here.
- "Hard stop, no auto-retry-around" for Security-Review means a rejection always routes back to Build rather than looping within Security-Review itself attempting an automatic fix; it does not mean the run cannot ever retry — it means the retry happens via the shared Build loop, not a Security-Review-local one.
