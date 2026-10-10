# Feature Specification: Seat Pool Hardening (closing out 009)

**Feature Branch**: `011-seat-pool-hardening`

**Created**: 2026-10-10

**Status**: Implemented (2026-10-11; V5 run 4 passed, see quickstart.md)

**Input**: User description: "Seat-pool hardening: close the follow-ups and known gaps of specs/009-credential-pool-handoff. F1 (highest priority, SC-002's core promise): the Build harness commits a checkpoint deterministically whenever a task is newly marked done, instead of relying on the model to commit per task. F2: stale utilization. F3: wait durably when every seat is exhausted. F4: token-expiry warning. F5: a Gate-feedback retry that hands off must not fail the 'no new commit' check. F6: a test hook that forces whichever seat runs a given handoff. Plus a live re-run proving mid-task resume."

Design input: `specs/009-credential-pool-handoff/` (spec, contracts, quickstart "V5 details" and "Follow-ups surfaced by V5") and the handoff prompt of 2026-10-10.

## Usage Constraint *(binding, restated from 009)*

This capability is for **internal, single-operator use only**:
- The subscription seats in the pool belong to the operator who runs this pipeline.
- The pipeline and its seat pool are never offered as a product or service to third parties.
- Seat login or rate limits are never exposed to anyone else's product.

This follows from the Agent SDK's terms ("Unless previously approved, Anthropic does not allow third party developers to offer claude.ai login or rate limits for their products"). Rotating several subscription seats to extend usage limits is a grey area under the Consumer Terms, chosen knowingly by the operator on 2026-10-10. Every artifact this feature produces MUST restate this constraint and MUST NOT present seat pooling as a supported product feature.

## Clarifications

### Session 2026-10-10

The six design forks from the handoff prompt (F1–F6). The operator was away (background job), so each takes the prompt's recommended option and is **agent-decided, to confirm**.

