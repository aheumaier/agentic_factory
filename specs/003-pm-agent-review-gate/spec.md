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

**Revision note (2026-09-03, third pass)**: A further senior-architect
review found that first revision had corrected FR-007/FR-009's *wording*
but left User Story 2's Independent Test, Acceptance Scenarios 2-4, Edge
Case 4, and the "PM Approval Decision" Key Entity still describing the same
system-level halting/bounding/escalating behavior the FRs had already
disowned — the exact defect class the first revision note above says it
fixed, just not fixed everywhere it appeared. Also added this pass: FR-002a
(Issue-Shaping must preserve the original issue content, not silently
discard it — a gap with no other human checkpoint in that job's path), and
a clarifying sentence on FR-011's idempotency key to resolve an apparent
conflict with FR-010. FR-012 is unchanged in substance but is now
documented (`plan.md`'s Structure Decision) as satisfied by `SKILL.md`
prose, not a registry manifest schema field.

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

Once a human has written `spec.md` on a feature branch and a pipeline run reaches the PM stage, the PM-agent reviews the spec and posts a value-judgment writeup to the target-repo pull request — is this the right thing, built the right way, does anything look like gold-plating. (A human decision then gates the run before it proceeds to the next stage — that gating and resumption behavior is implemented by the calling workflow, not by this feature; see Assumptions.)

**Why this priority**: This is the pipeline's first gate. Every later, more expensive stage (architecture, build, review) depends on the spec having passed this judgment check first — skipping it risks expensive downstream work on the wrong thing.

**Independent Test**: With a `spec.md` already on a branch and an open
target-repo PR, call the Spec-Review capability directly and verify: a
writeup addressing rightness-of-scope and gold-plating is both returned and
posted as a PR comment; a second call with rejection `feedback` and a
higher `attempt` number returns a fresh writeup that visibly addresses that
feedback; a repeated call with the same `attempt` number returns the
existing writeup and posts no duplicate comment. (Whether a human decision
then halts or resumes a larger pipeline run is a
`specs/005-pipeline-mode-signals-escalation/` concern, not something this
capability implements or can be tested for here.)

**Acceptance Scenarios**:

1. **Given** `spec.md` exists on the branch and a target-repo PR is open, **When** the Spec-Review capability is called, **Then** a value-judgment writeup is posted to the PR and returned to the caller.
2. **Given** a writeup for `attempt=N` has been posted, **When** the capability is called again with the same `attempt=N`, **Then** the existing writeup is returned and no duplicate comment is posted.
3. **Given** a writeup has been posted, **When** the capability is called with `attempt=N+1` and rejection `feedback`, **Then** a fresh writeup is produced and posted that explicitly addresses that feedback against the spec's current state.
4. **Given** the capability is called with any `attempt` number, including one far beyond a caller's own retry budget (e.g. `attempt=99`), **When** it runs, **Then** it does not raise or refuse — enforcing and escalating on an attempt budget is implemented entirely by the calling workflow (`specs/005-pipeline-mode-signals-escalation/`), not by this capability.

### Edge Cases

- What happens if `@pm-agent shape` is commented on an issue that already has a linked pull request? Per scope, this feature's Issue-Shaping job only acts on raw issues with no linked PR — a linked-PR issue should be left untouched by this job.
- What happens if the Issue-Shaping job is asked (via issue text or comment) to create a branch or a spec directly? It must be structurally unable to do so, regardless of instruction, given its intentionally narrow capability.
- What happens if the spec changes between a rejection and the next re-review attempt but not in a way that addresses the feedback? The re-review should judge the spec as it stands, and may reject again — the loop is bounded by attempt count, not by whether feedback appears to have been incorporated.
- What happens if a decision is never supplied at all (neither approval nor rejection)? This feature has no mechanism to know about or affect run state either way — it defines no timeout, and whether/how a stalled run is detected is a `specs/005-pipeline-mode-signals-escalation/` concern.
- What happens if the Spec-Review job is asked to make a change to the spec itself? It must be structurally unable to push any change — it can only read and comment.
- What happens to the original issue content when Issue-Shaping edits it? It must remain readable afterward — this job must not silently discard it, since there is no other human checkpoint on this path before the edit lands on the target repo.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide an Issue-Shaping capability that, when invoked on a raw GitHub issue with no linked pull request, rewrites the issue's content in place to add scope clarity and an explicit note flagging any apparent unnecessary scope expansion.
- **FR-002**: The Issue-Shaping capability MUST NOT create, modify, or reference any git branch, spec file, or pipeline run as a result of running.
- **FR-002a**: The Issue-Shaping capability MUST NOT discard the original issue content — the pre-shaping title/body MUST remain readable after shaping (e.g. preserved in a preceding comment), since no other human checkpoint exists on this path before the edit lands on the target repo.
- **FR-003**: The Issue-Shaping capability's access MUST be limited to reading and editing the issue itself — it must have no capability to run arbitrary shell commands, use git, or invoke spec-authoring tools.
- **FR-004**: System MUST provide a Spec-Review capability that, once a spec already exists on a branch and a pipeline run has reached this stage, produces a written value-judgment assessment of that spec.
- **FR-005**: The Spec-Review writeup MUST address whether the spec describes the right thing to build, whether it is scoped appropriately, and MUST explicitly flag any apparent unnecessary scope expansion.
- **FR-006**: System MUST post the Spec-Review writeup as a comment on the target-repo pull request associated with the run.
- **FR-007**: The Spec-Review capability MUST be able to read the spec and related repository content for its assessment, but MUST NOT be able to push any commit, or otherwise mutate the spec, the repository, or the target pull request — via git or via any other API — except for posting its own writeup as a comment.
- **FR-008**: The Spec-Review capability MUST accept an `attempt` number and an optional rejection `feedback` string as inputs and MUST include both, human-legibly, in the writeup it produces — this is what makes a caller-driven approve/reject/re-review loop possible; halting the run for a decision and resuming it on approval or rejection is implemented by the orchestration layer that calls this capability, not by this capability itself (see Assumptions).
- **FR-009**: The Spec-Review capability MUST NOT itself enforce, cap, or track a limit on the number of re-review attempts — bounding attempts and escalating to a human once a budget is exhausted is implemented entirely by the orchestration layer that calls it (see Assumptions).
- **FR-010**: On a re-review call carrying rejection feedback, the Spec-Review capability MUST produce a fresh writeup that explicitly addresses that feedback against the spec's current state.
- **FR-011**: Posting a Spec-Review writeup MUST be idempotent per `attempt` number — calling the capability again for an attempt whose writeup has already been posted MUST return that existing writeup rather than posting a duplicate comment. `attempt` MUST be strictly increasing per distinct review request and is the sole idempotency key; a caller reusing an `attempt` number with different `feedback` is caller error, not a case this capability is required to resolve (this is what makes FR-010's "fresh writeup on new feedback" and this FR's "same writeup on same attempt" compatible rather than contradictory).
- **FR-012**: Both capabilities MUST be registered as a single named agent entry with its own configuration, distinguishing the two jobs' distinct triggers and tool access.

### Key Entities

- **Raw Issue**: A GitHub issue with no linked pull request, no branch, and no spec — the input to Issue-Shaping.
- **Shaped Issue**: The same issue after Issue-Shaping has added scope clarity and a no-gold-plating note; still not linked to any branch or spec.
- **Spec-Review Writeup**: The value-judgment assessment of a spec, posted as a PR comment, addressing rightness of scope and flagging gold-plating.
- **PM Approval Decision**: External to this feature, owned by `specs/005-pipeline-mode-signals-escalation/` — the human's binary outcome (approve / reject-with-feedback) that gates progress past this stage. This feature's code has no type or representation for it; a re-review call's only awareness of a prior decision is the `feedback` argument a caller passes in (see `data-model.md`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every `@pm-agent shape` invocation on a qualifying raw issue results in the issue being edited with added scope clarity and a no-gold-plating note, and zero unrelated repository changes (no branch, no spec, no pipeline run).
- **SC-002**: Every call to the Spec-Review capability against an existing `spec.md` and open target-repo PR results in exactly one writeup comment on that PR for that `attempt` number — posted fresh, or returned unchanged if a writeup for that attempt already exists.
- **SC-003**: Calling the Spec-Review capability twice with the same `attempt` number never results in more than one PR comment for that attempt.
- **SC-004**: 100% of re-review calls carrying rejection feedback result in a fresh Spec-Review writeup that visibly incorporates the supplied feedback.
- **SC-005**: Every `@pm-agent shape` invocation, regardless of what the issue text or comment instructs, results in zero branches, spec files, or pipeline runs created — verified structurally (no tool is bound to the model), not by a runtime check that could itself be bypassed.
- **SC-006**: 100% of `@pm-agent shape` invocations result in the pre-shaping issue title/body remaining readable afterward (e.g. as a preceding comment) — never silently discarded (FR-002a).
- **SC-007**: Every Spec-Review call is verified to run with no tool bound capable of a GitHub mutation or shell execution, and no ambient push-capable credential during the model call — verified structurally, not by a runtime check (FR-007).

## Assumptions

- The bounded number of rejection-triggered re-review attempts defaults to 3 (`MAX_PM_ATTEMPTS=3`), matching the pipeline design doc's stated default; this may be tuned later without changing this feature's behavior contract.
- The mechanism by which a human's approval/rejection decision (and any feedback text) actually reaches this stage — e.g. a parsed PR comment routed through a separate trigger bridge — is a dependency of this feature, not part of it; this spec only requires that a decision, however delivered, can gate and (on rejection) feed back into a re-review.
- The orchestration sequencing that invokes Spec-Review as a stage inside a larger pipeline run, and waits on its gate, is a dependency of this feature (a separate workflow-level concern), not something this feature implements itself.
- "Escalates to a human" means the run's normal automatic progression stops and a human must intervene to resume or abandon it; the exact escalation mechanism is out of scope for this feature.
- A target-repo pull request already exists by the time the Spec-Review capability runs (FR-006 posts to it). This feature does not create or verify that PR; ensuring one exists before this stage runs is an orchestration-sequencing dependency this feature relies on but does not implement (see `plan.md`/`data-model.md` for the current state of that gap across the pipeline design).
