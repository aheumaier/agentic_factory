# Feature Specification: PM-Agent Issue-Shaping and Spec-Review Gate

**Feature Branch**: `003-pm-agent-review-gate`

**Created**: 2026-09-02

**Status**: Draft

**Revision note (2026-09-03)**: FR-007–FR-011 and SC-002/003/005 revised
after a senior-architect review found this feature's own Functional
Requirements and Success Criteria still asserted system-level behavior
(halting the pipeline run, bounding and escalating on rejection attempts)
that a prior revision of `plan.md`/`research.md` had already reassigned to
`specs/005-pipeline-mode-signals-escalation/`. `eval/braintrust/eval.config.py`
parses this file's `SC-NNN` bullets to score an implementation of this
feature — asserting criteria this feature's own code cannot produce
evidence for is a real spec-quality defect, independent of what today's
gate implementation happens to check. The revised items below describe only
what `harness/pm-agent/agent.py` itself does.

**Input**: User description: "PM-agent for the multi-agent SDLC pipeline (docs/70-multi-agent-pipeline-design.md §1 and §2's PM-agent subsection). Two decoupled jobs under one new registry/agents/pm-agent/ entry: (1) Issue-Shaping — triggered by \"@pm-agent shape\" on a raw GitHub issue with no linked PR; rewrites/clarifies the issue in place via gh issue edit, adding scope clarity and an explicit no-gold-plating note; tool access is deliberately narrow (gh issue only, no Bash/git/Spec Kit tools) so it structurally cannot create a branch or a spec; terminal at the issue, never touches the pipeline. (2) Spec-Review + PM-Approval-Gate — runs once spec.md already exists on a branch (as a Temporal activity inside AgentPipelineWorkflow, once that workflow reaches the PM stage); produces a value-judgment writeup (\"is this the right thing, built right\", explicit no-gold-plating check) posted as a comment to the target-repo PR; has read-only /speckit-analyze-style inspection access but no git-push capability; the run is gated by human pm_approved / pm_rejected:<feedback> decisions, looping back on rejection up to a bounded number of attempts (MAX_PM_ATTEMPTS=3) before escalating to a human. This spec covers both jobs' own behavior, prompts, and registry entry — it does NOT cover the webhook/signal delivery mechanism (separate feature) or the workflow's own orchestration sequencing beyond invoking this stage and waiting on its gate signal."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Shape a raw issue before it becomes a spec (Priority: P1)

A reviewer comments `@pm-agent shape` on a newly filed GitHub issue that has no linked pull request, no branch, and no spec yet. The issue is rewritten in place with clearer scope and an explicit note about anything that looks like unnecessary scope creep ("gold-plating"), so a human can decide with better information whether and how to turn it into a spec.

**Why this priority**: This is the earliest possible intervention point — catching scope ambiguity or gold-plating before any spec/plan/code is written is the cheapest place to catch it. It has no dependency on the pipeline or any other stage.

**Independent Test**: File a GitHub issue with vague scope, comment `@pm-agent shape`, and verify the issue body is edited to add scope clarity and a no-gold-plating note, with no branch, spec, or pipeline run created as a side effect.

**Acceptance Scenarios**:

1. **Given** a raw issue with ambiguous scope and no linked PR, **When** an authorized reviewer comments `@pm-agent shape`, **Then** the issue is edited in place to add scope clarity and a no-gold-plating note, and nothing else in the repository changes.
2. **Given** the issue has just been shaped, **When** a human later decides to turn it into a spec, **Then** that decision and the resulting `spec.md` are made manually, independent of this feature.

---

### User Story 2 - Review a spec for value and scope before build starts (Priority: P1)

Once a human has written `spec.md` on a feature branch and a pipeline run reaches the PM stage, the PM-agent reviews the spec, posts a value-judgment writeup to the target-repo pull request — is this the right thing, built the right way, does anything look like gold-plating — and the run waits for a human decision before proceeding to the next stage.

**Why this priority**: This is the pipeline's first gate. Every later, more expensive stage (architecture, build, review) depends on the spec having passed this judgment check first — skipping it risks expensive downstream work on the wrong thing.

**Independent Test**: With a `spec.md` already on a branch and a pipeline run at the PM stage, verify a writeup is posted to the PR and the run halts until an approval or rejection decision is supplied; verify a rejection triggers a bounded number of re-review attempts before escalating.

**Acceptance Scenarios**:

1. **Given** `spec.md` exists on the branch and the pipeline run has reached the PM stage, **When** the PM-agent runs, **Then** a value-judgment writeup is posted to the target-repo PR and the run waits for a decision.
2. **Given** the writeup has been posted, **When** the run receives an approval decision, **Then** the run proceeds to the next stage.
3. **Given** the writeup has been posted, **When** the run receives a rejection decision with feedback, **Then** the PM-agent re-reviews the (presumably updated) spec against that feedback, up to a bounded number of attempts.
4. **Given** the bounded number of rejection attempts has been exhausted without approval, **When** the last attempt is rejected, **Then** the run escalates to a human rather than looping indefinitely.

### Edge Cases

