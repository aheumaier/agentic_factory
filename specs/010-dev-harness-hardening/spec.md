# Feature Specification: Dev-Harness Hardening

**Feature Branch**: `010-dev-harness-hardening`

**Created**: 2026-10-10

**Status**: Draft

**Input**: User description: "Dev-harness hardening for this repo's own Claude Code harness (.claude/settings.json, .claude/hooks/py-check.sh, .claude/agents/py-codereviewer.md, CLAUDE.md). Problem: the harness's only hard gate (ruff+pytest) is not isolated per session, scoped to the whole dirty tree, misses Bash-made edits, and most repo rules exist only as prose that nothing checks and that has already drifted from the code. Scope: (P1) turn-scoped, session-safe quality gate; (P2) repo policy as deterministic pre-action checks instead of prose; (P3) context drift check that asserts CLAUDE.md and the reviewer prompt against the tree, plus fixing the currently-known stale facts. Out of scope: restructuring/shrinking CLAUDE.md, ratifying the Spec Kit constitution, nested per-directory CLAUDE.md files, user-level ~/.claude settings."

## Context

This feature hardens the **development harness** a coding agent (Claude Code) works
inside when it changes *this* repo. It is neither the foundation-tier agent factory
nor the SDLC-pipeline product (CLAUDE.md "What this repo is"); it is the guardrail
layer around both. It builds on commit `28221cc` (first harness: ruff + pytest
hooks, `py-codereviewer` subagent).

Problems observed on 2026-10-10 that motivate it:

- Two agent sessions shared one checkout. One switched the branch under the other
  mid-turn, and the end-of-turn gate judged the **whole dirty tree** rather than the
  turn's own edits, so one session's unfinished work can block the other.
- The per-edit gate fires only on the dedicated edit tools. Edits made through the
  shell (`sed`, heredocs), which the operator's auto mode encourages, bypass it.
- The per-edit gate runs the full test suites after every single edit, injecting
  mid-refactor failures into the agent's context and steering it toward fixing
  intermediate states.
