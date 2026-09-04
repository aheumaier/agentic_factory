# Feature Specification: Quality-Gate

**Feature Branch**: `006-quality-gate`

**Created**: 2026-09-02

**Status**: Draft

**Input**: User description: "Quality-Gate stage for the multi-agent SDLC pipeline (docs/70-multi-agent-pipeline-design.md §2's Quality-Gate subsection), positioned right after Eval-Gate in the pipeline, in the same objective-measurable-threshold family — extends the same success-criteria-parsing pattern the existing eval gate already uses rather than inventing a parallel mechanism. Enforces three concrete, blocking checks on a build's diff: (1) Traceability — every measurable-outcome bullet parsed from the spec's Measurable Outcomes section must be referenced at least once in the diff (test name, docstring, or commit message); (2) Documentation — every new/changed public function/class has a docstring, and any diff touching orchestration/harness code or introducing a new pipeline stage/layer must also touch a corresponding docs file, checked structurally (diff touches docs whenever diff touches orchestration/harness), not semantically judged; (3) Test coverage — combined line coverage across unit+integration+e2e tests meets or exceeds a configured threshold (default >=80%), read from whatever coverage tool the target repo already reports. Blocking only in 'full' mode per the pipeline's per-stage contract table (skipped entirely in 'vibe' mode — that mode switch itself is a separate feature). On failure, routes back to Build with the specific failing attribute (traceability/documentation/coverage) as feedback, sharing the same bounded retry budget as Eval-Gate/Automated-Review/Security-Review. This spec covers only the Quality-Gate check itself and its pass/fail/feedback contract — it does NOT cover the workflow's mode switch, retry budget mechanics, or escalation (separate feature), nor the Eval-Gate it extends the pattern from (pre-existing, already implemented)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Confirm every measurable outcome is actually covered by the build (Priority: P1)

After a build produces a diff, every measurable outcome the spec claims to deliver is checked for at least one concrete reference in that diff — a test name, a docstring, or a commit message — so a build cannot silently skip an outcome and still look complete.

**Why this priority**: This is the check most directly tied to whether the build actually did what the spec asked; the other two checks (documentation, coverage) matter but this one catches a build that omitted required behavior entirely.

**Independent Test**: Given a spec with several measurable outcomes and a build diff that references all but one of them, verify the check fails and names the specific unreferenced outcome; given a diff that references all of them, verify the check passes.

**Acceptance Scenarios**:

1. **Given** a spec with measurable outcomes and a build diff, **When** every outcome has at least one reference (test name, docstring, or commit message) in the diff, **Then** the traceability check passes.
2. **Given** the same setup but one outcome has zero references anywhere in the diff, **When** the check runs, **Then** it fails and identifies that specific outcome as unreferenced.

---

### User Story 2 - Confirm new code is documented (Priority: P2)

Every new or changed public function or class in the build's diff is checked for a docstring, and any diff that touches orchestration or harness code, or introduces a new pipeline stage, is checked for a corresponding change to a documentation file — structurally, by whether both kinds of files changed together, not by judging the content.

**Why this priority**: Documentation gaps compound over time and are cheap to check for mechanically, but a missing docstring is less immediately harmful than an uncovered measurable outcome, hence lower priority than Story 1.

**Independent Test**: Given a diff that adds a new public function with no docstring, verify the check fails and names the function; given a diff that touches orchestration code with no accompanying documentation file change, verify the check fails and names the gap; given a diff satisfying both, verify the check passes.

**Acceptance Scenarios**:

1. **Given** a diff that adds or changes a public function or class, **When** it lacks a docstring, **Then** the documentation check fails and identifies which function or class is missing one.
2. **Given** a diff that touches orchestration or harness code, or introduces a new pipeline stage, **When** it does not also touch a corresponding documentation file, **Then** the documentation check fails and identifies the gap.
3. **Given** a diff satisfying both conditions above, **When** the check runs, **Then** it passes.

---

### User Story 3 - Confirm the change is adequately tested overall (Priority: P2)

The combined test coverage across all test levels (unit, integration, end-to-end) is checked against a configured minimum threshold, using whatever coverage measurement the target repository already produces.

**Why this priority**: Overall coverage is a broader, slower-moving signal than the outcome-specific traceability check in Story 1, and is equally important to Story 2's documentation check, hence the same priority tier.

**Independent Test**: Given a build whose reported combined coverage is below the configured threshold, verify the check fails and reports the shortfall; given coverage at or above the threshold, verify it passes.

**Acceptance Scenarios**:

1. **Given** a build's reported combined coverage meets or exceeds the configured threshold, **When** the check runs, **Then** it passes.
2. **Given** a build's reported combined coverage falls below the configured threshold, **When** the check runs, **Then** it fails and reports the shortfall against the threshold.

