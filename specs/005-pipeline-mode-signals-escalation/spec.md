# Feature Specification: Pipeline Mode Switch, Human Gate Signals, and Escalation

**Feature Branch**: `005-pipeline-mode-signals-escalation`

**Created**: 2026-09-02

**Status**: Draft

**Input**: User description: "Orchestration-level extension of AgentPipelineWorkflow for the multi-agent SDLC pipeline (docs/70-multi-agent-pipeline-design.md §6). Add mode: Literal['full','vibe'] to AgentPipelineWorkflow.run — 'full' runs every new stage (PM Spec-Review, Architect panel, Completeness-Critic, Simplify, Quality-Gate, Automated-Review blocking, Security-Review) at full rigor; 'vibe' relaxes engineering rigor for speed per the per-stage contract table (§4) — single architect candidate instead of a panel, Completeness-Critic/Quality-Gate/Simplify skipped entirely, Automated-Review advisory-only — while Eval-Gate and Security-Review stay blocking in both modes, never mode-conditional. Add three new bare Temporal signals modeled with workflow.wait_condition (same pattern the existing RegistryPromotionWaiterWorkflow already uses for pr_merged, just inlined on this workflow instead of a sibling workflow): pm_approved/pm_rejected(feedback), plan_approved/plan_rejected(feedback), security_cleared/security_rejected(feedback). Adopt a deterministic workflow ID pipeline-{agent_name}-v{version} (mirroring the existing registry-promotion-{agent_name}-v{version} convention). Generalize the existing silent ApplicationError raised today on MAX_BUILD_ATTEMPTS exhaustion into a final human escalation signal (resume/abandon) triggered whenever any bounded attempt budget (PM/Architect/Build+Eval+Quality+Automated+Security's shared budget) is exhausted, so a human can resume or abandon rather than the run silently dying. This spec covers only the workflow's own sequencing, signal handling, and escalation behavior — it does NOT cover any individual stage's own agent behavior (separate features) or how a signal actually gets sent from GitHub (separate webhook-bridge feature)."

## Clarifications

### Session 2026-09-03 (cross-spec reconciliation with `specs/002-webhook-trigger-bridge`)

- Q: This spec's Input line proposes `pipeline-{agent_name}-v{version}` as the deterministic workflow ID. `specs/002-webhook-trigger-bridge` — the feature that actually calls `start_workflow`/`signal` against this ID from GitHub comments — settled on a different, repo-namespaced format. Which governs? → A: `specs/002-webhook-trigger-bridge`'s format governs: `pipeline/{repo}/{agent_name}/v{version}` (`/`-delimited, `repo` as `owner/name` used as-is, no slug normalization). A repo-less identity would let any repo the GitHub App is installed on collide with, or drive, another repo's run under the same `agent_name`/`version` — a real risk once a webhook comment (not just a trusted internal caller) can start a run. This supersedes the Input line's literal `pipeline-{agent_name}-v{version}` wording and FR-008/SC-004/Key-Entities' "agent name and version" phrasing below, which are amended to read "repo, agent name, and version." The `mode`-exclusion-from-identity behavior is unaffected — `mode` still never participates in the identity either way.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Choose how rigorously a pipeline run is checked (Priority: P1)

When starting a pipeline run, a choice is made between running every quality and review stage at full rigor, or relaxing most of them for a faster pass — while two specific checks (automated evaluation and security review) always run at full rigor regardless of that choice.

**Why this priority**: This choice determines which stages even exist for a given run, so every other story in this feature (which stages send signals, which attempt budgets apply) depends on it being resolved first.

**Independent Test**: Start one run in the rigorous mode and one in the relaxed mode against the same spec; verify the rigorous run includes every stage in the contract table while the relaxed run skips the ones designated skippable, and verify both runs still fully enforce the two never-relaxed checks.

**Acceptance Scenarios**:

1. **Given** a run is started in the rigorous mode, **When** it proceeds through the pipeline, **Then** every stage designated as running in that mode actually runs, including blocking human gates.
2. **Given** a run is started in the relaxed mode, **When** it proceeds through the pipeline, **Then** every stage designated as skippable in that mode is skipped, and every stage designated as non-blocking in that mode does not halt the run even if it reports a finding.
3. **Given** a run in either mode, **When** it reaches automated evaluation or security review, **Then** both remain fully blocking regardless of the chosen mode.

---

### User Story 2 - Let a human steer a run at its decision points (Priority: P1)

At each of the run's three human decision points (spec review, plan review, security review), the run pauses and waits for an explicit decision; an approval lets it continue, and a rejection — carrying the reason — sends it back to redo the relevant work.

**Why this priority**: Without a working pause/resume mechanism, none of the upstream stages' review output (Stories in the PM-agent and Architect features) can actually influence the run — this is what makes those stages' human gates real rather than decorative.

