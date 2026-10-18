# Feature Specification: Observability

**Feature Branch**: `020-observability`
**Created**: 2026-10-17
**Status**: Draft
**Input**: User description: "020 observability: send workflow and developer-experience telemetry (logs, metrics,
traces) in OpenTelemetry format to Coralogix from the Temporal worker, the webhook bridge, every pipeline step and
swe-agent inside E2B; Langfuse stays for single model calls; facts only, never prompt/answer/tool-input text; every
item carries repo + PR, run kind, stage, attempt, seat; amends architecture §3.8; spec 018 ledger stays the system of
record; one operator dashboard (no alerts); keep every trace; drop data when Coralogix is unreachable, never block or
slow a run."

## Why this feature exists

Today the operator cannot watch a run. The worker and the webhook bridge write plain log lines to their own terminal
(`logging.getLogger` in `orchestration/worker.py` and `orchestration/webhook_bridge/server.py`). swe-agent inside the
E2B sandbox prints to its own stdout and stderr (`harness/swe-agent/agent.py`), which the worker only reads for the
seat status line and the PR URL. The Temporal UI shows which activity ran, but not which task swe-agent was on, how
many tokens a stage used, or why a seat handed off. When a Build on `aheumaier/demo-app` takes 40 minutes, the
operator has no way to tell whether the time went to the model, to tests, or to waiting for a seat.

Architecture §3.8 names Langfuse as the observability layer, but no code sends anything to it yet. Spec 018 adds a
ledger: one record per run, written at fixed points, with cost and end state. The ledger answers "what happened in
the end". It does not answer "what is happening now" or "where did the time go".

This feature sends logs, metrics and traces from every part of a run to Coralogix, in OpenTelemetry (OTel) format,
and builds one dashboard for the operator. It sends facts only. It never sends what the model read or wrote.

**Words used in this spec:**

- **Item**: one log line, one metric point or one trace span sent to Coralogix.
- **Run trace**: all spans of one pipeline run, linked under one trace ID.
- **Identity fields**: the fields that say which run, stage, attempt and seat an item belongs to (FR-006).
- **Facts**: counts, durations, times, IDs, names from a fixed list, and outcome and error codes from fixed lists
  (FR-009). Not text.
- **Drop**: an item the factory gave up on because Coralogix could not take it in time.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The operator follows one run from start to end (Priority: P1)

The operator starts a product run on `aheumaier/demo-app` PR 42 by a PR comment. In Coralogix they search for
`demo-app` and PR 42. They see one run trace. It starts with the bridge accepting the comment, then shows each stage
the workflow ran (ensure the PR, architect, Build, Eval-Gate, register), each attempt of each stage, each seat lease and
handoff, and inside Build each swe-agent task, model call and tool call. Each span has its duration and outcome.

**Why this priority**: This is the reason for the feature. Without it the operator debugs a slow or failed run from
three terminals and the Temporal UI.

**Independent Test**: Run one product run on a disposable repo. Find it in Coralogix by repo and PR number. Compare
its spans with the run's spec 018 ledger record: every stage attempt and seat in the record has a matching span.

**Acceptance Scenarios**:

1. **Given** a product run that ships, **When** the operator searches Coralogix by repo and PR number, **Then** one
   run trace is found, and it holds one span per stage attempt the ledger record lists, in the same order.
2. **Given** a Build attempt that hands off from seat `max-1` to seat `max-2` (spec 009), **When** the operator opens
   that attempt's span, **Then** it shows two sandbox sessions, the first ending with the outcome "seat exhausted",
   each carrying its own seat ID, and both under the same attempt number.
3. **Given** a Build attempt, **When** the operator opens it, **Then** they see one span per swe-agent task (for
   example `T004`), each with its model calls (model ID, input and output tokens, duration) and tool calls (tool name,
   duration, outcome), and the checkpoint commit and push.
4. **Given** a run waiting for a person (spec 005's plan approval, spec 017's wait for the merge, or spec 018's
   budget decision), **When** the operator looks at the run, **Then** they find a "wait started" event with its start
   time, its kind and the deadline spec 017 sets, and the dashboard counts the run as in progress. The wait's span
   is sent when the wait ends (FR-001).
5. **Given** a PR comment the bridge rejects (for example a user without write access), **When** the operator
   searches the bridge's items, **Then** they find the delivery with its outcome "rejected" and the rule that
   rejected it, and no run trace.