- What happens if `@pm-agent shape` is commented on an issue that already has a linked pull request? Per scope, this feature's Issue-Shaping job only acts on raw issues with no linked PR — a linked-PR issue should be left untouched by this job.
- What happens if the Issue-Shaping job is asked (via issue text or comment) to create a branch or a spec directly? It must be structurally unable to do so, regardless of instruction, given its intentionally narrow capability.
- What happens if the spec changes between a rejection and the next re-review attempt but not in a way that addresses the feedback? The re-review should judge the spec as it stands, and may reject again — the loop is bounded by attempt count, not by whether feedback appears to have been incorporated.
- What happens if a decision is never supplied at all (neither approval nor rejection)? The run remains waiting indefinitely at the gate; this feature does not define a timeout — only the bounded rejection-retry count is in scope.
- What happens if the Spec-Review job is asked to make a change to the spec itself? It must be structurally unable to push any change — it can only read and comment.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide an Issue-Shaping capability that, when invoked on a raw GitHub issue with no linked pull request, rewrites the issue's content in place to add scope clarity and an explicit note flagging any apparent unnecessary scope expansion.
- **FR-002**: The Issue-Shaping capability MUST NOT create, modify, or reference any git branch, spec file, or pipeline run as a result of running.
- **FR-003**: The Issue-Shaping capability's access MUST be limited to reading and editing the issue itself — it must have no capability to run arbitrary shell commands, use git, or invoke spec-authoring tools.
- **FR-004**: System MUST provide a Spec-Review capability that, once a spec already exists on a branch and a pipeline run has reached this stage, produces a written value-judgment assessment of that spec.
- **FR-005**: The Spec-Review writeup MUST address whether the spec describes the right thing to build, whether it is scoped appropriately, and MUST explicitly flag any apparent unnecessary scope expansion.
- **FR-006**: System MUST post the Spec-Review writeup as a comment on the target-repo pull request associated with the run.
- **FR-007**: The Spec-Review capability MUST be able to read the spec and related repository content for its assessment, but MUST NOT be able to push any commit, or otherwise mutate the spec, the repository, or the target pull request — via git or via any other API — except for posting its own writeup as a comment.
- **FR-008**: The Spec-Review capability MUST accept an `attempt` number and an optional rejection `feedback` string as inputs and MUST include both, human-legibly, in the writeup it produces — this is what makes a caller-driven approve/reject/re-review loop possible; halting the run for a decision and resuming it on approval or rejection is implemented by the orchestration layer that calls this capability, not by this capability itself (see Assumptions).
- **FR-009**: The Spec-Review capability MUST NOT itself enforce, cap, or track a limit on the number of re-review attempts — bounding attempts and escalating to a human once a budget is exhausted is implemented entirely by the orchestration layer that calls it (see Assumptions).
- **FR-010**: On a re-review call carrying rejection feedback, the Spec-Review capability MUST produce a fresh writeup that explicitly addresses that feedback against the spec's current state.
- **FR-011**: Posting a Spec-Review writeup MUST be idempotent per `attempt` number — calling the capability again for an attempt whose writeup has already been posted MUST return that existing writeup rather than posting a duplicate comment.
- **FR-012**: Both capabilities MUST be registered as a single named agent entry with its own configuration, distinguishing the two jobs' distinct triggers and tool access.

### Key Entities

- **Raw Issue**: A GitHub issue with no linked pull request, no branch, and no spec — the input to Issue-Shaping.
- **Shaped Issue**: The same issue after Issue-Shaping has added scope clarity and a no-gold-plating note; still not linked to any branch or spec.
- **Spec-Review Writeup**: The value-judgment assessment of a spec, posted as a PR comment, addressing rightness of scope and flagging gold-plating.
- **PM Approval Decision**: The human's binary outcome (approve / reject-with-feedback) that gates progress past this stage.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every `@pm-agent shape` invocation on a qualifying raw issue results in the issue being edited with added scope clarity and a no-gold-plating note, and zero unrelated repository changes (no branch, no spec, no pipeline run).
- **SC-002**: Every call to the Spec-Review capability against an existing `spec.md` and open target-repo PR results in exactly one writeup comment on that PR for that `attempt` number — posted fresh, or returned unchanged if a writeup for that attempt already exists.
- **SC-003**: Calling the Spec-Review capability twice with the same `attempt` number never results in more than one PR comment for that attempt.
- **SC-004**: 100% of re-review calls carrying rejection feedback result in a fresh Spec-Review writeup that visibly incorporates the supplied feedback.
- **SC-005**: Every `@pm-agent shape` invocation, regardless of what the issue text or comment instructs, results in zero branches, spec files, or pipeline runs created — verified structurally (no tool is bound to the model), not by a runtime check that could itself be bypassed.

## Assumptions

- The bounded number of rejection-triggered re-review attempts defaults to 3 (`MAX_PM_ATTEMPTS=3`), matching the pipeline design doc's stated default; this may be tuned later without changing this feature's behavior contract.
- The mechanism by which a human's approval/rejection decision (and any feedback text) actually reaches this stage — e.g. a parsed PR comment routed through a separate trigger bridge — is a dependency of this feature, not part of it; this spec only requires that a decision, however delivered, can gate and (on rejection) feed back into a re-review.
- The orchestration sequencing that invokes Spec-Review as a stage inside a larger pipeline run, and waits on its gate, is a dependency of this feature (a separate workflow-level concern), not something this feature implements itself.
- "Escalates to a human" means the run's normal automatic progression stops and a human must intervene to resume or abandon it; the exact escalation mechanism is out of scope for this feature.
- A target-repo pull request already exists by the time the Spec-Review capability runs (FR-006 posts to it). This feature does not create or verify that PR; ensuring one exists before this stage runs is an orchestration-sequencing dependency this feature relies on but does not implement (see `plan.md`/`data-model.md` for the current state of that gap across the pipeline design).
