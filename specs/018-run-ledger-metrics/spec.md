# Feature Specification: Run Ledger and Outcome Metrics

**Feature Branch**: `018-run-ledger-metrics`
**Created**: 2026-10-17
**Status**: Draft
**Input**: User description: "Run ledger and outcome metrics for AgentPipelineWorkflow (spec 018). Every pipeline run
writes one ledger record: repo, PR number and run kind (run identity from spec 017), start and end time, end state
(shipped / abandoned / merged before checks / timed out / failed, from spec 017), the attempts at each stage, the gate
result of each attempt (gate-result.json from spec 015), the model tokens and cost of each stage, and which
subscription seat was used (specs/009). The ledger is the system of record: all metrics are computed from it, never
from a telemetry receiver, and it must keep records long enough for spec 019 (lessons loop). A per-run cost cap
RUN_BUDGET_USD: when a run goes over it, the run stops before the next model call and asks the operator on the PR
whether to continue or abandon. On a subscription seat, where there is no bill per call, cost is estimated as tokens x
a configured price per model. Metrics: cost per merged PR, the share of runs that pass the gate on the first attempt,
the median time from start to merge. Revert watch: for 30 days after a merge, check the merged PR for a later revert
and record it against the run. A simple command prints these numbers. Out of scope: observability export (logs,
metrics, traces to Coralogix and Langfuse; that is spec 020), a dashboard UI, and learning from the data (spec 019)."

## Why this feature exists

Today nobody can answer three plain questions about the pipeline: what does one merged PR cost, how often does the
first build pass the checks, and how long does a feature take from start to merge. The facts are not kept anywhere:

- **No token or cost data is recorded.** The only usage fact the code keeps is a seat's utilization reading (how full
  a subscription seat's usage window is), which `seat_guard.py` in `harness/swe-agent/` and `harness/architect-agent/`
  return and `release_seat` in `orchestration/activities.py` passes back to the credential pool (spec 009). It says how
  full a seat is, not what one run used.
- **A run's history does not last.** Temporal keeps a closed run's history only for its namespace retention period,
  then deletes it. Workflow history cannot be the record of what happened.
- **Nothing stops a run that costs too much.** The only limits today count attempts (`MAX_BUILD_ATTEMPTS`,
  `MAX_PLAN_ATTEMPTS`, `MAX_SEAT_HANDOFFS`), not money.

This feature adds a **run ledger**: one durable record per run, kept by the factory, from which all numbers are
computed. It adds a cost cap per run and a report command. Spec 019 (lessons loop) will read the ledger months later to
learn from past runs. Spec 020 (observability) will send the ledger's facts on to Coralogix and Langfuse; this spec
sends nothing anywhere.

In this spec, "FR" means functional requirement and "SC" means success criterion. "Operator" means the person who
runs the factory and answers its questions on the PR.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Every run leaves one complete record (Priority: P1)

The operator starts a product run on a target repo PR, for example `aheumaier/demo-app` PR 42. The run goes through
the architect stage, two Build attempts and the Eval-Gate, and a person merges the PR. Weeks later, after Temporal has
deleted the run's history, the operator can still see one record for that run: when it started and ended, that it
ended as shipped, both Build attempts with the seats each used, the gate result of each attempt, and the tokens and
cost of each stage.

**Why this priority**: Every other part of this feature (the cap, the metrics, the revert watch, and spec 019) reads
this record. Without it nothing else can work.

**Independent Test**: Run one product run on a disposable repo through to merge. After the run ends, read its record
and check each field against the run's PR comments, its gate-result.json files and the seats the pool lent out.

**Acceptance Scenarios**:

1. **Given** a product run is started on `aheumaier/demo-app` PR 42, **When** the run starts, **Then** a record for
   repo `aheumaier/demo-app`, PR 42, kind product exists and is marked open.
2. **Given** a Build attempt runs on seat `seat-a`, uses it up and hands off to `seat-b` (spec 009), **When** the
   attempt ends, **Then** the record shows one attempt with both seats, in order, and the tokens used on each seat.