**Independent Test**: Drive a run to each of the three decision points in turn and verify: an approval decision lets it proceed, and a rejection decision (with a reason) sends it back to redo that stage's work, carrying the reason along.

**Acceptance Scenarios**:

1. **Given** a run is paused at any of the three decision points, **When** an approval decision arrives, **Then** the run proceeds to the next stage.
2. **Given** a run is paused at any of the three decision points, **When** a rejection decision with a reason arrives, **Then** the run redoes that stage's work with the reason available to it, and this consumes one attempt from that stage's bounded retry budget.
3. **Given** a run is paused at a decision point, **When** no decision has yet arrived, **Then** the run remains paused indefinitely at that point rather than proceeding or failing on its own.

---

### User Story 3 - Give every run a stable, predictable identity (Priority: P2)

Each pipeline run for a given target agent and version has one fixed, predictable identity, so a decision sent later can always be matched to the correct run without needing to look anything up first.

**Why this priority**: This is what makes Story 2's decisions routable to the right run at all — but it is a smaller, mechanical piece compared to the mode switch and the decision-gating behavior, hence P2.

**Independent Test**: Start a run for a given agent/version pair and verify its identity is derived deterministically from that pair, matching the same pattern already used for the existing registry-promotion identity convention; verify attempting to start a second run for the same pair while one is in flight does not silently create a second, differently-identified run.

**Acceptance Scenarios**:

1. **Given** an agent name and version, **When** a run is started for that pair, **Then** its identity is derived deterministically from the pair, without needing any additional lookup.
2. **Given** a run is already in flight for a given agent/version pair, **When** a second start is attempted for the exact same pair, **Then** the system recognizes the identity collision rather than creating an ambiguous second run under a different identity.

---

### User Story 4 - Escalate to a human instead of silently dying when retries run out (Priority: P2)

When any stage's bounded number of automatic retry attempts is used up without success, the run stops making further automatic attempts and instead asks a human to decide whether to resume it (e.g. with a manual fix already applied) or abandon it — rather than failing invisibly.

