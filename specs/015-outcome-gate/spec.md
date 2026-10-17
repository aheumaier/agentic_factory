# Feature Specification: Outcome Gate

**Feature Branch**: `worktree-015-outcome-gate`

**Created**: 2026-10-16

**Status**: Draft

**Input**: User description: "Outcome gate for AgentPipelineWorkflow's Eval-Gate (eval/braintrust/eval.config.py::run_eval, run as eval_gate_activity). It replaces today's binary coverage check and specs/006-quality-gate FR-001..003 (006 keeps only its docstring, docs-touch and coverage-threshold checks). 1) SC->test traceability: every SC-NNN in the branch's specs/*/spec.md must map to at least one test that exists in the diff or the base branch and PASSES in the sandbox run. Tests declare the link in code (marker or test ID), never through commit messages, PR body, labels or trailers, which the gate ignores. 2) Test-integrity diff against the merge base: fail if a test ID present at the merge base is removed or skipped, if the assertion count of the suite drops, or if line coverage of any changed file drops by >=1 percentage point. The only excuse for a removal is an entry in a waiver file owned via CODEOWNERS, with a reason and an expiry date; expired waivers fail. 3) Output: a versioned gate-result.json v1 (per-SC verdict pass/fail/unmapped with the linked test IDs; integrity findings removed_tests / assertion_drop / coverage_drops / waivers_used; overall verdict; a feedback string). On fail the feedback is fed back to swe-agent on the next MAX_BUILD_ATTEMPTS lap, and the file is attached to the run for the human gates. Same rule in full and vibe mode (Eval-Gate is never mode-conditional, per specs/005). Out of scope: scoring the content of an SC beyond its linked tests passing, the run ledger and metrics (later spec), the GitHub-comment trigger path."

## Context

The research behind this repo (`docs/research/reports/Agent native software factory architecture.md`, gap 2) concludes that
the gate, not the agent, is what makes an agent factory improve over time. Today's Eval-Gate cannot play that role. As of
2026-10-16 on `main` (704ed29):

- `eval_gate_activity` clones only the branch tip (`git clone --depth 1`). It cannot see the merge base, so it cannot tell
  what a build removed.
- It reads `specs[0]`, the first spec directory in sort order, not the spec the branch is for.
- It runs no tests. The workflow passes it a hardcoded trace (`{"pr_url": ..., "exit_code": 0}`), so "sandbox exit 0" is
  always true at the gate.
- `run_eval` passes if the spec has at least one `SC-NNN` bullet and a PR URL exists. A build that deletes every test passes.

`specs/006-quality-gate` (Draft) proposed traceability through "a test name, a docstring, or a commit message". A commit
message is text the building agent writes, so it proves nothing. This feature replaces 006 FR-001..FR-003. 006 keeps its
docstring, docs-touch and coverage-threshold checks.

The rules on test integrity are adapted from the delivery-templates CI the user pointed to on 2026-10-16
(`github.com/7education/delivery-templates`): removed test IDs are diffed against the merge base, assertion counts must not
drop, per-file coverage must not drop, and a removal is excused only by an expiring waiver in a file with code owners. PR
labels, PR body and commit trailers are never read.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Each success criterion needs a passing test (Priority: P1)

The operator starts a pipeline run for a feature whose spec lists success criteria SC-001..SC-005. The building agent
implements the feature. The gate passes only if each SC is linked, in the test code itself, to at least one test, and every
linked test passes in a run the agent did not control. If SC-004 has no linked test, the gate fails, names SC-004, and the
next build attempt is told exactly that.

**Why this priority**: This is the core of the outcome gate. Without it the pipeline's "pass" means "a PR exists", and no
later metric (first-pass rate, cost per merged PR) means anything.

**Independent Test**: A fixture target repo with a feature spec of 3 SCs. Branch A links all 3 to passing tests. Branch B
links only 2. Branch C links all 3, but one linked test fails. Only A passes. B's result marks the missing SC `unmapped`.
C's result marks that SC `fail` with the failing test ID.

