# Feature Specification: Pipeline Mode Switch, Human Gate Signals, and Escalation

**Feature Branch**: `005-pipeline-mode-signals-escalation`

**Created**: 2026-09-02

**Status**: Draft

**Input**: User description: "Orchestration-level extension of AgentPipelineWorkflow for the multi-agent SDLC pipeline (docs/70-multi-agent-pipeline-design.md §6). Add mode: Literal['full','vibe'] to AgentPipelineWorkflow.run — 'full' runs every new stage (PM Spec-Review, Architect panel, Completeness-Critic, Simplify, Quality-Gate, Automated-Review blocking, Security-Review) at full rigor; 'vibe' relaxes engineering rigor for speed per the per-stage contract table (§4) — single architect candidate instead of a panel, Completeness-Critic/Quality-Gate/Simplify skipped entirely, Automated-Review advisory-only — while Eval-Gate and Security-Review stay blocking in both modes, never mode-conditional. Add three new bare Temporal signals modeled with workflow.wait_condition (same pattern the existing RegistryPromotionWaiterWorkflow already uses for pr_merged, just inlined on this workflow instead of a sibling workflow): pm_approved/pm_rejected(feedback), plan_approved/plan_rejected(feedback), security_cleared/security_rejected(feedback). Adopt a deterministic workflow ID pipeline-{agent_name}-v{version} (mirroring the existing registry-promotion-{agent_name}-v{version} convention). Generalize the existing silent ApplicationError raised today on MAX_BUILD_ATTEMPTS exhaustion into a final human escalation signal (resume/abandon) triggered whenever any bounded attempt budget (PM/Architect/Build+Eval+Quality+Automated+Security's shared budget) is exhausted, so a human can resume or abandon rather than the run silently dying. This spec covers only the workflow's own sequencing, signal handling, and escalation behavior — it does NOT cover any individual stage's own agent behavior (separate features) or how a signal actually gets sent from GitHub (separate webhook-bridge feature)."

## Clarifications

### Session 2026-09-04 (clarification session 3)

- Q (Q1): What does an `escalation_abandon` decision make observable — FR-013's "recorded reason" is invisible to humans unless surfaced, yet User Story 4 exists to eliminate invisible termination? → A: The workflow carries a notification obligation, not just an internal record: on budget exhaustion and on abandonment the workflow emits a structured notification (via a workflow-side notification step; transport owned by the trigger-bridge feature) naming the exhausted stage / attempts / accumulated reasons, or the abandon reason respectively. Amends FR-011/FR-013 and the corresponding Assumption.
- Q (Q2): Where does the mode choice come from, and what happens to a relaxed-mode run under a workflow that doesn't support the parameter (an older worker still holding task slots during rollout)? → A: Mode arrives as a new optional run-parameter with default = rigorous mode (existing zero-mode callers keep working unchanged); an unsupported value fails fast at workflow start with a distinct, named error (`mode_not_supported`) before any activity runs — never silently downgraded to rigorous. Amends FR-001; new SC-009.
- Q (Q3): After `escalation_resume`, where does control re-enter — for the shared Build-loop, the exhausting check (e.g. Security-Review) or the loop head? → A: Resume re-enters the exhausted stage's **loop at its head**, not the check that exhausted it: PM exhaustion → redo the PM stage then re-wait at the PM gate; Plan exhaustion → redo the architect stage then the plan gate; shared Build-loop exhaustion → return to **Build**, then all remaining blocking checks in sequence. One resume grant = one full lap. This guarantees a manual fix applied between exhaustion and resume is actually rebuilt and seen by every blocking check. Amends FR-012; matches design doc §4 "re-enters the exhausted stage's loop".
- Q (Q4): Does a run that successfully passes every gate after an escalation-resume still reach the normal terminus (Register), or does escalation mark the run as degraded? → A: Escalation state is fully discarded on a successful resumed lap — the run terminates normally through Register exactly like a never-escalated run; resumes are recorded only in the per-run log (FR-012), never as a terminal outcome attribute. New FR-018; aligns with design doc §4 ("`Register` never runs" applies exclusively to abandonment).
- Q (Q5): After a rejection loops the run back through a stage and it re-arrives at the same human gate, does the gate accept decisions again? → A: Yes — each arrival at a gate opens a fresh decision **window**; only decisions consumed in (or buffered for) a *previous* window stay dead, so a stale buffered decision can never release a later re-arm of its gate. Rejection re-entry = new window, commands valid again until the budget exhausts, then the escalation pair takes over and the gate never re-arms again. Prevents post-rejection deadlock while keeping FR-016's once-only semantics per window. Amends FR-016.