### Edge Cases

- What happens when the target repository reports no coverage data at all (e.g. tooling not configured)? The coverage check cannot pass without a number to evaluate — this should be treated as a failure with a reason distinct from "below threshold," not a silent pass.
- What happens when a measurable outcome is addressed only implicitly (e.g. covered by a broader test with no reference to that outcome's identifier)? Per this feature's structural approach, it is not counted as referenced unless it names the outcome; this may produce a false failure but is the defined behavior.
- What happens when more than one of the three checks fails at once? All applicable failing checks should be reported together as feedback, not just the first one found, so a retry can address everything in one pass.
- What happens when a diff touches orchestration/harness code and the documentation file it touches is unrelated to the actual change? The structural check only verifies that some documentation file changed alongside the orchestration/harness change — it does not judge whether the two are topically related.
- What happens on a spec with zero measurable outcomes listed? The traceability check has nothing to verify and should pass vacuously rather than fail or error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST parse every measurable-outcome bullet from the spec associated with a build's branch.
- **FR-002**: System MUST check that each parsed measurable outcome is referenced at least once in the build's diff, via a test name, a docstring, or a commit message.
- **FR-003**: System MUST fail the traceability check and identify the specific unreferenced outcome(s) whenever one or more parsed outcomes has zero references in the diff.
- **FR-004**: System MUST check that every new or changed public function or class in the diff has a docstring, and MUST fail the documentation check and identify the specific function(s)/class(es) missing one whenever this is not the case.
- **FR-005**: System MUST check, whenever a diff touches orchestration or harness code or introduces a new pipeline stage/layer, that the same diff also touches at least one documentation file, and MUST fail the documentation check and identify this gap whenever it does not.
- **FR-006**: System MUST check the build's combined test coverage (unit + integration + e2e) against a configured minimum threshold (default 80%), using the coverage figure already reported by the target repository's own tooling.
- **FR-007**: System MUST fail the coverage check and report the specific shortfall whenever combined coverage falls below the configured threshold, or whenever no coverage figure is available at all.
- **FR-008**: System MUST report all applicable failing checks together as feedback when more than one fails in the same run, rather than reporting only the first failure found.
- **FR-009**: System MUST pass the traceability check vacuously when the spec lists zero measurable outcomes.
- **FR-010**: On any failing check, system MUST route feedback back to the build stage naming which specific check(s) failed and why, so the next attempt can address it.
- **FR-011**: This gate's checks MUST be blocking only under the pipeline's rigorous mode; under the pipeline's relaxed mode, this gate is skipped entirely (mode selection itself is defined by a separate feature this one depends on).
- **FR-012**: A failing result from this gate MUST consume one attempt from the same shared bounded retry budget used by the pipeline's other build-loop gates (evaluation, automated review, security review), not a separate budget of its own.

### Key Entities

- **Measurable Outcome**: One parsed bullet from the spec's Measurable Outcomes section, identified well enough to be matched against diff content.
- **Quality-Gate Result**: The combined pass/fail outcome of the three checks (traceability, documentation, coverage), including specific failure reasons for any that failed.
- **Coverage Threshold**: The configured minimum combined coverage percentage a build must meet.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of builds whose diff references every parsed measurable outcome pass the traceability check; 100% of builds missing at least one reference fail it and receive the specific missing outcome(s) as feedback.
- **SC-002**: 100% of builds with fully docstringed new/changed public functions/classes and matching documentation-file changes (when orchestration/harness code changed) pass the documentation check; any gap is reported with the specific missing item.
- **SC-003**: 100% of builds at or above the configured coverage threshold pass the coverage check; any shortfall (including missing coverage data entirely) is reported with the specific gap.
- **SC-004**: Every gate run that fails one or more checks reports all failing checks together in a single feedback round, not spread across multiple retries.
- **SC-005**: Every failing gate result consumes exactly one attempt from the shared build-loop retry budget, with zero cases of this gate's failures escaping that shared budget.

## Assumptions

- The coverage threshold defaults to 80% combined across unit, integration, and e2e tests, matching the pipeline design doc's stated default; the exact figure is expected to be configurable rather than fixed permanently at this number.
- "Referenced in the diff" for traceability is satisfied by the measurable outcome's identifier appearing literally in a test name, a docstring, or a commit message — this feature does not attempt to judge semantic coverage beyond that literal match.
- The mode switch that makes this gate blocking-only in the rigorous mode, and the shared retry budget it draws from, are both dependencies of this feature (defined by the orchestration-level mode/signal/escalation feature), not implemented here.
- The pre-existing evaluation gate this feature's parsing pattern extends is already implemented and unchanged by this feature.
