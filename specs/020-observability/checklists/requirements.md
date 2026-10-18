# Specification Quality Checklist: Observability

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-17
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs). See note 1.
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders. See note 1.
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain. Four questions were answered by the operator (see note 2).
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details). See note 1.
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification. See note 1.

## Notes

1. The spec names Coralogix, OpenTelemetry (OTel), Langfuse and E2B's secrets egress proxy. The first three are
   operator decisions, not design choices made here; the proxy is the result of the research the operator asked for.
   It also names existing repo parts (`AgentPipelineWorkflow`, `_sandbox_envs`, `ensure_target_pr_activity`,
   `RegistryPromotionWaiterWorkflow`, `swe-agent-build.yml`, `shape_issue()`, `SEAT_HANDOFF_INDEX`, `_redact` in
   `orchestration/activities.py`, `pipeline_workflow.py`, architecture §3.8, specs 005 to 019). That is context for
   what changes, the convention in this repo's specs. The OTel libraries, how the identity fields reach the sandbox,
   how workflow code detects replay, the field list's format and the dashboard file's format are left to
   `/speckit-plan`.
2. Decisions by the operator on 2026-10-17: Coralogix for the workflow and developer view, Langfuse for single model
   calls, facts only, OTel format, §3.8 amended, the identity fields, and the spec 018 ledger as the system of record.
   Answers to four questions the same day: (a) one operator dashboard is in scope, alerts are not; (b) keep every
   trace, with a setting for sampling later; (c) when Coralogix cannot be reached, drop the data and count the drops;
   (d) for the key in E2B, use current best practice, which research the same day found to be E2B's secrets egress
   proxy with a worker relay as the fallback (FR-020). The defaults in the spec's Assumptions are open to change in
   `/speckit-plan`.
3. senior-architect-reviewer pass on 2026-10-17. It raised 16 findings. All 16 were confirmed against the spec text
   and the code (`orchestration/activities.py` lines 53, 79, 275-276, 293, 297; `pipeline_workflow.py` lines 216 and
   355) and applied; none reverses an operator decision. The counts are now 29 functional requirements (FR) and 10
   success criteria (SC); FR-029 is new (exporters set up in code, `OTEL_*` removed from child processes).
   - Finding 12 offered two options for the signal sender (a GitHub login): allow it, or drop the claim. The spec
     drops it, because a GitHub login is personal data in a hosted tool (FR-008). No finding was fixed differently
     from what the reviewer proposed, and nothing was added on our own.
   - The reviewer's three concerns about operator decisions: the move from §3.8's self-hosted choice to a hosted
     service is now stated as deliberate in FR-028. Metric series per run (and their cost) and the ingest quota are
     left to `/speckit-plan` (Assumptions).
4. Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`.