3. **Given** the Eval-Gate writes a gate-result.json for an attempt (spec 015), **When** the attempt ends, **Then** the
   record holds that gate result for that attempt.
4. **Given** the run ends in any of spec 017's five end states, **When** it ends, **Then** the record is closed with
   that end state, the end time and the end facts spec 017 FR-012 lists (merge commit, merge time, who merged or
   closed).
5. **Given** the run's Temporal history has been deleted, **When** the operator reads the record, **Then** every field
   above is still there.

---

### User Story 2 - A run that costs too much stops and asks (Priority: P1)

The operator sets a cost cap per run, for example 20 US dollars. A product run on `aheumaier/demo-app` PR 42 has used
21 dollars after its second Build attempt. Before its next model session the run stops, posts one comment on PR 42
saying what it has spent, where it stopped and how to answer, and waits. The operator answers on the PR: continue (the
run gets one more cap's worth, here 20 dollars more, and goes on where it stopped) or abandon (the run ends as
abandoned, with the reason "operator abandoned: over cost budget").

**Why this priority**: A runaway run on a seat costs real money even without a bill per call: it uses up seats that
other runs need. A cap that is checked too late, or that loses work when it stops a run, is worse than none.

**Independent Test**: Set a very low cap on a disposable repo, start a run, and check that it stops at the next check
point (FR-014), posts the comment, and that both answers do what they say.

**Acceptance Scenarios**:

1. **Given** a run's cost so far is at or over the cap, **When** the run reaches a check point (before the architect
   stage starts or retries, or before a Build model session), **Then** it does not go on, posts one comment on the PR
   with the cost so far, the cap and the stage it stopped at, and waits.
2. **Given** Build goes over the cap in the middle of its work, **When** the current model session ends, **Then** Build
   stops before the next session, pushes its finished work, and the run waits. No finished task is lost. A Build that
   runs as one single session (a retry with Gate feedback, see FR-014) can only stop after that session, so it may go
   over by up to one session's cost.
3. **Given** a run waits after a budget stop, **When** the operator answers "budget continue" on the PR, **Then** the
   cap for that run grows by one more cap's worth, the record notes the answer, and the run goes on from where it
   stopped. The stop and the continue do not use up a Build attempt or a seat handoff.
4. **Given** a run waits after a budget stop, **When** the operator answers "budget abandon" with a reason, **Then** the
   run ends as abandoned, with the reason "operator abandoned: over cost budget" and the operator's reason in the
   record.
5. **Given** a run waits after a budget stop, **When** nobody answers before the run's deadline (spec 017's maximum
   wait, default 30 days), **Then** the run ends as timed out and the stop is recorded as unanswered.
6. **Given** a run waits after a budget stop, **When** the PR is merged or closed (spec 017 FR-011, FR-014), **Then**
   the wait ends, the run ends in the end state spec 017 gives for that event, and the stop is recorded as unanswered.
7. **Given** a person without the permission level the other gate commands need (spec 002) answers, **When** the
   answer arrives, **Then** it is refused and the run keeps waiting.

---

### User Story 3 - The operator prints the numbers (Priority: P2)

The operator runs one command and sees, for product runs and for factory-agent runs apart: the cost per merged PR, the
share of runs that passed the gate on the first attempt, and the median time from start to merge. Next to each number
it says what it counts and how many runs it rests on, for example "Cost per merged PR: 14.20 USD (all run costs, 31
runs, divided by 9 shipped PRs)".

**Why this priority**: These are the numbers the operator needs to judge whether the pipeline gets better or worse.
They need the record (User Story 1) first.

**Independent Test**: Fill a test ledger with known records, run the command, and compare each number with a hand
count.

**Acceptance Scenarios**:

1. **Given** a ledger with records, **When** the operator runs the report command, **Then** it prints the three
   numbers per run kind, each with its definition and the count of runs behind it.
2. **Given** the operator names a time range or a repo, **When** the report runs, **Then** it counts only the records
   in that range or for that repo.