---

### User Story 2 - Nothing the model read or wrote reaches Coralogix (Priority: P1)

The operator puts a marker string in a spec, in a task, and in a file the agent reads. After the run they search
Coralogix for the marker. It is not there. They find token counts, durations, tool names and error classes, but no
prompt text, no answer text, no tool inputs or outputs, no file content and no diff.

**Why this priority**: Coralogix is a hosted service. Target repo code, specs and model answers must not go there.
This is the operator's rule for the feature, and a breach cannot be undone once sent.

**Independent Test**: Plant a marker string in a disposable repo's spec, a task and a source file. Run one product
run. Search every item sent for that run for the marker. Zero hits.

**Acceptance Scenarios**:

1. **Given** a run whose spec, tasks and source files contain a marker string, **When** the run ends, **Then** no
   item sent to Coralogix contains the marker.
2. **Given** a tool call such as `Bash` running `pytest`, **When** its span is sent, **Then** it holds the tool name,
   the duration and the outcome (success or error), and not the command, its output or its exit text.
3. **Given** a `git push` that fails with an error text that includes a URL with a token in it, **When** the error is
   sent, **Then** the item holds the error class and an error code from the fixed list (for example `push_failed`),
   and no text from the error (FR-010).
4. **Given** the agent runtime (the Claude Code CLI) has its own telemetry export, **When** a run starts in the
   sandbox or the worker, **Then** that export is off (FR-011).

---

### User Story 3 - One dashboard shows how the pipeline is doing (Priority: P2)

The operator opens one Coralogix dashboard. It shows runs in progress, runs ended per end state, how long each stage
takes, how many attempts each stage needs, seat handoffs per seat, tokens and estimated cost per run, Eval-Gate
results, bridge deliveries per outcome, and how many items were dropped. Every panel says what it counts and what a
good value is.

**Why this priority**: The trace in US1 answers "what happened in this run". The dashboard answers "is the pipeline
getting better or worse" without opening runs one by one. It is less urgent, because the 018 report gives the same
end numbers from the ledger.

**Independent Test**: Create the dashboard from the file in this repo in an empty Coralogix space. Run three test
runs. Every panel shows data, and each panel's text says what it counts.

**Acceptance Scenarios**:

1. **Given** the dashboard file in this repo, **When** the operator creates the dashboard from it, **Then** it shows
   every panel FR-022 lists, with no manual edit.
2. **Given** three test runs with no drops and no sampling, **When** the operator compares the dashboard's runs per
   end state with the spec 018 report for the same time range, **Then** the counts are the same.
3. **Given** the dashboard, **When** the operator reads any panel, **Then** its text says what the number counts, how
   it is measured and what a good value is.

---

### User Story 4 - Telemetry never hurts a run (Priority: P2)

Coralogix is down for an hour. Runs started in that hour end the same way they would have ended with Coralogix up.
They take no noticeably longer. The items they could not send are dropped and counted, and the worker's own log says
how many.

**Why this priority**: Telemetry is for watching. A run that waits on, slows down for, or fails because of its own
telemetry has the priorities backwards. The operator chose "drop the data" over "wait" for this reason.

**Independent Test**: Block the Coralogix endpoint. Run the same test run as a baseline. Compare end state, ledger
record and duration.

**Acceptance Scenarios**:

1. **Given** Coralogix cannot be reached, **When** a run goes through all its stages, **Then** it ends in the same
   end state as the baseline run and its ledger record matches the baseline except for times and IDs.
2. **Given** Coralogix cannot be reached, **When** the worker gives up on items, **Then** it counts them per process
   and per kind (log, metric, span) and writes the count to its own local log (FR-015).
3. **Given** Coralogix answers slowly, **When** a stage ends, **Then** the stage does not wait for its items to be
   sent beyond the flush limit (FR-014).
4. **Given** the telemetry key is revoked, **When** a run starts, **Then** it runs normally, the items are dropped and
   counted, and the local log says once that the key was refused.

---

### User Story 5 - From a slow model call to its detail in Langfuse (Priority: P3)

The operator sees in a Build span that one model call took 4 minutes. They want the prompt and the answer. Those are
not in Coralogix (US2). The model call's span carries a model-call ID. The same ID is the key a later Langfuse
capture uses for that call, so the operator can look it up there.

