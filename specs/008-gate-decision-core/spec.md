# Feature Specification: Gate Decision Core

**Feature Branch**: `008-gate-decision-core`

**Created**: 2026-10-09

**Status**: Draft

**Input**: User description: "Decision core for the pipeline's human gates, with no Teams dependency (docs/80-teams-workspace-design.md §16 "008 Decision core", §7.2, §12, §14.8, §15). Goal: prepare AgentPipelineWorkflow and orchestration/webhook_bridge so a second decision surface (Microsoft Teams, spec 009) can plug in later. The change must be safe today on GitHub alone and fix today's decision race. Scope: (1) a read-only status query; (2) a first-valid-wins plan gate: a validated decide_plan request that rejects decisions for no open window, an already-decided window or a mismatched attempt, while the existing plan_approved/plan_rejected signals stay, become set-if-unset and accept an optional {resolved_by, via, attempt} payload, with 005 FR-016 window semantics; (3) a bridge core/adapter split with no behaviour change on GitHub, a validated-decision path with a worker_unavailable outcome, and signal_issued_no_handler renamed to signal_issued for the plan gate only; (4) tests: two decisions in one workflow task, stale-attempt rejection, status while blocked, all existing bridge tests unchanged; (5) pin the Temporal server image (≥1.28) in place of the deprecated auto-setup:latest. Out of scope: anything Teams, PM/security/escalation handlers and the mode param (005), lanes (013), the outbound notifier. Constraints: 002 FR-016 disposable-repo rule unchanged; patched-based determinism; no dependency on 005."

## Context

The pipeline has one live human gate: plan review. It pauses a run until a
human approves the architect's plan or rejects it with feedback
(`orchestration/workflows/pipeline_workflow.py:66-73`, wait at `:140`).
Today the only way to deliver that decision is a GitHub PR comment, relayed
by `orchestration/webhook_bridge/`.

Three problems block adding a second decision surface (Microsoft Teams,
`docs/80-teams-workspace-design.md`, spec 009), and one of them is a defect
already:

1. **Decisions race.** If two decisions reach a waiting run close together,
   the later one silently replaces the earlier one before the run acts. The
   human whose decision "won" in the PR thread may not be the one the run
   followed.
2. **Nobody can ask a run where it is.** There is no read-only way to see a
   run's current stage, whether a decision is awaited, or how much retry
   budget is left.
3. **The bridge is shaped for one surface.** Parsing, de-duplication,
   auditing and the calls into the run are mixed with GitHub-specific
   concerns (signature checks, permission lookup, emoji reactions), so a
   second surface would have to duplicate them.

This feature fixes the race, adds a read-only status view, and separates
the bridge into a surface-neutral core plus a GitHub adapter. GitHub
behaviour stays the same. Nothing here requires Microsoft Teams access.

## Clarifications

### Session 2026-10-09

- Q: The unchanged bridge tests pin the GitHub plan signal to carry no payload, but status is expected to show "X via github". Which gives? → A: GitHub stays payload-less in 008. Its decisions record as `resolved_by=unknown, via=unknown`. Attribution in status is exercised through the validated path. Attaching GitHub attribution is a follow-up.
- Q: Must FR-021's workflow tests run the real `AgentPipelineWorkflow` or may they use a stub? → A: The real `AgentPipelineWorkflow` class, with its activities mocked, in an in-process test environment. Bridge-core tests may keep using stubs and mocks.
- Q: FR-014 forbids reactions in gate signalling, but the unchanged tests require `signal_gate` to post them. How is that reconciled? → A: The existing module paths and public signatures (including `temporal_client.signal_gate(..., github_client)`) are kept as the GitHub adapter's contract. `signal_gate` becomes a thin adapter that calls a new core operation and renders the reaction from the returned outcome. The core lives in new module(s), and FR-014 applies to core operations only.
- Q: In status, does "last decision" include duplicates, and where are ignored decisions visible? → A: "Last decision" is the last **applied** decision. Status also lists recently ignored decisions (duplicate, stale, or no-window legacy signal), each with its reason and attribution; superseded on 2026-10-10 by a rolling list of the last 20 across windows. The list covers signals only. Validated-path refusals are returned synchronously and never recorded (FR-007).