3. **Given** some records have incomplete cost (FR-011) or an unknown model (FR-018), **When** the report runs,
   **Then** it says how many of each. Incomplete cost makes the cost numbers a lower bound; an unknown model priced at
   the highest price makes them an upper bound. The report says which applies.
4. **Given** open records that are past their own deadline exist (FR-002), **When** the report runs, **Then** it lists
   them as stale.

---

### User Story 4 - A revert after merge is noticed (Priority: P3)

A product run on `aheumaier/demo-app` PR 42 ships on 2026-11-02. On 2026-11-20 someone uses GitHub's revert button
and merges the revert PR. The run's record now shows a revert, with the revert's commit or PR and its date. The report
shows how many shipped PRs were reverted within 30 days.

**Why this priority**: A merged PR that is reverted two weeks later did not really ship. Spec 019 needs this to learn
from bad merges. It is the least urgent part because it only matters once runs ship.

**Independent Test**: On a disposable repo, ship a run, revert its merge with GitHub's revert button, and check that
the record shows the revert within one check interval.

**Acceptance Scenarios**:

1. **Given** a run ended as shipped, **When** a revert of its merge lands on the target repo's default branch within
   30 days of the merge, **Then** the record shows the revert, its commit or PR, and its time.
2. **Given** the revert watch missed some days (the worker was down), **When** it runs again, **Then** it still finds
   a revert that landed in those days, as long as the revert's commit time is within 30 days of the merge.
3. **Given** 30 days have passed since the merge with no revert, **When** the watch ends, **Then** the record says "no
   revert found in 30 days".

### Edge Cases

- **Build is stopped from outside.** Spec 017 FR-014 stops a sandbox when the PR is merged or closed before the checks
  pass. A sandbox can also time out or be killed. The usage of every model session that finished before the stop is
  kept (FR-009); only the session that was running is missing, and the record marks that attempt's cost "incomplete".
- **A seat runs out in the middle of an attempt** (spec 009, exit 75 or 77). The tokens used on that seat up to the
  handoff are kept, and the next seat's tokens are added to the same attempt. The next seat starts with the correct
  remaining cap, because the seat outcome carries the usage so far.
- **A step is retried by Temporal.** Usage that was already reported is not counted twice (FR-005), and the run does
  not get a second record. But a retry that runs model calls again is real spend and is counted: the architect stage
  is retried up to 4 times on a passing error, and each try's model calls count.
- **The architect stage runs several candidates at the same time** (spec 004). The cost check happens before the stage
  starts and before each retry of it. The stage can then go over the cap by up to one stage's cost; the report shows by
  how much.
- **A model that is not in the price table is used.** See FR-018.
- **The price table changes.** Records already written keep the prices they were computed with (FR-017).
- **A run is ended by hand** in the Temporal UI. Its record stays open. The report lists it as stale once it is past
  its own deadline (FR-002, User Story 3 scenario 4).
- **The ledger cannot be written** at a step. The run does not fail for this, and the cost cap still works, because
  the run itself keeps the running cost and the cap (FR-006). The write is tried again; if the close write is lost, the
  record keeps its "last written" time and shows as stale.
- **A revert of a revert.** If the PR is reverted and the revert is reverted again, the record shows both, in order.
- **Partial or hand-made undos** (someone deletes the code by hand, or reverts only some files) are not detected. The
  report says so next to the revert count.
- **Runs that started before this feature shipped** get no record and are not changed.
- **A factory-agent run** ships when its feature PR is merged and its registry PR is opened (spec 017 FR-027). It gets
  a record like a product run. Its revert watch looks at the feature PR, because that PR holds the code; the registry
  PR only records the version.

## Requirements *(mandatory)*

### Functional Requirements

**The record**

