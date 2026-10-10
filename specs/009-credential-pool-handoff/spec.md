# Feature Specification: Subscription-Seat Credential Pool with Checkpointed Agent Handoff

**Feature Branch**: `009-credential-pool-handoff`

**Created**: 2026-10-10

**Status**: Draft

**Input**: User description: "009-credential-pool-handoff: a Max-subscription credential pool with checkpointed agent handoff. Run the pipeline's agents (swe-agent, architect-agent; pm-agent review_spec later) on a pool of Claude Max OAuth seats. Each seat has one `claude setup-token` token, passed as CLAUDE_CODE_OAUTH_TOKEN. A seat can be assigned to one agent or several. The seat for each run is the one with the lowest last-seen utilization (RateLimitEvent). When a seat is exhausted (429/rejected) or invalid (401/login expired) mid-task, the work is pushed and a successor run on another seat resumes from the last pushed tasks.md checkpoint without losing committed work. A long-lived Temporal CredentialPoolWorkflow leases seats via updates. Only seat IDs, never tokens, appear in Temporal history, logs and PR comments. Constraint to record: internal, single-operator use only, never offered to third parties (Agent SDK terms; seat rotation is a Consumer-Terms grey area, knowingly accepted). Ships with one real seat (seat-a); failover is testable with two logical seats on one token. Open research: whether LiteLLM can front OAuth seats (if so, rotating seats in LiteLLM is cheaper), and whether empty-string env overrides beat an inherited ANTHROPIC_API_KEY/BASE_URL in the CLI. Out of scope: the GitHub-comment path and pm shape_issue (they stay on the API key), a durable sleep-until-reset when all seats are out, and token-expiry alerting."

Design input:
- `~/.claude/plans/think-about-how-we-kind-honey.md`: the design and its rationale.
- `~/.claude/plans/implement-claude-plans-think-about-how-w-fluttering-sutton.md`: corrections from code reading, and the build order.

## Usage Constraint *(binding)*

This capability is for **internal, single-operator use only**. Concretely:
- The subscription seats in the pool belong to the operator who runs this pipeline.
- The pipeline and its seat pool are never offered as a product or service to third parties.
- Seat login or rate limits are never exposed to anyone else's product.

This constraint follows from the Agent SDK's terms ("Unless previously approved, Anthropic does not allow third party developers to offer claude.ai login or rate limits for their products"). Rotating several subscription seats to extend usage limits is a grey area under the Consumer Terms. The operator chose that knowingly and on purpose (2026-10-10). Every artifact this feature produces (docs, `SKILL.md`, architecture §3.4) MUST restate this constraint, and none of them may present seat pooling as a supported product feature.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run a pipeline stage on a subscription seat instead of an API key (Priority: P1)

The operator configures a pool of subscription seats; today the pool holds one seat. When the pipeline runs a seat-backed stage (Build, then Architect), it borrows a seat from the pool, runs the agent on it, and returns the seat with that run's last-seen usage recorded. The operator can see which seat each run used, by seat ID only, and how much usage each seat had left the last time it was seen. No API key is needed for that stage.

**Why this priority**: This is the minimum useful slice, and with one seat it is fully testable today. Every other story depends on a stage being able to borrow a seat and give it back.

**Independent Test**: Configure a single-seat pool. Run one Build. Verify that:
- the run succeeded;
- the run used that seat's credential, even with a stray, invalid API key in the process environment;
- the pool records the seat as free again, with the usage figure from that run;
- no credential value appears in workflow history, logs or PR comments.

**Acceptance Scenarios**:

1. **Given** a pool with one healthy seat assigned to the Build agent, **When** a Build runs, **Then** it runs on that seat, completes, and the seat goes back to free with its last-seen usage updated.
2. **Given** the process environment also contains an API key and an alternate API base URL, **When** a seat-backed stage runs, **Then** the agent still authenticates with the seat credential, not the API key.
3. **Given** any seat-backed run, **When** an operator inspects workflow history, logs or PR comments, **Then** they find seat IDs only, never a seat credential.

---

### User Story 2 - Lose no committed work when a seat runs out mid-task (Priority: P1)

