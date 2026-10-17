# Feature Specification: swe-agent Session Context

**Feature Branch**: `022-swe-session-context`
**Created**: 2026-10-17
**Status**: Draft
**Input**: User description:

> 022-swe-session-context (swe-agent only)
>
> - Row 10: a read-only exploration subagent via the SDK `agents` option (Read/Grep/Glob + 021's index tools).
>   Returns paths and short findings. The main session stays the only writer.
> - Row 9 remainder: per-session max_turns and max_budget_usd, set from the normal range in 018's records, not
>   guessed.
> - Row 6: a live check that a target repo's CLAUDE.md reaches swe-agent (marker line in a disposable repo), as a
>   success criterion.
>
> Out: eval set from failed runs (row 5), every-attempt feedback (row 1, goes to the 015 owner).

The input above is kept as written. It was approved by the operator on 2026-10-17. "Row N" means gap row N of
`docs/research/reports/Agent memory and large codebase context.md`. Two facts found while writing this spec add to it:

- Spec 018 (Draft) records tokens and cost per model session (its FR-008, FR-009), but not the number of turns. A turn
  ceiling cannot be "set from the normal range in 018's records" until a turn count is recorded. FR-010 adds it.
- Today a session that stops on a limit ends silently: `run_implement` in `harness/swe-agent/agent.py` collects the
  messages and does not check why the session ended. And any Build failure that is not a seat outcome (exit 75 or 77)
  fails the whole run (`pipeline_workflow.py`, Build loop). So a ceiling needs its own outcome (FR-012 to FR-015).

## Why this feature exists

swe-agent runs one model session per open task (spec 011), and that one session does everything: it explores the
repo, reads files, runs commands and writes code. Its tools are `Bash`, `Read`, `Edit`, `Write`, `Grep` and `Glob`
(`build_options` in `harness/swe-agent/agent.py`). Three gaps follow from the research report above:

- **Row 10. Exploration fills the writer's context.** Every file read and every search result stays in the session that
  later writes the code. The research finds that accuracy drops well before the context window is full, and that most
  of the context is tool output. A read-only helper that explores in its own context and returns only paths and short
  findings keeps the writer's context small. Only one session writes, as Cognition and Anthropic advise.
- **Row 9. No session has a ceiling.** No `max_turns` or `max_budget_usd` is set. Spec 018 adds a cost cap per run and
  checks it before each Build session, but it admits that one session can go over the cap by up to its own cost. A
  ceiling per session bounds that.
- **Row 6. Nobody has checked that the target repo's `CLAUDE.md` reaches swe-agent.** `setting_sources` is left at its
  default on purpose (a comment in `build_options` says `setting_sources=[]` breaks `/speckit-implement`). The SDK docs
  say the default loads the project's `CLAUDE.md`, but this has not been seen in a live run.

This feature is for swe-agent only. The architect candidates and `review_spec()` keep their own settings.

The exploration helper works with `Read`, `Grep` and `Glob` alone. When spec 021 (code index) ships, it also gets the
index tools. So this feature does not wait for 021.

In this spec, "FR" means functional requirement and "SC" means success criterion. "Operator" means the person who runs
the factory. "Session" means one model session of swe-agent (one per open task, or one for a whole attempt when Build
runs as a single session, per spec 011). "Explorer" means the read-only exploration subagent. "Ceiling" means the
per-session turn limit or cost limit.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The writer asks an explorer instead of reading everything itself (Priority: P1)

A Build session on `aheumaier/demo-app` must add a field to every place a `Settings` object is built. The session asks
the explorer "where is `Settings` built and read?". The explorer searches and reads in its own context and returns
twelve paths with one line each. The writing session reads only the four files it has to change.

**Why this priority**: It is the largest change to how much the writer's context holds, and it needs nothing from other
specs.

**Independent Test**: Run Build on a disposable target repo with the explorer turned on. Check that the explorer was
called, that it made no edit and ran no command, that its answer stayed within its size limit, and that the run's
result is valid as before.

**Acceptance Scenarios**:

1. **Given** the explorer is turned on, **When** a Build session starts, **Then** the session can call the explorer, and
   the explorer has `Read`, `Grep` and `Glob` only (plus spec 021's index tools when an index is ready for the run).
2. **Given** the explorer is running, **When** it tries to edit a file, write a file, run a shell command or start
   another subagent, **Then** it cannot, because it has no such tool.
3. **Given** the explorer returns, **When** its answer is longer than the size limit (FR-004), **Then** the writer gets
   the answer cut to the limit with a note that it was cut.
4. **Given** the explorer is turned off by its setting, **When** Build runs, **Then** it runs exactly as today.

---

### User Story 2 - A runaway session stops, keeps its work, and the next attempt knows why (Priority: P1)

A Build session on task T007 goes around in circles for 140 turns. The turn ceiling for per-task sessions is 120. The
session is stopped at 120 turns. swe-agent commits the work so far, pushes it, and ends with a "session ceiling"
outcome. The run counts it as one failed Build attempt. The next attempt starts from the pushed work, and its feedback
says: "Session ceiling: task T007 stopped at 120 turns (limit 120)."

**Why this priority**: A ceiling that stops a session without saying so, or that fails the whole run, is worse than no
ceiling. The outcome must be defined before any ceiling is turned on.

**Independent Test**: Set a very low turn ceiling on a disposable target repo and run Build. Check the outcome, the
pushed checkpoint, the attempt count and the next attempt's feedback.

**Acceptance Scenarios**:

1. **Given** a turn ceiling is set, **When** a session reaches it, **Then** the session stops, its leftover edits are
   committed and pushed, and swe-agent ends with the session-ceiling outcome, not with success, a seat outcome (exit 75
   or 77) or a plain failure.
2. **Given** a cost ceiling is set, **When** a session's cost reaches it, **Then** the same happens, and the feedback
   names the cost limit.
3. **Given** a session-ceiling outcome and Build attempts left, **When** the run goes on, **Then** one Build attempt is
   used, and the next attempt's feedback names the ceiling kind, the task ID (when there is one), the value reached and
   the limit.
4. **Given** a session-ceiling outcome and no Build attempts left, **When** the run goes on, **Then** the run ends the
   same way as when Build attempts are used up by Eval-Gate failures.
5. **Given** the run's remaining cost cap (spec 018) is lower than the cost ceiling, **When** the session reaches the
   remaining cap, **Then** the outcome is spec 018's budget stop, not a session ceiling.

---

### User Story 3 - The operator sets the ceilings from real numbers (Priority: P2)

After 30 recorded runs the operator reads the report. It shows, for per-task sessions and for whole-attempt sessions,
the median and the 95th percentile of turns and cost per session. The operator sets each ceiling at about twice the
95th percentile.

**Why this priority**: The input says the ceilings are set from the normal range, not guessed. That needs a turn count
per session and a report of the range.

**Independent Test**: Run the report on a set of recorded runs and check its numbers against the records by hand.

**Acceptance Scenarios**:

1. **Given** fewer than 10 recorded sessions of a kind, **When** the operator reads the report, **Then** it shows the
   count and says there is not enough data to set that ceiling.
2. **Given** at least 10 recorded sessions of a kind, **When** the operator reads the report, **Then** it shows the
   median and 95th percentile of turns and of cost for that kind.
3. **Given** no ceiling is set, **When** Build runs, **Then** no session has a ceiling, as today.

---

### User Story 4 - The operator knows the target repo's CLAUDE.md reaches swe-agent (Priority: P2)

The operator puts a marker line in a disposable target repo's `CLAUDE.md` and runs Build. The run shows that the
session received the marker. If it did not, this feature makes the target repo's `CLAUDE.md` reach swe-agent, without
breaking `/speckit-implement`.

**Why this priority**: Spec 019's lessons and any target repo's own rules depend on this file reaching the agent. It
is cheap to check and has not been checked.

**Independent Test**: The live check itself (SC-005).

**Acceptance Scenarios**:

1. **Given** a disposable target repo whose `CLAUDE.md` holds a unique marker line, **When** Build runs on it,
   **Then** the run's record shows evidence that the session received the marker.
2. **Given** the check finds the marker did not reach the session, **When** this feature is done, **Then** a second
   live run shows the marker reached it, and `/speckit-implement` still runs.

---

### User Story 5 - The explorer stays only if it helps (Priority: P3)

The operator runs 5 to 10 real tasks with the explorer off, then on. They keep it on only if the writer's context per
task drops and the gate pass rate does not.

**Why this priority**: A subagent costs tokens of its own. The gain must show on this pipeline's tasks.

**Independent Test**: Run the measurement (FR-018) and read its table.

**Acceptance Scenarios**:

1. **Given** the measurement has run, **When** the operator reads it, **Then** it shows, with the explorer off and on:
   the writer's context tokens per task, the total tokens per task (writer plus explorer), the gate pass rate and the
   turns per task.
2. **Given** the explorer did not lower the writer's context tokens, or lowered the gate pass rate, **When** the result
   is recorded, **Then** the explorer's setting defaults to off, with the reason written down.

---

### Edge Cases

- **A seat runs out while the explorer is working.** The explorer runs on the session's seat. A seat outcome inside it
  is the session's seat outcome (spec 009): the work so far is pushed and the run hands off to another seat, as today.
- **The explorer reads a file that tells it to do something.** It has no tool that writes, runs commands or reaches
  the network, and its answer goes only to the writer, which already reads the same files. The explorer adds no new
  way in.
- **The explorer's answer is wrong or stale.** The writer still has `Read`, `Grep` and `Glob` and checks before it
  edits. The explorer only reads the checkout as it is at that moment, including the writer's own edits.
- **A ceiling stop with no new commit.** It is still a session-ceiling outcome, not the "no new commit" failure.
- **The SDK and spec 018 count cost differently.** On a subscription seat there is no bill per call, and 018 estimates
  cost from a price table (its FR-012). The cost ceiling uses 018's rule. Where the SDK's own budget option counts cost
  another way, the plan says which one stops the session and how far apart they can be.
- **The retry after a ceiling stop.** It is a retry with feedback, so today's rules (spec 011) run it as one session.
  Ticked tasks stay ticked and are not redone.
- **The GitHub-comment path.** It runs the same `agent.py` but has no workflow, no 018 record and no attempts. The
  explorer works there as on the Temporal path. Ceilings are not set there, as today.
- **A ceiling that is too low.** Every session of a kind could stop. The report (FR-011) shows how many sessions
  stopped on each ceiling, so the operator can see it.

## Requirements *(mandatory)*

### Functional Requirements

**The explorer (row 10)**

- **FR-001**: swe-agent MUST offer its Build sessions one exploration subagent through the SDK's subagent option. Its
  tools MUST be `Read`, `Grep` and `Glob`, plus spec 021's index tools when an index is ready for the run (021 FR-021).
  It MUST NOT have `Bash`, `Edit`, `Write`, any other tool that changes files or runs commands, or a way to start
  another subagent.
- **FR-002**: The writer session MUST keep every tool it has today. The explorer is added, never a replacement. The
  writer stays the only session that changes files.
- **FR-003**: The explorer MUST return file paths with short findings (what is where, and why it matters to the
  question). It MUST NOT return whole files.
- **FR-004**: An explorer answer MUST be at most a set size (a setting, default 1,500 tokens). A longer answer MUST be
  cut to the limit, with a note that it was cut.
- **FR-005**: The explorer's model MUST be a setting, with the writer's model as the default. Its turns per call MUST
  have their own limit (a setting).
- **FR-006**: The writer learns of the explorer from the explorer's description only. This feature MUST NOT add text to
  `IMPLEMENT_PROMPT` or `TASK_PROMPT`. The start of the prompt is spec 019's, for lessons.
- **FR-007**: The explorer's tokens and cost MUST count in the session's usage (spec 018 FR-008, FR-009), in the
  session's cost ceiling, and in the run's cost cap. The usage report MUST show the explorer's share on its own.
- **FR-008**: The explorer MUST have a setting that turns it off. Off, Build MUST run as today.

**Ceilings (row 9)**

- **FR-009**: swe-agent MUST accept two ceilings per session, a turn ceiling and a cost ceiling, each set separately
  for per-task sessions and for whole-attempt sessions. Each MUST default to off. The Temporal path passes them; the
  GitHub-comment path does not.
- **FR-010**: Every session's usage report (spec 018 FR-009) MUST include its number of turns. If spec 018's owner does
  not add the field, this feature adds it to the same report.
- **FR-011**: The report (spec 018's command) MUST show, for each session kind, the count of recorded sessions, the
  median and the 95th percentile of turns and of cost per session, and the count of sessions stopped on each ceiling.
  Below 10 recorded sessions of a kind it MUST say there is not enough data instead of showing percentiles.
- **FR-012**: When a session reaches a ceiling, swe-agent MUST stop it, commit its leftover edits, push every commit of
  the attempt, and end with a session-ceiling outcome. That outcome MUST use an exit code different from success (0),
  a plain failure (1), the seat outcomes (75, 77) and spec 018's budget stop. Its last output line MUST name the
  ceiling kind, the task ID (when there is one), the value reached and the limit.
- **FR-013**: The run MUST treat a session-ceiling outcome as a failed Build attempt: it uses one of
  `MAX_BUILD_ATTEMPTS`, it is never treated as a seat outcome, and it does not fail the run while attempts are left.
  The next attempt's feedback MUST name the ceiling kind, the task ID, the value reached and the limit.
- **FR-014**: When Build attempts are used up by session-ceiling outcomes, or by a mix of them and Eval-Gate failures,
  the run MUST end the same way it ends when Eval-Gate failures use them up.
- **FR-015**: A session's cost ceiling MUST be the lower of the set ceiling and the run's remaining cost cap (spec 018
  FR-014). When the remaining cap is the lower one and the session reaches it, the outcome MUST be spec 018's budget
  stop. This bounds the overrun that spec 018 FR-014 allows today to the cost of one model turn.
- **FR-016**: A session that ends for any other reason MUST end as today. This feature types only the ceiling stops.

**CLAUDE.md (row 6)**

- **FR-017**: The feature MUST include a repeatable live check: a disposable target repo whose `CLAUDE.md` holds a
  unique marker line, one Build run on it, and a recorded result that shows whether the session received the marker.
  If it did not, the feature MUST make the target repo's `CLAUDE.md` reach every Build session, keep
  `/speckit-implement` working, and repeat the check. The architect candidates and `review_spec()` keep
  `setting_sources=[]`; changing them is out of scope.

**Measurement**

- **FR-018**: The feature MUST ship with a repeatable measurement: 5 to 10 real tasks on a large target repo, at least
  half touching three or more files, run with the explorer off and on. For each run it records the writer's context
  tokens per task (the largest context the writer reached in a session), the total tokens per task, the gate pass rate
  and the turns per task. A result where the explorer does not lower the writer's context tokens, or lowers the gate
  pass rate, MUST set the explorer's default to off, with the reason written in the spec directory.

**Out of scope**

- **FR-019**: This feature MUST NOT build an eval set from failed runs (row 5), pass every attempt's feedback to the next
  attempt (row 1, an amendment to spec 015), change the architect or pm agents, or add a ceiling to the architect stage.

### Key Entities

- **Explorer**: the read-only subagent of a Build session. Has a tool list, a model, an answer size limit, a turn limit
  and an on/off setting.
- **Session ceiling**: a turn limit or a cost limit for one session kind (per-task or whole-attempt). Off by default.
- **Session-ceiling outcome**: how a Build attempt ends when a session hits a ceiling. Holds the ceiling kind, the task
  ID, the value reached and the limit. Uses one Build attempt.
- **Session usage report**: spec 018's per-session record, plus the turn count and the explorer's share.
- **Marker check result**: the date, the target repo, the marker, and whether the session received it, with the
  evidence.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 10 of 10 test runs with the explorer on, the explorer makes no file change and runs no command.
- **SC-002**: No explorer answer in the measurement is longer than its size limit.
- **SC-003**: With a turn ceiling set low on purpose, 3 of 3 test runs end the session with the session-ceiling
  outcome, push the work so far, use exactly one Build attempt each time, and give the next attempt feedback that names
  the ceiling, the task and the limit.
- **SC-004**: In those test runs, no ceiling stop is reported as success, as a seat outcome or as a failed run while
  Build attempts are left.
- **SC-005**: The CLAUDE.md marker check is recorded in the spec directory with its date and evidence, and shows the
  marker reached the session (after this feature's fix, if one was needed).
- **SC-006**: The report shows the turn and cost range per session kind and agrees with the records checked by hand
  on 10 sessions.
- **SC-007**: In the measurement, the median of the writer's context tokens per task is at least 20% lower with the
  explorer on, and the gate pass rate is not lower. If that is not reached, the explorer ships turned off and the result
  is reported, not hidden.
- **SC-008**: With the explorer off and no ceiling set, Build runs pass the same tests and live checks as before this
  feature.

## Assumptions

- **Ceiling values.** The recommended value is about twice the 95th percentile of the recorded range, from at least 10
  sessions of that kind. The operator sets it; nothing sets it on its own.
- **One Build attempt per ceiling stop.** A ceiling stop is charged like an Eval-Gate failure. This is a judgment call:
  the session ran long on the task, so it counts as a failed try, unlike a seat outcome, which says nothing about the
  task.
- **Explorer size limit.** 1,500 tokens, from the report's advice to return paths and short findings. A setting.
- **Explorer model.** The writer's model by default. A cheaper model is a setting the measurement can try.
- **Depends on.** Spec 018 for the session usage report, the report command, the run's cost cap and the budget stop.
  Until 018 ships, the ceilings stay off and the measurement reads usage from each session's own result. Spec 021 only
  for the index tools, which the explorer gets when they exist. Spec 011 for the session kinds and checkpoints. Spec
  009 for seat outcomes.
- **Changes to other specs.** Spec 018 gets a turn count per session (FR-010) and the ceiling rows in its report
  (FR-011); its owner is told. Spec 015 gets the every-attempt feedback amendment (row 1); its owner is told. Neither is
  changed by this branch.
- **Research files.** The report and its notes are untracked on main on 2026-10-17. This branch carries them so the
  paths above resolve. The report links to the code index report, which is on branch `021-code-index`; that link works
  once 021 merges.