**Why this priority**: The operator decided that Langfuse stays the place for single model calls. This story keeps
the two tools linked. It is P3 because nothing writes model calls to Langfuse yet, and that capture is not part of
this spec (see Assumptions).

**Independent Test**: For one test run, every model-call span has a model-call ID, and no two calls share one.

**Acceptance Scenarios**:

1. **Given** a model call in any stage, **When** its span is sent, **Then** it holds a model-call ID that is unique
   across all runs, and the run's identity fields.

---

### Edge Cases

- **Before the PR exists.** This applies only until spec 017 ships: 017 (FR-004, FR-006) starts every run on a PR
  that already exists. Until then, a run has no PR number until `ensure_target_pr_activity` opens one. Items before
  that carry the workflow ID and "PR: none yet"; later items carry the number. A span cannot be changed once sent, so
  the top span gets the PR number when it ends, and a search by workflow ID finds the early items.
- **A bridge delivery that starts nothing.** It gets its own short trace with the delivery ID and outcome. It never
  joins a run trace.
- **A signal from the bridge to a running run** (plan approved, plan rejected). The bridge's span links to the run
  trace by the workflow ID, so the operator sees which signal was sent and when it arrived. Who sent it is not sent:
  a GitHub login is personal data. The operator can allow it later by adding it to the field list.
- **A seat handoff starts a new sandbox.** The new sandbox's items belong to the same attempt, with the next handoff
  index (`SEAT_HANDOFF_INDEX`) and the new seat ID.
- **The worker restarts while a run is open.** Temporal replays the workflow's history, and it also replays when the
  worker drops a workflow from its cache. Replay MUST NOT send items for work that already happened again (FR-016).
- **The sandbox is killed or times out.** Items still inside it may be lost. With the worker relay (FR-020), all of
  that sandbox's items are lost unless the worker reads them before it kills the sandbox. The attempt's span on the
  worker side still ends with the outcome "sandbox lost", so the trace shows the gap.
- **A run that waits days for a person.** A span is sent only when it ends, so an open wait is not visible as a span.
  The "wait started" event is sent at once, and the in-progress count (FR-022) includes the run until it ends (spec
  017's timed-out end state ends it). The wait's span is sent when the wait ends, with the start time the workflow
  recorded.
- **Clock skew inside the sandbox.** Sandbox span times may be off by seconds. Durations are measured inside one
  process, so they stay right; the order of spans across worker and sandbox may be off by the skew.
- **The model writes fake items.** Code inside the sandbox runs next to the model, which can run shell commands, so
  it can send items that look real or that hold text. The source mark is set outside the sandbox: by the worker on
  the relay path, and by a header the E2B proxy adds on the proxy path (FR-007, FR-021). On the proxy path, the
  facts-only rule holds for the harness's own code, not against a model that sends items on purpose. On the relay
  path, the worker's checks (FR-021) hold against both. Nothing in the pipeline reads Coralogix (FR-025), so a fake
  item can mislead the operator's view, but cannot change a run, a gate or the ledger.
- **Sampling is turned on later.** Whole runs are kept or dropped, never part of a run. Each run trace says which
  sampling rate was in effect (FR-017), so the dashboard can show that its numbers are sampled.
- **Telemetry is switched off.** The run behaves the same. Nothing is sent and nothing is counted as dropped.
- **The same PR runs twice** (a second run after the first ended). Each run has its own trace and ledger record key.
  A search by repo and PR finds both, ordered by start time.

## Requirements *(mandatory)*

### Functional Requirements

**What is sent, and from where**

- **FR-001**: The Temporal worker MUST send one run trace per pipeline run (`AgentPipelineWorkflow`). Its spans MUST
  cover every activity the workflow schedules (today: ensure the PR, architect, Build, Eval-Gate, register, and the
  seat lease and release calls; later, any stage added by specs 005 to 007 or 015 to 019), every attempt of each
  stage, every seat handoff, and every wait for a person. A span is sent only when it ends. So the worker MUST also
  send a "run started" event when a run starts and a "wait started" event when a wait starts, each with the
  identity fields and, for a wait, its kind and deadline. A wait's span is sent when the wait ends, with the start
  time the workflow recorded.
- **FR-002**: The webhook bridge MUST send one span per GitHub delivery it handles, with the delivery ID, the event
  type, the command as a verb from a fixed list (for example `run`, `approve-plan`, `reject-plan`, or `unknown`), the
  outcome (started, signalled, ignored or rejected) and, for a rejection, the rule that rejected it. When the
  delivery starts or signals a run, its span MUST be linked to that run's trace.
- **FR-003**: swe-agent inside the E2B sandbox MUST send spans for its session, each task in its task loop, each
  model call, each tool call, each checkpoint commit, the push and the PR open, and its exit outcome (ok, seat
  exhausted, seat invalid, failed). It sends token counts only; the worker computes the cost estimate from spec
  018's usage record. Its logs MUST go to stderr or the telemetry path, never to stdout: the worker reads the PR URL
  from the last stdout line (`orchestration/activities.py`). It MUST report its own drop counts in its last status
  line to the worker, and the worker MUST write them to its local log.
- **FR-004**: The architect stage, which runs in the worker (§6.1 carve-out), MUST send spans for each candidate,
  the scoring, the synthesis and the completeness critic, with each model call inside them.
- **FR-005**: Only log lines written through one dedicated structured logger in the factory's own code (worker,
  bridge, harness agents) MUST be sent as log items, with the identity fields, and under the facts-only rule (FR-009).
  Plain log calls MUST stay local. For example, `workflow.logger.warning("Seat %s release failed: %s", seat_id, e)`
  in `pipeline_workflow.py` puts the error text in the line, so it is not sent. Output of child processes (for
  example `git`, `gh` or `pytest`) MUST NOT be sent as logs.