- **FR-001**: Every run of `AgentPipelineWorkflow` started after this feature ships MUST have exactly one ledger
  record. The record MUST be keyed by an ID that stays the same for the whole run, across step retries and worker
  restarts (for example Temporal's run ID), so a retried step finds the same record. The record MUST also store the run
  identity from spec 017 FR-004 (target repo and PR number) and the run's start time as taken by the run itself, so
  that two runs on the same PR at different times get two records that can be told apart.
- **FR-002**: The record MUST be created when the run starts and marked open. It MUST be updated as each stage attempt
  ends, and closed when the run ends. Each write MUST set the record's "last written" time. While the run is open, the
  record MUST hold the run's current deadline (spec 017's maximum wait from its last wait start). An open record past
  its own deadline is **stale**.
- **FR-003**: The record MUST hold:
  - the repo, PR number and run kind (product or factory-agent, spec 017 FR-001), and for a factory-agent run the agent
    name and version;
  - the start time, the end time and the end state (one of spec 017 FR-010's five), with the end facts spec 017 FR-012
    and FR-013 list;
  - for a failed run, the reason (an error, a spent attempt budget, or a bot merge), and for an abandoned run, who or
    what abandoned it (the PR closed, the PR gone, or the operator, with the operator's reason);
  - every attempt of every stage, in order, with its start and end time and its outcome;
  - for every Eval-Gate attempt, its gate-result.json from spec 015 as written, or "no gate result" when the gate did
    not run;
  - every human gate decision the run received (plan approved or rejected, budget continue or abandon), with when it
    arrived, and who answered (see FR-015 for what this needs);
  - for every attempt that made model calls, its model usage (FR-008) and the seats it used, in order;
  - the run's total cost, its cost cap, and every budget stop and answer;
  - the revert watch result (FR-024).
- **FR-004**: The record MUST hold facts only. It MUST NOT hold model prompt text, model answer text, tool input or
  output text, or any credential or token value. A seat is recorded by its seat ID only, as in spec 009.
- **FR-005**: Retrying a step MUST NOT create a second record, and MUST NOT count the same usage twice. Each usage
  report MUST be identified by its stage, attempt, seat handoff number, step try and model session, and a report with
  an identity already in the record MUST be ignored. A step try that makes model calls again is new usage and MUST be
  counted.
- **FR-006**: The run itself MUST keep its running cost and its cap; the ledger is written from them, not the other way
  round. A failure to write the ledger MUST NOT fail or stop the run, and MUST NOT turn off the cost cap. The write MUST
  be tried again. If a stage's facts are still lost when the run ends, the record MUST be marked "incomplete" and name
  what is missing. If the close write itself is lost, the record stays open with its "last written" time and shows as
  stale (FR-002).
- **FR-007**: The ledger MUST be kept by the factory, outside Temporal's history, and MUST keep every record for at
  least 2 years. Records MUST NOT be deleted by any part of this feature.

**Tokens and cost**

- **FR-008**: Every stage that makes model calls MUST report its model usage back to the run: per model, the counts of
  input tokens, output tokens, cache-read tokens and cache-write tokens. This holds for the stages that call models
  today (the architect stage, with each candidate and the critic, and Build) and for any such stage added later, such
  as spec 003's spec review once it runs in the pipeline. The Eval-Gate makes no model call (spec 015 FR-004) and
  reports none.
- **FR-009**: Every stage MUST report the usage of each model session as soon as that session ends, before the next
  session starts, and not only at the end of the stage. For Build that is one session per open task (spec 011), or one
  session for the whole attempt when Build runs as a single session (a retry with Gate feedback, a task list without
  task IDs, or several task files). For the architect stage it is each candidate, the scoring, the synthesis and the
  critic. A seat outcome (spec 009, exit 75 or 77) MUST carry the usage of the sessions on that seat. This way usage up
  to a seat handoff, a budget stop or an outside stop is kept.
- **FR-010**: Usage MUST be counted per seat when a stage moves from one seat to another (spec 009). A seat handoff is
  not a new attempt, as today.
- **FR-011**: When a stage stops in the middle of a model session (it is killed, it times out, or the sandbox is
  stopped), the record MUST keep the usage of every session that finished and mark that attempt's cost "incomplete".
  "Incomplete" means the usage of the session that was running is missing, nothing more.
- **FR-012**: Cost MUST be computed in US dollars as, for each model, the token counts of each type times that model's
  price for that type, from the price table (FR-017). This one rule MUST apply to every call, on a seat or with an API
  key. A provider's own cost figure, when there is one, MAY be stored next to it but MUST NOT replace it.

**Cost cap**

- **FR-013**: Each run MUST have a cost cap, `RUN_BUDGET_USD`, a setting with a default of 20 US dollars. The value in
  force when the run starts MUST be recorded on the run.
- **FR-014**: The run MUST compare its cost so far with its cap at these check points, and MUST NOT go on when the cost
  so far is at or over the cap:
  - before the architect stage starts, and before each retry of it (the stage runs its candidates at the same time, so
    it cannot stop inside);
  - before each Build model session. Each Build attempt MUST be given its remaining cap when it starts, and MUST stop
    itself after the session that reaches it: it pushes its finished work and ends with a typed "budget stop" outcome,
    the same way it ends on a seat outcome (spec 009, exit 75 or 77).

  A Build that runs as one single session (FR-009) can only stop after that session, so it may go over the cap by up
  to one session's cost. The report MUST show, for every budget stop, how far the run went over its cap.
- **FR-015**: On a budget stop the run MUST post one comment on the PR with the cost so far, the cap, the stage it
  stopped at, and the two answers it accepts. It MUST then wait for the operator's answer, using its own answer pair,
  separate from spec 005's escalation pair: **budget continue** (no payload) and **budget abandon** with a reason. The
  pair is separate because spec 005's `escalation_resume` restarts a stage's loop at its head (005 FR-012), while
  budget continue goes on from the exact step that stopped. The pair MUST follow spec 005 FR-016's decision-window rule:
  an answer that arrives while no budget stop is waiting is applied at most once, and only to the next budget stop of
  that run. The bridge MUST accept the answer only from a person with the permission level the other gate commands need
  (spec 002). Recording who answered (FR-003) needs the bridge to pass the answering person's login with the answer;
  today's signals (`plan_approved`, `plan_rejected`) carry no such field, so this changes the bridge-to-workflow
  contract of specs 002 and 005.
- **FR-016**: On budget continue, the run's cap MUST grow by one more `RUN_BUDGET_USD` (the value recorded at run
  start), and the run MUST go on from the step it stopped before. A budget stop and its continue MUST NOT use up a Build
  attempt (`MAX_BUILD_ATTEMPTS`), a plan attempt (`MAX_PLAN_ATTEMPTS`) or a seat handoff (`MAX_SEAT_HANDOFFS`). On
  budget abandon, the run MUST end as abandoned, with the reason "operator abandoned: over cost budget" and the
  operator's reason, as spec 017's Assumptions say an operator abandon should end. When no answer comes before the
  run's deadline (spec 017's maximum wait, default 30 days), the run MUST end as timed out. When the PR is merged or
  closed during the wait, the wait MUST end and the run MUST end as spec 017 FR-011 and FR-014 say for that event. In
  both of these cases the stop MUST be recorded as unanswered.

