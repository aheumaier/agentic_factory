# Specification Quality Checklist: Dev-Harness Hardening

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-10
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- "No implementation details" is interpreted for a developer-tooling feature: the
  *subject* of the spec is the repo's Claude Code harness, so naming the harness's own
  artifacts (hooks, `git commit`, `.env`, `registry/agents/`, `specs/NNN-*`) is
  domain vocabulary, not implementation choice. How snapshots are stored, the
  exception variable's name, hook wiring and test-marker mechanics are deferred to
  `/speckit-plan`.
- "Written for non-technical stakeholders": the audience here is the operator
  (a developer); stories are phrased around operator/agent outcomes.
- Zero [NEEDS CLARIFICATION] markers: the three judgment calls (exception mechanism =
  operator-set at launch; shell edits caught post-hoc rather than pre-parsed; commit
  gate checks working tree not index) are recorded as Assumptions/Edge Cases and can be
  revisited in `/speckit-clarify`.
- 2026-10-10 replan: User Story 4 (context budget and continuity), FR-027–FR-031,
  SC-008–SC-010 and the FR-001 adoption rule were added from research.md R14
  (operator decisions recorded there). The env var name, transcript parsing and
  script names stay in plan/contracts. The items above were re-checked and still
  hold.
- Two items were left open in spec.md Edge Cases for `/speckit-plan`; both are now
  **resolved**:
  - (1) Commit-gate behaviour inside the swe-agent E2B sandbox: the image ships `jq`
    and `uv` (FR-025, research R13).
  - (2) Whether Claude Code re-reads hook config mid-session: it does, so `.claude/**`
    edits need confirmation (FR-026, rule AF-HARNESS; research R1–R2).