**Identity fields**

- **FR-006**: Every item MUST carry these identity fields, with a fixed value such as "none" where one does not apply:
  - the repo and the PR number (or "none yet", see Edge Cases);
  - the run kind (product or factory-agent, spec 017 FR-001), and for a factory-agent run the agent name and version;
  - the Temporal workflow ID and the spec 018 ledger record key;
  - the stage, the attempt number in that stage, the seat handoff index, and the step try (as spec 018 FR-005
    defines it);
  - the seat ID (never its token), or "none" for work that holds no seat;
  - the process that sent it (worker, bridge or sandbox).
- **FR-007**: The worker MUST pass the identity fields to the sandbox when it starts it. Code in the sandbox MUST NOT
  work them out for itself. The mark that an item came from the sandbox MUST be set outside the sandbox: on the relay
  path the worker sets it and overwrites the identity fields with its own values (FR-021); on the proxy path a
  header rule in E2B, outside the sandbox, sets Coralogix's subsystem to "sandbox" (FR-020).

**Facts only**

- **FR-008**: No item MUST contain: prompt text, model answer text, model reasoning, tool inputs or outputs, file
  contents, diffs, commit messages, spec or task text, PR or issue titles and bodies, comment text, gate feedback text,
  the output of child processes, or account and person identifiers (email addresses, GitHub logins, Anthropic
  account or organization IDs).
- **FR-009**: An item MAY contain only these kinds of values: IDs (run, trace, span, delivery, seat, model call, task
  IDs such as `T004`, success criterion (SC) IDs such as `SC-003`); times and durations; counts (tokens in and out,
  cache tokens, tasks, tool calls, retries, drops); the cost estimate in spec 018's terms; the model ID; tool names;
  stage names; outcome, end-state and error codes from fixed lists; exit codes; the error class (FR-010); and the
  setting values this spec names. Each field MUST come from one list kept in this repo, with its type, a pattern or
  fixed set of values, and a length cap. Every process MUST pass every item through one filter just before export.
  The filter drops fields not on the list and values that do not match, and it removes exception events and span
  status text that the OTel libraries add on their own. An automated test MUST fail when any code path sends a field
  that is not on the list.
- **FR-010**: An error item MUST hold the error class and an error code from a fixed list (for example
  `push_failed`, `sandbox_timeout`, `seat_exhausted`, `other`), never the error's text (`str(e)`), the response
  body of a failed HTTP call or the stderr of a child process. As a second line of defence, every string value MUST
  pass the repo's one secret-pattern list, shared with the `_redact` helper in `orchestration/activities.py`, before
  export. That list MUST cover GitHub tokens, the seats' OAuth tokens, the Coralogix key, credentials inside URLs,
  and any run of 24 or more characters from a token alphabet. A value that matches is dropped, not cut.