### Session 2026-10-10

- Q: Is `worker_unavailable` a "decision not applied" outcome? → A: No. It means **outcome unknown**: the server may still deliver the decision to a worker later and apply it. The core derives the decision's request id deterministically from the surface-namespaced delivery id (FR-018), so resubmitting the same decision is idempotent. Surfaces MUST NOT present it as a failure.
- Q: Who answers a status request with a bounded timeout (SC-005, User Story 2 scenario 4)? → A: A new core **status operation** (FR-016a). It resolves the run as gate signalling does, asks it for status with a bounded timeout, and returns the snapshot, `no in-flight run`, `multiple in-flight runs`, or `worker_unavailable`. It is subject to the allow-list (FR-019). GitHub gets no status command in 008.
- Q: What exactly is the attempt number a decision must name? → A: The plan loop's iteration number. It only ever increases within a run, may have gaps (failed architect attempts use up numbers, `pipeline_workflow.py:95`, `:120`), and is **never reused** in that run, including after a future escalation-resume (005 must honour this). Callers take it from status or the stage's PR comment and never compute it.
- Q: Which ignored decisions does status keep, and how many? → A: One **rolling list of the last 20 ignored signals** for the run, across windows. Each entry carries its reason, decision, the attempt it named (if any), `resolved_by`, `via`, and the window open when it arrived (or none). The oldest entry is dropped beyond 20. This replaces the rule that dropped earlier windows' lists.
- Q: Which orchestration server image and version floor? → A: `temporalio/server` plus `temporalio/admin-tools`, pinned to an exact tag **≥1.29.3**, so it is never older than the schema `auto-setup:latest` (server 1.29.3) already wrote to existing `temporal-pg-data` volumes. The stack MUST also do what `auto-setup` does today: set up and migrate the database schema, create the default namespace, and register the search attributes. The floor exists to prevent a schema downgrade, not for validated decisions.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A plan decision is never silently overwritten (Priority: P1)

A lead reviewing a plan posts `plan_approved` on the target PR. At almost
the same moment, another authorized reviewer posts `plan_rejected: <reason>`.
Today, whichever reaches the run last silently replaces the other, and
nothing records that a decision was overwritten. After this change, the
first valid decision **to reach the run** for the open decision window is
the one the run acts on. Any later decision for the same window is ignored,
and it is recorded as a duplicate rather than lost silently.

"First" means first in the run's own recorded order, not first in the PR
thread. The bridge relays and handles comments concurrently, so a comment
posted earlier can reach the run later. This feature guarantees one
deterministic, recorded winner; it does not promise that PR-thread order
wins.

**Why this priority**: This is a correctness defect in the only live human
gate. It also underpins every multi-surface design later: with two surfaces,
concurrent decisions become routine.

**Independent Test**: Start a run that reaches the plan gate. Deliver an
approval and a rejection so that both arrive before the run resumes. Check
that the run follows exactly the first, and that the second is visibly
recorded as ignored. Repeat with the order reversed.

**Acceptance Scenarios**:

1. **Given** a run waiting at the plan gate for attempt N, **When** an
   approval and then a rejection arrive before the run resumes, **Then** the
   run proceeds as approved, and the rejection is recorded as a duplicate
   for attempt N.
2. **Given** a run waiting at the plan gate for attempt N, **When** a
   rejection and then an approval arrive before the run resumes, **Then**
   the run redoes the plan with the rejection's feedback, charges one budget
   attempt, and records the approval as a duplicate.
3. **Given** a run that rejected attempt N and now waits at the plan gate
   for attempt N+1, **When** a decision that names attempt N arrives,
   **Then** it is refused as stale and does not release attempt N+1.
4. **Given** a run that is not waiting at any gate, **When** a decision that
   names an attempt arrives, **Then** it is refused because no decision
   window is open, and the run's progress is unchanged.
5. **Given** a run waiting at the plan gate, **When** an approval arrives in
   exactly today's form (a bare GitHub `plan_approved` comment, with no
   attempt and no attribution), **Then** it is accepted for the open window,
   exactly as today.

---