A Build can be partway through its task list when its seat hits a usage limit. When that happens:
1. The agent stops.
2. Everything completed so far is already saved as one checkpoint per finished task, and gets published to the feature branch.
3. The pipeline starts a successor run on a different seat.
4. The successor continues from the first unfinished task.

The finished tasks are not redone. There is still exactly one pull request, and the handoff does not use up any of the pipeline's retry budgets for real failures.

**Why this priority**: Without this, a usage limit in the middle of a run throws the whole run away, which is the outcome this feature exists to prevent. With only one real seat, the mechanics can still be tested by configuring two logical seats that share the same credential.

**Independent Test**: Use a pool of two logical seats and force exhaustion after the first finished task. Verify that:
- the first task's checkpoint was published;
- the successor used the other seat and started at the second task;
- exactly one pull request exists;
- the Build-attempt and plan-attempt budgets are untouched.

**Acceptance Scenarios**:

1. **Given** a Build that has finished and checkpointed task 1, **When** its seat reports exhaustion during task 2, **Then** task 1's checkpoint is published to the branch before the run ends.
2. **Given** a published checkpoint with task 1 marked done, **When** the successor run starts on another seat, **Then** it skips task 1 and starts with the first task not yet marked done.
3. **Given** a handoff happened, **When** the successor finishes, **Then** the branch has exactly one pull request, and the handoff consumed neither the Build-attempt nor the plan-attempt budget.
4. **Given** a predecessor that had checkpointed every task but stopped before opening the pull request, **When** the successor starts, **Then** it does no implementation work and goes straight to publishing and opening (or reusing) the pull request.

---

### User Story 3 - Choose seats by remaining usage, respecting assignments and sharing (Priority: P2)

The operator assigns each seat to one or more agents, with a per-agent order of preference. A seat that appears in several agents' lists is shared. When a stage needs a seat, the pool picks it as follows:
- it considers only seats assigned to that agent;
- it skips seats that are known to be exhausted until their reset time;
- it skips seats whose credential has been reported invalid, until the operator renews it;
- it skips seats already running their maximum number of concurrent runs;
- from the rest, it picks the seat with the lowest last-seen usage, breaking ties by the agent's preference order.

The operator can ask the pool for its current seat table at any time.

**Why this priority**: This matters once there is more than one seat. Until then, a one-seat pool still exercises the same rules on a trivial input.

**Independent Test**: Use the pool's selection rules with a constructed seat table that covers assignment order, a shared seat, a full concurrency cap, an exhausted seat whose reset time has passed, an invalid seat, and every seat unavailable. Verify each pick.

**Acceptance Scenarios**:

1. **Given** two free seats assigned to an agent with last-seen usage of 0.7 and 0.2, **When** that agent asks for a seat, **Then** it gets the 0.2 seat.
2. **Given** a seat marked exhausted until a reset time, **When** a request comes in before that time, **Then** the seat is skipped. **When** a request comes in after that time, **Then** it is eligible again.
3. **Given** a seat marked invalid, **When** any request arrives, **Then** that seat is skipped until the operator renews it, however much time has passed.
4. **Given** a shared seat already running its maximum number of concurrent runs, **When** another agent asks for a seat, **Then** the shared seat is skipped.
5. **Given** the operator asks for the seat table, **When** the pool answers, **Then** every seat shows its ID, active lease count, last-seen usage, exhaustion state with reset time, and invalid flag, and no credential.

---

### User Story 4 - Fail clearly when every seat is unavailable (Priority: P2)

Every seat an agent may use can be exhausted or invalid at once. When that happens, the stage stops with a clear, distinguishable failure that names the earliest time a seat is expected to reset. That failure does not charge the Build-attempt or plan-attempt budgets. All work committed so far stays published.

**Why this priority**: With today's single seat this is the most likely failure. Exhaustion must not look like a bug or a gate failure, and it must not burn the retry budgets that later escalation (spec 005) relies on.

**Independent Test**: Use a one-seat pool and force exhaustion. Verify that:
- the run fails with the "credential pool exhausted" failure kind and an earliest reset time;
- the completed work was published;
- no budget was charged.