### Session 2026-09-04 (architect-review remediations R1–R6)

- Q (R1): FR-011/FR-012/FR-013 refer to the escalation decision generically ("resume or abandon") while the three gate signals are named — is the genericness deliberate? → A: Not deliberate; names pinned per `docs/70-multi-agent-pipeline-design.md` §6: **`escalation_resume`** (no payload) and **`escalation_abandon(reason: str)`** (reason required, consistent with the three `*_rejected` signals all requiring feedback text). One pair reused across all three exhaustion points (PM, Plan, shared Build-loop), since Escalation is a single cross-cutting state in the design's §3 diagram, not per-stage. Amends FR-011 below.
- Q (R2): Is FR-015's "inserting the architect stage" the full scope of the activity-sequence change, and are any executions actually in flight to migrate? → A: No — the change is a re-sequence, not an insertion of one step: the target sequence prepends `ensure_target_pr_activity` and the PM/Architect/Critic stages ahead of Build (design doc §3's transition graph), so the changed prefix spans everything before Eval-Gate. And no production-relevant executions can be in flight today: nothing starts `AgentPipelineWorkflow` except tests and bridge runs restricted to disposable repos (`specs/002-webhook-trigger-bridge`'s FR-016). Amends FR-015 below.
- Q (R3): Does a passing pass through the shared Build-loop consume a budget attempt, and what happens when security rejections alone exhaust the shared budget in relaxed mode? → A: Attempts count only failures/rejections — a clean pass through any gated check consumes nothing (matching the existing workflow's loop shape). And yes: because Security-Review draws from the shared Build-loop budget in both modes, security rejections alone CAN exhaust it even when every convenience check was skipped/advisory (relaxed mode); this routes a safety gate into the same escalation pair as convenience gates, which is accepted behavior — the escalation PR comment MUST name the exhausted stage so the human sees which kind of gate stalled. Amends FR-010/FR-011 below.
- Q (R4): Edge Case 1 covers stale/duplicate delivery but not Temporal's signal buffering — a decision delivered before its wait point is reached fires immediately on arrival, and the bridge resolves targets by running-execution search attributes, so early delivery is easy from GitHub. What governs? → A: New FR-016: buffered decisions apply at most once, only to their own gate; a decision for a gate already passed never re-arms it.
- Q (R5): Relaxed mode's architect stage has a distinct auto-proceed condition in the design's §4 table ("auto-proceeds once `/speckit-analyze` passes or budget exhausted") that FR-003's generic skip/advisory language doesn't capture. → A: Named explicitly in FR-003a.
- Q (R6): With what feedback does a resumed attempt run (FR-012)? → A: Per design doc §6, the resume reuses the last rejection/failure feedback already given — no new payload on resume. Amends FR-012 below.

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
4. **Given** a shared Build-loop budget exhausted by Security-Review rejections, **When** a human applies a manual source fix and signals resume, **Then** the resumed lap starts at Build (not at Security-Review), so the fix is rebuilt and all remaining blocking checks evaluate it.

### Edge Cases

- What happens if a rejection decision arrives for a decision point the run is not currently paused at (e.g. stale or duplicate delivery)? It must not be applied to the wrong stage or retroactively change a stage already passed — and per FR-016's window semantics it must not release a *later* re-arm of its own gate either. This includes Temporal's signal-buffering behavior: a signal delivered while the run has not yet reached its wait point is buffered and fires immediately on arrival — see FR-016 for how buffered decisions are governed.
- What happens when a rejection loops the run back through a stage and the run re-arrives at the same human gate? The gate opens a fresh decision window (FR-016): new decisions are accepted, prior windows' decisions stay dead — otherwise the first rejection would deadlock the run (no approval could ever release the second window).
- What happens if an approval and a rejection for the same decision point both arrive close together? Only one decision governs; this feature does not need to define which wins beyond first-applied-wins, but must not apply both.
- What happens when a stage's bounded retry budget is shared across multiple gated checks within one loop (e.g. evaluation, quality, automated review, and security review draw from the same budget)? Exhaustion by any one of them still triggers escalation for the whole shared budget, not a per-check budget.
- What happens if a second start is attempted for an agent/version pair whose prior run already completed (not still in flight)? A fresh run with the same deterministic identity is expected to be startable again once the prior one has finished.
- What happens to a run's mode choice if a rejection sends it back to redo earlier work — can mode change mid-run? Out of scope for this feature: mode is fixed for the lifetime of one run once started.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept a mode choice (rigorous or relaxed) when a pipeline run starts, fixed for that run's entire lifetime. Mode arrives as an optional run-parameter defaulting to the rigorous mode (existing callers that pass no mode keep working unchanged); an unrecognized or unsupported mode value MUST fail fast at workflow start with a distinct, named error before any stage runs — never silently fall back to the rigorous mode.
- **FR-002**: In the rigorous mode, system MUST run every stage designated as running in that mode, per the pipeline's per-stage contract, including all blocking human gates.
- **FR-003**: In the relaxed mode, system MUST skip every stage designated as skippable in that mode and MUST treat findings from stages designated as non-blocking in that mode as advisory only, never halting the run.
- **FR-003a**: In the relaxed mode, the architect stage runs with a single candidate instead of a panel and MUST auto-proceed without a human plan gate once the design's stated pass condition is met (`/speckit-analyze` clean on the synthesized plan) or its bounded attempt budget is exhausted (exhaustion routing to FR-011 escalation), per `docs/70-multi-agent-pipeline-design.md` §4's per-stage contract table.
- **FR-004**: Automated evaluation and security review MUST remain fully blocking in both modes — neither may be skipped or downgraded by the mode choice.
- **FR-005**: System MUST pause the run at each of the three human decision points (spec review, plan review, security review) and wait for an explicit approval or rejection decision before proceeding past that point.
- **FR-006**: On an approval decision at any of the three points, system MUST allow the run to proceed to the next stage.
- **FR-007**: On a rejection decision (carrying a reason) at any of the three points, system MUST redo that stage's work with the reason available, and MUST count this against that stage's bounded retry budget.
- **FR-008**: System MUST derive each run's identity deterministically from its target repo, agent name, and version (`pipeline/{repo}/{agent_name}/v{version}` — see Clarifications), without requiring a separate lookup step.
- **FR-009**: System MUST recognize an attempt to start a second run for a repo/agent/version triple that already has a run in flight, rather than silently creating an ambiguously-identified second run.
- **FR-010**: System MUST track a bounded number of automatic retry attempts for each gated stage (PM review, plan review, and the shared evaluation/quality/automated-review/security-review loop), consistent with the pipeline design's stated defaults. Attempts are charged on failures and rejections only — a clean pass through any gated check consumes nothing from its budget. Because security review draws from the shared Build-loop budget in both modes, security rejections alone MAY exhaust that shared budget even when every convenience check was skipped or advisory-only (relaxed mode); this is accepted behavior, not a mode-dependent exemption.
- **FR-011**: When any stage's bounded retry budget is exhausted without success, system MUST stop making further automatic attempts at that stage and MUST require a human escalation decision delivered as the named signal pair `escalation_resume` (no payload) / `escalation_abandon(reason: str)` (reason required) — one cross-cutting pair reused across all three exhaustion points (PM, Plan, shared Build-loop), per the pipeline design's §6 — rather than terminating with no human-visible outcome. On exhaustion the workflow MUST emit this escalation notice as a structured, human-facing notification through a workflow-side notification step (transport to a specific surface is owned by the trigger-bridge feature, per Assumptions); the notice MUST name the exhausted stage, attempts used, and accumulated failure/rejection reasons, so a safety-gate exhaustion (security review) is visibly distinguishable from a convenience-gate exhaustion.
- **FR-012**: On an `escalation_resume` decision after escalation, system MUST make exactly one further attempt at the stage where the run stalled, reusing the last rejection/failure feedback already given (the resume signal carries no new feedback payload). The resume re-enters the exhausted stage's **loop at its head**, not the check that exhausted it: PM exhaustion → redo the PM stage then re-wait at the PM gate; Plan exhaustion → redo the architect stage then the plan gate; shared Build-loop exhaustion → return to Build, then all remaining blocking checks in sequence — so a manual fix applied between exhaustion and resume is rebuilt and seen by every blocking check. One resume grant = one full lap. This behavior is repeatable and uncapped in v1; each resume MUST be logged.
- **FR-013**: On an `escalation_abandon(reason)` decision after escalation, system MUST end the run without further attempts, recording the reason as the final outcome of the run AND emitting a structured abandonment notification through the same workflow-side notification step as FR-011's escalation notice, naming the abandoned stage and the abandon reason — an abandoned run must be human-visible, not merely recorded internally (consistent with User Story 4's intent). Abandonment is the only escalation path that terminates a run: the register step MUST NOT run for an abandoned run.
- **FR-018**: A run that passes every gate after an escalation-resume (FR-012) MUST terminate normally through the pipeline's standard terminal step (Register), exactly as a run that never escalated; escalation state MUST NOT mark the run degraded or alter its terminal outcome. Resume history is visible only via the per-resume log entries required by FR-012.
- **FR-014**: For the architect stage specifically, the retry budget of FR-010 MUST be charged according to `specs/004-architect-fanout-judge/contracts/architect-agent-interface.md`'s **Consumer obligations** and `specs/004-architect-fanout-judge/spec.md`'s "Consumer obligations" subsection, both of which 004 originates but cannot itself implement (it deliberately does not name `MAX_PLAN_ATTEMPTS`). Concretely, the system MUST:
  - charge **one** plan attempt when the stage returns `gap_round_ran: True` — 004's FR-010 requires the gap-driven round to cost an attempt, and because that round runs *inside* one stage call, only this layer can charge it. Without this, the round is free and 004's FR-010 is violated silently (CO-1);
  - charge **one** plan attempt on a **deterministic** scoring/synthesis/critic-step error (004 FR-013a's deterministic half, CO-2), and **not** charge one on a **transient** error (004 FR-013a's transient half, CO-2a), retrying at the activity level instead;
  - **not** charge a plan attempt on the stage's `MAX_MALFORMED_RETRIES`-exhausted failure (004 FR-013), and route it to FR-011's escalation instead (CO-3). This is not a budget exhaustion, so FR-011 does not fire on its own — without an explicit mapping the run dies with no human-visible outcome, exactly the failure FR-011 exists to eliminate;
  - branch on the stage's `idempotent_hit` flag before reading any other result key (CO-4), since the idempotent early-return is a degraded three-key shape rather than the full result dict.
- **FR-015**: The target-stage insertion changes `AgentPipelineWorkflow`'s activity sequence as a **re-sequence, not a single-step insertion**: the changed prefix spans everything ahead of Eval-Gate (a setup/target-PR step, the PM Spec-Review gate, the architect stage, and the completeness-critic all move ahead of Build, per the pipeline design's §3 transition graph). System MUST choose and apply a determinism-preserving migration rather than editing the sequence in place — either `workflow.patched(...)` around the re-sequenced prefix, or a new workflow name/task-queue version. Note for that choice: no production-relevant executions can be in flight at migration time (nothing starts this workflow except tests and bridge runs restricted to disposable repos, per `specs/002-webhook-trigger-bridge` FR-016), which lowers the bar for the cheaper new-name option; planning MUST still state the choice explicitly rather than default to it silently.
- **FR-016**: Decisions are governed per **decision window**: each arrival at a gate (initial or after a rejection loop-back) opens a fresh window, and within one window a decision applies at most once. A decision signal delivered before its window is active MUST NOT take effect early out of order: Temporal buffers signals received before the run reaches the corresponding wait point, and such a buffered decision MUST be applied at most once, only when (and if) the run reaches the window it was delivered into. A decision consumed in — or buffered for — a previous window of a gate MUST never release or re-arm a later window of that gate, and a decision for a gate the run has already passed (final approval) MUST be ignored and MUST never re-arm that gate or retroactively change a passed stage. Once a gate's budget exhausts and escalation takes over (FR-011), that gate stops re-arming entirely.