- Q: F1 — How are checkpoints enforced? → A: (a) the harness commits deterministically when the set of done task IDs grows and the tree is dirty (`checkpoint: T001`). Rejected: (b) only warn when commits < tasks done; (c) a git hook in the sandbox. *Agent-decided, to confirm.*
- Q: F2 — How is a stale usage reading handled? → A: reset-aware: the reading stores the reset time of the window it came from (the max-utilization window, not the top-level reset), and selection treats it as 0 once that time has passed. Rejected: time-based decay. *Agent-decided, to confirm.*
- Q: F3 — What happens when every seat is out? → A: (b) wait durably until the earliest reset when it is at most 6 h away, at most 2 waits per stage invocation, then ask again; behind a new workflow patch ID. A reset further away, or only-invalid pools (no reset time), still fail fast. (The prompt's "cap at 6 h" is read as a horizon, not a partial wait: sleeping 6 h toward a reset 9 h away only delays the same failure.) Rejected: (a) always fail fast. *Agent-decided, to confirm.*
- Q: F4 — How is the operator warned about expiring credentials? → A: (a) a worker-startup log warning for seats within 14 days of expiry, plus `expires_in_days` in the seat table. Rejected: (b) also a PR/issue comment. *Agent-decided, to confirm.*
- Q: F5 — Fix the feedback-retry handoff gap, or document it? → A: fix it: the Build run receives its handoff index and skips the "made no new commit" check when it is above 0. The prompt's extra condition "and the branch is ahead of the original start" is dropped, because a successor has no original-start commit without threading one through the exhaustion details; the remaining narrow gap (predecessor pushed nothing *and* successor commits nothing) then surfaces at the Eval-Gate instead of as exit 1. *Agent-decided, to confirm.*
- Q: F6 — How can the force hook not be routed around? → A: (b) a new setting `SEAT_GUARD_FORCE_EXHAUST_HANDOFF=N` forces whichever seat runs handoff N of the Build stage (possible because F5 delivers the handoff index); the 009 seat-name setting keeps working. Rejected: (a) query `seats()` first and force the seat that will be picked. *Agent-decided, to confirm.*

### Session 2026-10-11

- Q: Does the operator confirm F1–F6? → A: Yes, all six as recorded above. *Operator-confirmed, 2026-10-11.*
- Q: F7 — How does a Build make the successor start at the next task when the model ticks several tasks in one edit? → A: (a) one model session per open task (FR-023–FR-026). *Operator-ruled, 2026-10-11.* Rejected: (b) change only the fixture or the scratch repo's implement skill; (c) accept the model's tick granularity.

### Fork F7, raised by V5 run 3 (2026-10-10; ruled F7-a on 2026-10-11)

F1(a) assumes the model ticks one task at a time. The live run shows it doesn't: in 009 run 2 and again in 011 run 3, the model implemented all three tasks and then marked them `[X]` in one edit. The harness saved that work (nothing was lost), but one tick event can only become one checkpoint. So "the successor starts at task 2" (User Story 2, SC-001) cannot be shown on this fixture with F1(a) alone.

- **F7-a (agent's recommendation): drive one task per model session.** The harness loops over the open tasks in order. Each `query()` says "implement only `<ID>`, mark it `[X]`, stop", and the checkpointer commits between sessions. The all-done shortcut and the single-session Gate-feedback retry stay as they are. Costs: N CLI sessions per Build, each re-reading the spec and plan; no shared context between tasks; more seat usage per Build; `/speckit-implement` may still ignore "only T001", so the prompt would name the task, not the skill.
- **F7-b: change the fixture or the scratch repo's implement skill** (one phase per task, a stronger instruction). Cheap but unreliable, and it proves nothing about production runs.
- **F7-c: accept tick granularity as the model's.** F1 still guarantees that whatever is ticked survives a handoff. SC-001 of this spec and SC-002 of 009 are then met only for models that tick per task.

Related, for specs 006/008: today's Eval-Gate passes a Build whose diff touches only `tasks.md`, or nothing at all. It should require a non-empty diff beyond `tasks.md`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Every finished task is saved, whatever the model does (Priority: P1)

A Build works through a task list. Each time a task is newly marked done in the task list, the harness itself saves a checkpoint (a commit naming the task IDs), so finished work no longer depends on the model remembering to commit. When the stream ends with unsaved edits, the harness saves them too. If the seat runs out in the middle of the list, every task marked done before that point is on the branch, and the successor starts at the first task not yet marked done.

**Why this priority**: This is 009's SC-002 promise. In the 009 live run the model batched three tasks into one commit, so an exhaustion in the middle of that batch would have lost finished work.

**Independent Test**: Drive the Build agent with a scripted model that marks T001 done and edits a file without committing. Verify that a commit "checkpoint: T001" exists afterwards, that a forced exhaustion after one commit fires right after that checkpoint, and that the pushed branch holds it.

**Acceptance Scenarios**:

1. **Given** a Build in which the model marks T001 done and leaves the change uncommitted, **When** the harness sees the next message, **Then** it commits the work as "checkpoint: T001".
2. **Given** the model marks T001 done and commits it itself, **When** the harness checks, **Then** it makes no extra commit and does not report T001 again later.
3. **Given** the model marks T002 and T003 done in one edit, **When** the harness checks, **Then** it makes one commit naming both IDs.
4. **Given** the stream ends (normally or on a seat outcome) with uncommitted edits, **When** the harness finishes, **Then** those edits are committed before any push. On a seat outcome, edits are committed only when a task was newly marked done; otherwise they stay uncommitted (009's accepted loss of at most the task in progress).
5. **Given** a checkpoint commit fails (for example because the model is committing at the same moment), **When** the next message arrives, **Then** the harness tries again, and the Build does not fail because of it.

---

### User Story 2 - Live proof of mid-task resume (Priority: P1)

The operator re-runs the 009 live end-to-end test so that the first Build seat runs out after exactly one task checkpoint, and the successor on the other seat continues at the second task.

**Why this priority**: 009 proved a lossless handoff, but not "resume in the middle of the list". This run is the evidence that closes SC-002.

**Independent Test**: The live V5 procedure in `quickstart.md`.

**Acceptance Scenarios**:

1. **Given** a two-seat test pool and a forced exhaustion of whichever seat runs the first Build handoff, after one commit, **When** the run completes, **Then**:
   - the first Build seat failed as exhausted after exactly one task commit (T001);
   - the remote branch holds T001's commit, made by the first seat;
   - the successor ran on the other seat and its first commit is for T002 or later;
   - there is exactly one feature pull request;
   - a search of workflow histories, the worker log and PR comments finds 0 credential values.

---

### User Story 3 - Seats are not avoided after their window resets (Priority: P2)

A seat's last-seen usage belongs to a usage window that has its own reset time. Once that time passes, the reading no longer describes the seat. Selection then treats the seat's usage as 0, so a seat that was busy before its reset is chosen again on merit. An exhausted seat's 1.0 reading likewise stops counting once its exhaustion period ends.

**Why this priority**: In the 009 run, seat-a kept a 0.91 reading after its reset and was avoided for no reason. Wrong but harmless with one seat; wasteful with several.

**Independent Test**: Selection rule test with a seat whose reading is 0.9 with a reset time in the past and another seat at 0.3: the first seat is picked.

**Acceptance Scenarios**:

1. **Given** seat A at 0.9 whose reading's reset time has passed and seat B at 0.3, **When** an agent asks for a seat, **Then** it gets seat A.
2. **Given** seat A at 0.9 whose reading's reset time is still in the future, **When** an agent asks for a seat, **Then** it gets seat B.
3. **Given** a seat marked exhausted until a time that has passed, **When** an agent asks for a seat, **Then** the seat's old 1.0 reading is treated as 0.
4. **Given** a reading with no known reset time, **When** selection runs, **Then** the reading is used as is (today's behavior).
5. **Given** pool state carried from before this feature (no reset time stored), **When** the pool runs, **Then** it keeps working and treats those readings as having no known reset time.

---

### User Story 4 - Wait for a reset instead of failing (Priority: P2)

When every seat an agent may use is exhausted and the earliest known reset time is at most 6 hours away, the stage waits until that time, then asks for a seat again, instead of failing the run at once. A stage waits at most twice. If no seat has a known reset time (for example every seat is invalid), the earliest reset is more than 6 hours away (for example a seven-day window), or both waits are spent, the stage fails as today with the "credential pool exhausted" failure kind, which names the earliest reset time. Waiting charges no retry budget and no handoff.

**Why this priority**: With one real seat, running out is the most likely failure. A run that can wait out a five-hour window finishes on its own instead of needing an operator to restart it.

**Independent Test**: Stub the seat lease so that the first request returns "no seat, earliest reset in 2 seconds" and the second returns a seat. Verify that the stage succeeds, that no budget was charged, and that a pool with only invalid seats still fails at once.

**Acceptance Scenarios**:

1. **Given** every assigned seat exhausted with the earliest reset 2 hours away, **When** a stage asks for a seat, **Then** the run waits until that time (durably, surviving worker restarts) and then asks again.
2. **Given** the earliest reset is 9 hours away, **When** a stage asks for a seat, **Then** it fails at once with "credential pool exhausted" and that reset time (waiting 6 hours for a seat that is still out would only delay the failure).
3. **Given** a stage that has already waited twice and still gets no seat, **When** it asks again, **Then** it fails with "credential pool exhausted" and the earliest reset time.
4. **Given** every assigned seat invalid (no reset time), **When** a stage asks for a seat, **Then** it fails at once with "credential pool exhausted".
5. **Given** a run started before this feature, **When** it is replayed, **Then** it follows the old fail-fast behavior.

---

### User Story 5 - Warn before a seat credential expires (Priority: P3)

Seat credentials last about a year and are renewed by hand. At startup the worker logs a warning for every seat whose credential expires within 14 days or has already expired, naming the seat ID and the date, never the credential. The pool's seat table shows the days left for every seat.

**Why this priority**: An expired credential fails every call on that seat. A warning a fortnight ahead is cheap and prevents a surprise outage.

**Independent Test**: Load a pool config with one seat expiring in 3 days, one in 400 days and one with no date; verify one warning line and the days-left values in the seat table.

**Acceptance Scenarios**:

1. **Given** a seat expiring in 3 days, **When** the worker starts, **Then** one warning names that seat and its expiry date.
2. **Given** a seat with no expiry date, **When** the seat table is read, **Then** its days-left value is empty, and no warning is logged for it.
3. **Given** any seat, **When** the operator reads the seat table, **Then** each row shows its days left (negative once expired).

---

### User Story 6 - A feedback retry that hands off does not fail for lack of a new commit (Priority: P3)

On a Gate-feedback retry, the first seat may commit the fix, push it and then run out. The successor finds the fix already on the branch and has nothing new to commit. Today that fails the Build with "made no new commit". The successor now knows it is a successor (its handoff index is above 0) and skips that check, because the predecessor's pushed commits count as this attempt's work.

**Why this priority**: Rare (needs a gate failure and a seat outcome in the same attempt), but when it happens it fails the whole run.

**Independent Test**: Run the Build agent with feedback, a handoff index of 1, and a scripted model that makes no commit: it opens (or reuses) the pull request and exits 0. With handoff index 0 the same input still fails.

**Acceptance Scenarios**:

1. **Given** handoff index 1 and no new commit, **When** the Build finishes, **Then** it proceeds to the pull request step.
2. **Given** handoff index 0 and no new commit, **When** the Build finishes, **Then** it fails as today.

---

### User Story 7 - The forced-exhaustion test hook cannot be routed around (Priority: P3)

The live test forces exhaustion on whichever seat runs a given handoff of the Build stage (for example the first), instead of on a seat named in advance. Seat selection by usage can therefore no longer send the Build to a seat that is not forced.

**Why this priority**: In 009's first live run the forced seat was never picked and no handoff happened. The live test in Story 2 depends on this.

**Independent Test**: With the hook set to handoff 0, the activity forwards the force setting to the sandbox on handoff 0 for any seat, and never on handoff 1.

**Acceptance Scenarios**:

1. **Given** the hook is set to handoff 0, **When** handoff 0 runs on any seat, **Then** forced exhaustion is armed for that run.
2. **Given** the hook is set to handoff 0, **When** handoff 1 runs, **Then** forced exhaustion is not armed.
3. **Given** the older seat-name hook is set, **When** that seat runs, **Then** it still works as in 009.

---

### Edge Cases

- **The model ticks a task but its edit is still being written.** The check runs between stream messages, after a tool call completes, so a tick is seen only once its edit is on disk.
- **The model commits at the same moment as the harness.** One of the two commits fails; the harness retries on the next message and never fails the Build over it.
- **Edits after the last tick** (test fixes, verification tweaks) are committed at the end of the stream on a normal finish.
- **The task list has no task IDs.** A checkpoint is still made when the count of done tasks rises, with a generic message.
- **A wait outlives the workflow's own limits.** Waits use durable timers, so a worker restart during a wait resumes it.
- **A reset time in the past arrives as the earliest reset.** The stage asks again at once rather than waiting; it still counts as one wait.
- **Old pool state.** State carried from 009 has no reading reset time; it is treated as unknown.
- **Feedback retry where nobody commits.** On handoff index > 0 with every task done, if the predecessor pushed nothing and the successor commits nothing, the Build proceeds to the pull request step. Today's Eval-Gate does not look at the diff, so the unchanged branch can pass (accepted gap, F5; no worse than 009, where a model's no-op commit also passed).

## Requirements *(mandatory)*

### Functional Requirements

**Deterministic checkpoints (F1)**

- **FR-001**: During a Build, after every message from the model, the harness MUST compare the set of task IDs marked done in the feature's task list with the set it last saved. When new IDs appear and the working tree has changes, it MUST commit everything with the message `checkpoint: <IDs>` (space-separated, in task order).
- **FR-002**: When the model already committed the work for newly done tasks (clean tree), the harness MUST record them as saved without committing.
- **FR-003**: A failed checkpoint commit MUST NOT fail the Build; the harness MUST retry on the next message.
- **FR-004**: When the stream ends normally with uncommitted edits, the harness MUST commit them before the "new commit" check and the push. When it ends on a seat outcome, the harness MUST first save any newly done tasks (FR-001), then push.
- **FR-005**: The forced-exhaustion test hook MUST observe the checkpoint commit made for the same message, so "exhaust after 1 commit" fires right after the first task's checkpoint.
- **FR-006**: The Build prompt MUST tell the model to mark each task done as soon as it finishes it, and that the harness saves a checkpoint when it does.
- **FR-007**: Harness commits MUST work in the sandbox without any git identity set by the model.

**Reset-aware utilization (F2)**

- **FR-008**: The seat's usage reading MUST carry the reset time of the window it came from (the window with the highest utilization), separate from the exhaustion reset time.
- **FR-009**: Every successful seat-backed stage MUST report that reset time with its usage, and releasing the seat MUST store it with the reading.
- **FR-010**: Seat selection MUST treat a reading as 0 once its reset time has passed. A reading with no reset time MUST be used as is.
- **FR-011**: Marking a seat exhausted MUST set the reading's reset time to the exhaustion end.
- **FR-012**: Pool state without a stored reset time MUST load and behave as "unknown reset time".

**Waiting for a reset (F3)**

- **FR-013**: When no seat is eligible and the earliest known reset time is at most 6 hours away, the stage MUST wait durably until that time and ask again, at most twice per stage invocation.
- **FR-014**: When no reset time is known, the earliest reset is more than 6 hours away, or both waits are spent, the stage MUST fail with "credential pool exhausted" carrying the earliest reset time, as in 009.
- **FR-015**: A wait MUST NOT charge the Build-attempt, plan-attempt or handoff budget.
- **FR-016**: The waiting behavior MUST be gated so that runs started before it replay with the old fail-fast behavior.

**Expiry warning (F4)**

- **FR-017**: At startup the worker MUST log one warning per seat whose credential expires within 14 days or has expired, naming seat ID and date only.
- **FR-018**: The seat table MUST show each seat's days left until its credential expires, or empty when no date is configured.

**Feedback-retry handoff (F5)**

- **FR-019**: Each seat-backed Build run MUST receive its handoff index (0 for the first seat of an invocation).
- **FR-020**: When the handoff index is above 0 and no task is left open, the Build MUST skip the "made no new commit" check. With tasks still open, a run without a new commit fails as on the first seat.

**Test hook (F6)**

- **FR-021**: A test setting MUST arm forced exhaustion for whichever seat runs a named handoff index of the Build stage. The 009 seat-name setting MUST keep working.

**Secrecy (carried from 009)**

- **FR-022**: No credential value may appear in workflow history, activity arguments or results, logs, exception messages, PR comments or the agent's output. New fields (reset times, handoff index, days left) carry no credential.

**One session per task (F7-a)**

- **FR-023**: A Build without Gate feedback, whose task list is one file and whose open tasks all carry a task ID, MUST run one model session per open task, in file order. Each session's prompt names that one task and its task file and tells the model to mark it done and stop.
- **FR-024**: A task already marked done before its session starts (by a predecessor seat, or by the model ahead of time in an earlier session) MUST be skipped. When a session ends with its task still open, the Build MUST run no further task sessions.
- **FR-025**: After each task session ends normally, the harness MUST commit any remaining edits, so the next session's seat outcome cannot lose them. One harness checkpointer, one usage reading and one forced-exhaustion commit count span all sessions of the run. A seat outcome in any session ends the run with the 009 push and exit code.
- **FR-026**: A Gate-feedback retry, a task list with an open task that has no task ID, and a run with several task files MUST keep the single `/speckit-implement` session.

### Key Entities

- **Usage reading**: last-seen utilization of a seat, its limit type, and the reset time of the window it came from.
- **Checkpoint**: a commit made by the harness (or by the model) after a task is newly marked done; its message names the task IDs.
- **Handoff index**: the position of a seat run within one stage invocation, 0 for the first seat.
- **Pool wait**: one durable pause of a stage until the earliest seat reset.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In the live re-run, the first Build seat's run ends after exactly 1 task checkpoint, the successor's first commit is for task 2 or later, and 0 tasks marked done before the handoff are redone.
- **SC-002**: In the scripted tests, 100% of tasks marked done before a forced exhaustion are on the pushed branch, even when the model never commits.
- **SC-003**: For every case in the selection matrix (reading reset passed, reading reset future, no reset time, exhausted reading expired, old state), the pool picks the expected seat.
- **SC-004**: A stage that finds every seat exhausted and gets a seat after one wait finishes successfully, with 0 change to the Build-attempt, plan-attempt and handoff counters; a pool of only invalid seats fails within one request.
- **SC-005**: A worker started with a seat expiring within 14 days logs exactly one warning for it.
- **SC-006**: A feedback retry on handoff index 1 with no new commit reaches the pull request step; on index 0 it fails as before.
- **SC-007**: The live re-run's credential search finds 0 hits in every source.
- **SC-008**: Both test suites pass with 0 skipped and the linter is clean.

## Assumptions

- The model still marks tasks done in the task list (Spec Kit's implement skill does so per task). If it ticks several tasks in one edit, the harness can only save them as one checkpoint; the prompt asks for one tick per task.
- The usage signal reports a reset time per window. If a window has none, the top-level reset time is used; if that is missing too, the reading has no reset time.
- A 6-hour horizon and 2 waits cover one five-hour window plus slack. Longer outages (a seven-day window) still fail at once, naming the reset time.
- The live re-run uses the same disposable repository and two logical seats on one credential as 009's V5.

## Out of Scope

- Integration-test workflows left on the production task queue (owned by spec 010's session; reported to it).
- The plan-approval signal race (spec 005).
- The GitHub-comment Build path on seats, and pm-agent `review_spec` on seats.
- Alerting outside the worker log (PR or Teams notices) for expiring credentials.