### User Story 2 - Anyone operating a run can see where it is (Priority: P2)

An operator, or a decision surface preparing a decision card, asks a
running pipeline run for its status. The answer covers:

- which stage it is in;
- whether a decision window is open, and for which gate and attempt;
- how much of each retry budget has been charged;
- the target PR;
- the last applied decision, with who made it and through which surface;
- the most recently ignored decisions (up to 20, across windows), and why.

Asking never changes the run.

**Why this priority**: It turns an opaque run into an inspectable one, and a
decision surface needs it to know whether to offer a decision at all. It
depends on nothing else in this feature.

**Independent Test**: Start a run, query it at each stage, including while
it waits at the plan gate. Check that every answer reflects the run's actual
state and that querying leaves the run's history unchanged.

**Acceptance Scenarios**:

1. **Given** a run blocked at the plan gate for attempt 2 with 1 of 3 plan
   attempts charged, **When** its status is requested, **Then** the answer
   names the plan gate, attempt 2, budget 1/3, and the PR URL.
2. **Given** a run whose last plan decision was an approval submitted
   through the validated decision path with `resolved_by` X and `via`
   "github", **When** its status is requested, **Then** the answer reports
   that decision with X and "github". A decision delivered as a legacy
   GitHub comment is reported with `resolved_by` and `via` as unknown.
3. **Given** a run in the Build stage, **When** its status is requested,
   **Then** the answer reports no open decision window.
4. **Given** no worker is currently processing runs, **When** status is
   requested, **Then** the requester gets a distinct "pipeline unavailable"
   result within a bounded time instead of hanging.

---

### User Story 3 - A second decision surface can plug in without changing GitHub behaviour (Priority: P2)

A future surface (Teams, spec 009) needs to submit decisions, have them
validated before they take effect, and learn the outcome at once. It must
reuse the bridge's existing rules: command shapes, de-duplication, audit
outcomes and run resolution. Meanwhile every GitHub user sees exactly what
they see today: the same commands are accepted, the same reactions appear,
and the same permission rules apply.

**Why this priority**: It is the enabling step for spec 009, but it gives
no user-visible value on its own. Story 1 already fixes the defect.

**Independent Test**: Run the bridge's existing test suite unchanged; it
passes. Then submit a validated plan decision through the core's new
decision path: once for an open window, once for an already-decided window,
once with a stale attempt, and once with no worker running. Each returns its
distinct outcome.

**Acceptance Scenarios**:

1. **Given** the bridge after the split, **When** the pre-existing bridge
   test suite runs without modification, **Then** every test passes.
2. **Given** a run waiting at the plan gate, **When** a validated decision
   with the correct attempt is submitted through the core, **Then** it is
   accepted and recorded with its `resolved_by` and `via`.
3. **Given** a window that already has a recorded decision, **When** a
   validated decision is submitted for it, **Then** the submitter gets an
   immediate "already resolved" outcome naming who resolved it and how.
4. **Given** no worker is processing runs, **When** a validated decision is
   submitted, **Then** the submitter gets the `worker_unavailable` outcome
   within a bounded time, marked as outcome unknown. **When** a worker
   later starts and the same delivery is resubmitted, **Then** at most one
   decision is applied for it.
5. **Given** a GitHub `plan_approved` comment that reaches a waiting run,
   **When** the bridge audits it, **Then** the outcome reads `signal_issued`
   (not `signal_issued_no_handler`) and the reaction is unchanged (👀). PM
   and security gate comments still audit as `signal_issued_no_handler`.

---

### User Story 4 - The local stack starts from a supported, pinned orchestration server (Priority: P3)

A developer running `make up` gets the same orchestration server version
every time, from a supported image, never older than the schema already on
their local volume.

**Why this priority**: It is housekeeping. The image in use today is
deprecated and unpinned, so it can change under the team without warning.
It is independent of Stories 1-3: Updates and Queries work on the server
`auto-setup:latest` already resolves to (1.29.3).

**Independent Test**: Bring the stack up from a clean state twice and check
that the same pinned server version runs both times. Then bring it up on an
existing volume created by today's `auto-setup:latest` and check that it
starts without a schema reset. This is a manual stack check; the automated
Story 1-3 tests stay in-process (FR-021).