### Key Entities

- **Pipeline Run**: One execution of the pipeline for a specific target repo, agent, and version, with a fixed mode choice and a deterministic identity.
- **Mode**: The rigorous/relaxed choice fixed for a run's lifetime, determining which stages run, are skipped, or are advisory-only.
- **Gate Decision**: An approval or a rejection-with-reason delivered at one of the three human decision points.
- **Retry Budget**: The bounded count of automatic attempts allowed at a gated stage (or shared group of stages) before escalation is required. Charged on failures/rejections only; a clean pass consumes nothing.
- **Escalation Decision**: The resume-or-abandon choice a human makes once a retry budget is exhausted, delivered as the named signal pair `escalation_resume` / `escalation_abandon(reason)`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of runs started in the rigorous mode execute every stage the contract designates for that mode; 100% of runs started in the relaxed mode skip every stage designated skippable and treat non-blocking findings as advisory only.
- **SC-002**: 100% of runs, regardless of mode, keep automated evaluation and security review fully blocking.
- **SC-003**: Every approval decision at a human decision point results in the run proceeding; every rejection decision results in that stage's work being redone with the reason available, consuming exactly one retry-budget attempt.
- **SC-004**: 100% of runs for a given repo/agent/version triple receive the same deterministic identity, with zero cases of two concurrently in-flight runs for the same triple going unnoticed.
- **SC-005**: 100% of retry-budget exhaustions result in an explicit human escalation decision being required, with zero silent run failures.
- **SC-006**: 0% of decisions delivered before their gate window is active (buffered signals) take effect out of order or apply to a window other than the one they were delivered into, and 0% take effect after their gate has finally passed or re-arm a passed gate (FR-016).
- **SC-007**: 100% of escalation notices name the exhausted stage, so safety-gate and convenience-gate exhaustions are distinguishable to the human without inspecting run internals.
- **SC-008**: 100% of budget exhaustions emit the FR-011 escalation notice, and 100% of `escalation_abandon` decisions emit the FR-013 abandonment notification (with abandoned stage and reason) — zero runs terminate without a human-visible outcome at either point.
- **SC-009**: 0% of runs with an unsupported mode value silently execute in the rigorous mode — every such start fails fast at workflow start with the distinct error (FR-001).
- **SC-010**: 100% of resumed runs that pass all gates reach the standard terminal step with zero escalation-derived degradation flags, and 0% of abandoned runs invoke it (FR-018 / FR-013).