**Acceptance Scenarios**:

1. **Given** a branch whose spec has SC-001..SC-003 and three passing tests, each linked to one SC, **When** the gate runs,
   **Then** the verdict is `pass` and each SC lists its linked test ID.
2. **Given** the same branch with no test linked to SC-002, **When** the gate runs, **Then** the verdict is `fail`, SC-002 is
   `unmapped`, and the feedback names SC-002.
3. **Given** a branch where a commit message, the PR body and a PR label all say "covers SC-002", but no test links SC-002,
   **When** the gate runs, **Then** SC-002 is still `unmapped`.
4. **Given** a test linked to SC-001 that exists on the base branch and still passes, **When** the gate runs, **Then** it
   counts for SC-001. A test does not have to be new.
5. **Given** a linked test that fails or errors in the gate's run, **When** the gate runs, **Then** that SC is `fail` and
   the result shows the test ID and its outcome.
6. **Given** a spec where SC-001 was tagged manual before the run and SC-002 has a passing linked test, **When** the gate
   runs, **Then** SC-001 is `manual`, SC-002 is `pass`, the verdict is `pass`, and the result lists SC-001 for the human
   checkpoint to confirm.
7. **Given** a build that adds a manual tag to SC-002 on its branch, **When** the gate runs, **Then** it judges SC-002 as
   it was at the run-start commit, and the verdict is `fail` with `spec_changed` naming the added tag.
8. **Given** a build that deletes SC-003 from the spec on its branch, **When** the gate runs, **Then** it still judges
   SC-003, and the verdict is `fail` with `spec_changed` naming the removed SC.
9. **Given** a spec where every SC was tagged manual before the run, **When** the gate runs, **Then** the verdict is
   `fail` ("no automatically checked criteria").

---

### User Story 2 - A build cannot pass by weakening the tests (Priority: P1)

The building agent hits a failing test and deletes it, marks it skipped, removes assertions from it, or deletes code paths
so coverage falls. Each of these fails the gate, even if every SC is linked to a passing test.

**Why this priority**: Without this, traceability is easy to game. An agent under a retry budget is the classic source of
"make the check green" edits. It is P1 next to Story 1 because either alone is weak.