- **FR-011**: The agent runtime's own telemetry export (the Claude Code CLI that the Claude Agent SDK runs) MUST be
  off in the sandbox and in the worker: its switch is unset, and the test in SC-002 checks that. It can send prompt
  text and account identifiers, which FR-008 forbids. Per-call token counts come from the SDK's own messages, which
  `/speckit-plan` confirms.
- **FR-029**: Each process MUST set up its exporter in code, not from `OTEL_*` environment variables. It MUST remove
  every `OTEL_*` variable from the environment of the child processes it starts (the Claude Code CLI, `git`, `gh`,
  and the target repo's tests), so a child cannot send to Coralogix by inheriting the settings.

**Delivery and failure**

- **FR-012**: Items MUST be sent in the background, from a bounded buffer in each process. Sending MUST NOT block
  any stage, activity or workflow code.
- **FR-013**: When the buffer is full, new items MUST be dropped, not old ones held while the process waits.
- **FR-014**: When a process ends (a stage's sandbox, the worker, the bridge), it MAY wait at most 5 seconds to send
  what is left in its buffer. After that the rest is dropped.
- **FR-015**: Every drop MUST be counted per process and per kind (log, metric, span). The count MUST be written to
  the process's own local log at least once a minute while drops happen and once when the process ends, and MUST be
  sent to Coralogix as a metric once it can be reached again. A refused key (an HTTP 401 or 403 from Coralogix or
  from the E2B proxy) MUST be written to the local log once per process start, not once per item.
- **FR-016**: A telemetry failure MUST NOT change a run's stages, attempts, retry budgets, seat leases, end state or
  ledger record, and MUST NOT raise an error into stage or workflow code. Workflow code MUST check whether it is
  replaying and send nothing while it is, both after a worker restart and after a cache eviction; a version patch
  alone is not enough. Telemetry MUST NOT be sent through extra Temporal activities, since those would change the
  workflow's history.
- **FR-017**: Every run trace MUST be kept by default. One setting MAY turn on sampling. Sampling MUST keep or drop
  whole runs, never part of one. The sampling rate in effect MUST be sent on each kept run trace.
- **FR-018**: One setting MUST turn all sending off. With it off, runs MUST behave as with it on.

**The Coralogix key**

- **FR-019**: The Coralogix key MUST be a send-only key (Coralogix's "Send Your Data" key). The worker and the bridge
  MUST read it from the environment (`.env`, with its name in `.env.example`) and MUST NOT write it to any log, item,
  command line or file in the repo.
- **FR-020**: No Coralogix key MUST be readable inside the sandbox: not in the sandbox template, not in an env var,
  not in a file. The sandbox MUST send items in one of these two ways, in this order of choice:
  1. **E2B's secrets egress proxy.** The sandbox holds only a reference. It sends OTel over HTTPS (not gRPC), and the
     proxy adds the key only to calls to the Coralogix host, set by a host rule. A second header rule sets
     Coralogix's subsystem header to "sandbox" (FR-007). This is the preferred way.
  2. **Worker relay**, if the proxy is not available on the operator's E2B plan. The sandbox writes its items to a
     file inside the sandbox. The worker reads that file when the sandbox ends, and when the sandbox fails or times
     out, before it kills the sandbox, and sends the items itself. With this way, Build has no live view on the
     dashboard; items arrive when the sandbox ends; and the items of a sandbox that dies are lost.
  Whether the proxy is available on the operator's E2B plan, its exact header names, and how it matches Coralogix's
  auth header, are the first check in `/speckit-plan`.
- **FR-021**: The worker relay MUST treat the file as untrusted: it MUST pass each item through the filter (FR-009),
  drop items that fail, count them as drops, and cap the file it reads at a size set in `/speckit-plan`. It MUST
  overwrite the identity fields and the source mark with the worker's own values before it sends an item.

**The dashboard**

- **FR-022**: There MUST be one operator dashboard, kept as a file in this repo, from which it can be created in
  Coralogix without manual edits. It MUST show:
  - runs in progress now, per run kind, from a gauge the worker sends (spans of open runs are not sent yet);
  - runs ended per end state (spec 017's five), per run kind, over a chosen time range;
  - time per stage (middle value and slowest), and the time spent waiting for a seat or for a person;
  - attempts per stage, and runs that spent their attempt budget;
  - seat handoffs and seat stops (exhausted, invalid) per seat;
  - tokens and the cost estimate per run and per stage;
  - Eval-Gate attempts per outcome;
  - bridge deliveries per outcome;
  - items dropped per process and kind, and the sampling rate in effect.
- **FR-023**: Each panel MUST say in plain words what it counts, how it is measured, and what a good value is.
  Panels that repeat a number from the spec 018 report MUST say that the report is the record.
- **FR-024**: This feature MUST NOT set up alerts. Alerts are left to a later spec.

**The ledger, Langfuse and the architecture doc**

- **FR-025**: Nothing in the pipeline MUST read Coralogix: not the gate, not the ledger, not the spec 018 report,
  not spec 019's lessons drafter. When Coralogix and the ledger differ, the ledger is right.
- **FR-026**: When spec 018 closes a run's ledger record, the worker MUST send one item on the run trace with the
  record's facts: end state, total tokens, cost estimate, attempts per stage, seats used, and the record key.
- **FR-027**: Every model-call span MUST carry a model-call ID, unique across all runs. A later Langfuse capture MUST
  use the same ID for the same call. This spec does not write model calls to Langfuse.
- **FR-028**: Architecture §3.8 (`docs/agent-factory-architecture.md`) MUST be updated in the change that builds this
  feature. It MUST say: Coralogix, fed in OTel format, is where the operator watches runs and the pipeline; Langfuse
  stays the place for single model calls, including their text; Coralogix gets facts only; and the spec 018 ledger is
  the system of record. It MUST also say that sending facts to a hosted service is a deliberate change from §3.8's
  self-hosted choice, made by the operator on 2026-10-17, and that the gate is fed by the ledger, not by Coralogix.

### Key Entities

- **Item**: one log line, metric point or span. Holds the identity fields (FR-006), the process that sent it, and
  only values from the field list (FR-009).
- **Run trace**: all spans of one run under one trace ID. Its top span holds the run's identity, the sampling rate,
  and, at close, the ledger facts (FR-026).
- **Field list**: the one list in this repo of fields an item may hold, each with its type, pattern or fixed values,
  and length cap. The test in FR-009 checks against it.
- **Export filter**: the one check every process runs on every item just before export (FR-009, FR-010).
- **Drop count**: per process and kind; written to the local log and sent once Coralogix can be reached.
- **Operator dashboard**: one dashboard, kept as a file in this repo, with the panels FR-022 lists.
- **Model-call ID**: the shared key between a model-call span in Coralogix and the same call in a later Langfuse
  capture.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For 5 out of 5 test runs on a disposable repo, the operator finds the run trace in Coralogix by repo
  and PR number within 1 minute, and the trace has one span for every stage attempt and every seat the ledger
  record lists.
- **SC-002**: Across 5 test runs whose spec, tasks and a source file contain a marker string, the marker appears in 0
  items sent to Coralogix, 0 items hold a field that is not on the field list, and the agent runtime's own
  telemetry switch is unset in 5 out of 5 sandboxes and in the worker (FR-011).
- **SC-003**: Across the same 5 runs, 100% of items carry every identity field of FR-006 (with "none" or "none yet"
  where it does not apply).
- **SC-004**: With Coralogix blocked, 5 out of 5 test runs end in the same end state as their baseline runs, and
  their ledger records match the baseline except for times and IDs. A test run with a stubbed model (so model time
  does not vary) and Coralogix blocked takes at most 5% (or 10 seconds, the larger) longer than the same run with
  sending off.
- **SC-005**: With Coralogix blocked, the drop counts in the local logs are greater than zero for every process that
  ran, and the worker's count is written at least once a minute while it drops.
- **SC-006**: With sending on and Coralogix reachable, a test run with a stubbed model takes at most 5% (or 10
  seconds, the larger) longer than the same run with sending off.
- **SC-007**: A check run inside a test sandbox finds the Coralogix key in 0 places: no env var, no file in the
  template or the work directory, no process command line.
- **SC-008**: The dashboard, created from the repo file in an empty Coralogix space, shows data in every panel after
  3 test runs, with no manual edit; and its runs per end state match the spec 018 report for the same range.
- **SC-009**: For a test set of 10 bridge deliveries (accepted, rejected for each rejection rule, and ignored), 10 out
  of 10 appear in Coralogix with the right outcome.
- **SC-010**: After a worker restart in the middle of a test run, and after a forced cache eviction in another, the
  run trace holds no span twice. Twice means two spans with the same stage, attempt, handoff index, step try and
  kind.

## Assumptions

- **Depends on 017 and 018.** The identity fields use spec 017's run kind and spec 018's ledger record key. FR-026
  needs spec 018's close event. Until both ship, the worker sends "none" for those fields and skips FR-026. The rest
  of this feature can be built before them.
- **Decisions the operator made on 2026-10-17:**
  - Coralogix for the workflow and developer view: logs, metrics and traces from the worker, the bridge, every
    pipeline stage and swe-agent inside E2B;
  - Langfuse stays for single model calls;
  - Coralogix gets facts only, never prompt, answer or tool-input text;
  - OTel format;
  - this spec amends architecture §3.8;
  - every item carries repo and PR, run kind, stage, attempt and seat;
  - the spec 018 ledger stays the system of record;
  - one operator dashboard is in scope, alerts are not;
  - keep every trace, with a setting that allows sampling later;
  - when Coralogix cannot be reached, drop the data in the background, count the drops, and never block or slow a
    run;
  - for the key in E2B, the operator asked for current best practice. The result is FR-020 (see the next point).
- **Why the sandbox key rule is stricter than for other tokens.** The sandbox already holds the seat's OAuth token
  and the per-run GitHub App token as plain env vars (`_sandbox_envs` in `orchestration/activities.py`). Those are
  needed by the agent to do its work, and spec 013 limits the GitHub token to one repo. The telemetry key is not
  needed by the agent, and a leaked key lets anyone write fake data into the operator's dashboard and run up ingest
  cost. The E2B proxy keeps it out at low cost. Research done on 2026-10-17 (Coralogix's key and send-your-data
  docs, E2B's secrets docs) compared four ways: an env var (the model can read the key and leak it in a commit), a
  gateway with short-lived tokens (needs a public endpoint, high effort), the worker relay, and the proxy. Points not
  confirmed: whether the proxy is generally available, how it matches the auth header, and whether Coralogix keys can
  expire. These go to `/speckit-plan`.
- **Langfuse is narrowed to a shared ID.** Nothing writes to Langfuse today, and the sandbox cannot reach the
  operator's local Langfuse (port 3000). This spec only adds the model-call ID that links the two (FR-027). Writing
  model calls, with their text, to Langfuse is a separate spec. Text may go there because Langfuse runs on the
  operator's own machine.
- **Spec 018 says this feature exports the ledger's facts to Coralogix and Langfuse.** This spec sends them to
  Coralogix only (FR-026). Langfuse gets model calls, not ledger facts. Spec 018's Assumptions should be changed to
  match, in its own worktree.
- **Out of scope, with reasons:**
  - the GitHub-comment path (`.github/workflows/swe-agent-build.yml` through `@e2b/cli`) and pm-agent's
    `shape_issue()` on a target repo's runner: they have no worker, no seat and no stage or attempt to report, and the
    runner cannot reach the operator's machine;
  - `RegistryPromotionWaiterWorkflow`: nothing starts it yet. Spec 017 (FR-025) will start it; tracing it is a
    follow-up once that ships;
  - alerts (operator decision);
  - writing model calls to Langfuse (see above);
  - how long Coralogix keeps data: the account's default applies.
- **Defaults chosen here, open to change in `/speckit-plan`:** the 200-character error message cap, the 5-second
  flush limit, the once-a-minute drop log, and the 5% or 10-second slow-down limit in SC-004 and SC-006. The buffer
  size per process and the relay file cap are set in `/speckit-plan`.
- **Left to `/speckit-plan`:** the OTel libraries and where they hook in; how the identity fields reach the sandbox
  (FR-007); how workflow code detects replay (FR-016), plus a version patch where the workflow's code path changes,
  as specs 009, 011 and 017 use; the field list's format and the test that checks it (FR-009); the dashboard file's
  format; the E2B proxy check and its header names (FR-020); that the SDK's messages give per-call token counts
  (FR-011); how many metric series the identity fields create per run, against Coralogix's series limits and cost;
  and the account's ingest quota.
