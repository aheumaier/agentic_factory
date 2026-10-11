# Feature Specification: Dev-Harness Follow-ups

**Feature Branch**: `worktree-012-dev-harness-followups`

**Created**: 2026-10-11

**Status**: Draft

**Input**: User description: "Dev-harness follow-ups to feature 010 (dev-harness hardening). Sources, all on disk: specs/010-dev-harness-hardening/tasks.md T042 "Before merge" items 6-7 and "Deferred follow-ups" (16 items), T023 extractor resolutions, line 369 (AF-SECRET fix and the open AF-SPEC gap), T045 operator-pending list. Scope: (1) AF-COMMIT vs swe-agent's IMPLEMENT_PROMPT "commit even if verification doesn't pass" inside the E2B sandbox - decide known gap vs env-marker exemption; (2) amend contracts/hook-interface.md "Matching rules" to match what policy.sh ships for AF-SECRET (case-folding, SECRET_RE on Grep glob / Glob pattern, any directory); (3) close the AF-SPEC `..`/case path gap (<root>/docs/../harness/a.py, <root>/Harness/a.py); (4) amend contracts/drift-conventions.md with the three T023 extractor resolutions (split on whitespace and comma, repo-path class by existing top-level dir, sentence split on dot+any whitespace) and decide whether lowercase non-private names stay unchecked; (5) the 16 deferred follow-ups (…); (6) NEW observed 2026-10-11: after a session launched with `claude --worktree` removes its launch worktree (ExitWorktree remove) and enters a new one (EnterWorktree), hook commands use "$CLAUDE_PROJECT_DIR"/.claude/hooks/... and a Write under harness/ on a branch without specs/NNN-*/tasks.md was NOT denied - the repo policy failed open for the rest of the session (cause not verified; likely CLAUDE_PROJECT_DIR still names the deleted launch dir, and a missing hook script is a non-blocking error). Out of scope: T045 live-session checks are an operator checklist, not agent work; the stale 7d005ba commit message is won't-fix (operator decision 2026-10-11, main is protected)."

## Context

Feature 010 (merged 2026-10-11 as `3f63147`) gave this repo's Claude Code harness a
turn-scoped quality gate, five repo rules (AF-SPEC, AF-SECRET, AF-COMMIT,
AF-REGISTRY, AF-HARNESS), a context-drift test and a context budget. Its review left
work that the operator chose not to do inside 010:

- two operator decisions (T042 "Before merge" items 6 and 7);
- one known AF-SPEC path gap (T036 finding 1);
- three extractor rulings the drift contract does not state yet (T023, T024);
- 16 deferred follow-ups (T042 "Deferred follow-ups");
- one new failure seen on 2026-10-11, after 010 merged: the repo policy stopped
  running for the rest of a session once that session removed its launch worktree and
  entered a new one. A Write under `harness/` on a branch without a spec was not
  denied. The cause is not verified.

This feature closes those items. The source text for each item is in
`specs/010-dev-harness-hardening/tasks.md` (T023, T024, T036, T042) and in the two
010 contracts, `contracts/hook-interface.md` and `contracts/drift-conventions.md`.

## User Scenarios & Testing *(mandatory)*

Actors: the **operator** (the human running agent sessions on this repo), the
**agent** (a Claude Code session, including its subagents) and a **reviewer** (human
or reviewer subagent) reading a change or a contract.

### User Story 1 - The repo policy never fails open without a trace (Priority: P1)

The operator relies on the five repo rules to hold for the whole session. Today some
paths let an action through with no check and no notice: the session's launch
worktree is gone, the commit gate runs past its time limit, the hook gets empty
input, or the agent creates a commit with a git command other than `git commit`.
After this story, each of those paths either applies the rule or fails closed with a
message that names the rule and the way out.

**Why this priority**: A rule that silently stops applying is worse than no rule. The
operator believes it holds and stops watching. The 2026-10-11 incident showed this
happens in normal use of worktrees, which CLAUDE.md recommends.