**Acceptance Scenarios**:

1. **Given** a clean machine, **When** the local stack is started, **Then**
   the orchestration server reports the pinned version, which is at least
   1.29.3, and the default namespace exists.
2. **Given** a `temporal-pg-data` volume created by today's
   `auto-setup:latest`, **When** the pinned stack starts on it, **Then** it
   starts without a downgrade error or a volume reset.
3. **Given** the pinned stack, **When** the existing worker and bridge
   start, **Then** they connect and the custom search attributes the bridge
   relies on (`TargetRepo`, `PRNumber`) are available.

---

### Edge Cases

- **Both decisions in one processing step.** Two decisions arrive close
  enough that the run handles them in the same processing step. Exactly one
  is applied, and it is the first in the run's recorded order. This holds
  for every pairing: two signals, two validated decisions, and a signal
  with a validated decision.
- **A decision arrives while the architect stage is still running for the
  next attempt.** No window is open, so a validated decision is refused. A
  legacy GitHub comment is ignored on arrival with reason "no window open"
  and listed in status (FR-001); it never releases the next window. This
  preserves today's "stale reply to a prior attempt's comment" behaviour
  (`pipeline_workflow.py:133-139`).
- **A validated decision carries no attempt number.** It is refused as
  malformed. Only legacy GitHub comments may omit the attempt.
- **A decision arrives after the plan budget is exhausted and the run has
  failed.** No window is open, and the run is no longer running. The
  submitter gets the existing "no in-flight run" outcome.
- **A validated decision times out as `worker_unavailable`, then a worker
  starts.** The run may still apply that decision. If the submitter
  resubmits the same delivery, the deterministic request id (FR-016) keeps
  it to one decision. If someone decides on another surface meanwhile,
  first-valid-wins (FR-005) picks exactly one.
- **The worker restarts between accepting a decision and acting on it.**
  The accepted decision is durable, and the run acts on it after the
  restart.
- **Runs started before this change.** They continue on their original
  behaviour (determinism-preserving migration). None are expected to exist
  at rollout.
- **A rejection with empty feedback.** A validated rejection with empty
  feedback is refused (FR-006), just as the existing grammar requires
  feedback after `plan_rejected:`. A `plan_rejected` signal with empty or
  whitespace-only feedback, which can only bypass the grammar from outside
  the bridge (for example the Temporal CLI), is ignored with reason
  "malformed" and listed in status; it never releases the window.

## Requirements *(mandatory)*

### Functional Requirements

**Status view**

- **FR-001**: Each pipeline run MUST answer a read-only status request with:
  - its current stage, from a fixed, documented set of stage values that
    includes terminal values for a completed or failed run (planning
    defines the set and the snapshot's shape as a versioned contract in
    `contracts/`, since specs 005 and 009 consume it);
  - the open decision window (gate and attempt number) or none;
  - charged versus maximum attempts for each budgeted stage;
  - the target PR URL, if known;
  - the most recent **applied** decision (gate, attempt, decision,
    `resolved_by`, `via`);
  - the last 20 ignored decision **signals** for the run, across windows
    (a duplicate for an already-decided window, a non-matching `attempt`,
    no window open, or malformed), each with its reason, decision, attempt (if given),
    `resolved_by`, `via`, and the window open when it arrived (or none).
    Beyond 20, the oldest entry is dropped, so the run's state stays
    bounded however many comments arrive. A refused validated decision
    never appears here: it is returned synchronously (FR-016) and leaves
    no trace (FR-007).
- **FR-002**: Answering a status request MUST NOT change the run's state or
  add to its recorded history.
- **FR-003**: The status answer MUST be treated as advisory. No component
  may rely on it alone to decide whether a decision will be accepted;
  FR-006 stays authoritative.

**Decision windows and first-valid-wins**

- **FR-004**: Each arrival of a run at the plan gate MUST open a new
  decision window identified by the plan attempt number. This follows the
  per-window semantics of `specs/005-pipeline-mode-signals-escalation`
  FR-016. The plan attempt number is part of the external contract:
  - it is the plan loop's iteration number, as today;
  - it only ever increases within a run, and gaps are allowed (an
    architect attempt that fails before reaching the gate uses up a
    number but opens no window);
  - it is never reused within a run, including after any future
    escalation-resume (a constraint on spec 005);
  - callers obtain it from status (FR-001) or the stage's PR comment and
    never compute it.
