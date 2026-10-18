# Specification Quality Checklist: Lessons Loop

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-17
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs). See note 1.
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders. See note 1.
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain. Four judgment calls and a set of defaults were confirmed by the
  operator (see note 2).
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
- [x] No implementation details leak into specification. See note 1.

## Notes

1. The spec names existing repo parts (`AgentPipelineWorkflow`, `IMPLEMENT_PROMPT`, `TASK_PROMPT`,
   `register_activity`, `_open_factory_pr`, the LiteLLM proxy and `litellm/config.yaml`, the Eval-Gate,
   gate-result.json and its `schema_version`, CODEOWNERS, specs 009, 011, 013, 015, 017, 018, 020) and the default
   file paths `.factory/lessons.md` and `.factory/pipeline-lessons.md`. That is context for what changes, the
   convention in this repo's specs, not a design choice. How the files are read and given to each stage, how a draft
   is triggered, how a draft is added to an open PR, and the replay-safety mechanism are left to `/speckit-plan`.
2. Judgment calls confirmed by the operator on 2026-10-17: (a) the model writes only new lesson text or names an
   existing lesson, and code builds every change; (b) a repo lesson needs the same failure class in two or more runs
   on that repo, and a revert drafts at once; (c) the factory proposes removing quiet lessons through a PR a person
   merges; (d) the factory file is for the operator and is not given to agents. The defaults listed in the spec's
   Assumptions (trust check, caps, triggers that are dropped, drafter inputs) were stated to the operator on the same
   day without objection.
3. Second senior-architect-reviewer pass on 2026-10-17, after the first pass's findings were applied the same day. It
   raised 14 findings. All 14 were confirmed against the spec text and applied; none reverses an operator decision.
   The counts are now 29 functional requirements (FR) and 15 success criteria (SC); SC-015 is new, for US5 scenario 3.
   - Finding 7 (a lesson's path must appear in the facts) was fixed differently: FR-012 now allows one file or folder
     path that exists on the default branch. Test IDs only give path prefixes, and US5's own example is a folder.
     FR-013 bans any other test ID or file name from the facts in the text, since the agent chose those strings.
   - Added on our own, prompted by finding 1 (who can change a lessons file): FR-017's check that every commit on an
     open lessons PR is either a factory commit in the ledger or a person's commit. Otherwise drafts for that file
     are refused until a person merges or closes the PR. The reviewer did not ask for this rule.
   - A focused re-check by senior-architect-reviewer the same day confirmed findings 1 and 3 closed. It reopened
     finding 2 (the sweep and the close could both evaluate one point) and raised 8 smaller defects. All 9 were
     applied: the stored outcome is now the claim (FR-006); the sweep catches up reverts (FR-027); closing a tampered
     PR does not suppress drafts (FR-001); FR-013 allows the one path; FR-017 matches commit SHAs; FR-019 fences are
     escape-safe; FR-021 falls back to the whole history and names the merge-queue limit; and the edge case on a
     tampered PR matches FR-021. Counts unchanged.
   - Left open for `/speckit-plan`: whether the line and file caps count characters or bytes (the spec says bytes),
     and whether lesson-draft cost counts in spec 018's cost per merged PR (the spec counts it only in its own report
     line, FR-015).
4. Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`.