**Independent Test**: Start a session in a worktree, remove that worktree, enter a
new worktree on a branch with no spec and try to write a file under `harness/`. The
write is denied, or the operator sees a notice that the policy cannot run. Separately,
make the commit gate's test run exceed its time limit and try to commit: the commit
is denied.

**Acceptance Scenarios**:

1. **Given** a session whose launch worktree was removed and which then entered a new
   worktree, **When** the agent writes a file under `harness/` on a branch without
   `specs/NNN-*/tasks.md`, **Then** the write is denied with `[AF-SPEC]`, or every
   tool call is refused with a message that says the harness cannot find its hooks
   and how to recover.
2. **Given** a commit attempt whose lint and test run would take longer than the
   commit gate's own time limit, **When** the limit is reached, **Then** the commit
   is denied with `[AF-COMMIT]` and a message that says the gate timed out.
3. **Given** a tool call whose hook input is empty or not readable, **When** the
   policy runs, **Then** the call is denied, not allowed.
4. **Given** a red working tree, **When** the agent runs `git revert`, `git
   cherry-pick`, `git merge`, `git am` or `git rebase` in a form that creates a
   commit, **Then** the command is denied with `[AF-COMMIT]`, just as `git commit`
   is.
5. **Given** a red working tree in the middle of a rebase, cherry-pick, merge or am,
   **When** the agent aborts it (`--abort`, `--quit`), **Then** the command is
   allowed.

---

### User Story 2 - Each rule does what its contract says (Priority: P2)

A reviewer reads `contracts/hook-interface.md` to know what a rule blocks. Today the
code blocks more than the contract says for AF-SECRET, and less than the operator
expects for AF-SPEC and the shell secret check. After this story, contract, code and
tests agree, and the remaining sandbox question is decided and written down.

**Why this priority**: The contract is how a reviewer judges a change to the hooks.
When code and contract disagree, the next change can "fix" the code back to the
contract and reopen a hole that 010 closed.

**Independent Test**: For each rule, take the table of path spellings in this spec
(FR-008, FR-009) and run them through the policy. Each spelling gets the same verdict
as its plain form. Then read the AF-SECRET part of the contract next to the tests:
every case the tests pin is stated in the contract.

**Acceptance Scenarios**:

1. **Given** a branch without a spec, **When** the agent edits
   `<root>/docs/../harness/a.py` or `<root>/Harness/a.py` on a case-insensitive
   volume, **Then** the edit is denied with `[AF-SPEC]`, the same as
   `<root>/harness/a.py`.
2. **Given** a shell command that names `.ENV`, `` `.env` ``, `@.env`, `{.env}` or
   `a,.env`, **When** the policy runs, **Then** it is denied with `[AF-SECRET]`, and
   `.env.example` in any of those spellings is still allowed.
3. **Given** a shell command that writes `.env` (for example `cp .env.example .env`),
   **When** it is denied, **Then** the message talks about writing or naming the file
   from the shell, not about reading it.
4. **Given** the amended contract, **When** a reviewer compares its AF-SECRET rules
   with the tests, **Then** case-folding, the glob-field checks and "any directory"
   are all stated.
5. **Given** a `swe-agent` run inside the E2B sandbox against this repo, **When** the
   agent commits with failing local checks as its prompt allows, **Then** the outcome
   matches the decision recorded under FR-011.

---

### User Story 3 - The turn gate recovers from stuck states (Priority: P2)

The end-of-turn gate and the turn snapshot sometimes leave the operator in a loop or
with a wrong baseline: a missing `uv` blocks every retry, a twice-red turn throws
away its snapshot, a rebase conflict blocks all edits under `harness/`, a broken
shared library denies every tool call with no way out, and old state files pile up.
After this story, each of these states either clears itself or tells the operator
the one step that clears it.

**Why this priority**: These states are rare but costly. Each one stalls a session
until the operator debugs the harness by hand.

**Independent Test**: Make a turn red twice in a row and end it. The next turn's
baseline is the state from before the red turn, so the red files still count as this
turn's change at its end. Separately, start a rebase that stops on a conflict in a
file under `harness/` and edit that file: the edit is allowed when the branch being
rebased has a spec.