- **FR-005**: Within one decision window, the first valid decision in the
  run's recorded order MUST be the one the run acts on. Every later signal for that window MUST be
  ignored and recorded as a duplicate; every later validated decision MUST
  be refused per FR-006. This holds even when several
  decisions arrive in the same processing step, for every pairing of
  signal and validated decision.
- **FR-006**: The run MUST offer a validated decision path for the plan
  gate. It takes the decision (approve or reject), feedback (required for
  reject), the attempt number, `resolved_by` and `via`. It MUST refuse the
  decision before it takes effect, with a distinct reason, when:
  - no plan window is open;
  - the open window already has a recorded decision;
  - the attempt does not match the open window;
  - a rejection has empty feedback.
- **FR-007**: A refused validated decision MUST leave no trace in the run's
  recorded history. The submitter MUST receive the refusal reason
  synchronously.
- **FR-008**: The existing plan decision signals (`plan_approved`,
  `plan_rejected(feedback)`) MUST keep working, including with no extra
  arguments, exactly as today's bridge sends them. They MUST:
  - apply to whichever plan window is open;
  - take effect only if that window has no recorded decision yet;
  - accept an optional attribution `{resolved_by, via, attempt}`. When an
    attempt is supplied and does not match the open window, the signal is
    ignored as stale.
- **FR-009**: A decision delivered while no plan window is open MUST NOT
  release any later window (005 FR-016).
- **FR-010**: Every applied decision MUST be recorded with gate, attempt,
  decision, feedback, `resolved_by` and `via`. Absent attribution is
  recorded as unknown, never guessed.
- **FR-011**: The retry-budget accounting of the plan gate MUST be
  unchanged. Today's charge rules (004 consumer obligations CO-1..CO-4, as
  implemented in `pipeline_workflow.py:83-150`) apply exactly as before, and
  a duplicate or refused decision charges nothing.
- **FR-012**: The behaviour change MUST be introduced with a
  determinism-preserving migration, so a run started under the previous
  behaviour replays unchanged.

**Bridge core and GitHub adapter**

- **FR-013**: The bridge MUST be split into:
  - a **surface-neutral core**: command shapes, delivery de-duplication,
    audit outcomes, run identity and resolution, and the calls that start,
    signal, submit validated decisions to, and request status from runs;
  - a **GitHub adapter**: webhook signature verification, repo-permission
    authorization, PR and fork resolution, comment parsing into core
    commands, and rendering of outcomes as reactions.
- **FR-014**: Core operations MUST return their outcome to the caller
  instead of performing surface-specific side effects. In particular, the
  core's gate-signalling operation MUST NOT post GitHub reactions; the
  GitHub adapter renders them. The bridge's existing module paths and
  public signatures (`server`, `audit`, `auth`, `dedup.DeliveryCache`,
  `temporal_client` including `signal_gate(..., github_client)`) are
  preserved as the GitHub adapter's contract. `signal_gate` becomes a thin
  adapter that calls the core operation and renders the reaction from the
  returned outcome. The core lives in new module(s).
- **FR-015**: GitHub-visible behaviour MUST be unchanged: the same accepted
  commands, authorization rules, allow-list rule, fork rejection, reactions
  and HTTP responses. The pre-existing bridge test suite MUST pass without
  modification.
- **FR-016**: The core MUST expose a validated-decision submission that
  waits only until the run has accepted or refused the decision, with a
  bounded timeout. It reports:
  - accepted;
  - refused, with the FR-006 reason (refused-as-already-resolved also
    carries who resolved it and via which surface);
  - `worker_unavailable`, when no worker accepts the request within the
    timeout. This outcome is **indeterminate**, not a refusal: the run may
    still receive and apply the decision once a worker is available.
    Callers MUST NOT present it as "not applied"; they report the outcome
    as unknown and point to the run's status.

  Each submission MUST carry a request id derived deterministically from
  the surface-namespaced delivery id (FR-018), so resubmitting the same
  surface delivery is idempotent and can never yield a second decision.