**Price table**

- **FR-017**: Prices MUST come from one price table the operator keeps with the factory's settings. It MUST give, per
  model ID, a price per million tokens for input, output, cache read and cache write. The table MUST have a version,
  and each record MUST store the version and the prices it used, so a later price change does not change past records.
- **FR-018**: When a model is used that is not in the table, the cost MUST be computed with the highest price in the
  table for each token type, the record MUST name the unknown model, and the report MUST flag it.

**Report**

- **FR-019**: A report command MUST print, per run kind, from the ledger only:
  - **cost per merged PR**: the total cost of all closed runs in the range, of every end state, divided by the number
    of shipped runs. Open runs are left out. Merged-before-checks runs are not shipped and MUST be shown as a separate
    count. The cost MUST be shown split in two: the seat estimate (calls on subscription seats, priced per FR-012) and
    the API-billed part (calls with an API key);
  - **first-attempt gate pass share**: of the runs, open or closed, that have a first Eval-Gate result, the share
    whose first Eval-Gate attempt has an overall verdict of pass. A verdict of fail or error counts as not passed. A
    pass with criteria marked manual (spec 015) counts as passed;
  - **median time from start to merge**: over shipped runs only, from the run's start to the merge time.

  Because the range filters by run start date (FR-022), a range that ends near today leaves out runs that started in
  it but have not merged yet. The report MUST say so under the numbers.