**Independent Test**: A fixture repo, and one branch per violation (a test removed, a test newly skipped, assertions
removed, one changed file's coverage down 1.0 points, another down 0.9 points). Each branch fails and names its violation,
except the 0.9-point branch, which passes.

**Acceptance Scenarios**:

1. **Given** a test ID that exists and runs at the merge base, **When** the branch deletes or renames it and no valid waiver
   covers it, **Then** the verdict is `fail`, and `removed_tests` lists the ID.
2. **Given** a test that runs at the merge base, **When** the branch makes it skip, xfail or not get collected, **Then** it
   is reported the same as a removal.
3. **Given** the merge base suite has N assertions, **When** the branch's suite has fewer than N, **Then** the verdict is
   `fail`, and `assertion_drop` reports both counts.
4. **Given** a file changed by the branch, **When** its line coverage at the branch head is at least 1.0 percentage point
   lower than at the merge base, **Then** the verdict is `fail`, and `coverage_drops` lists the file with both values.
5. **Given** a drop smaller than 1.0 point, or a drop in a file the branch did not change, **When** the gate runs,
   **Then** it is not a violation.
6. **Given** a branch that adds new tests and assertions, **When** the gate runs, **Then** the higher counts are fine. Only
   decreases are checked.

---

### User Story 3 - A removal can be excused, but only by an approved, expiring waiver (Priority: P2)

Sometimes a test is removed on purpose, for example when the feature it covered is retired. A code owner of the target repo
adds an entry to the repo's test-waiver file on the base branch: the test ID, a reason, and an expiry date. Until it
expires, the gate excuses that removal and lists the waiver in the result.

**Why this priority**: Without an escape hatch the rule blocks legitimate work, and people will route around the gate. It
is P2 because Stories 1 and 2 work without it; the gate is just stricter.

**Independent Test**: Three fixture branches removing the same test. One has a waiver on the merge base with an expiry in
the future: it passes, and `waivers_used` lists the waiver. One has an expired waiver: it fails. One adds the waiver in its
own commits: it fails, because the waiver is not on the base.

**Acceptance Scenarios**:

1. **Given** a waiver for test T on the merge base, with a reason and an expiry after the gate's run date, **When** the
   branch removes T, **Then** the removal is excused and listed in `waivers_used`.
2. **Given** the waiver has expired, **When** the branch removes T, **Then** the removal fails the gate, and the feedback
   says the waiver expired and on which date.
3. **Given** a waiver for T that exists only on the branch (added by the build), **When** the gate runs, **Then** it is
   ignored and reported as `waiver_not_on_base`. The removal fails.
4. **Given** a waiver entry with no reason or no expiry, **When** the gate runs, **Then** the entry is invalid and excuses
   nothing.
5. **Given** the target repo has no code-owner rule covering the waiver file at the merge base, **When** the gate runs,
   **Then** no waiver in it is honored, and the result says why.

---

### User Story 4 - One result file feeds the agent and the humans (Priority: P2)

Every gate run produces one versioned result document. On a fail, its feedback goes into the next build attempt as the
agent's instructions. A human approving later sees the same document: which SCs passed, which tests prove them, and what
integrity findings came up.

**Why this priority**: The result document is the handover between the gate, the agent and the human checkpoints. Later
features (run ledger, metrics, lessons) read it. It is P2 because Stories 1 and 2 can be shown with a plain pass/fail.

**Independent Test**: Run the gate on the Story 1 and Story 2 fixtures. Every result validates against the v1 schema. On
each fail, the next build attempt's input contains the result's feedback, unchanged.

**Acceptance Scenarios**:

1. **Given** any gate run, pass or fail, **When** it completes, **Then** it produces one result document that validates
   against schema version 1.
2. **Given** a failing result, **When** the workflow starts the next build attempt, **Then** that attempt receives the
   result's feedback, which names every failing SC and every integrity finding.
3. **Given** a passing result, **When** the run continues to Register (today) or to a human checkpoint (specs/005,
   specs/008), **Then** the result is part of what that step records or shows.
4. **Given** the gate could not run the suite at all (the merge base is missing, dependencies fail to install, the run
   times out), **When** it completes, **Then** the verdict is `error`, not `fail`, with the reason. The run treats it as a
   failed attempt with that reason as feedback.

### Edge Cases

- **The branch has more than one spec directory, or none.** The gate uses the spec directory or directories the branch
  adds or changes relative to the merge base. A branch that adds or changes no spec gets verdict `error`
  ("no spec for this branch"). It never falls back to the first spec in sort order. If the branch changes more than one
  spec, every SC in each of them must be covered.
- **SC IDs repeat across specs.** Every spec numbers from SC-001, so a link always names the feature (for example
  `015/SC-002`). A bare `SC-002` is ambiguous and does not count.
- **A test links an SC that does not exist in the spec.** It is reported as `unknown_sc` and does not fail the gate.
- **A linked test is flaky.** In v1 the gate does not rerun tests. A failing linked test fails its SC. The result shows the
  test ID so a human can spot flakiness.
- **The merge base itself has failing or skipped tests.** Only changes are judged. A test already skipped at the merge
  base is not a new skip, and a test failing at the merge base is reported but not counted as a removal.
- **A test is renamed.** A rename shows up as one removal and one addition. It needs a waiver, or the old ID kept, like
  any other removal. This is deliberate. The gate does not guess at renames.
- **A file is deleted.** A deleted file has no coverage at the head and is not a coverage drop. Tests it contained count
  as removals.
- **A changed file has no coverage data at the merge base** (a new file). There is nothing to compare with, so it is not
  a drop.
- **An SC that cannot be tested automatically** (for example "an operator can read the status in under a minute").
  The spec author marks such an SC as manual in the spec, before the pipeline run starts. The gate reports it as
  `manual` and does not fail on it, and the human checkpoint must confirm it (FR-026). A manual tag added during the run
  does not count (FR-027).
- **An agent edits the criteria during the run** (adds a manual tag, deletes or rewords an SC). The gate judges the
  criteria as they were when the run started and fails with `spec_changed` (FR-027).
- **A human changes the criteria during the run** (for example while reviewing the plan). This also fails with
  `spec_changed`. To change the criteria, the human starts a new run.
- **Every SC is manual.** Nothing is checked automatically, so the gate fails ("no automatically checked criteria").
- **A manual SC also has linked tests.** The gate lists them and their outcomes, but the verdict stays `manual`.

## Requirements *(mandatory)*

### Functional Requirements

**Inputs and isolation**

- **FR-001**: The gate MUST compare the branch head with the merge base of the branch and the target repo's base branch.
  It MUST fetch enough history to compute that merge base, and MUST report `error` if it cannot.
- **FR-002**: The gate MUST run the target repo's test suite itself, at both the branch head and the merge base, in a
  fresh isolated sandbox that the building agent never had access to. It MUST NOT trust test results, coverage numbers or
  exit codes reported by the build.
- **FR-003**: The gate MUST NOT read commit messages, commit trailers, the PR title or body, PR labels or PR comments to
  decide any verdict. Changing any of them MUST NOT change the result.
- **FR-004**: The gate MUST be deterministic: no model calls. The same pair of commits and the same gate date MUST give
  the same verdict, apart from tests that are themselves nondeterministic.

**Which spec**

- **FR-005**: The gate MUST judge the spec directory or directories that the branch adds or changes under `specs/`
  relative to the merge base. If there is none, the verdict MUST be `error`. The gate MUST NOT fall back to any other spec.
- **FR-006**: The gate MUST parse SC IDs the same way the existing parser does: `- **SC-NNN**:` bullets under
  `### Measurable Outcomes`. It MUST read them, and their manual tags, from the run-start commit (FR-027), not from the
  head. A spec with no SCs MUST give verdict `fail` ("spec has no success criteria").

**SC → test traceability**

- **FR-007**: A test MUST declare which SCs it proves in the test source itself, naming the feature number and the SC ID
  (for example `015/SC-002`). The gate MUST read these links from the tests collected at the branch head.
- **FR-008**: An SC MUST be `pass` only if at least one linked test was collected and passed at the branch head. A linked
  test may be new or may already exist on the base branch.
- **FR-009**: An SC with no linked test MUST be `unmapped`. An SC whose linked tests all failed, errored or were skipped
  MUST be `fail`, with each linked test ID and its outcome.
- **FR-010**: A link to an SC ID that is not in the judged spec MUST be reported as `unknown_sc`. It MUST NOT count as
  coverage for any SC.

**Test integrity**

- **FR-011**: Every test ID collected and run at the merge base that is not collected and run at the branch head (deleted,
  renamed, newly skipped, newly marked expected-to-fail, or no longer collected) MUST be listed in `removed_tests`. Each
  one MUST fail the gate unless a valid waiver excuses it (FR-014).
- **FR-012**: If the total assertion count of the test suite at the branch head is lower than at the merge base, the gate
  MUST fail and report both counts in `assertion_drop`. An increase MUST NOT be reported.
- **FR-013**: For each source file the branch changes that has line coverage data at both commits, the gate MUST fail if
  head coverage is at least 1.0 percentage point below merge-base coverage. Each such file MUST be listed in
  `coverage_drops` with both values. Files the branch did not change MUST NOT be judged.

**Waivers**

- **FR-014**: A removal MUST be excused only by an entry in the target repo's test-waiver file as it exists at the merge
  base. The entry must name the test ID, a non-empty reason and an expiry date on or after the gate's run date (UTC).
- **FR-015**: Waiver entries that exist only on the branch MUST be ignored and reported as `waiver_not_on_base`. Expired or
  incomplete entries MUST excuse nothing and MUST be reported with the reason.
- **FR-016**: The gate MUST honor waivers only if, at the merge base, the target repo's code-owner rules assign the waiver
  file to at least one owner. Otherwise it MUST honor none and say why.
- **FR-017**: Every waiver that excused a removal MUST be listed in `waivers_used`, with the test ID, reason and expiry.

**Result and feedback**

- **FR-018**: Every gate run MUST produce one result document with `schema_version: 1`. It contains:
  - the judged spec path or paths
  - the head and merge-base commit IDs
  - the run-start commit ID (FR-027)
  - one entry per SC with verdict `pass`, `fail`, `unmapped` or `manual`, and its linked test IDs and outcomes
  - `removed_tests`, `assertion_drop`, `coverage_drops`, `waivers_used`, `unknown_sc`, `spec_changed` and the waiver
    problems
  - an overall verdict: `pass`, `fail` or `error`
  - a `feedback` string
- **FR-019**: The overall verdict MUST be `pass` only if every SC is `pass` or `manual`, at least one SC is `pass`, and
  there is no unexcused integrity finding and no `spec_changed`. If every SC is `manual`, the verdict MUST be `fail`
  ("no automatically checked criteria").
  It MUST be `error` when the gate could not produce a judgment (FR-001, FR-005, a suite that cannot run, a timeout).
- **FR-020**: On `fail` or `error`, `feedback` MUST name every failing SC, every integrity finding and every `spec_changed`
  difference, with test IDs, file paths and numbers. It MUST be plain text the building agent can act on without reading the rest of the result.
- **FR-021**: On `fail` or `error`, the workflow MUST pass `feedback` unchanged into the next build attempt. It MUST count
  that attempt against the existing `MAX_BUILD_ATTEMPTS` budget. This feature adds no new budget.
- **FR-022**: The result document MUST be the value the workflow keeps for the run. It is what `register_activity` records
  today, and what the human checkpoints of specs/005 and the status view of specs/008 show once those land.
- **FR-023**: The gate MUST apply the same rules in `full` and `vibe` mode (specs/005). No mode relaxes it.

**Compatibility**

- **FR-024**: The gate replaces `run_eval`'s binary check. The existing SC parsers stay compatible, because the architect
  stage (`harness/architect-agent/`) keys its coverage map on the same SC IDs.
- **FR-025**: `specs/006-quality-gate` FR-001..FR-003 are superseded by this feature. 006 MUST be updated to say so, and
  keeps only its docstring, docs-touch and coverage-threshold checks.

**Manual criteria and spec freeze**

- **FR-026**: The spec author MAY tag an SC as manual, inside that SC's own bullet text, so the existing parsers still
  read the bullet. The gate MUST give a manual SC the verdict `manual`, list any linked tests with their outcomes, and
  MUST NOT fail on it. The result MUST list every manual SC so the human checkpoint can confirm each one. It is shown
  there (specs/005) and in the status view (specs/008) once those land.
- **FR-027**: A manual tag MUST be set before the run starts. The workflow MUST record the branch head when the run
  starts, before the architect stage and before any build (the run-start commit). The gate MUST read the SCs and their
  manual tags from that commit. If the `## Success Criteria` section of the judged spec differs between the run-start
  commit and the head, the gate MUST fail with `spec_changed`, naming each added, removed or changed SC and each added or
  removed manual tag. No waiver excuses `spec_changed`.

### Key Entities

- **Gate result (v1)**: One document per gate run. It holds the verdicts per SC, the integrity findings, the overall
  verdict and the feedback. It is the handover from the gate to the agent (feedback) and to the humans (evidence).
- **Run-start commit**: The branch head recorded when the pipeline run starts, before the architect stage and the build.
  The SCs and manual tags are read from it.
- **Manual SC**: An SC the spec author tagged as manual before the run. It needs a human's confirmation, not a test.
- **SC link**: A declaration inside a test that it proves `<feature>/SC-NNN`. A test can link several SCs, and an SC can
  have several tests.
- **Test inventory**: The set of test IDs collected and run at one commit, with each test's outcome and its assertion
  count. The gate takes one at the merge base and one at the head, and compares them.
- **Coverage snapshot**: The line coverage of each source file at one commit. The gate takes one at each commit and
  compares only the files the branch changed.
- **Waiver**: An entry in the target repo's test-waiver file: test ID, reason, expiry date. It is valid only as read from
  the merge base, and only if a code owner owns the file.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the traceability fixtures (Story 1), the gate gives the expected verdict on all branches in 3 runs out of
  3. Each unmapped or failing SC is named in the feedback.
- **SC-002**: On the integrity fixtures (Story 2), each of the 5 violation branches fails and names its violation, and the
  0.9-point coverage branch passes. That is 6 of 6 correct verdicts.
- **SC-003**: Changing only commit messages, trailers, PR title, PR body and labels on any fixture branch changes no
  verdict and no finding. 0 differences across all fixtures.
- **SC-004**: On the waiver fixtures (Story 3), the valid waiver excuses its removal, and the expired, branch-only and
  incomplete waivers each fail with their stated reason. 4 of 4 correct.
- **SC-005**: 100% of gate results, pass, fail or error, validate against the v1 schema.
- **SC-006**: In a pipeline run whose first build fails the gate, the second build attempt's input contains the first
  result's feedback unchanged. Checked in 1 end-to-end run against a disposable repo.
- **SC-007**: A build that deletes every test and still opens a PR (it passes today's gate) fails the new gate.
- **SC-008**: For a target suite that takes up to 3 minutes to run once, the gate finishes within 10 minutes, merge-base
  and head runs included.
- **SC-009**: On the manual-criteria fixtures (Story 1, scenarios 6-9), a spec with one manual SC (tagged before the
  run) and one tested SC passes and lists the manual SC. A build that adds a manual tag, a build that deletes an SC and
  an all-manual spec each fail with their stated reason. 4 of 4 correct.

## Assumptions

- **Target repos in v1 are Python repos with a pytest suite**, like every target repo used so far. Other languages are
  out of scope until a target needs them.
- **The test-waiver file and the SC-link convention are defined in the plan** (`/speckit-plan`), including the file path
  and the exact marker syntax, and the syntax of the manual tag inside an SC bullet. The spec fixes only what they must
  contain.
- **Assertion count** means assertions counted in the test source by a fixed, documented rule. It does not mean assertions
  executed at runtime. The plan picks the rule.
- **The gate's own sandbox** uses the existing E2B template family, with a template that has no repo write token. The
  gate only reads. This keeps the gate out of the building agent's reach (the Rule of Two idea in the blueprint).
- **The gate date** for waiver expiry is the UTC date when the gate activity starts.
- **Timing**: today's `eval_gate_activity` has a 5-minute timeout. That is too short for two suite runs and will be raised
  in the plan, within SC-008.
- **Out of scope**: scoring whether a test really proves its SC (a human sees the linked tests at the checkpoints); flaky
  test detection and reruns; the run ledger, cost and outcome metrics (a later spec); the GitHub-comment trigger path
  (`@swe-agent build`), which still has no gate (a later spec); 006's docstring, docs-touch and coverage-threshold checks.

## Dependencies

- **specs/005-pipeline-mode-signals-escalation** (Draft): FR-023 relies on its rule that Eval-Gate is never
  mode-conditional. This feature does not need 005 to ship first.
- **specs/008-gate-decision-core** (Draft): its status view is where humans will see the result (FR-022). Not required to
  ship first.
- **specs/006-quality-gate** (Draft): amended by FR-025.
- **specs/013-sandbox-app-token**: the gate's sandbox must not receive the build's write token.