- **FR-016a**: The core MUST expose a status operation. It resolves the
  target run the same way gate signalling does, requests the run's status
  (FR-001) with a bounded timeout, and reports:
  - the status snapshot;
  - `no in-flight run` or `multiple in-flight runs`, as gate signalling
    does today;
  - `worker_unavailable`, when no worker answers within the timeout.

  It is read-only, so its `worker_unavailable` is a plain "try later".
  The allow-list (FR-019) applies to it. No GitHub command reaches it in
  008: GitHub-visible behaviour is unchanged (FR-015), and spec 009 is its
  first surface.
- **FR-017**: The audit outcome set MUST gain `worker_unavailable`. For the
  plan gate only, `signal_issued_no_handler` MUST become `signal_issued`.
  PM and security gate signals keep `signal_issued_no_handler` until spec
  005 adds their handlers. The reaction for `signal_issued` stays 👀.
- **FR-018**: Delivery de-duplication keys in the core MUST be namespaced
  by surface, so ids from different surfaces never collide. GitHub's
  existing delivery-id behaviour is unchanged.
- **FR-019**: The repo allow-list rule (002 FR-016: disposable repos only
  until 005 ships) MUST be unchanged and MUST apply to every core entry
  point.
- **FR-019a**: Authorization is the adapter's job. The core trusts the
  `resolved_by` and `via` its caller passes and does not verify them, so
  every adapter MUST authorize the actor before calling a core operation,
  and the core MUST NOT be exposed except through an adapter that does.
  In 008 the GitHub adapter's existing permission check (002) is the only
  production caller of the gate path; the validated-decision path and the
  status operation have no production caller until spec 009.

**Local stack**

- **FR-020**: The local stack MUST run the supported `temporalio/server`
  and `temporalio/admin-tools` images, pinned to an exact tag at version
  ≥1.29.3, in place of today's deprecated `temporalio/auto-setup:latest`.
  The floor is the version `auto-setup:latest` resolves to today, so
  existing `temporal-pg-data` volumes are never downgraded. The stack MUST
  replace every setup step `auto-setup` performs today:
  - database schema setup and migration;
  - default namespace creation;
  - registration of the bridge's custom search attributes (`TargetRepo`,
    `PRNumber`).

  The search-attribute steps in
  `specs/002-webhook-trigger-bridge/quickstart.md` MUST still work, or be
  updated to match.

**Verification**

- **FR-021**: Automated tests MUST cover:
  - two decisions delivered in the same processing step (first wins,
    second recorded as duplicate or refused), separately for each pairing:
    signal + signal, validated + validated, and signal + validated in both
    orders;
  - an empty-feedback `plan_rejected` signal is ignored as malformed;
  - stale-attempt refusal;
  - no-window refusal;
  - already-resolved refusal with attribution;
  - legacy no-argument signals;
  - status while blocked at the plan gate;
  - `worker_unavailable` on timeout, for both the validated-decision
    submission (FR-016) and the status operation (FR-016a).

  They MUST run against an in-process test orchestration environment, with
  no external services. The workflow-level cases (every bullet above except
  `worker_unavailable`) MUST exercise the real `AgentPipelineWorkflow`
  class with its activities mocked, not a stand-in workflow. Bridge-core
  tests may use stubs and mocks.

### Key Entities

- **Decision window**: one opportunity to decide a gate for one attempt.
  Identified by gate (plan, for now) and attempt number, which only ever
  increases, may have gaps, and is never reused within a run (FR-004). It is open or
  closed, and holds at most one recorded decision.
- **Decision**: approve or reject. It carries feedback (required for
  reject), the attempt it targets (optional for legacy GitHub comments),
  `resolved_by` (a GitHub login or a directory user id; unknown if absent)
  and `via` (`github`, later `teams`; unknown if absent).
- **Run status**: a read-only snapshot of stage, open window, budgets, PR
  URL, last applied decision, and the last 20 ignored decision signals, each
  tagged with the window open when it arrived.