**Acceptance Scenarios**:

1. **Given** no `uv` on the path and a turn that changed Python files, **When** the
   turn ends, **Then** Stop blocks once, and the retry ends the turn with a notice,
   the same as any other red gate.
2. **Given** a turn whose end-of-turn gate is red twice, **When** the next turn
   starts, **Then** the snapshot from before the red turn is still the baseline.
3. **Given** a rebase of branch `NNN-slug` stopped on a conflict, **When** the agent
   edits the conflicted file under `harness/`, **Then** AF-SPEC judges the edit
   against `NNN-slug` and its spec, not against the detached HEAD.
4. **Given** the shared hook library cannot be loaded, **When** any tool call runs,
   **Then** it is denied, and the message names the library and the manual recovery
   step.
5. **Given** state files from earlier sessions (`ctx-*.level`,
   `exception-*.notified`), **When** a new turn starts, **Then** files older than the
   existing retention window for turn snapshots are removed.
6. **Given** a session that was just compacted, **When** the next turn starts,
   **Then** the context warning is based on usage recorded after the compaction, or
   no warning is shown.

---

### User Story 4 - The drift check is precise and runs sooner (Priority: P3)

The drift test compares CLAUDE.md and the reviewer prompt against the code. Three of
its rules were settled during 010 but are not in its contract. It also reads files
that are not part of the repo, it runs only on Python changes, and nothing checks the
hook scripts with a shell linter or checks that every live-Temporal test is marked.
After this story, the contract states every rule the extractor applies, and these
checks run at the end of every turn that could break them.

**Why this priority**: The drift test already works. These items make its results
more exact and earlier. They don't fix a hole.

**Independent Test**: Put a stale identifier in CLAUDE.md with a docs-only edit and
end the turn: Stop reports it. Put an untracked file that names a made-up private
identifier in the repo: the drift test is not affected by it.

**Acceptance Scenarios**:

1. **Given** a docs-only turn that adds a stale fact to CLAUDE.md, **When** the turn
   ends, **Then** Stop reports the drift failure, without waiting for the next commit.
2. **Given** an untracked or git-ignored file under the repo, **When** the drift test
   builds its corpus, **Then** that file is not part of it.
3. **Given** a test that reaches the live-Temporal connection helper without the
   `temporal` mark, **When** the repo test suite runs, **Then** a test fails and names
   that test.
4. **Given** a change to a hook script, **When** the gate runs, **Then** a shell
   linter runs on it, with the known false positives silenced at the line where they
   occur.
5. **Given** the amended drift contract, **When** a reviewer compares it with the
   extractor, **Then** token splitting, the repo-path class, the `NNN` placeholder and
   the sentence split are all stated.

---

### Edge Cases

- **Launch worktree removed, cause unknown (US1)**: the 2026-10-11 cause is a guess.
  The plan must first reproduce it and record the cause in research. If the hooks
  cannot be made to follow the session's current worktree, the fallback is that the
  harness detects the lost hooks and says so (FR-001), and CLAUDE.md tells the
  operator to start a new session instead of removing the launch worktree.
- **`git rebase --continue` on a red tree (US1)**: it creates a commit, so AF-COMMIT
  judges it. The working tree at that moment is the replayed commit plus the
  resolved conflict, which is what will be committed.
- **`git merge --ff-only` and `git pull` (US1)**: they may create no commit. Judging
  them anyway is an accepted false positive, in line with the contract's rule that
  false positives are accepted and false negatives are not. `git pull` is not added
  unless the plan shows it can create a merge commit in this repo's setup.
- **Rebase with no spec on the branch being rebased (US3)**: AF-SPEC denies, as it
  would on that branch outside a rebase.
- **Rebase of a branch whose spec dir appears only in a later commit (US3)**: the
  spec is looked up on the tip of the branch being rebased, not on the replay point.
- **Path spellings outside the repo (US2)**: a path that resolves outside the repo is
  not under `harness/`, `orchestration/` or `eval/` and is not judged by AF-SPEC.
  AF-SECRET keeps judging `.env` in any directory.