## Assumptions

- The bounded retry budgets default to the values already stated in the pipeline design doc (PM: 3, Architect/plan: 3, the shared Build+Eval+Quality+Automated+Security loop: 3); this feature only requires that some bounded, human-visible-on-exhaustion budget exists per gated stage, not that these exact numbers are hardcoded permanently.
- The actual mechanism by which a gate decision or an escalation decision is delivered to the run (e.g. a parsed PR comment routed through a separate trigger bridge) is a dependency of this feature, not part of it — this feature only requires that, however delivered, a decision can reach and be applied to the correct paused run.
- Each individual stage's own internal behavior (what the PM-agent writes, what the architect panel produces, what security review checks) is defined by that stage's own separate feature; this feature only defines the sequencing, pausing, and retry/escalation behavior around those stages.
- "Abandon" ends the run's own automatic progression; any cleanup of partially-created artifacts (branches, draft PRs) on abandonment is out of scope for this feature.
- Open question for the trigger-bridge owner (`specs/002-webhook-trigger-bridge`): its reaction-on-outcome requirement currently covers run commands only (🚀/😕); an abandoned run leaves a draft target PR with no reaction-level signal that anything happened. FR-011/FR-013 now require the workflow to *emit* escalation and abandonment notifications (content obligation settled in this spec); whether the bridge renders them as comment reactions — and whether `resume`/`abandon` command reactions are added bridge-side — remains 002's call, not this feature's.