**Acceptance Scenarios**:

1. **Given** a one-seat pool whose seat becomes exhausted mid-Build, **When** no other seat is eligible, **Then** the run fails with a pool-exhausted failure that carries the earliest reset time, and the work committed so far is on the branch.
2. **Given** a pool-exhausted failure during the Architect stage, **When** the workflow handles it, **Then** the plan-attempt budget is not charged.

---

### User Story 5 - Run the Architect stage on seats (Priority: P3)

The Architect stage (spec 004) runs on a pool seat. If that seat runs out partway through, the whole stage runs again on another seat. The architect has no candidate-level checkpoint, and a re-run is cheap and idempotent per attempt. A re-run does not post a duplicate stage comment and does not charge the plan-attempt budget.

**Why this priority**: The Architect stage uses less of a seat than Build, and it is already idempotent per attempt. Build delivers most of the value first.

**Independent Test**: Stub the stage so its first seat reports exhaustion. Verify that the stage re-ran on a different seat, that the plan-attempt budget was not charged, and that exactly one stage comment exists for that attempt.

**Acceptance Scenarios**:

1. **Given** an Architect stage whose seat reports exhaustion during candidate fan-out, **When** that happens, **Then** the sibling candidate calls on the same seat stop instead of continuing to hit it, and the stage re-runs on another seat.
2. **Given** a seat-triggered Architect re-run, **When** it completes, **Then** the plan-attempt budget is unchanged by the handoff.

---

### Edge Cases

- **The credential has expired or been revoked.** The seat is marked invalid, not exhausted, so it is never tried again automatically. Work is published and the run hands off to another seat as for exhaustion. Only an operator renewing the credential clears the invalid mark.
- **A seat is exhausted on the agent's very first call**, before any task is done. Nothing new needs publishing, and the successor starts from the same first unfinished task.
- **The task in progress has uncommitted edits when the seat runs out.** Those partial edits are lost, and the successor redoes that one task. This bounded loss of at most one task is accepted.
- **Usage signal never appears.** That signal is undocumented and best-effort. If it is never emitted, the seat's last-seen usage stays at its previous value (initially 0), and selection falls back to preference order. Exhaustion detection does not depend on the signal, because the failure result also reveals it.
- **An agent has no assigned seats.** Asking for a seat returns none immediately, which surfaces as a pool-exhausted failure, never a hang.
- **A run crashes without returning its seat.** For example, the worker dies mid-run. The lease must not stay held for ever. Each lease is tied to a run identity and can be cleared when that run's handoff or retry asks again. See FR-007.
- **Handoffs exceed their budget.** A bounded handoff budget, separate from the Build-attempt and plan-attempt budgets, stops endless seat ping-pong. Exceeding it fails the stage with a distinct failure kind.
- **A successor finds an existing pull request.** It reuses the pull request and never opens a second one.
- **The pool's state history grows without bound** over weeks of uptime. The long-lived pool periodically restarts itself and carries its seat table forward.

## Requirements *(mandatory)*

### Functional Requirements

**Seat registry**

- **FR-001**: The system MUST read the seat pool from a checked-in configuration that contains:
  - for each seat: its ID, the *name* of the environment variable holding its credential, its maximum concurrent runs, and its credential's expiry date;
  - for each agent: an ordered list of the seats it may use.

  Credential values MUST live only in the worker's environment, never in the configuration or the repository.
- **FR-002**: The configuration MUST let one seat appear in several agents' lists (shared) or in only one (dedicated).
- **FR-003**: The configuration path MUST be overridable per environment, so a test pool can point two logical seats at the same credential.

**Pool and leasing**

- **FR-004**: A single long-lived pool MUST own all seat state:
  - active leases (by run identity);
  - last-seen usage and limit type;
  - exhausted-until time;
  - an invalid flag.
- **FR-005**: Seat selection MUST, for the requesting agent:
  1. consider only its assigned seats;
  2. exclude seats that are invalid, exhausted until a time still in the future, or at their concurrency cap;
  3. pick the lowest last-seen usage, breaking ties by the agent's preference order;
  4. return "none" when no seat is eligible.

  Selection MUST be a pure, independently testable rule.