- **Symlinks (US2)**: a path is judged by its spelling after `..` and case are
  resolved. Following symlinks is out of scope.
- **Shell linter not installed (US4)**: the shell lint check says so visibly. It does
  not pass silently, and it does not block a machine that has no linter.
- **Inner gate time limit vs. hook time limit (US1)**: the inner limit must leave
  enough room inside the hook limit to print the deny. The plan sets both numbers.

## Requirements *(mandatory)*

### Functional Requirements

**Fail-closed policy (US1)**

- **FR-001**: Once a session can no longer run the repo's hook scripts (for example
  because its launch worktree was removed), the harness MUST either keep applying the
  rules from the session's current worktree, or deny each covered tool call with a
  message that names the problem and the recovery step. It MUST NOT silently allow.
  The plan MUST first reproduce the 2026-10-11 failure and record its cause.
- **FR-002**: Repo-relative paths in all hooks MUST resolve against the session's
  current worktree after a mid-session worktree change, or FR-001's fallback applies.
- **FR-003**: The commit gate MUST deny the commit when its lint and test run exceeds
  an inner time limit set below the hook's own time limit. The deny message MUST say
  that the gate timed out.
- **FR-004**: The policy hook MUST deny when its input is empty, unreadable or not
  valid JSON.
- **FR-005**: AF-COMMIT MUST also gate `git revert`, `git cherry-pick`, `git merge`,
  `git am` and `git rebase` (including `--continue`), in the forms that can create a
  commit. `--abort`, `--quit` and `--skip` MUST NOT be gated.

**Rules match their contracts (US2)**

- **FR-006**: `contracts/hook-interface.md` "Matching rules" for AF-SECRET MUST state
  what the code does today: the basename is lower-cased before the check; the check
  applies in any directory; Grep's `glob` and Glob's `pattern` are also denied when
  their basename matches the secret-file pattern (`.env*`, `.env{,.braintrust}`).
  This is the ruling T042 item 7 asks for. The amendment is recorded in 012's own
  contracts, and 010's contract carries a pointer to it.
- **FR-007**: The AF-SECRET message for a shell command MUST use wording about naming
  or writing the file from the shell. The wording for Read, Grep and Glob stays.
- **FR-008**: AF-SPEC MUST judge a path after resolving `.` and `..` segments and
  after case-folding the top-level directory name. These MUST get the same verdict as
  `<root>/harness/a.py`: `<root>/docs/../harness/a.py`, `<root>/./harness/a.py` and
  `<root>/Harness/a.py`.