- Repo rules ("no code without a spec", "never commit red", "the registry is
  written by `register_activity`", "never read secrets") exist only as prose.
- The always-loaded context (CLAUDE.md, the reviewer prompt, `eval/gate-policy.md`)
  already contradicts the code in at least six places, and nothing detects it.
- The operator's guidance caps a session's context at 150k tokens, but nothing in the
  harness knows about it. Without a cap, auto-compaction fires near the model's full
  window, far past the budget. Nothing warns as the budget nears, and after `/compact`
  or `/clear` the agent loses track of which feature and task it was on. `/clear` also
  starts a new session, which orphans the turn snapshot of an interrupted turn
  (research.md R14).

## User Scenarios & Testing *(mandatory)*

Actors: the **operator** (the human running agent sessions on this repo), the
**agent** (a Claude Code session, including its subagents), and a **reviewer**
(human or `py-codereviewer`) reading a change.

### User Story 1 - A turn is judged only on what it changed (Priority: P1)

The operator runs an agent session. At the end of each turn, the harness checks lint
and tests only if the turn itself changed Python-relevant files, no matter which tool
made the change. Files that were already dirty before the turn and that the turn did
not touch don't count against it. While the agent edits, it gets fast, file-local
lint feedback only; the test suites run once, at the end of the turn.

**Why this priority**: The end-of-turn gate is the only hard gate today. If it misses
shell-made edits or blames a session for someone else's work, every other rule built
on top of it is unreliable.

**Independent Test**: Start a turn on a tree that already holds an unrelated failing
`.py` change. Make a change that is lint- and test-clean, and end the turn: the turn
ends unblocked. Then, in a new turn, introduce a lint error with a shell command (not
an edit tool) and end the turn: it is blocked, and the message names the file.

**Acceptance Scenarios**:

1. **Given** a tree with a pre-existing failing Python file the turn never touches,
   **When** the turn edits only a clean file and ends, **Then** the end-of-turn gate
   passes and does not report the pre-existing failure.
2. **Given** a turn that creates or modifies a `.py` file only through a shell
   command, **When** the turn ends with that file failing lint, **Then** the turn is
   blocked and the feedback names that file and the lint finding.
3. **Given** a turn that changes only `pyproject.toml` or a `uv.lock`, **When** the
   turn ends, **Then** the lint and test checks still run, because those files can
   turn the baseline red without any `.py` change.
4. **Given** a turn that changes no Python-relevant file, **When** it ends, **Then**
   no checks run and the turn ends with no added delay.
5. **Given** the agent edits a `.py` file with an edit tool, **When** the edit lands,
   **Then** only lint for that file runs, and the test suites do not run until the end
   of the turn.
6. **Given** the end-of-turn gate already blocked this turn once and is still red,
   **When** the agent tries to end the turn again, **Then** the turn ends, and the
   operator sees a visible "gate still red" notice instead of an endless block.
7. **Given** a test run fails, **When** the feedback reaches the agent, **Then** each
   failure is shown with a short traceback that keeps the failing test's name inside
   the output limit.
8. **Given** any check runs, **When** it resolves the Python environment, **Then** it
   never modifies a lockfile.

---

### User Story 2 - Repo rules are enforced before the action, not after review (Priority: P2)

The rules the repo states in prose are checked by the harness at the moment the agent
tries to break them. Each refusal says which rule applied and exactly how to satisfy
it. The operator has one documented, explicit way to grant an exception.

**Why this priority**: Prose rules are applied inconsistently by a model and
invisibly skipped. Deterministic checks make the most important rules hold without
relying on the agent remembering them, but they depend on Story 1's reliable gate for
the "never commit red" rule.

**Independent Test**: On a branch with no matching spec, ask the agent to edit a file
under `harness/`: the edit is refused with a message naming the spec rule. Ask it to
commit while a test is failing: the commit is refused. Ask it to read `.env`: the read
is refused. Grant the documented exception, and confirm the spec-rule refusal no
longer applies for that session.

**Acceptance Scenarios**:

1. **Given** the current branch does not start with a three-digit feature number, or
   no `specs/NNN-*/tasks.md` with that same number exists, **When** the agent tries to
   create or modify a file under `harness/`, `orchestration/` or `eval/`, **Then** the
   action is refused, and the message names the rule and the Spec Kit steps that
   satisfy it.
2. **Given** the branch is `NNN-<slug>` and `specs/NNN-<any-slug>/tasks.md` exists,
   **When** the agent edits a file under those directories, **Then** the action
   proceeds without prompting.
3. **Given** lint or either test suite is red, **When** the agent runs a `git commit`,
   **Then** the commit is refused, and the message includes the trimmed failures.
4. **Given** lint and both suites are green, **When** the agent runs a `git commit`,
   **Then** the commit proceeds.
5. **Given** any branch, **When** the agent tries to modify a registry manifest
   (`registry/agents/*/manifest.yaml`) or a version file
   (`registry/agents/*/versions/**`), **Then** the operator is asked to confirm,
   because those files are normally written by the Register stage.
6. **Given** any branch, **When** the agent tries to read `.env` or `.env.braintrust`
   with the read tool or a plain shell read, **Then** the read is refused, while
   `.env.example` stays readable. Shell coverage is best-effort; see FR-016.
7. **Given** the operator started the session with the documented exception for the
   spec rule, **When** the agent edits under the guarded directories on a branch with
   no spec, **Then** the edit proceeds, and the harness says once that the exception
   is active.

---

### User Story 3 - The always-loaded context can't silently drift from the code (Priority: P3)

The facts the agent reads on every session (CLAUDE.md, the reviewer subagent prompt,
the gate policy) are checked against the tree by an ordinary test. When a change makes
one of them false, the test suite goes red, and so does the Story 1 gate.

**Why this priority**: Stale context misleads the agent on every session, but it
needs Story 1's gate to turn a red test into a blocked turn. It is also the slice
whose first deliverable is fixing what is already wrong.

**Independent Test**: With the known stale facts fixed, the drift test passes. Rename
one code identifier named in the reviewer prompt, or delete a referenced
`specs/NNN-slug/` directory, and the drift test fails with a message naming the stale
reference and the file it appears in.

**Acceptance Scenarios**:

1. **Given** CLAUDE.md states how many entries `registry/agents/` holds or lists them,
   **When** the drift test runs, **Then** it fails if that statement does not match
   the directories actually present.
2. **Given** CLAUDE.md or the reviewer prompt refers to a spec directory by path
   (`specs/NNN-slug`), **When** the drift test runs, **Then** it fails if that
   directory does not exist in the tree.
3. **Given** the reviewer prompt names a code identifier (for example a private
   helper, a module-level constant or a module file), **When** the drift test runs,
   **Then** it fails if that identifier is found nowhere in the repo's code, unless
   the prompt explicitly marks it as conditional on in-flight work.
4. **Given** this feature's fixes are applied, **When** the drift test runs on the
   resulting tree, **Then** it passes.

---

### User Story 4 - Context budget and continuity (Priority: P3)

*(Added 2026-10-10 after `/speckit-tasks`; research.md R14.)*

Sessions stay inside the operator's 150k-token context budget without the operator
watching a counter. Automatic compaction is capped at the budget, and the operator is
warned before it is reached, with the action to take. When the context is compacted or
cleared, the agent is told where it was (branch, feature, next tasks, gate state), so
progress never lives only in the conversation. Nothing is ever blocked by the budget.

**Why this priority**: Long Spec Kit sessions in this repo reach the budget routinely.
Exceeding it is a policy problem, and losing the thread after `/clear` costs a re-read
of the spec directory. But no correctness gate depends on it, except the snapshot
adoption fix, which belongs to Story 1 (FR-001).

**Independent Test**: Feed the turn-start check a session whose last recorded context
size is above the warn level: exactly one notice appears, naming the size, the budget
and the action, and the prompt is not blocked. Repeat: no second notice. Compact or
clear a session on a feature branch: the first turn afterwards carries the branch,
the active spec directory and the next unchecked tasks.

**Acceptance Scenarios**:

1. **Given** a session whose context is below the warn level, **When** the operator
   submits a prompt, **Then** no budget notice appears.
2. **Given** a session whose context has just reached the warn level or the budget,
   **When** the operator submits a prompt, **Then** the operator sees one notice
   naming the current size, the budget and the recommended action (`/compact <focus>`
   at the next task boundary, or `/clear` between tasks). The agent is told the same,
   so it can persist its state to the spec directory. Later prompts at the same level
   repeat nothing.
3. **Given** the context size can't be determined, **When** a prompt is submitted,
   **Then** no notice appears and the prompt proceeds unaffected.
4. **Given** the harness's project configuration is loaded, **When** a session's
   context grows toward the budget, **Then** automatic compaction happens at or before
   the budget, not near the model's full window.
5. **Given** a session on a feature branch with a `specs/NNN-*/tasks.md`, **When** the
   context is compacted or cleared, **Then** the agent's next turn receives the branch,
   the active spec directory, the next unchecked tasks, whether a gate snapshot is
   pending, and the policy rule IDs.
6. **Given** a session that is not on a feature branch, **When** the context is
   compacted or cleared, **Then** nothing is injected.
7. **Given** a turn that was interrupted before its end-of-turn gate ran, **When** the
   operator runs `/clear` and starts a new turn, **Then** the interrupted turn's
   changes are still checked by the next end-of-turn gate (FR-001 adoption).

---

### Edge Cases

- **Shared checkout, concurrent sessions**: Even turn-scoped, a second session's edits
  that land *during* this turn are indistinguishable from this turn's own. The
  supported setup is one session per worktree; the harness documents this. It does
  not try to tell sessions apart inside one shared tree.
- **Branch switch mid-turn** (by another session or the operator): The end-of-turn
  comparison may see many changed files. The gate must not crash. It treats them as
  changed and reports normally, and the worktree recommendation applies.
- **No turn-start snapshot** (hook added mid-session, snapshot missing or unreadable):
  The gate falls back to today's behaviour, comparing against HEAD, rather than
  skipping checks. It fails safe toward checking more.
- **Deleted Python files in the turn**: A deletion counts as a change. The test suites
  run, and lint does not try to lint a missing file.
- **Files outside the project root** (`/tmp`, scratchpad): These are ignored by every
  check.
- **Commit attempts in other shapes** (`git -C … commit`, `git commit --amend`, a
  commit inside a compound shell command): All are treated as commits. A false
  positive (running the checks before a non-commit command that mentions
  `git commit`) is acceptable; a false negative is not.
- **The checks' own tools are missing** (`jq`, `uv`): Every gate fails closed with a
  message naming the missing tool, as today.
- **Mid-turn user messages**: Claude Code delivers a message sent while a turn is
  running inside that turn, and it fires the turn-start event again. The snapshot
  must not be retaken (FR-001), or edits made before the message would escape the
  gate.
- **Worktree branch names**: Claude Code's worktree command names branches
  `worktree-<name>`. The spec rule accepts that prefix (FR-012), so the recommended
  one-session-per-worktree setup (FR-011) doesn't push operators onto the refusal
  path.
- **Headless runs inside the E2B sandbox**: `swe-agent` loads project settings, so the
  hooks run there when the target repo *is* this repo. `swe-agent` always works on an
  `NNN-*` branch with a spec, so the spec rule passes there. However, the commit gate
  (FR-014) fails closed if `jq` or `uv` is missing, which would stop `swe-agent` from
  ever committing. **Resolved 2026-10-10 (operator):** the sandbox image provides
  both (FR-025). The gate does not special-case the sandbox.
- **Agent editing its own hook configuration**: FR-019 leaves `.claude/**` ungated, so
  the agent could edit the hook settings that enforce FR-012, FR-014 and FR-016. This
  is harmless if Claude Code snapshots hook configuration at session start and
  ignores changes until it is reviewed. Otherwise FR-018's "operator-set only"
  guarantee needs `.claude/settings.json` and `.claude/hooks/**` edits to require
  confirmation. **Resolved 2026-10-10 (`/speckit-plan`, research.md R1–R2):**
  Claude Code does *not* snapshot settings. Edits to `settings.json`, including
  `hooks`, `permissions` and `env`, take effect live after a short file-stability
  delay (docs: debug-your-config). Hook scripts are re-read on every call. So
  `.claude/settings.json`, `.claude/settings.local.json` and `.claude/hooks/**` edits
  require operator confirmation (rule `AF-HARNESS`). Like FR-015, this uses a
  `permissions.ask` rule, which the docs say always prompts, even in auto mode. A
  hook `ask` is not used, because its auto-mode behaviour is undocumented. Shell-made
  edits to those files remain an uncovered, documented gap.
- **Harness bootstrap**: Changes to `.claude/**` itself are not covered by the spec
  rule, so the harness can be repaired even when a spec-rule bug blocks other edits.
- **Docs-only and spec-authoring work on `main`**: Editing `docs/`, `specs/`,
  `CLAUDE.md` or `README.md` is never blocked by the spec rule.
- **Partial staging**: The commit gate checks the working tree, not the staged index.
  A commit of a green subset taken from a red tree is refused. This is accepted as
  conservative.
- **`/clear` after an interrupted turn**: `/clear` starts a new session, so a snapshot
  keyed to the old session would be ignored, and the next turn would take a fresh
  baseline that already contains the interrupted edits. The harness adopts the
  pending snapshot instead (FR-001), which fails toward checking more. A pending
  snapshot older than the staleness limit is discarded rather than adopted, because
  it predates edits the operator made outside any session. The commit gate (FR-014)
  still covers anything that slips through.
- **Mid-turn automatic compaction**: Compaction can happen inside a turn. The harness
  never blocks it, because blocking a compaction forced by the context limit surfaces
  an API error instead. The turn snapshot lives on disk, so the end-of-turn gate is
  unaffected, and the continuity context (FR-029) is re-injected after compaction.
- **Context size unknown**: The only source of the current context size is Claude
  Code's internal session transcript, whose format may change between versions. The
  warning (FR-028) is best-effort and silent on any read or parse failure. The cap
  (FR-027) doesn't depend on it.

## Requirements *(mandatory)*

### Functional Requirements

**Turn-scoped quality gate (Story 1)**

- **FR-001**: The harness MUST record a snapshot of the working tree's Python-relevant
  files (`*.py`, `*pyproject.toml`, `*uv.lock`, tracked and untracked, not ignored)
  at the start of every turn. It MUST take a snapshot only when none is pending, so a
  user message delivered mid-turn doesn't reset the baseline. A snapshot left pending
  by an earlier session in the same worktree (for example by a turn interrupted
  before `/clear`) MUST be adopted as this session's baseline rather than replaced,
  unless it is older than the staleness limit (7 days). The end-of-turn gate consumes
  and clears the snapshot.
- **FR-002**: At the end of a turn, the harness MUST compare against that snapshot and
  treat as changed every Python-relevant file that was added, modified or deleted,
  however the change was made.
- **FR-003**: If no Python-relevant file changed in the turn, the end-of-turn gate MUST
  run no checks.
- **FR-004**: If at least one changed, the end-of-turn gate MUST run lint on the
  changed, still-existing `.py` files and run both test suites (`tests/` and
  `orchestration/`).
- **FR-005**: The per-edit check MUST run lint only on the edited `.py` file and MUST
  NOT run the test suites.
- **FR-006**: Test output fed back to the agent MUST use a short traceback format and
  MUST keep each failing test's identifier within the trimmed output.
- **FR-007**: No check MAY modify a lockfile or resolve dependencies over the network
  as a side effect.
- **FR-008**: Tests that need a live Temporal server MUST be identifiable as a group,
  so a check can include or exclude them deliberately. The end-of-turn gate keeps
  today's behaviour: they run if the server is reachable and skip if it isn't.
- **FR-009**: The gate MUST keep its existing properties: the one-block-per-turn loop
  guard with a visible "still red" notice, arguments passed without shell
  re-parsing, and failing closed when a required tool is missing.
- **FR-010**: If the turn-start snapshot is missing or unreadable, the end-of-turn gate
  MUST fall back to comparing against HEAD.
- **FR-011**: CLAUDE.md MUST state that concurrent sessions are supported only with one
  session per worktree, and why.

**Policy as deterministic checks (Story 2)**

- **FR-012**: Creating or modifying a file under `harness/`, `orchestration/` or
  `eval/` MUST be refused unless the current branch name is `NNN-*` or
  `worktree-NNN-*` (the name Claude Code's worktree command produces) and some
  `specs/NNN-*/tasks.md` exists with the same number. This is a branch-scoped
  tightening of `swe-agent`'s `verify_spec_exists()`.
- **FR-013**: FR-012 MUST apply to the dedicated edit tools. Shell-made edits under
  those directories are not pre-checked (they can't be parsed reliably), but they are
  still caught after the fact by the Story 1 gate. This asymmetry MUST be documented.
- **FR-014**: A `git commit` attempted by the agent (any form; see Edge Cases) MUST be
  preceded by lint on the whole repo and both test suites, and refused if any is red.
- **FR-015**: Modifying `registry/agents/*/manifest.yaml` or
  `registry/agents/*/versions/**` MUST require explicit operator confirmation.
- **FR-016**: Reading `.env` and `.env.braintrust` with the dedicated read tool MUST be
  refused by the harness's permission rules, and `.env.example` MUST stay readable.
  Shell reads (`cat .env`, `grep … .env`) MUST be denied by pattern on a best-effort
  basis. Shell commands can't be parsed completely, so this rule reduces accidental
  exposure but is not a hard boundary. This MUST be documented the same way as FR-013.
- **FR-017**: Every refusal MUST name the rule (a stable short identifier plus one
  sentence) and the concrete action that satisfies it.
- **FR-018**: There MUST be exactly one documented exception mechanism for the spec
  rule (FR-012). It MUST be set by the operator when starting the session, not
  something the agent can enable itself in the middle of a turn. While it is active,
  the harness MUST say so once per session. It MUST NOT bypass FR-014 or FR-016.
- **FR-019**: Changes under `.claude/`, `docs/`, `specs/`, `CLAUDE.md` and `README.md`
  MUST NOT be subject to FR-012.

**Context drift check (Story 3)**

- **FR-020**: The repo-root test suite MUST include a drift test that checks CLAUDE.md
  and the reviewer subagent prompt against the tree, covering at least:
  (a) the registry entries stated in CLAUDE.md match the directories under
  `registry/agents/`;
  (b) every `specs/NNN-slug` path referenced exists;
  (c) every code identifier named in the reviewer prompt exists in the repo's code,
  including tests but excluding `specs/` and `.claude/`, unless explicitly marked
  conditional. Some named helpers, such as `_connect_or_skip`, live only in tests.
- **FR-021**: The reviewer prompt MUST have one explicit convention for marking
  identifiers conditional on in-flight work (for example the credential-pool work on
  branch `009`). The drift test MUST honour it.
- **FR-022**: Drift-test failures MUST name the stale reference, the file and line it
  appears in, and what was expected.
- **FR-023**: Before the drift test is enabled, the following known stale facts MUST
  be corrected:
  (a) architect-agent's Temporal wiring (CLAUDE.md layer-table row and build-order
  bullet; commit `787cfe2` wired a narrow plan-review slice);
  (b) the "two entries" versus "three entries" registry statement;
  (c) `specs/001-agent-spec-schema-test/` named as the example spec (its schema is
  retired);
  (d) the build order omitting features 008 and 009, referenced by number rather than
  path while they are unmerged;
  (e) `eval/gate-policy.md` describing the gate in the retired spec schema's terms
  (`success_criteria`, `guardrails.requires_human_approval`) instead of the actual v1
  `SC-NNN` coverage gate;
  (f) seat-pool identifiers in the reviewer prompt that don't exist on `main`, marked
  conditional per FR-021 or removed.
- **FR-024**: CLAUDE.md's description of the harness (hooks, gates, reviewer, exception
  mechanism) MUST match the shipped behaviour of this feature.

**Sandbox parity**

- **FR-025**: The `swe-agent` sandbox image (`sandbox/swe-agent/Dockerfile`) MUST ship
  every tool the harness's hooks need (`jq`, `uv`), pinned, so the hooks behave the
  same in the sandbox as on the operator's machine.

**Harness self-protection** (added in `/speckit-plan`; see Edge Cases → "Agent
editing its own hook configuration")

- **FR-026**: Modifying `.claude/settings.json`, `.claude/settings.local.json` or
  `.claude/hooks/**` with the dedicated edit tools MUST require explicit operator
  confirmation (rule `AF-HARNESS`), using a permission rule that prompts even in auto
  mode. Shell-made edits to these files are not covered, and this MUST be documented
  the same way as FR-013. This does not make `.claude/**` subject to FR-012
  (FR-019 still holds).

**Context budget and continuity (Story 4)**

- **FR-027**: The harness's project configuration MUST cap automatic context
  compaction at the context budget (150k tokens), so the cap applies to every session
  without a launch flag. If Claude Code doesn't honour that setting from project
  configuration, CLAUDE.md MUST document the launch-time equivalent instead. Changes
  to the cap are covered by FR-026, like any other harness setting.
- **FR-028**: At turn start, the harness MUST warn once when the session's context
  first reaches the warn level (120k tokens), and once when it reaches the budget. The
  warning MUST name the current size, the budget and the recommended action, and MUST
  reach both the operator and the agent. It re-arms once the context drops below the
  warn level (after compaction). It MUST never block the prompt, and MUST stay silent
  when the context size can't be determined.
- **FR-029**: After the context is compacted or cleared on a feature branch (FR-012's
  branch grammar with a matching `specs/NNN-*/` directory), the harness MUST inject
  into the agent's context: the branch, the active spec directory, the next three
  unchecked tasks from its `tasks.md` (if present), whether a turn snapshot is
  pending, and the policy rule IDs. Off a feature branch it MUST inject nothing. It
  MUST never block.
- **FR-030**: CLAUDE.md MUST state the context budget and its rules:
  - the budget and warn level, with the mechanisms that enforce them;
  - `/clear` between Spec Kit phases and after each feature commit (the spec
    directory is the handoff);
  - `/compact <focus>` only at a task boundary with the gate green;
  - tick `tasks.md` checkboxes as each task finishes;
  - what a compaction summary must preserve: current task ID, files modified in the
    task, failing test IDs, and decisions not yet written to the spec directory.
- **FR-031**: The harness MUST NOT block or veto compaction.

### Key Entities

- **Turn snapshot**: A per-session record, taken at turn start (only if none is
  pending), of the identity and content fingerprint of each Python-relevant file. A
  pending snapshot from an earlier session in the same worktree is adopted, not
  replaced (FR-001). It is consumed and cleared by the end-of-turn gate.
- **Policy rule**: A named, deterministic check. It has a stable identifier, a scope
  (which actions and paths), a verdict (allow, ask or deny), a reason, and a
  remediation hint.
- **Spec-rule exception**: An operator-set, session-scoped switch that disables only
  the spec rule.
- **Drift assertion**: A single fact claimed in a context file (CLAUDE.md, the
  reviewer prompt), paired with the tree check that confirms it.
- **Context budget**: The operator's per-session context limit (150k tokens) and its
  warn level (120k), with a per-session record of which level has already been
  announced.
- **Continuity context**: The short orientation block (branch, spec directory, next
  tasks, gate state, rule IDs) injected after compaction or clearing.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a checkout with an unrelated pre-existing failure, 100% of clean turns
  end unblocked (zero false blocks across the acceptance scenarios of Story 1).
- **SC-002**: 100% of Python-relevant changes made in a turn, whether through edit
  tools or shell commands, are checked before that turn can end green.
- **SC-003**: Per-edit feedback finishes in under 2 seconds for a single file on the
  operator's machine, with no test output injected between edits.
- **SC-004**: Each of the five policy rules (spec rule, commit gate, secret read,
  registry confirmation, harness confirmation (FR-026)) is demonstrated by at least
  one automated test showing both its allow and its refuse/ask path. For the two
  confirmation rules, the automated test proves that the permission pattern covers
  exactly the intended paths. The prompt itself is verified live (research R11).
- **SC-005**: 100% of refusals name a rule identifier and a remediation step, verified
  by the tests in SC-004.
- **SC-006**: The drift test passes on the merged tree, and fails for each of the
  injected-staleness cases in Story 3's acceptance scenarios.
- **SC-007**: After the change, a lockfile is byte-identical before and after a full
  run of every gate.
- **SC-008**: In automated tests, a prompt submitted at the first crossing of each
  level produces exactly one notice, a repeat at the same level produces none, and a
  prompt below the warn level or with an unreadable context size produces none. No
  case blocks the prompt.
- **SC-009**: After compaction or clearing on a feature branch, the block injected
  into the agent's context names the correct branch, spec directory and next three
  unchecked tasks, and nothing is injected off a feature branch (automated test). In
  one live check, the agent names them before reading any file.
- **SC-010**: After a turn interrupted before its end-of-turn gate, followed by
  `/clear`, 100% of that turn's Python-relevant changes are checked by the next
  end-of-turn gate.

## Assumptions

- The operator runs Claude Code with this repo's project settings loaded, and has `jq`
  and `uv` installed, as already required by commit `28221cc`.
- "Turn" means a span from one prompt submission to the agent's stop. Subagent edits
  within that span count as the turn's own.
- One session per worktree is the supported concurrency model. Telling sessions apart
  inside one shared checkout is explicitly not attempted.
- The spec rule's exception is an operator-set environment variable at session launch.
  This was chosen because the agent cannot change its own hook environment
  mid-session; the exact name is a planning decision.
- Shell commands are not parsed for file writes. Shell-made edits are covered after
  the fact by the turn-scoped gate (FR-013), not refused up front.
- Hook decisions use Claude Code's documented `PreToolUse` allow/ask/deny outputs and
  `permissions.deny` rules. Confirmations (FR-015, FR-026) use `permissions.ask` rules,
  which the docs guarantee prompt even in auto mode (research.md R1). No external
  policy engine is introduced.
- The context budget (150k) and warn level (120k) are operator guidance as of
  2026-10-10. They are constants kept in one place, not per-session settings.
- Test-suite runtime stays in the low seconds (measured on 2026-10-10: about 0.4s for
  `tests/` and about 1.8s for `orchestration/` with Temporal down; re-measured during planning at
  0.8s and 5.2s, still acceptable, see research.md R12), so running both
  suites at every commit and every turn end is acceptable.

## Out of Scope / Follow-ups

- Restructuring or shrinking CLAUDE.md: moving status narrative to
  `docs/00-status.md` and keeping invariants, commands and pointers.
- Ratifying `.specify/memory/constitution.md` from the invariants enforced here, so
  `/speckit-plan`'s Constitution Check stops being "N/A".
- Nested per-directory context files (`orchestration/CLAUDE.md`,
  `harness/CLAUDE.md`).
- The operator's user-level `~/.claude/settings.json` auto-mode environment, which
  currently carries agentic_factory-specific trust and push rules into every repo.
- Making the LLM reviewer (`py-codereviewer`) a hard pre-commit requirement. It stays
  advisory; FR-014 makes the mechanical checks mandatory.