- **FR-020**: Next to each number the report MUST say what it counts and how many runs it rests on. When it rests on
  no runs, it MUST say "no data" instead of a number.
- **FR-021**: The report MUST also print: the count of runs per end state, the count of budget stops, the count of
  records with incomplete cost (which make the cost numbers a lower bound), the count of records with an unknown model
  (which make them an upper bound, FR-018), the count of shipped runs reverted within 30 days, and the list of stale
  open records (FR-002), each with its "last written" time.
- **FR-022**: The report MUST accept a time range (by run start date) and a repo as filters. With no filter it MUST
  cover all records.
- **FR-023**: The report MUST read only the ledger. It MUST NOT call Temporal, GitHub, Coralogix or Langfuse.

**Revert watch**

- **FR-024**: For every run that ends as shipped, the factory MUST watch the target repo's default branch for 30 days
  after the merge time and record any revert of the merged PR it finds, with the reverting commit or PR and its time.
  For a factory-agent run the watched PR is the feature PR, not the registry PR. After 30 days with none, it MUST record
  "no revert found in 30 days". The watch MUST read GitHub with a read-only credential, the same one spec 017 FR-022's
  hourly state check uses, never a sandbox token (spec 013).
- **FR-025**: A revert MUST be counted when either (a) a PR merged into the default branch says in its body that it
  reverts this PR, as the PR that GitHub's revert button opens does, or (b) a commit on the default branch reverts the
  PR's merge commit or squash commit. Partial or hand-made undos are out of scope and MUST be named as not detected in
  the report.
- **FR-026**: Each check MUST read every change since the merge, not only since the last check, so that a missed check
  never loses a revert. A revert counts when its commit time is within 30 days of the merge time. The check interval
  MUST be a setting, with a default of once a day.
- **FR-027**: The revert watch MUST NOT change the target repo, the PR or the run's end state. It only adds facts to
  the record.

**Rollout**

- **FR-028**: Runs that were in flight when this feature ships MUST finish as before, with no record and no cost cap.
  Older runs MUST NOT be backfilled.
- **FR-029**: The behaviour of a run that never reaches its cap MUST stay as it is today, apart from writing the record.

### Key Entities

- **Run record**: one per run. Record key (stable run ID), run identity (repo, PR number), start time, run kind, agent
  and version for a factory-agent run, end time, end state and end facts, failure or abandon reason, cost cap and total
  cost, price table version, open/closed, current deadline, "last written" time, incomplete markers, revert result.
- **Stage attempt**: one per attempt of one stage in one run. Stage name, attempt number, start and end time, outcome,
  model usage, seats used in order, gate result for an Eval-Gate attempt, cost and an "incomplete" marker.
- **Model usage**: one per model session, identified by stage, attempt, seat handoff number, step try and session
  (FR-005): the model, the seat, input, output, cache-read and cache-write token counts, and the cost computed from
  them.
- **Price table**: version, and per model ID a price per million tokens for each of the four token types.
- **Budget stop**: when the run stopped, at which stage, the cost so far, the cap, how far over it was, and the
  operator's answer (continue, abandon, or unanswered), who gave it and when.
- **Human gate decision**: which gate, the answer, who gave it, when.
- **Revert finding**: the reverting commit or PR, its time, and how it was found (FR-025 a or b).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For 10 out of 10 test runs on a disposable repo, one for each end state at least, the ledger has exactly
  one closed record per run, and every field FR-003 lists matches the run's PR comments, gate results and seat leases.