- **FR-009**: The shell secret check MUST fold case and MUST treat `` ` ``, `@`, `{`
  and `,` as delimiters before `.env`, in addition to the current ones.
  `.env.example` MUST keep passing in every spelling.
- **FR-010**: Every behaviour added by FR-003 to FR-009 MUST be stated in the 012
  contracts and pinned by at least one test that fails on the old behaviour.
- **FR-011**: A `swe-agent` run inside the E2B sandbox against this repo runs under
  a prompt that asks it to commit even when local checks fail. AF-COMMIT denies that
  commit today. The harness MUST [NEEDS CLARIFICATION: keep denying it and record
  this in CLAUDE.md as a known gap (the run then ends with no commit for that
  attempt), or exempt sandbox runs from AF-COMMIT through an environment marker set
  only by the sandbox launcher (the commit then lands red and the Eval-Gate judges
  it)?]. This is the decision T042 item 6 asks for.

**Gate recovery (US3)**

- **FR-012**: A missing `uv` MUST NOT block Stop more than once per turn. The check
  for `uv` MUST come after the loop guard that ends a turn on its second red Stop.
- **FR-013**: A turn whose gate is red twice MUST keep its turn-start snapshot, so the
  next turn starts from the same baseline. The contract's Stop step 5 MUST be updated
  to match.
- **FR-014**: During an in-progress rebase, AF-SPEC MUST take the branch name from
  the branch being rebased and accept a `specs/NNN-*/tasks.md` that exists on that
  branch's tip.
- **FR-015**: When the shared hook library cannot be loaded, the policy hook MUST
  keep denying, and the deny message MUST name the library and the manual recovery
  step. CLAUDE.md MUST describe that recovery.
- **FR-016**: Turn start MUST prune `ctx-*.level` and `exception-*.notified` with the
  same retention rule it already uses for turn snapshots.
- **FR-017**: The context warning MUST NOT be based on a usage value recorded before
  the session's latest compaction. If no usage value since then exists, no warning
  is shown. The plan MUST first confirm whether the stale read happens.

**Drift and lint checks (US4)**

- **FR-018**: `contracts/drift-conventions.md` MUST state the extractor's rules as
  shipped:
  - tokens are split on whitespace and `,`;
  - a token with `/` is a repo path when its first segment is an existing top-level
    directory, and otherwise each `/` part is classified on its own;
  - `NNN` is a placeholder in the path class, as in D-SPEC;
  - D-REG splits sentences on a dot followed by any whitespace (newline included) and
    on blank lines.
- **FR-019**: Lowercase names that are not private (for example `shape_issue`,
  `execute_activity`, `retry_policy`) MUST [NEEDS CLARIFICATION: stay unchecked, as
  the drift contract says today (a rename goes unnoticed, but no new false
  positives), or be checked when they appear in code formatting in the reviewer
  prompt (renames are caught; common words in code formatting may need an
  allow-list)?].
- **FR-020**: The D-ID corpus MUST contain only tracked files and untracked files that
  git does not ignore.
- **FR-021**: The end-of-turn gate MUST run the drift test when the turn changed any
  file in the drift test's scope, not only when it changed Python files.
- **FR-022**: The repo test suite MUST fail, naming the test, when a test that reaches
  the live-Temporal connection helper does not carry the `temporal` mark. The check
  works per test, because some modules mix pure and live tests.
- **FR-023**: A shell lint check MUST run on the hook scripts in the gate. The known
  false positives (unused-variable reports for variables used by sourcing scripts, and
  unfollowed `source` paths) MUST be silenced at the line where they occur, not
  globally. Where no shell linter is installed, the check MUST say so visibly.

**Housekeeping**

- **FR-024**: CLAUDE.md's harness section MUST reflect every behaviour change above
  that an operator or agent would notice, and the drift test MUST pass on the result.
- **FR-025**: No change MAY modify a lockfile or resolve dependencies over the
  network, as in 010 FR-007.

### Traceability

Every item from the sources maps to a requirement or to an explicit exclusion.

| Source item | Requirement |
|---|---|
| (1) T042 before-merge 6: AF-COMMIT vs. sandbox prompt | FR-011 |
| (2) T042 before-merge 7: AF-SECRET contract ruling | FR-006 |
| (3) T036 finding 1: AF-SPEC `..`/case gap | FR-008 |
| (4) T023/T024: extractor rulings | FR-018, FR-019 |
| (5.1) Gate overrun past the hook time limit | FR-003 |
| (5.2) Missing `uv` blocks every Stop retry | FR-012 |
| (5.3) Second red Stop deletes the snapshot | FR-013 |
| (5.4) AF-SECRET wording for shell writes | FR-007 |
| (5.5) Shell secret check: case and delimiters | FR-009 |
| (5.6) Pruning `ctx-*.level`, `exception-*.notified` | FR-016 |
| (5.7) No shell lint gate | FR-023 |
| (5.8) Unloadable hook library denies everything | FR-015 |
| (5.9) D-ID corpus reads untracked and ignored files | FR-020 |
| (5.10) `temporal` mark check | FR-022 |
| (5.11) AF-SPEC during a rebase conflict | FR-014 |
| (5.12) Docs-only edits skip the drift test at Stop | FR-021 |
| (5.13) Repo root after a mid-session worktree change | FR-002 |
| (5.14) AF-COMMIT misses other commit-making commands | FR-005 |
| (5.15) Policy allows on empty input | FR-004 |
| (5.16) Stale context warning after compaction | FR-017 |
| (6) Policy failed open after the launch worktree was removed | FR-001, FR-002 |
| T045 operator-pending live checks | Out of scope (operator checklist) |
| `7d005ba` commit message | Out of scope (won't fix, operator decision 2026-10-11) |

### Key Entities

- **Repo rule**: one of AF-SPEC, AF-SECRET, AF-COMMIT, AF-REGISTRY, AF-HARNESS. It has
  an ID, a set of covered actions, a verdict (allow, deny, ask) and a message that
  starts with the ID and names the way out.
- **Hook contract**: the normative text in the 010 and 012 contracts that says what
  each rule covers. Code and tests must agree with it.
- **Turn snapshot**: the per-session record of Python-relevant files taken at turn
  start. It is the baseline the end-of-turn gate compares against.
- **Hook state files**: the per-session files the hooks keep between calls (turn
  snapshots, context-warning levels, exception notices). They are pruned by age.
- **Drift corpus**: the set of files the drift test searches for identifiers named in
  CLAUDE.md and the reviewer prompt.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a reproduction of the 2026-10-11 scenario (launch worktree removed,
  new worktree entered), 0 covered tool calls are allowed without a rule being
  applied. Each is either judged by its rule or refused with a "hooks not found"
  message. Measured in a live session; the plan says which part automated tests can
  cover.
- **SC-002**: In automated tests, 100% of commit attempts whose gate exceeds the
  inner time limit are denied, and 100% of policy calls with empty or invalid input
  are denied.
- **SC-003**: In automated tests, each of the five commit-making git commands from
  FR-005 is denied on a red tree, and each abort form is allowed.
- **SC-004**: In automated tests, every path and command spelling listed in FR-008
  and FR-009 gets the same verdict as its plain form, and `.env.example` passes in
  every spelling.
- **SC-005**: For AF-SECRET, AF-SPEC and the drift extractor, a reviewer comparing
  each contract with its tests finds 0 behaviours that are tested but not stated.
- **SC-006**: In automated tests, after a turn that is red twice, the next turn's
  baseline equals the baseline from before that turn, 100% of the time.
- **SC-007**: Each of the 21 in-scope source items in the traceability table is
  closed by a passing test, a contract or CLAUDE.md change, or a recorded operator
  decision. 0 items are left without one.
- **SC-008**: The existing harness tests still pass. A test is changed only where a
  requirement here changes the behaviour it pins, and each such change names the
  requirement.
- **SC-009**: Both lockfiles are byte-identical before and after a full gate run.

## Assumptions

- The work stays inside this repo's harness: `.claude/hooks/**`,
  `.claude/settings.json`, the repo test suites, CLAUDE.md, the reviewer prompt and
  the contracts. User-level settings (`~/.claude`) are out of scope.
- Every edit to `.claude/settings.json` and `.claude/hooks/**` prompts the operator
  (AF-HARNESS). That is expected and is not worked around.
- The 2026-10-11 cause (the hooks still point at the removed launch worktree, and a
  missing hook script counts as a non-blocking error) is a hypothesis. FR-001 asks the
  plan to confirm it before choosing a fix.
- On an unloadable hook library, the harness keeps failing closed and documents the
  recovery (FR-015), instead of allowing edits under `.claude/hooks/**`. Failing
  closed matches every other missing-tool case in 010.
- The retention window for the new pruning (FR-016) is the one already used for turn
  snapshots. No new setting is added.
- A shell linter is installed on the operator's machine (010's review ran one). The
  E2B sandbox image does not get one; there the check reports that it was skipped.
- Feature 010's contracts stay as merged history. 012 amends them through its own
  contracts and adds a pointer in each 010 contract.

## Out of Scope

- The T045 live-session checks (quickstart §2, §3, §6.1-6.5). They are an operator
  checklist that needs fresh sessions, relaunches and `/clear`, not agent work.
- Rewording the `7d005ba` commit message (won't fix; main is protected; operator
  decision 2026-10-11).
- Rebuilding the `swe-agent-sandbox` E2B template, unless FR-011's decision needs a
  change that only a rebuild can ship. Any rebuild needs the operator's approval.
- Following symlinks in AF-SPEC or AF-SECRET path checks.
