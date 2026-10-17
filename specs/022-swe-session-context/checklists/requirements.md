# Specification Quality Checklist: swe-agent Session Context

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-17
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs). See note 1.
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders. See note 1.
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain. The input was approved by the operator, and the defaults are listed
  in the spec's Assumptions (see note 2).
- [ ] Requirements are testable and unambiguous. See note 4.
- [ ] Success criteria are measurable. See note 4.
- [x] Success criteria are technology-agnostic (no implementation details). See note 1.
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [ ] Dependencies and assumptions identified. See note 4.

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification. See note 1.

## Notes

1. The spec names existing repo parts (`harness/swe-agent/agent.py`, `build_options`, `run_implement`,
   `IMPLEMENT_PROMPT`, `TASK_PROMPT`, `MAX_BUILD_ATTEMPTS`, the exit codes 75 and 77, `setting_sources`, specs 009,
   011, 015, 018, 019, 021) and the SDK options the operator named in the input (`agents`, `max_turns`,
   `max_budget_usd`). That is context for what changes and the operator's own choice, the convention in this repo's
   specs, not a design choice made here. The exit code number, how the ceilings reach the sandbox, and how the
   explorer's answer is cut are left to `/speckit-plan`.
2. The input was approved word for word by the operator on 2026-10-17. Two facts that differ from it are written under
   the input (spec 018 records no turn count; a limit stop ends silently today). Defaults chosen while writing, stated
   in the Assumptions and to the operator: a ceiling stop uses one Build attempt (a judgment call), the ceilings stay
   off until 10 sessions are recorded and then sit at about twice the 95th percentile, the 1,500-token answer limit,
   the explorer's model defaults to the writer's, the cost ceiling is capped by the run's remaining cost cap, and the
   20% keep threshold in SC-007.
3. Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`.
4. A design review on 2026-10-17 (`review-2026-10-17.md` in this directory) found two wrong facts. A limit stop
   does not end silently: the SDK raises an error, and the run exits 1 or is misread as a seat outcome. The writer has
   the CLI's full default tool set, not six tools, because `build_options` sets `allowed_tools` and not `tools`. Note 2
   repeats the first fact. The review also found that FR-014's final failure and FR-015's changes to spec 018 are
   undefined. The items above are unticked until those findings are applied or rejected with a reason.