- **FR-006**: The pool MUST support these operations:
  - acquire (agent, run);
  - release (seat, run, last-seen usage, limit type);
  - mark-exhausted (seat, run, reset time);
  - mark-invalid (seat, run);
  - a read-only seat-table query.

  Mark-exhausted and mark-invalid MUST also release the lease.
- **FR-007**: Acquire and release MUST be idempotent per run identity. A repeated acquire for a run that already holds a lease returns that same seat. A release for a lease that isn't held is a no-op.
- **FR-008**: The pool MUST bound its own history growth over long uptimes and carry its seat table across a restart.
- **FR-009**: Starting the pool MUST be idempotent: worker boot starts it if it is absent and reuses it if present. The pool's identity MUST be overridable, so tests do not collide with a running pool.

**Agent-side detection**

- **FR-010**: Every seat-backed agent call MUST:
  - record the last-seen usage, limit type and reset time from the usage signal while it runs;
  - classify the call's outcome. A rejected usage signal, a "too many requests" result, or a usage/rate-limit message means **exhausted**, with the reset time when one is known. An authentication failure, a "forbidden" result or an expired-login message means **invalid**. Any other failure passes through unchanged.
- **FR-011**: The *exhausted* and *invalid* outcome kinds MUST NOT be caught or remapped by any existing generic error handling. A seat outcome must never be reported as a deterministic plan failure or a malformed-candidate failure.
- **FR-012**: A seat-backed call MUST authenticate with the seat credential only. Any API key, alternate base URL or bearer token inherited by the agent process MUST NOT take precedence over it.
- **FR-013**: Within the Architect stage, a seat outcome in any one candidate call MUST stop that stage's other in-flight calls on the same seat.

**Checkpointing and handoff (Build)**

- **FR-014**: The Build agent MUST checkpoint after each completed task by marking it done in the task list and committing locally. It MUST treat tasks already marked done as finished by a predecessor and skip them.
- **FR-015**: When a Build ends on a seat outcome, the agent MUST:
  1. publish all committed work to the feature branch;
  2. report a machine-readable seat status (exhausted or invalid, with reset time and usage);
  3. end with an exit status that distinguishes exhausted from invalid from other failures.

  On success it MUST report a seat status of "ok" with usage, and keep reporting the pull-request URL as its final output.
- **FR-016**: The stage runner MUST translate those exit statuses into distinct, non-retryable failure kinds (*SeatExhausted*, *SeatInvalid*) that carry the seat ID and reset time. Every other failure keeps today's behavior. It MUST also make sure the agent's command time limit is not shorter than the stage's own time limit.
- **FR-017**: If the checked-out task list has no unfinished tasks, a Build MUST skip implementation and go straight to publishing and opening (or reusing) the pull request.

**Workflow wiring**

- **FR-018**: Each seat-backed stage invocation MUST:
  1. acquire a seat;
  2. run the stage on it;
  3. release the seat with the reported usage on success;
  4. on *SeatExhausted* or *SeatInvalid*, report it to the pool and go back to step 1 for a successor.
- **FR-019**: Seat handoffs MUST count against their own bounded budget (default 4 per stage invocation). They MUST NOT be charged to the Build-attempt budget or the plan-attempt budget. Exceeding the handoff budget MUST fail the stage with a distinct failure kind.
- **FR-020**: When acquire returns none, the stage MUST fail with a distinct *CredentialPoolExhausted* failure that carries the earliest known reset time. This failure MUST NOT be charged to the Build-attempt or plan-attempt budget.
- **FR-021**: The workflow change MUST be gated so that any run started before it replays deterministically.
- **FR-022**: Build MUST be wired to the pool first. Architect wiring follows, under the same rules.

**Secrecy and observability**

- **FR-023**: A seat credential MUST NOT appear in any of the following:
  - workflow inputs, outputs or history;
  - activity arguments or results;
  - logs;
  - exception messages;
  - PR comments;
  - the agent's own output.

  Only seat IDs may appear.