- **Core command / outcome**: a surface-neutral request (start run, gate
  decision, status) and its audit outcome. The existing outcomes are kept;
  `worker_unavailable` and `signal_issued` are new.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For 100% of tested cases where two or more decisions reach the
  same decision window, exactly one is acted on, and it is the first in
  the run's recorded order. Every other signal is recorded as a duplicate, and every other
  validated decision is refused as already resolved.
- **SC-002**: 0% of decisions naming an earlier attempt, or arriving with no
  window open, change a run's outcome.
- **SC-003**: 100% of the bridge's pre-existing tests pass without any
  change to the tests.
- **SC-004**: A status request returns an accurate snapshot in 100% of
  tested states, including while blocked at the plan gate. It leaves the
  run's recorded history the same length as before the request.
- **SC-005**: When no worker is running, 100% of validated decision
  submissions and status requests return a distinct "unavailable" result
  within 10 seconds, instead of hanging.
- **SC-006**: Every applied decision is recorded with who made it and
  through which surface, or explicitly as unknown. No attribution is ever
  guessed.
- **SC-007**: Starting the local stack twice from a clean state yields the
  same pinned orchestration server version both times, and that version is
  ≥1.29.3. Starting it on a volume created by today's `auto-setup:latest`
  needs no schema reset.

## Assumptions

- **Only the plan gate exists today.** PM, security and escalation gates
  (spec 005) will adopt the same decision-window and first-valid-wins model
  when 005 adds them. This feature does not add those handlers.
- **GitHub keeps today's surface.** It continues to send plain signals,
  with no attempt number and no attribution payload, because the unchanged
  bridge tests pin the signal's call shape (FR-015). GitHub decisions are
  therefore recorded with `resolved_by` and `via` as unknown (FR-010). Two
  possible follow-ups are not part of this feature: attaching
  `{resolved_by, via: "github"}` to GitHub signals, and making the GitHub
  path query the open attempt and submit validated decisions.
- **A losing GitHub comment can't be reacted to differently.** Signals give
  no synchronous feedback, so a GitHub comment that loses the race still
  gets today's 👀 reaction. That it was ignored is visible in the run's
  status, in its ignored-decisions list (FR-001). Changing the GitHub reaction for that
  case would be a GitHub-visible behaviour change and is out of scope.
- **Keeping the bridge tests unchanged shapes the split.** FR-015's rule
  that the existing tests pass unmodified is what places the core in new
  modules and turns the existing modules (including `signal_gate(...,
  github_client)`) into the GitHub adapter. This is a deliberate trade-off:
  a slightly awkward layout in exchange for a regression guard on GitHub
  behaviour.
- **Landing order with spec 005.** 008 has no functional dependency on 005,
  but both change the same plan-gate code in `AgentPipelineWorkflow`
  under determinism markers. Whichever spec lands second MUST rebase onto
  the other's markers rather than add a parallel one. 008 removes today's
  reset of the plan decision before the wait
  (`pipeline_workflow.py:138-139`), because set-if-unset handlers and
  per-window state replace it.
- **`docs/80` diverges from this spec in two places, and this spec governs.**
  - §12.1 says a GitHub comment that loses the race is logged as
    `duplicate_ignored`. The bridge cannot know that, because signals
    return nothing; the run records it instead (FR-001).
  - §12.4 says a late GitHub answer gets 😕. It gets 👀, as today.

  `docs/80` should be corrected to match.
- **The 10-second bound in SC-005 is a default.** The exact timeout is a
  planning decision.
- **No production-relevant runs are in flight at rollout.** The 002 FR-016
  disposable-repo rule guarantees it, so the determinism-preserving
  migration is a safeguard, not a data-migration effort.
- **Out of scope:**
  - Microsoft Teams (spec 009);
  - the run mode parameter, and PM/security/escalation handlers (spec 005);
  - feature-level lanes (spec 013);
  - the outbound notifier (spec 009);
  - any change to the architect stage's own behaviour (spec 004).
- **Design references.** The design rationale and research evidence live in
  `docs/80-teams-workspace-design.md` §7.2, §12 and §14.8, and in
  `docs/research/teams-workspace-research-findings.md` (entries L.1, L.2).