- **SC-002**: A record can still be read in full after Temporal has deleted the run's history.
- **SC-003**: For a test run, the token counts in its record match the counts the model provider reported for the
  same calls. The test includes one seat handoff, one Temporal retry of a step whose usage was already reported (it is
  not counted twice), and one architect stage retry that ran its model calls again (both tries are counted).
- **SC-004**: In a test with a cap lower than one Build attempt's cost, Build stops before its next model session, no
  finished task is lost (its commit is on the PR branch), and the comment is on the PR within 1 minute of the stop.
- **SC-005**: A budget continue answer lets the run go on from where it stopped and raises its cap by one cap's worth,
  without using up a Build attempt or a seat handoff; a budget abandon answer ends the run as abandoned with the reason
  "operator abandoned: over cost budget". Both are shown in the record, with who answered.
- **SC-006**: On a test ledger with known content, every number the report prints matches a hand count, and each
  number shows its definition and the count of runs behind it.
- **SC-007**: The report finishes in under 10 seconds for a ledger of 10,000 records.
- **SC-008**: A revert made with GitHub's revert button on a disposable repo appears in the run's record within one
  check interval plus 1 hour.
- **SC-009**: No record contains model prompt text, model answer text, tool text or a credential, checked by a scan of
  the test ledger for the test prompts and test token values used.
- **SC-010**: A run that stays under its cap behaves as it did before this feature: same stages, same comments, same
  end state, on the same test input.

## Assumptions

- **Depends on 015 and 017.** The record uses spec 017's run identity, run kinds and end states, and spec 015's
  gate-result.json. Until those ship, the matching fields cannot be filled.
- **Does not depend on 005's escalation pair.** The budget stop has its own answer pair (FR-015), because its continue
  means "go on from this exact step", not 005's "restart the stage's loop". It reuses only 005 FR-016's
  decision-window rule. Both pairs and the plan signals need the answering person's login added to the
  bridge-to-workflow contract (specs 002 and 005); the plan does that once for all of them.
- **Build stops itself.** Build runs inside the sandbox with no automatic retry, and its usage today comes back only in
  its final result, so a kill loses it. This feature therefore needs Build to report usage per session (FR-009) and to
  stop itself on its remaining cap (FR-014), with a typed outcome next to the seat outcomes (exit 75 and 77).
- **Decisions confirmed by the operator on 2026-10-17:** (a) budget continue raises the cap by one more
  `RUN_BUDGET_USD`; (b) budget abandon ends the run as abandoned with the reason "operator abandoned: over cost
  budget", as spec 017's Assumptions say an operator abandon should, instead of failed or a sixth end state; (c) the
  default cap is 20 US dollars; (d) cost per merged PR counts the cost of every closed run, not only shipped ones,
  because failed runs are part of what a merge costs; (e) an unknown model is priced at the table's highest price; (f)
  the budget stop has its own answer pair instead of reusing spec 005's.
- **The revert watch can ship on its own.** User Story 4 does not depend on the cap or the report, so the plan may
  build it in a later step than the record and the cap. The operator chose on 2026-10-17 to keep it in this spec.
- **Retention.** Two years is a default chosen so spec 019 has enough history. It is a setting.
- **Where and how the ledger is stored**, how stages report their usage, how a budget stop reaches the harness, how
  cache writes with different lifetimes are priced, and the replay-safety mechanism for runs in flight (a workflow
  version patch, as specs 009, 011 and 017 use) are left to `/speckit-plan`.
- **Seat cost is an estimate.** A subscription seat has no bill per call, so the dollar figure for seat calls is what
  the same tokens would cost at the table's prices. It measures how much model work a run used, not money paid.
- **Spec 020 will export the ledger's facts** to Coralogix and Langfuse. The ledger stays the system of record: if
  the two ever disagree, the ledger is right.
- **Not in scope:** a dashboard UI, learning from the data (spec 019), and any export (spec 020).