- **FR-024**: The sandbox image MUST include the seat-detection support and an SDK version that emits the usage signal.

### Key Entities

- **Seat**: one subscription login. It has an ID, a reference to where its credential lives (never the value), a concurrency cap and a credential expiry date. Its runtime state is active leases, last-seen usage (0–1), last limit type, exhausted-until and invalid.
- **Assignment**: the per-agent ordered list of the seats that agent may use.
- **Lease**: a seat held by one run identity, from acquire until release, mark-exhausted or mark-invalid.
- **Seat Outcome**: the result of a seat-backed run: ok (with usage), exhausted (with reset time) or invalid.
- **Checkpoint**: a committed task-list state in which done tasks are marked done. It is published to the feature branch at handoff and at the end of a run.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With a single configured seat, a Build stage completes end to end with no API key in use. The pool then reports the seat as free, with a last-seen usage value recorded from that run.
- **SC-002**: In a forced mid-run exhaustion, 100% of tasks completed and checkpointed before the exhaustion appear on the branch afterwards, and the successor redoes at most one task (the one in progress).
- **SC-003**: Every handoff ends with exactly one pull request on the feature branch.
- **SC-004**: A seat handoff, or a pool-exhausted failure, changes the Build-attempt and plan-attempt budget counters by 0.
- **SC-005**: For every combination in the selection test matrix, the pool picks the expected seat: assignment order, shared seat, concurrency cap, exhaustion expiry, invalid seat, and every seat unavailable.
- **SC-006**: A search of workflow history, worker logs and PR comments from a full seat-backed run, including one handoff, finds 0 occurrences of any seat credential value.
- **SC-007**: With a deliberately invalid API key and base URL in the parent environment, a seat-backed call still succeeds 100% of the time. This shows the seat credential takes precedence.
- **SC-008**: When every seat is unavailable, the stage fails within one acquire attempt, with no hang or busy-wait, and the failure states the earliest reset time.

## Assumptions

- **One seat to start.** The operator holds one working subscription seat credential today (verified live on 2026-10-10). The first pool configuration contains only that seat, so real failover starts when a second seat is added. Two logical seats sharing one credential are a test fixture only and do not add capacity.
- **Credential lifetime.** Seat credentials last about one year and are never renewed automatically. When one expires, every call fails as an expired login, so the operator renews it by hand.
- **Usage signal.** The usage signal is undocumented and best-effort, and it only appears while a call is running. "Usage left" therefore means the *last-seen* value per seat, not a live reading.
- **Seat-backed calls bypass the inference proxy (§3.4).** This is a documented deviation: the assumption is that the proxy can't front subscription logins. Research in the planning phase MUST check that assumption. If the proxy *can* pass the subscription credential through, rotating seats at the proxy becomes the cheaper alternative and the plan MUST weigh it.
- **Override behavior is unverified.** Research MUST verify whether blanking an inherited API key or base URL in the agent's own environment overrides it. If it doesn't, the inherited values MUST be removed for the duration of the call instead.
- **Task-skipping must be told explicitly.** The implementation skill marks finished tasks but does not itself promise to skip them on a re-run, so the resume instruction is supplied explicitly.
- **Architect re-runs are safe.** The Architect stage's existing per-attempt idempotency (no duplicate stage comment) makes a whole-stage re-run on another seat safe.
- **Dependencies.** Spec 005's escalation work is expected to consume the *CredentialPoolExhausted* failure later. This feature only defines it and does not escalate it.

## Out of Scope

- **The GitHub-comment Build path and the PM issue-shaping capability** stay on the API key. The GitHub-hosted runners they use have no access to the pool.
- **Waiting for a reset.** A durable "wait until the earliest reset time, then resume" when every seat is unavailable is a follow-up after spec 005.
- **Expiry alerting.** The expiry date is captured now. Alerting the operator before a credential expires (for example a Teams notice 7 days ahead) is a follow-up.
- **pm-agent `review_spec` on seats.** It is listed for later and not wired in this feature.
- **Unrelated defects found along the way.** The template agent bypasses the inference proxy, and the GitHub-path sandbox's API-key variable mapping is wrong. Both are tracked separately.
