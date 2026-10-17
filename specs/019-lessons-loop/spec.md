# Feature Specification: Lessons Loop

**Feature Branch**: `019-lessons-loop`
**Created**: 2026-10-17
**Status**: Draft
**Input**: User description: "Lessons loop for AgentPipelineWorkflow (spec 019). When a run goes badly in a way an
outside check can see (the Eval-Gate fails twice, the run ends as abandoned or timed out, or the merged PR is reverted
within 30 days, from spec 018's revert watch), the factory drafts one short lesson and opens it as a PR for a person to
merge, edit or close. Lessons live in two files: one per target repo (for example `.factory/lessons.md`) for lessons
about that codebase, and one factory-wide file in this repo for lessons about the pipeline itself. A small model call
drafts the line from facts only (spec 015's gate-result.json and spec 018's ledger record, never prompt or answer
text), and its cost is recorded in the 018 ledger. Every run reads both files from the default branch at its start and
gives them to every agent. Each file is capped at about 40 lines; people prune lessons that are no longer true. Out of
scope: changing tools or prompts automatically, learning from runs that went well, an eval set built from past runs,
and observability export (spec 020)."

The input above is kept as written. The operator changed four parts of it on 2026-10-17 (see Assumptions): a repo
lesson needs the same failure in two or more runs, the factory file is for the operator and not given to agents, the
model writes only the text of a new lesson, and the factory proposes removing old lessons.

## Why this feature exists

Every run of the pipeline starts with no memory of the runs before it. Each activity starts fresh
(`docs/70-multi-agent-pipeline-design.md`), and the prompts are fixed in code (`IMPLEMENT_PROMPT` and `TASK_PROMPT` in
`harness/swe-agent/agent.py`, the `.format` templates in `harness/architect-agent/agent.py`). When Build fails the
Eval-Gate on `aheumaier/demo-app` because the spec's tests live in a folder the agent does not expect, the next run on
that repo makes the same mistake. The only feedback today is the gate's reason, passed to the next Build attempt of the
same run (spec 015 FR-021) and then lost.

The research this repo is built on points at one fix and three dangers. The research files are not yet committed to
this repo; on 2026-10-17 they exist only in the operator's main checkout, under `docs/research/`.

- **The fix.** `docs/research/reports/Agent native software factory architecture.md` (gap 10) asks that each repeated
  gate failure leads to a line in the target repo's agent instructions, or a new tool, added through a PR a person
  merges. `docs/research/reports/Agent memory and large codebase context.md` and the notes in
  `docs/research/research_notes/Agent memory and large codebase context/` say to keep such rules in version control,
  review them by PR, and keep the file short.
- **Danger 1: learning from nothing.** An agent that reflects on its own work without an outside check gains about
  nothing. Adding only checked records beats adding everything. This feature drafts a lesson only when an outside check
  says something went wrong, and for a repo lesson only when the same failure comes back in a second run.
- **Danger 2: poisoned memory.** A wrong or planted line in a file every run reads stays there and harms every later
  run. Published attacks of this kind succeed most of the time. This feature lets no lesson in without a person merging
  it, drafts from listed facts only, skips a lessons file with any change no code owner approved, and stops a run from
  editing the lessons it reads.
- **Danger 3: memory that rots.** When a model rewrites memory again and again, detail is slowly lost. Old lessons
  that are no longer true mislead later runs. This feature never lets a model rewrite a lesson: code adds lines, adds
  runs to a line's citation, and proposes removing old lines, and a person merges each change.

This feature adds that loop: draft one line from facts, open it as a PR, let a person decide, give every merged repo
lesson to every agent at the start of every run, and propose removing lessons that have gone quiet.

In this spec, "FR" means functional requirement and "SC" means success criterion. "Operator" means the person who
runs the factory. A "lesson" is one `- ` line in a lessons file. A "trigger" is one of the events that starts a draft
(FR-001). A "failure class" is a kind of gate failure (FR-002).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A gate failure that repeats across runs becomes a lesson for that repo (Priority: P1)

A product run on `aheumaier/demo-app` PR 42 fails its first Eval-Gate attempt because `SC-003` has no linked test
(spec 015 verdict "unmapped"). The gate's feedback goes to the second attempt, which passes, and the run ships. Two
weeks later a run on PR 57 fails its first attempt the same way, this time for `SC-002`. When PR 57's run ends, the
factory sees the failure class "unmapped SC" in two runs on this repo and opens a PR in `aheumaier/demo-app` that adds
one line to `.factory/lessons.md`, for example: "- Every SC-NNN in a spec here needs a linked test before Build
(runs: aheumaier/demo-app#42, aheumaier/demo-app#57; seen 2 times; added 2026-10-31; last seen 2026-10-31)." The PR
body lists the facts the line came from. A code owner of the file reads it, adds where the tests should go, approves
the PR's final commit, and merges it.

**Why this priority**: This is the loop the research asks for, and the failure a repo's agents will repeat most often.
Inside one run, spec 015 already sends the gate's feedback to the next attempt; what is lost today is the step from one
run to the next.

**Independent Test**: On a disposable repo, start two runs whose specs each have an SC with no test. Check that the
first run makes no draft, that the second run opens one PR in that repo adding exactly one line to
`.factory/lessons.md`, that the line cites both runs, and that the PR body lists only allowed facts (FR-009).

**Acceptance Scenarios**:

1. **Given** a run with an "unmapped SC" gate failure, and an earlier closed run on the same repo within the look-back
   window with the same failure class, **When** the later run's record is closed (spec 018), **Then** one draft is made
   for the repo file.
2. **Given** a run with a failure class seen in no earlier run on that repo within the look-back window, **When** its
   record is closed, **Then** no draft is made, even when the run spent its whole Build attempt budget.
3. **Given** a draft is made, **When** it is applied, **Then** the draft's commit changes exactly one line of the
   file, the line cites the runs, and the PR body lists the facts given to the drafter.
4. **Given** the file, or its open lessons PR, already has a lesson that the drafter names as saying the same thing,
   **When** the draft is
   applied, **Then** code adds the new run to that lesson's citation and sets its "last seen" date, and changes nothing
   else in the line.
5. **Given** a person closes the lessons PR without merging, **When** later runs start, **Then** they do not see the
   draft.

---

### User Story 2 - Every run reads the merged repo lessons (Priority: P1)

After the lesson from User Story 1 is merged, the operator starts a new run on `aheumaier/demo-app` PR 61. At the
start of the run, the factory reads `.factory/lessons.md` from the repo's default branch and checks that a person
merged its last change. Every model session of the run gets the same text near the start of its prompt, shown as
lessons written and approved by people. The run's ledger record shows which commit the file was read at.

**Why this priority**: A lesson nobody reads is useless. Today no stage reads the target repo's default branch, and
the architect stage loads no repo settings, so nothing reaches the agents without this.

**Independent Test**: Merge a lessons file with a known line on a disposable repo, start a run, and check with a test
that captures what each model session is given that every session in FR-021's list got the line word for word, and
that the record names the commit the file was read at.

**Acceptance Scenarios**:

1. **Given** the repo file exists on the default branch and passes the trust check (FR-021), **When** a run starts,
   **Then** it reads the file once, and every model session in the run gets the same text.
2. **Given** the repo file does not exist, **When** a run starts, **Then** the run goes on without it, and the record
   says the file was absent.
3. **Given** a change to the file was pushed straight to the default branch, merged by a bot or the factory's App, or
   merged with no code-owner approval on the PR's final commit, **When** a run starts, **Then** no session gets the
   file, and the record says it was untrusted and why.
4. **Given** the file changes on the default branch while a run is going, **When** the run's later stages start,
   **Then** they still get the text read at run start.
5. **Given** the file is over its cap (FR-024), **When** a run reads it, **Then** the run uses only the first lessons
   up to the cap, and the record says the file was over its cap.
6. **Given** the run's feature branch has a changed copy of the file, **When** the run reads lessons, **Then** it reads
   them from the default branch, never from the feature branch.
7. **Given** the factory file has lessons, **When** a run starts, **Then** no model session gets the factory file.

---

### User Story 3 - A pipeline failure becomes a lesson for the operator (Priority: P2)

A product run on `aheumaier/demo-app` PR 64 waits 30 days for a plan approval and ends as timed out. A week later the
operator abandons a run on another repo after a budget stop (spec 018). Each time, the factory opens a PR in this repo
that adds one line to the factory file, for example: "- Plan approvals on aheumaier/demo-app went unanswered for 30
days (runs: aheumaier/demo-app#64; seen 1 time; added 2026-11-30; last seen 2026-11-30)." The operator reads it, fixes
the cause (for example, who gets told about a waiting plan), and keeps or closes the line. No agent is given this file.

**Why this priority**: These failures are about the pipeline, which the operator fixes, not about a target repo's
code. They are less common than gate failures.

**Independent Test**: On a disposable repo, start a run with a very short maximum wait so it times out, and check that
one PR opens in this repo that adds one line to the factory file, and none in the target repo.

**Acceptance Scenarios**:

1. **Given** a run ends as timed out, as abandoned by the operator, or as failed with an error, **When** its record is
   closed, **Then** one draft is made for the factory file.
2. **Given** a run ends as abandoned because its PR was closed or is gone, **When** its record is closed, **Then** no
   draft is made for this trigger.
3. **Given** a run has an Eval-Gate verdict "error" on two attempts, **When** its record is closed, **Then** one draft
   is made for the factory file and none for the repo file.
4. **Given** a run ends as shipped or merged before checks, **When** its record is closed, **Then** no draft is made
   for the factory file.

---

### User Story 4 - A revert becomes a lesson for that repo (Priority: P3)

A product run on `aheumaier/demo-app` PR 42 shipped on 2026-11-02. On 2026-11-20 the merge is reverted, and spec
018's revert watch records it. Within minutes of that record, the factory opens a PR in `aheumaier/demo-app` that adds
one line saying the PR passed every gate check and was reverted 18 days later, citing the run. A person adds why it
was reverted, or closes the PR. A revert drafts at once; it does not need a second run.

**Why this priority**: A revert is the strongest outside sign that a merge was wrong, but it comes weeks later and
says nothing about why. It matters only once runs ship.

**Independent Test**: On a disposable repo, ship a run, revert it with GitHub's revert button, and check that one PR
opens in that repo within the revert watch's interval plus 10 minutes.

**Acceptance Scenarios**:

1. **Given** the revert watch records a revert for a shipped run, **When** the revert is recorded, **Then** one draft
   is made for the repo file, citing the run.
2. **Given** the revert is itself reverted later, **When** that is recorded, **Then** no second draft is made.

---

### User Story 5 - Lessons that have gone quiet are proposed for removal (Priority: P3)

The lesson "Integration tests here live in `tests/integration/`" was last seen on 2026-11-02. By 2027-02-01 no run has
hit that failure again, and the folder was renamed in January. The daily lessons sweep opens a removal PR in
`aheumaier/demo-app` that deletes the line and says why: 90 days with no new run, and the named path is gone. A person
merges it. If the person closes it instead, the factory does not propose that lesson again for 90 days.

**Why this priority**: Without it, files fill with lessons that are no longer true, and every run pays for reading
them. It matters only once lessons pile up.

**Independent Test**: On a disposable repo, merge a lesson with a "last seen" date older than the setting and a named
path that does not exist. Run the sweep, and check that one removal PR opens that deletes only that line.

**Acceptance Scenarios**:

1. **Given** a lesson whose "last seen" date is older than the quiet period (FR-026), **When** the sweep runs,
   **Then** the factory's removal PR for that file deletes the line and names the reason.
2. **Given** a lesson that names a path that no longer exists on the default branch, **When** the sweep runs, **Then**
   the removal PR deletes the line and names the missing path.
3. **Given** a person closed a removal PR without merging, **When** the sweep runs again within the quiet period,
   **Then** it does not propose the lessons from that PR again.

---

### Edge Cases

- **A run matches two triggers.** A run whose gate failure repeats an earlier run's and that then ends as timed out
  gets one draft for the repo file and one for the factory file (FR-005).
- **A run spends its whole Build attempt budget on a failure class not seen before on that repo.** It makes no draft.
  Spec 015 already fed the gate's feedback to each attempt; the next run with the same class will draft.
- **Two failure classes repeat in one run.** The run still gets one draft for the repo file, whose facts list both
  classes (FR-005).
- **A worker restart or a step retry during a draft.** The draft is applied at most once (FR-006); a retry finds its
  earlier commit by its identity and goes on from where it stopped.
- **A lessons PR is already open** for the same file. The new draft is added to it as one more commit (FR-017).
- **The file is at its cap.** A draft that would add a new line is refused, and the record and the report say so
  (FR-025). A draft that only adds a run to an existing lesson's citation is still applied.
- **The drafter returns something that is not valid** (more than one line, too long, a link, code, a lesson number
  that does not exist). It is tried once more; if it is still not valid, no change is made and the record says the
  draft was refused, with the check that failed (FR-013).
- **The model call or the PR fails.** The draft is tried again. If it still fails, the record says so. The run's end
  state never changes because of a draft.
- **The App is not installed on the target repo any more.** No PR opens there; the record says why.
- **A run's branch changes a lessons file**, compared with the merge base. The Eval-Gate fails it (FR-023), even when
  a person made that change on the PR branch before the run started.
- **A run's record never closes** (the close write was lost, and spec 018 shows it as stale). The daily sweep treats
  it as "ended badly" and drafts for the factory file (FR-027). If the record closes later, no second draft is made.
- **Gate results contain agent-chosen text.** Test IDs and file names come from code the agent wrote. They reach the
  drafter only as listed facts, marked as data; they may not appear in a lesson's text; they appear in the PR body only
  in fenced code; and a code owner approves every line before it is merged (FR-010, FR-013, FR-019, FR-021).
- **Something other than the factory or a person pushes to an open lessons PR**, for example a Build using the
  sandbox token, which belongs to the same App. Later drafts for that file are refused until a person merges or closes
  that PR (FR-017). If that PR is merged, the file fails the trust check unless a code owner approved its final
  commit (FR-021). Closing it does not hold back later drafts (FR-001).
- **A person closes a lessons PR that adds lines.** The same kind of draft for that file is not made again for 90
  days, apart from reverts (FR-001).
- **A lesson that works.** A lesson that stops a failure from coming back is never seen again, so it is proposed for
  removal after the quiet period. The person who reads the removal PR keeps it by closing the PR.
- **Runs that started before this feature shipped** make no drafts and read no lessons.
- **A factory-agent run.** Its target repo is this repo, so its repo file is this repo's `.factory/lessons.md`, which
  is a different file from the factory file (FR-003).

## Requirements *(mandatory)*

### Functional Requirements

**Triggers and routing**

- **FR-001**: A lesson draft MUST be made only for these triggers:
  - **repeated gate failure** (repo file): a failure class (FR-002) appears in at least one Eval-Gate attempt of the
    run that just closed and in at least one Eval-Gate attempt of an earlier closed run on the same repo whose start
    falls within the look-back window, a setting with a default of 90 days;
  - **gate error** (factory file): the gate's overall verdict is `error` (spec 015 FR-019) on two or more attempts,
    counted over the run that just closed and the earlier closed runs on the same repo within the look-back window, and
    at least one of those attempts is in the run that just closed;
  - **ended badly** (factory file): the run ends as timed out, as abandoned by the operator (including a budget abandon
    from spec 018), as failed with an error, or as failed because its plan attempt budget (`MAX_PLAN_ATTEMPTS`) was
    spent;
  - **reverted** (repo file): spec 018's revert watch records a revert of the run's merged PR within 30 days. This
    trigger needs no second run.

  A run that ends as shipped or merged before checks, and has no other trigger, MUST NOT get a draft. A run abandoned
  because its PR was closed or is gone MUST NOT get a draft for that reason. A failed run whose reason is a spent Build
  attempt budget MUST NOT get an "ended badly" draft; only the "repeated gate failure" trigger applies to it. A failed
  run whose reason is a bot merge (spec 017) MUST NOT get a draft, because it is a setup problem the operator already
  sees.

  After a person closes a lessons PR that adds lines without merging it, no draft with the same key MUST be made for
  that file for the quiet period (FR-026). The key is the file, the trigger, and the failure classes or end-state code
  of the draft, taken from the ledger's draft records for that PR's URL (FR-016), never from the PR's text. The
  "reverted" trigger is exempt: each revert is its own event. So is a PR on which drafts were refused for an unknown
  commit (FR-017), since a person closing it is a cleanup, not a judgment of its lessons. A draft held back this way
  is recorded as "suppressed".
- **FR-002**: A failure class MUST be computed by code from the stored gate-result.json (spec 015 FR-018), never judged
  by a model. Only attempts whose overall verdict is `fail` count, and only the SC verdicts and integrity findings
  that spec 015 counts toward that `fail`. A finding that does not fail the gate (such as `unknown_sc`, spec 015
  FR-010), a removed test that a waiver excuses (spec 015 FR-011), and every attempt with verdict `error` add no class.
  The classes are: an SC with verdict `fail`, an SC with verdict `unmapped`, "every SC manual", and each failing
  integrity finding kind (`removed_tests`, `assertion_drop`, `coverage_drops`, `spec_changed`, a waiver problem, and
  `lessons_changed` from FR-023). A class does not include the SC ID or test ID, because different runs judge different
  specs.
- **FR-003**: There MUST be two lessons files:
  - the **repo file**, `.factory/lessons.md` on the target repo's default branch, for lessons about that repo's code;
  - the **factory file**, `.factory/pipeline-lessons.md` on this repo's default branch, for lessons about the pipeline.

  Both paths MUST be settings with these defaults.
- **FR-004**: The triggers that come from the run's end MUST be checked when spec 018 closes the run's record, by
  reading the ledger: this run's record, and the earlier closed records on the same repo within the look-back window
  (spec 018 FR-003 stores every attempt's gate-result.json). The "reverted" trigger MUST be checked when the revert
  watch records the revert. A trigger MUST NOT be checked from Temporal's history.
- **FR-005**: There are two kinds of evaluation point. **Run end** is one per run record: it is reached when the
  record closes, or by the sweep (FR-027), whichever acts first. **Revert recorded** is one per revert the watch
  records. Each evaluation point MUST make at most one draft per file. When more than one trigger or failure class
  applies to the same file, that one draft's facts MUST list all of them.
- **FR-006**: Each draft MUST be applied at most once, across step retries, worker restarts, and the record's close
  racing the sweep. Its identity MUST be the run's record key (spec 018 FR-001), the evaluation point (run end, or
  the revert), and the file. The outcome stored in the ledger for that identity (FR-016) is the claim: before
  evaluating a point, the factory MUST check for it and do nothing more when one exists, whatever it is. As a second
  guard, the identity MUST be written into the commit that applies the draft, and before applying a draft the factory
  MUST check the open lessons PR and the default branch for a commit with that identity. Evaluations and drafts for
  the same file MUST run one at a time.

**Drafting**

- **FR-007**: A draft MUST be written by one model call with no tools and no repo settings loaded. The model MUST be a
  setting, with a small, low-cost model as the default: `claude-haiku-5-5`.
- **FR-008**: The drafter MUST return one of two answers: the text of one new lesson, or the number of an existing
  lesson, in the file or pending in its open lessons PR, that says the same thing. The drafter MUST NOT write or
  return the citation, the dates, or any change to an existing lesson.
- **FR-009**: The drafter MUST be given only these facts:
  - from the gate results of the runs involved: each SC's verdict and its linked test IDs, each integrity finding's
    kind and count, the failure classes, and the overall verdict;
  - from the ledger records of the runs involved: repo, PR number, run kind, end state and its code (never a free-text
    reason), stage attempts with their outcomes, and for a revert the reverting PR and the days from merge to revert;
  - the current lessons for the file it drafts for, as one numbered list: the lines on the default branch first, then
    the lines pending in the file's open lessons PR, each pending line marked as not yet approved.
- **FR-010**: The drafter MUST NOT be given the gate's `feedback` string, the operator's free-text reason for an
  abandon (spec 018 FR-003), model prompt text, model answer text, tool input or output text, the spec, plan or tasks
  text, the PR's diff, title, body or comments, or any credential or token value. Test IDs and file names, which come
  from code the agent wrote, MUST be marked to the model as data, not instructions.
- **FR-011**: Code, not the model, MUST build each change to a file:
  - for new text, code adds the line `- <text> (runs: <repo#PR, ...>; seen <N> times; added <date>; last seen <date>)`;
  - for an existing lesson's number, code adds the new run to that lesson's citation, adds one to "seen", and sets
    "last seen", in the default branch's line or in the pending line of the open lessons PR. The citation lists at
    most the 3 most recent runs.
- **FR-012**: A lesson's text MAY name one repo path, a file or a folder, in backticks, and only a path that exists on
  the default branch when the draft is checked. The sweep uses it to find lessons whose path is gone (FR-026).
- **FR-013**: The factory MUST check every draft before applying it:
  - the text: one line, at most 200 characters, no link, no HTML, no code other than one allowed path (FR-012), and no
    test ID or file name from the facts other than the one allowed path, since those come from code the agent wrote;
    or a lesson number that exists in
    the file or is pending in its open lessons PR;
  - the resulting change: it adds exactly one `- ` line in the format of FR-011, or changes exactly one existing line
    whose citation alone changed.

  A draft that fails the check MUST be tried once more. If it fails again, no change MUST be made and the record MUST
  say the draft was refused, with the check that failed.

**Cost**

- **FR-014**: The draft's model call MUST go through the LiteLLM proxy with the factory's API key, not on a
  subscription seat, because the run's seat lease has ended by the time a draft is made. The proxy MUST have a route
  for the drafter's default model; today it has only `claude-sonnet` and `claude-sonnet-5` (`litellm/config.yaml`).
- **FR-015**: The draft's model usage and cost (per spec 018 FR-008 and FR-012, with the same price table) MUST be
  added to the run's closed record as a "lesson draft" fact, without reopening the record, the same way spec 018
  FR-027 adds revert facts. The draft MUST NOT count against the run's cost cap. Spec 018's report MUST print, on one
  more line (an addition to spec 018 FR-021), the count and total cost of lesson drafts, the count refused, the count
  refused because a file was at its cap, the count refused because the open lessons PR had an unknown commit
  (FR-017), and the count suppressed (FR-001).

**The lessons PRs**

- **FR-016**: The record MUST store, for each evaluation point and file (FR-006), its identity, trigger, target file,
  status (no trigger, suppressed, applied, refused or failed, with a reason) and the trigger key of FR-001; and, when a
  model was called, the model, token counts and cost, the PR URL, the commit, and a hash of the line. It MUST NOT
  store the line's text, which is model answer text under spec 018 FR-004.
- **FR-017**: Each draft MUST be applied as one commit to the open lessons PR for that file, or to a new one when none
  is open. There MUST be at most one open lessons PR per file for additions, and at most one for removals (FR-026).
  Before applying a draft to an open lessons PR, the factory MUST check every commit on it: each one must be either a
  factory commit whose SHA the ledger stored for a draft (FR-016), or a commit by a user account that is not a bot and
  not the factory's App. Author identity alone cannot tell the lessons token from the sandbox token, because both
  belong to the same App, and a commit trailer can be copied, so the SHA decides. The check for a person's commit is
  best effort, since a push can claim any git author; FR-021's approval on the final commit is the real gate. If any
  commit fails this check, the draft MUST be refused with the reason "lessons PR has an unknown commit". Every later
  draft for that file is refused the same way until a person merges or closes that PR. Lines pending in the open PR
  count toward the caps (FR-024, FR-025).
- **FR-018**: The factory MUST NOT merge, approve or close a lessons PR. Only a person does. The factory MUST NOT treat
  a lesson as accepted until it is on the default branch.
- **FR-019**: The PR body MUST list, for each draft in it, the facts the drafter was given (FR-009, apart from the
  file's current lessons), the trigger, the run's record key, and the model and cost of the draft. Test IDs and file
  names, which the agent chose, MUST appear only inside fenced code blocks, each fence longer than any run of
  backticks in what it holds, and a string with a line break MUST be left out. The body MUST say that a code owner must
  check each line and approve the PR's final commit before merging.
- **FR-020**: A lessons PR in a target repo MUST be opened with a GitHub App installation token minted on the worker
  for that repo only, with contents write and pull requests write, under the same rules as spec 013 (the token stays in
  worker memory and is never an activity argument or result). It MUST be a separate token from the one minted for the
  sandbox. A lessons PR in this repo MUST use the path the factory already uses for its own PRs (the one
  `register_activity` uses). Today that path, `_open_factory_pr` in `orchestration/activities.py`, pushes with the
  worker's own `GH_TOKEN`, which may be the operator's personal access token, so a factory lessons PR can look as if
  a person wrote it. The trust check does not depend on who opened the PR: it needs a code owner's approval on the
  final commit (FR-021). The factory file is never given to agents (FR-022).

**Reading lessons**

- **FR-021**: At the start of a run, before the first model session, the run MUST read the repo file from the target
  repo's default branch, once, and MUST use it only if it passes the trust check:
  - the repo's CODEOWNERS file on the default branch assigns an owner to the file's path; and
  - every commit that changed the file on the default branch since the commit of the repo's last trusted read in the
    ledger (or, when the ledger has no trusted read for this repo or that commit is no longer in the default branch's
    history, in the file's whole history) came in through a
    merged PR that was merged by a person, and that a code owner of the file approved on the PR's final head commit.
    A person here is a user account that is not a bot and not the factory's App.

  So a change pushed straight to the default branch fails the check, as does a PR merged with no such approval on its
  final commit. The sandbox token can write contents and open and merge PRs (spec 013), and a Build could push to an
  open lessons PR after a person approved it; the approval then no longer covers the final commit, so that change
  MUST fail this check. A known limit: on a repo that merges through a merge queue, GitHub records the queue's bot as
  the merger, so the file never passes. That fails safe.

  When the file passes, every one of these model sessions in the run MUST be given that same text, near the start of
  its prompt, marked as lessons written and approved by people: each architect candidate, the scoring, the synthesis,
  the critic, and each Build session (one per open task, or the single session of an attempt, as spec 018 FR-009 lists
  them), and any model-calling stage added later. The text MUST be given explicitly and MUST NOT rely on an agent
  loading repo settings on its own. A file that is absent or untrusted MUST NOT stop the run. The record MUST store the
  commit the file was read at, and whether it was absent, untrusted (with the reason) or over its cap.
- **FR-022**: The factory file MUST NOT be given to any model session other than the drafter. It is for the operator.
- **FR-023**: The Eval-Gate MUST fail an attempt when either lessons file at the attempt's head differs from the file
  at the merge base (as spec 015 FR-001 compares them), with the finding `lessons_changed` naming the file. So the
  branch of a factory run must leave both files as they are on the merge base. This is an addition to spec 015's
  integrity findings and its result document; if spec 015 has shipped with `schema_version: 1`, this raises it to 2.

**Size and removal**

- **FR-024**: Each lessons file MUST have a cap of 40 lessons, a line cap of 400 bytes and a file cap of 16 KB, all
  settings. A run MUST read only the first lessons that fit within the caps (FR-021).
- **FR-025**: A draft that would add a new line to a file at a cap MUST be refused, and the record MUST say "file at
  cap". The lines on the default branch and the lines pending in the file's open lessons PR count together toward the
  caps. A draft that only changes an existing lesson's citation MUST still be applied.
- **FR-026**: A lessons sweep MUST run on a schedule, a setting with a default of once a day. For each lessons file it
  MUST propose removing, in the file's one open removal PR, every lesson that:
  - has a "last seen" date older than the quiet period, a setting with a default of 90 days; or
  - names a path (FR-012) that no longer exists on the default branch.

  The PR body MUST give each line's reason. Each removal PR MUST carry a label, a setting. The sweep MUST NOT propose
  a lesson again within the quiet period after a person closed a removal PR that held it. It finds those PRs by their
  label and matches a lesson by its text without its citation, so a citation update does not make it new again.
  Removal follows FR-018: a person merges it. People MAY also edit or remove lessons through any normal PR, meaning a
  PR the factory does not build: a factory run's branch must leave both lessons files as they are on the merge base
  (FR-023).
- **FR-027**: The same sweep MUST find closed records with no draft decision yet and stale open records (spec 018
  FR-002), and evaluate them at their "run end" point (FR-005). A stale record counts as "ended badly". It MUST also
  find recorded reverts with no draft decision and evaluate them at their "revert recorded" point. The sweep MUST
  act on a record only after spec 018's write-retry window (its FR-006) has passed, so it does not race a close that is
  still being written. Every evaluation point of every run started after this feature ships MUST end with one stored
  outcome: no trigger, suppressed, applied, refused or failed (FR-016).

**Rollout**

- **FR-028**: Runs that were in flight when this feature ships MUST finish as before: they make no drafts and read no
  lessons. Their records have no draft decision, and the sweep MUST skip them.
- **FR-029**: A run on a repo with no repo file MUST behave as it does today, apart from what spec 018 records.

### Key Entities

- **Lessons file**: a file on a default branch. Which file (repo or factory), its path, its caps, and its lessons in
  order.
- **Lesson**: one `- ` line. Its text, an optional path, the up to 3 most recent runs it cites (`repo#PR`), how many
  times it was seen, the date it was added, and the date it was last seen.
- **Failure class**: a kind of gate failure, computed from gate-result.json (FR-002).
- **Trigger**: repeated gate failure, gate error, ended badly, or reverted, with the runs it fired for.
- **Lesson draft**: one per evaluation point and file. What the record stores is listed in FR-016.
- **Lessons read**: one per run. The commit the repo file was read at, and whether it was absent, untrusted (with the
  reason) or over its cap.
- **Removal proposal**: one open removal PR per file, with each lesson and its reason.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For two test runs on a disposable repo with the same failure class, the first makes no draft, and a
  lessons PR is open in that repo within 10 minutes of the second run's record closing, whose draft commit changes
  exactly one line, a line that cites both runs.
- **SC-002**: For a test run that times out, a lessons PR is open in this repo within 10 minutes of the record closing,
  adding one line to the factory file, and no PR opens in the target repo.
- **SC-003**: For a test run that is shipped and then reverted, a lessons PR is open in the target repo within 10
  minutes of the revert being recorded.
- **SC-004**: After a forced worker restart and a forced step retry in the middle of a draft, there is still exactly one
  commit with that draft's identity and one open lessons PR for that file.
- **SC-005**: In a test run after a lesson is merged, a test that captures what each model session is given shows the
  repo lesson word for word in 100% of the sessions FR-021 lists, the factory file in 0% of them, and the record names
  the commit the repo file was read at.
- **SC-006**: In each of these six cases on a disposable repo, a test run gives the repo file to 0 sessions and the
  record says "untrusted" with the reason: the file's last change was pushed straight to the default branch; it was
  merged by the factory's App; it was merged with no code-owner approval on the PR's final commit; the App's token
  pushed to an open lessons PR after a code owner approved it, and then a person merged it; CODEOWNERS has no entry for
  the file; and, with no earlier trusted read in the ledger, an untrusted change sits deep in the file's history under
  later trusted ones.
- **SC-007**: A test run whose commits change `.factory/lessons.md` fails the Eval-Gate with a `lessons_changed`
  finding that names the file.
- **SC-008**: A scan of every test lessons PR (its lines and body) and every lesson-draft record finds none of the test
  prompts, model answers, gate `feedback` strings, operator reasons or token values used in the test runs, and no
  lesson line contains a test ID or file name from the facts other than its one allowed path (FR-012).
- **SC-009**: In 7 out of 7 test drafts with an invalid model answer (two lines, too long, a link, code, a lesson
  number that does not exist, a path that does not exist on the default branch, a test ID taken from the facts), no
  change is made and the record says why.
- **SC-010**: On the test repos, every change to a lessons file on a default branch came in through a PR merged by a
  person, and the factory made zero merges, zero approvals and zero direct pushes to any lessons file.
- **SC-011**: With a test file at its 40-lesson cap, a new-line draft is refused and the report counts it, and a draft
  that names an existing lesson is applied.
- **SC-012**: With a test lesson whose "last seen" date is past the quiet period, and one whose named path is gone, the
  removal PR is open within one sweep interval, removes exactly those two lines, and gives each line's reason.
- **SC-013**: Each test draft's tokens and cost are in its run's record, and spec 018's report prints the count and
  total cost of lesson drafts.
- **SC-014**: A test run on a repo with no repo file behaves as it did before this feature: same stages, same comments,
  same end state, on the same test input.
- **SC-015**: After a person closes a test removal PR, the next sweep within the quiet period proposes none of its
  lessons again, even when one of them gained a new run in its citation meanwhile.

## Assumptions

- **Depends on 015, 017 and 018.** Triggers use spec 015's gate results, spec 017's end states and run identity, and
  spec 018's record, close event, stale records and revert watch. Until those ship, this feature cannot run.
- **Decisions the operator made on 2026-10-17:**
  - both files, a repo file and a factory file;
  - a model drafts from listed facts only, with its cost in the ledger, and it writes only the text of a new lesson or
    names an existing one; code builds every change (this replaces "the model drafts the line");
  - a repo lesson needs the same failure class in two or more runs on that repo; a revert drafts at once (this replaces
    the earlier reading of "the gate fails twice" as two attempts in one run);
  - the factory file is for the operator and is not given to agents (this replaces "every run gives both files to
    every agent");
  - the factory proposes removing lessons that have gone quiet or whose path is gone, through a PR a person merges
    (this replaces "the factory never removes a lesson");
  - and these defaults: the trust check on the repo file; a gate `error` goes to the factory file; a PR closed or gone
    is not a trigger; the operator's free-text reason and the gate's `feedback` are never given to the drafter; the
    paths `.factory/lessons.md` and `.factory/pipeline-lessons.md`; caps of 40 lessons, 400 bytes per line and 16 KB
    per file, with a new line refused at the cap; one open lessons PR per file, with drafts applied one at a time;
    lessons placed near the start of each prompt; and no memory tool and no search index.
- **"Last seen" means the last run that cited the lesson**, not the last run that read it. A lesson that works stops
  the failure, is not cited again, and is proposed for removal after 90 days. The person reading the removal PR keeps
  it by closing the PR. The other reading would never let a lesson expire on a busy repo.
- **The factory file passes the trust check by itself**, because this repo's main is protected and every change needs
  a PR (since 2026-10-11). It is not given to agents, so FR-021's check is not applied to it.
- **Showing the current file to the drafter is safe enough.** Lines pending in the open lessons PR are marked as not
  yet approved (FR-009), the drafter has no tools and cannot act on what it reads, and every line it writes passes the
  checks of FR-013 and then a code owner before it is merged (FR-021).
- **What makes a lesson useful is left to the person merging it.** The drafter has only facts, so its line often says
  what went wrong but not why. The person merging the PR is expected to add the why or close the PR.
- **The target repo's code owners** must own `.factory/lessons.md` for the file to pass the trust check. Live checks
  need a repo set up that way, as spec 017's live checks do.
- **How the files are read and given to each stage**, how a draft is triggered from the record's close, the revert
  watch and the sweep, and the replay-safety mechanism for runs in flight (a workflow version patch, as specs 009, 011
  and 017 use) are left to `/speckit-plan`. Note for the plan: today `_open_factory_pr`
  (`orchestration/activities.py`) returns an already-open PR without applying the new change, so adding a commit to an
  open lessons PR needs new handling.
- **Changes to other specs.** Spec 015 gains the `lessons_changed` finding (FR-023). Spec 018's report gains one line
  (FR-015). Spec 018's lesson-draft facts follow its FR-004. Spec 018 must also define a close event that other
  features can act on (it has none today), and an end-state code that tells a spent Build budget from a spent plan
  budget (FR-001).
- **Possible amendment to spec 015, not part of this feature.** The research suggests giving each Build attempt every
  earlier attempt's failures, not only the last one's. Today spec 015 FR-020 and FR-021 pass only the last `feedback`.
- **Not in scope:** changing prompts, tools or settings automatically; learning from runs that went well; building an
  eval set from past runs; a memory tool or a search index over lessons; checking that a target repo's own
  `CLAUDE.md` reaches swe-agent; and any export (spec 020).