**Why this priority**: This closes a real gap (today's silent failure) but only matters once a run actually exhausts a budget, which is the less common path compared to Stories 1–3's every-run behavior, hence P2.

**Independent Test**: Drive a run's bounded retry budget to exhaustion at any gated stage and verify the run stops automatic retries and instead waits for an explicit resume-or-abandon decision, rather than terminating with no human-visible outcome.

**Acceptance Scenarios**:

1. **Given** a stage's bounded retry budget has just been exhausted without success, **When** the run notices this, **Then** it stops making further automatic attempts at that stage and signals that it needs a human decision.
2. **Given** a run is waiting for an escalation decision, **When** a resume decision arrives, **Then** the run makes one more attempt at the stage where it stalled.
3. **Given** a run is waiting for an escalation decision, **When** an abandon decision arrives, **Then** the run ends without further attempts.

### Edge Cases

- What happens if a rejection decision arrives for a decision point the run is not currently paused at (e.g. stale or duplicate delivery)? It must not be applied to the wrong stage or retroactively change a stage already passed.
- What happens if an approval and a rejection for the same decision point both arrive close together? Only one decision governs; this feature does not need to define which wins beyond first-applied-wins, but must not apply both.
- What happens when a stage's bounded retry budget is shared across multiple gated checks within one loop (e.g. evaluation, quality, automated review, and security review draw from the same budget)? Exhaustion by any one of them still triggers escalation for the whole shared budget, not a per-check budget.
- What happens if a second start is attempted for an agent/version pair whose prior run already completed (not still in flight)? A fresh run with the same deterministic identity is expected to be startable again once the prior one has finished.
- What happens to a run's mode choice if a rejection sends it back to redo earlier work — can mode change mid-run? Out of scope for this feature: mode is fixed for the lifetime of one run once started.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept a mode choice (rigorous or relaxed) when a pipeline run starts, fixed for that run's entire lifetime.
- **FR-002**: In the rigorous mode, system MUST run every stage designated as running in that mode, per the pipeline's per-stage contract, including all blocking human gates.
- **FR-003**: In the relaxed mode, system MUST skip every stage designated as skippable in that mode and MUST treat findings from stages designated as non-blocking in that mode as advisory only, never halting the run.
- **FR-004**: Automated evaluation and security review MUST remain fully blocking in both modes — neither may be skipped or downgraded by the mode choice.
- **FR-005**: System MUST pause the run at each of the three human decision points (spec review, plan review, security review) and wait for an explicit approval or rejection decision before proceeding past that point.
- **FR-006**: On an approval decision at any of the three points, system MUST allow the run to proceed to the next stage.
- **FR-007**: On a rejection decision (carrying a reason) at any of the three points, system MUST redo that stage's work with the reason available, and MUST count this against that stage's bounded retry budget.
- **FR-008**: System MUST derive each run's identity deterministically from its target repo, agent name, and version (`pipeline/{repo}/{agent_name}/v{version}` — see Clarifications), without requiring a separate lookup step.
- **FR-009**: System MUST recognize an attempt to start a second run for a repo/agent/version triple that already has a run in flight, rather than silently creating an ambiguously-identified second run.
- **FR-010**: System MUST track a bounded number of automatic retry attempts for each gated stage (PM review, plan review, and the shared evaluation/quality/automated-review/security-review loop), consistent with the pipeline design's stated defaults.
- **FR-011**: When any stage's bounded retry budget is exhausted without success, system MUST stop making further automatic attempts at that stage and MUST signal that a human decision (resume or abandon) is needed, rather than terminating with no human-visible outcome.
- **FR-012**: On a resume decision after escalation, system MUST make one further attempt at the stage where the run stalled.
- **FR-013**: On an abandon decision after escalation, system MUST end the run without further attempts.
- **FR-014**: For the architect stage specifically, the retry budget of FR-010 MUST be charged according to `specs/004-architect-fanout-judge/contracts/architect-agent-interface.md`'s **Consumer obligations** and `specs/004-architect-fanout-judge/spec.md`'s "Consumer obligations" subsection, both of which 004 originates but cannot itself implement (it deliberately does not name `MAX_PLAN_ATTEMPTS`). Concretely, the system MUST:
  - charge **one** plan attempt when the stage returns `gap_round_ran: True` — 004's FR-010 requires the gap-driven round to cost an attempt, and because that round runs *inside* one stage call, only this layer can charge it. Without this, the round is free and 004's FR-010 is violated silently (CO-1);
  - charge **one** plan attempt on a **deterministic** scoring/synthesis/critic-step error (004 FR-013a's deterministic half, CO-2), and **not** charge one on a **transient** error (004 FR-013a's transient half, CO-2a), retrying at the activity level instead;
  - **not** charge a plan attempt on the stage's `MAX_MALFORMED_RETRIES`-exhausted failure (004 FR-013), and route it to FR-011's escalation instead (CO-3). This is not a budget exhaustion, so FR-011 does not fire on its own — without an explicit mapping the run dies with no human-visible outcome, exactly the failure FR-011 exists to eliminate;
  - branch on the stage's `idempotent_hit` flag before reading any other result key (CO-4), since the idempotent early-return is a degraded three-key shape rather than the full result dict.
- **FR-015**: Inserting the architect stage ahead of Build changes `AgentPipelineWorkflow`'s activity sequence, so system MUST choose and apply a determinism-preserving migration for executions in flight — either `workflow.patched(...)` around the new step or a new workflow name on a new task queue — rather than editing the sequence in place.

### Key Entities

- **Pipeline Run**: One execution of the pipeline for a specific target repo, agent, and version, with a fixed mode choice and a deterministic identity.
- **Mode**: The rigorous/relaxed choice fixed for a run's lifetime, determining which stages run, are skipped, or are advisory-only.
- **Gate Decision**: An approval or a rejection-with-reason delivered at one of the three human decision points.
- **Retry Budget**: The bounded count of automatic attempts allowed at a gated stage (or shared group of stages) before escalation is required.
- **Escalation Decision**: The resume-or-abandon choice a human makes once a retry budget is exhausted.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of runs started in the rigorous mode execute every stage the contract designates for that mode; 100% of runs started in the relaxed mode skip every stage designated skippable and treat non-blocking findings as advisory only.
- **SC-002**: 100% of runs, regardless of mode, keep automated evaluation and security review fully blocking.
- **SC-003**: Every approval decision at a human decision point results in the run proceeding; every rejection decision results in that stage's work being redone with the reason available, consuming exactly one retry-budget attempt.
- **SC-004**: 100% of runs for a given repo/agent/version triple receive the same deterministic identity, with zero cases of two concurrently in-flight runs for the same triple going unnoticed.
- **SC-005**: 100% of retry-budget exhaustions result in an explicit human escalation decision being required, with zero silent run failures.

## Assumptions

- The bounded retry budgets default to the values already stated in the pipeline design doc (PM: 3, Architect/plan: 3, the shared Build+Eval+Quality+Automated+Security loop: 3); this feature only requires that some bounded, human-visible-on-exhaustion budget exists per gated stage, not that these exact numbers are hardcoded permanently.
- The actual mechanism by which a gate decision or an escalation decision is delivered to the run (e.g. a parsed PR comment routed through a separate trigger bridge) is a dependency of this feature, not part of it — this feature only requires that, however delivered, a decision can reach and be applied to the correct paused run.
- Each individual stage's own internal behavior (what the PM-agent writes, what the architect panel produces, what security review checks) is defined by that stage's own separate feature; this feature only defines the sequencing, pausing, and retry/escalation behavior around those stages.
- "Abandon" ends the run's own automatic progression; any cleanup of partially-created artifacts (branches, draft PRs) on abandonment is out of scope for this feature.
