# Research: Dev-Harness Hardening (010)

Phase 0 output for `plan.md`. Each entry: **Decision / Rationale / Alternatives**.
Sources marked *[doc]* are official Claude Code docs (code.claude.com); *[measured]*
were measured in this worktree on 2026-10-10 (Claude Code 2.1.285, uv 0.10.0,
jq 1.8.1); *[unverified]* means the docs are silent and the design is built to be
correct either way.

---

## R1. Where confirmation ("ask") gates live: `permissions.ask`, not hook `ask`

**Decision**: FR-015 (registry) and the new harness self-protection rule (R2) are
implemented as `permissions.ask` rules in `.claude/settings.json`, e.g.
`Edit(/registry/agents/*/manifest.yaml)`. The PreToolUse hook never returns `ask`;
it returns only `deny` (refusals) or no decision.

**Rationale**: *[doc]* auto-mode-config: `permissions.ask` rules "are evaluated
before the classifier and always force a permission prompt, even in auto mode,
because an explicit ask rule is your stated intent to be prompted for that action."
The docs say nothing about hook `permissionDecision: "ask"` under auto mode or
bypassPermissions *[unverified]*. Third-party issue trackers report it is silently
auto-approved there. The operator works in auto mode, so a hook `ask` could turn
"explicit operator confirmation" into a no-op. `Edit(...)` rules cover every built-in
file-editing tool (Edit, Write, MultiEdit, NotebookEdit).

**Consequence**: an `ask` prompt carries Claude Code's generic text, not a rule ID.
FR-017 covers *refusals*, so this is acceptable. CLAUDE.md's rule catalogue lists
`AF-REGISTRY` and `AF-HARNESS` next to their ask patterns so the operator can tell
which rule fired.

**Headless caveat**: under `bypassPermissions` (`swe-agent` in E2B) an `ask` rule
has no human to answer it *[unverified]*: it may be skipped or denied. `swe-agent`
never writes registry or `.claude/` files, so either outcome is acceptable. This is
recorded as a known limit, not engineered around.

**Alternatives**: hook `ask` with a rule-ID reason. Rejected because it may be
auto-approved in the operator's normal mode. Hook `deny` plus an env-var escape for
the registry. Rejected because the spec asks for confirmation, not refusal, and a
deny would force a session restart for a routine supervised edit.

## R2. The spec's open edge case: can the agent edit its own hook configuration?

**Decision (answer recorded in spec.md → Edge Cases)**: Yes. *[doc]*
debug-your-config: "When you edit `settings.json`, the change takes effect in the
running session after a brief file-stability delay". Hook script files are re-read
on every invocation in any case. So a session that edits `.claude/settings*.json` or
`.claude/hooks/**` changes its own gates mid-session, and that includes the `env`
block that could set the FR-018 exception variable. Add rule **AF-HARNESS**:
`permissions.ask` on `Edit(/.claude/settings.json)`,
`Edit(/.claude/settings.local.json)` and `Edit(/.claude/hooks/**)`.

**Rationale**: FR-018 ("operator-set only") and FR-012/014/016 depend on the agent
not rewriting the harness without the operator noticing. Using `ask` rather than
`deny` keeps the "harness bootstrap" edge case working: the operator can still
approve a repair. FR-019 is unaffected, because `.claude/**` stays outside the
*spec* rule.

**Residual gap (documented like FR-013)**: shell-made edits (`sed -i
.claude/hooks/...`) aren't pre-checked. There is no after-the-fact catch for them
either, because the gate checks Python, not shell or JSON. CLAUDE.md states this.

**Implementer bootstrap**: building 010 means editing `.claude/hooks/**` and
`.claude/settings.json` constantly. Task ordering in `tasks.md` MUST add the
`permissions.ask` / `permissions.deny` / PreToolUse wiring **last**, as the final
settings change, so that earlier steps aren't prompted on every edit. After that,
further harness edits prompt the operator once per edit, which is the intended
steady state. The implementing branch `010-dev-harness-hardening` plus
`specs/010-*/tasks.md` satisfy AF-SPEC for the `tests/` and `orchestration/` edits.

## R3. Turn snapshot: storage, keying and fingerprint

**Decision**:
- **Location**: `$(git rev-parse --git-path claude-harness)/`. In a worktree this
  resolves to `.git/worktrees/<name>/claude-harness/` *[measured]*, so it is
  per-worktree, outside the working tree, never committed, and needs no `.gitignore`
  entry.
- **Key**: one file per session, `turn-<session_id>.tsv`, where `session_id` comes
  from the hook payload, sanitised to `[A-Za-z0-9_-]`. If it's missing, the
  literal `nosession` is used.
- **Content**: one line `<blob-sha>\t<path>` per Python-relevant file currently on
  disk, from `git ls-files -co --exclude-standard -z -- '*.py' '*pyproject.toml'
  '*uv.lock'` piped to `git hash-object --stdin-paths`. Lines are sorted, and the
  file is written atomically (tmp + `mv`).
- **Diff at Stop**: `comm -3` of the two sorted listings. The union of paths on
  either side is the changed set, which covers added, modified and deleted files.
- **Lifecycle**: UserPromptSubmit writes only if no file exists (FR-001). Stop
  deletes the file whenever it lets the turn end: green, nothing changed, or the
  "still red" notice. It keeps the file when it blocks, so the retry compares
  against the same baseline. UserPromptSubmit deletes `turn-*.tsv` files older than
  7 days to clean up after crashed sessions. *(Superseded in part by R14: a
  pending snapshot younger than 7 days is now adopted, at turn-start and at stop,
  rather than ignored.)*

**Rationale**: the full fingerprint costs 0.03s for 45 files *[measured]*, so hashing
everything is simpler and more robust than "dirty vs HEAD + HEAD sha" bookkeeping.
It also handles commits and branch switches mid-turn with no special case: they just
show up as changed paths. Keying by session keeps a second session in the *same*
worktree from consuming this session's snapshot, but FR-011 still states that
sessions sharing a tree are unsupported.

**Edge behaviour**:
- Missing or unreadable snapshot → fall back to today's `git diff HEAD` + untracked
  check (FR-010).
- Esc interrupt: whether Stop fires is *[unverified]*. If it doesn't, the snapshot
  stays pending and the next turn is judged against the older baseline. That is
  wider than strictly necessary, which is the safe direction.
- Subagent tool calls: reports conflict on whether they carry the parent
  `session_id` *[unverified]*. It doesn't matter, because only UserPromptSubmit and
  Stop (main agent only) touch the snapshot, and Stop compares *tree state*. A
  subagent's edits, through any tool, are in the diff either way.

**Alternatives**: a state dir under `.claude/` (needs gitignore and is shared across
worktrees via the main checkout path; rejected). `git stash create` as the baseline
(writes objects, can't fingerprint untracked files cleanly; rejected). Per-tool
journaling of edited paths (misses shell edits, which is FR-002's whole point;
rejected).

## R4. Lockfile safety and uv invocation (FR-007, SC-007)

**Decision**: every `uv run` in the hooks passes `--locked`. The one exception is the
per-edit lint, which passes `--frozen`.

**Rationale**: today's `py-check.sh` runs plain `uv run`, which may re-lock and
rewrite `uv.lock`, a live FR-007 violation. `--locked` never writes the lock and
*fails* if `pyproject.toml` has drifted from it, so a turn that edits
`pyproject.toml` without re-locking is blocked with uv's own "lockfile needs to be
updated" message (Story 1 scenario 3). Per-edit lint uses `--frozen` (no
staleness check) so that mid-edit lock drift doesn't flood every edit with the same
error; Stop and the commit gate still catch it.

**Not chosen**: `--offline`. A fresh worktree has no `.venv` and the first run
creates one *[measured: "Creating virtual environment at: .venv"]*. Installing
pinned wheels from cache or network is install, not resolution, so FR-007 allows it.

## R5. Test-output shape (FR-006)

**Decision**: suites run as `pytest -q --tb=short -rfE` (no `-x`). The feedback block
for a failed suite is: first, every `FAILED …`/`ERROR …` summary line (grep of
`^(FAILED|ERROR) `), then the tail of the remaining output, up to a total of 60
lines.

**Rationale**: putting the summary first guarantees that every failing test ID
survives trimming, whatever the traceback length. With `-x`, only the first failure
would be reported, which contradicts Story 1 scenario 7 ("each failure"). Suites
are fast enough to run in full.

## R6. Live-Temporal tests as a group (FR-008)

**Decision**: register a `temporal` marker in `orchestration/pyproject.toml`
(`[tool.pytest.ini_options] markers`) and add `pytestmark = pytest.mark.temporal`
to the three modules that use `_connect_or_skip`:
`orchestration/tests/test_pipeline_workflow.py`,
`orchestration/webhook_bridge/tests/test_integration.py` and
`orchestration/webhook_bridge/tests/test_e2e_pipeline_gate.py`. The gates don't
filter on the marker, so today's run-if-reachable/skip-otherwise behaviour is kept,
but `-m "not temporal"` and `-m temporal` now work. After the rebase onto main
(2026-10-11), 009's `orchestration/tests/test_credential_pool.py` is a fourth live
module. It mixes pure and live tests, so only its 18 `_running_pool` tests carry
`@pytest.mark.temporal`, one by one.

**Rationale**: these are the only modules with a live-server dependency *[measured:
10 skipped = 7 + 1 + 2]*. A module-level mark is the smallest change and keeps
`_connect_or_skip` (still referenced by the reviewer prompt).

## R7. Hook process layout and fail-closed behaviour

**Decision**: three scripts plus shared helpers, all bash:
- `.claude/hooks/lib.sh`: shared code: `require_tools` (jq, uv, git; exit 2 naming
  the missing tool), `run_check`, `trim_pytest`, `run_suites`, `state_dir`,
  `rel_path`.
- `.claude/hooks/py-check.sh`: modes `turn-start` (UserPromptSubmit), `edit`
  (PostToolUse) and `stop` (Stop).
- `.claude/hooks/policy.sh`: the **single** PreToolUse hook for every guarded tool
  (`Edit|Write|MultiEdit|NotebookEdit|Read|Grep|Glob|Bash`). It evaluates AF-SPEC,
  AF-SECRET and AF-COMMIT in a fixed order and stops at the first deny.

**Rationale**:
- Fail-closed needs bash as the entry point. Exit 2 blocks, and any other non-zero
  exit is a *non-blocking* error, so a missing interpreter fails open *[doc]*.
  `onFailure: "block"` would fix this but is reported for 2.1.295+, newer than the
  operator's 2.1.285 *[unverified]*. The existing script is bash, and so is the
  reviewer prompt's hook review guidance.
- One PreToolUse script, because the docs don't define how conflicting decisions
  from parallel hooks on one event are merged *[unverified]*.
- No hook-level `"if"` field. Permission-rule prefix matching
  (`Bash(git commit*)`) would miss `cd x && git commit` and `git -C …
  commit`, which the spec requires to be caught. A regex in the script catches them.

## R8. Rule catalogue and matching

| ID | Mechanism | Match | Verdict | Remediation in message |
|---|---|---|---|---|
| `AF-SPEC` | policy.sh | Edit-family tool, path under `harness/`, `orchestration/` or `eval/`, and branch not `^(worktree-)?([0-9]{3})-` or no `specs/<NNN>-*/tasks.md` | deny | `/speckit-specify` → `/speckit-plan` → `/speckit-tasks`, work on branch `NNN-slug`; or operator relaunches with `AF_SPEC_EXCEPTION` |
| `AF-SECRET` | policy.sh + `permissions.deny` | Read/Grep/Glob path or pattern whose basename is `.env`/`.env.braintrust`; Bash command matching `(^|[[:space:]/'"=<])\.env(\.braintrust)?($|[[:space:];|&)'"<>*?[{])` (glob/brace chars included, so `cat .env*` matches) | deny | read `.env.example` for variable names; ask the operator for values |
| `AF-COMMIT` | policy.sh | Bash command containing word `git` and word `commit` | deny if whole-repo `ruff check .` or either suite is red | trimmed failures + "fix, then commit again" |
| `AF-REGISTRY` | `permissions.ask` | `Edit(/registry/agents/*/manifest.yaml)`, `Edit(/registry/agents/*/versions/**)` | ask | (Claude Code prompt) |
| `AF-HARNESS` | `permissions.ask` | `Edit(/.claude/settings.json)`, `Edit(/.claude/settings.local.json)`, `Edit(/.claude/hooks/**)` | ask | (Claude Code prompt) |

`permissions.deny` additionally lists `Read(/.env)` and `Read(/.env.braintrust)`
as a backstop if hooks are disabled. The hook fires first and supplies the
rule-ID message (FR-017). The `.env.example` exclusion falls out of the regex:
a `.` after `.env` is not an allowed terminator.

All seven rules start with a single `/`, which Claude Code resolves against the
project root. `./` would resolve against the directory the session started in,
so a session started in `orchestration/` would get no AF-REGISTRY or AF-HARNESS
prompt (T042 review, 2026-10-11).

Message format (contract): `[<ID>] <one-sentence rule>. To proceed: <action>.`
See `contracts/hook-interface.md`.

## R9. Spec-rule exception (FR-018)

**Decision**: environment variable **`AF_SPEC_EXCEPTION`**, which takes effect when
non-empty. By convention its value is the reason, e.g.
`AF_SPEC_EXCEPTION="hotfix #123" claude`. It bypasses only AF-SPEC.

- **Announce once**: the first time AF-SPEC *would* deny but the exception is
  active, policy.sh allows the call and emits a `systemMessage`
  (`[AF-SPEC] exception active for this session: <value>`). It then touches
  `exception-<session_id>.notified` in the state dir, and later calls are silent.
  SessionStart was rejected for this: whether its `systemMessage` renders is
  disputed *[unverified]*, and announcing on first use is also more accurate.
- **Agent can't self-enable**: hook processes inherit Claude Code's launch
  environment plus the settings `env` block *[doc: env-vars]*. Bash
  `export`/`CLAUDE_ENV_FILE` affect only Bash subprocesses. The settings `env`
  block is hot-reloaded (R2) and is covered by AF-HARNESS's ask rule.

## R10. Drift test parsing conventions (FR-020/021)

**Decision**: `tests/test_context_drift.py` runs three assertion families over
`CLAUDE.md` and `.claude/agents/py-codereviewer.md`. The full grammar is in
`contracts/drift-conventions.md`.

- **D-REG** (CLAUDE.md only):
  - every `registry/agents/<name>` path reference exists;
  - every brace list `registry/agents/{a,b,…}` must equal the actual set *exactly*.
    To name a subset, write individual paths instead;
  - every number word (`one`…`ten`) directly before `entries`/`entry`, in a sentence
    that mentions `registry/agents`, must equal the directory count.
- **D-SPEC** (both files): every `specs/NNN-slug` path (regex
  `specs/(\d{3}-[a-z0-9][a-z0-9-]*)`) exists. In-flight features are referenced by
  **number only** ("feature 009"), never as a path, which settles FR-023(d) against
  FR-020(b).
- **D-ID** (reviewer prompt only): each backticked token that is a private name
  (`_x`, `_x()`), an `UPPER_SNAKE` name (optional trailing `*` = prefix match) or a
  bare `*.py`/`*.yaml` filename must appear in the repo's code: a word-boundary match
  in `*.py` files, or a filename match. The search excludes `specs/`, `.claude/`,
  `.specify/` and `.venv/`, and includes tests. Dotted names (`workflow.now()`,
  `shlex.join`) are library APIs and are skipped. Tokens containing `/` are checked
  as paths.
- **Conditional convention (FR-021)**: a token immediately followed by
  `(pending NNN)` is exempt from D-ID and D-SPEC. A pending token that *does* now
  exist fails with "remove the `(pending NNN)` marker". This makes the drift test
  flag the cleanup when feature 009 merges.

**Rationale**: the failure messages name file, line, the stale token and what was
expected (FR-022). Only stdlib `re`/`pathlib` is used, so no new dependency. The
reviewer prompt's first users of the convention are `CLAUDE_CODE_OAUTH_TOKEN`,
`CLAUDE_OAUTH_SEAT_*`, `seat_guard.py` and `pool.yaml`, which are absent from code on
this tree *[measured]*; they belong to feature 009. The full candidate set the D-ID
rules extract from today's prompt was triaged by hand: those four are the only
absent ones. `_scrubbed()`, `_REPO_RE`, `_BRANCH_RE`, `_validate_*`,
`_NO_AUTO_RETRY`, `_load_module_by_path`, `_connect_or_skip`, `MAX_*_ATTEMPTS`,
`GH_TOKEN`, `ANTHROPIC_*`, `LITELLM_*`, `activities.py`, `agent.py`,
`eval.config.py` and `pyproject.toml` all exist. Even so, `tasks.md` MUST include a
step that runs the finished extractor in report-only mode and triages every hit
*before* the test is enabled.

**Not chosen**: HTML-comment drift markers per fact. Every new fact would need an
author to remember a marker, and the facts that drift most are the ones written
without one.

## R11. Hook tests (SC-004/005) without network or real suites

**Decision**: `tests/test_harness_hooks.py` drives the real scripts through
`subprocess` with synthetic JSON on stdin, inside a `tmp_path` git repo that has the
hook files copied in and `CLAUDE_PROJECT_DIR` pointed at it. `uv` is replaced by a
**stub executable earlier on `PATH`**. The stub's exit code and output are
controlled per test through a file in `tmp_path`, so "suite red" and "suite green"
are deterministic and need no network.

**`permissions.ask` rules (AF-REGISTRY, AF-HARNESS) can't be tested behaviourally**,
because pytest can't drive Claude Code's permission prompt. Their automated test
reads `.claude/settings.json` and asserts two things: each rule string is present,
and an `fnmatch`/gitignore-style match shows each pattern covers its targets
(`registry/agents/swe-agent/manifest.yaml`,
`registry/agents/pm-agent/versions/0.1.0.yaml`, `.claude/hooks/policy.sh`) but not
neighbours (`registry/agents/swe-agent/SKILL.md`, `.claude/agents/py-codereviewer.md`).
The live prompt is verified manually (quickstart §3.5–3.6). This is how SC-004
counts for those rules.

**Rationale**: no test-only env var or seam in the hook code, so nothing an agent
could flip to skip a gate. `jq` and `git` are real. Each rule gets an allow test and
a refuse test (SC-004), and every refuse test asserts `[AF-…]` and `To proceed:` in
the output (SC-005). The turn-gate scenarios from Story 1 (pre-existing failure,
shell-made edit, pyproject-only change, no-change fast path, loop guard, missing
snapshot fallback, deletion) use the same fixture.

## R12. Measured performance vs. spec assumptions

*[measured, warm cache]*:

| Step | Time |
|---|---|
| fingerprint (45 files) | 0.03s |
| per-file `ruff` via `uv run` | 0.43s (SC-003 < 2s ✔) |
| `tests/` suite | 0.8s |
| `orchestration/` suite (Temporal down) | **5.2s** |

The spec's Assumptions cite about 1.8s for `orchestration/`. The measured figure is
about 3× higher but still acceptable for once-per-turn and once-per-commit runs.
`plan.md` uses the measured number. Hook timeouts stay at 300s for Stop and commit,
and drop to 60s for per-edit lint.

## R13. Sandbox parity (FR-025)

**Decision**: already satisfied by the uncommitted `sandbox/swe-agent/Dockerfile`
change on this branch (`jq` via apt; `uv`/`uvx` copied from
`ghcr.io/astral-sh/uv:0.10.0`, matching the operator's host). It is committed
with this feature unchanged. In the sandbox, `swe-agent` runs `bypassPermissions`.
Hook `deny` applies in every mode *[doc: hooks]*, so AF-COMMIT and AF-SPEC are still
enforced there, while the `permissions.ask` rules are a known limit (R1).

## R14. Context budget and continuity across /compact and /clear (added 2026-10-10, after `/speckit-tasks`)

**Trigger**: operator guidance caps agent-session context at **150k tokens**. The
harness had no rules for `/compact` or `/clear`, and the R3 snapshot design has a
gap with `/clear` (below).

**Operator decisions (2026-10-10)**:
- **Cap + warn, no hard lock.** Cap auto-compaction at 150k and warn the operator
  ahead of it. Nothing is blocked.
- Fold into **010 as a new User Story 4**. The snapshot-adoption fix goes into
  **US1**, because it's a correctness gap there.
- Record here, then `/clear`, and do the Spec Kit updates in a fresh session.

**Facts**:
- `/clear` assigns a **new `session_id`** and starts a new transcript file
  *[measured: d0525110… ended 14:56Z at ~139k context; 32e58c13… began 15:22Z
  containing the `/clear` local_command]*. It fires `SessionEnd` with
  `reason: "clear"` and `SessionStart` with `source: "clear"` *[doc: hooks]*.
  Whether UserPromptSubmit or Stop fire for `/clear` itself is *[unverified]*;
  presumably not.
- Compaction fires `PreCompact` (matcher `manual`/`auto`, payload `trigger`,
  `custom_instructions`), then `PostCompact` (observational), then
  `SessionStart` with `source: "compact"`. The `additionalContext` from that
  SessionStart is injected after compaction *[doc: hooks]*. Whether `session_id`
  survives compaction is *[unverified]*; presumably it does.
- **Auto-compaction can happen mid-turn** *[doc: hooks]*. A PreCompact exit 2 skips
  a proactive compaction, but if the context limit was already hit the API error
  surfaces instead. So **never block PreCompact(auto)**.
- **No hook payload carries the current context size.** SessionStart has
  `context_tokens` for `resume`/`fork` only, not for startup, clear or compact
  *[doc: hooks]*. The only source is `transcript_path`: the last `type=="assistant"`
  entry's `.message.usage`, as `input_tokens + cache_read_input_tokens +
  cache_creation_input_tokens` *[measured]*. The docs call the JSONL format
  internal and liable to change between versions *[doc: sessions]*. So any parse is
  best-effort, and it must **fail silent**.
- **`CLAUDE_CODE_AUTO_COMPACT_WINDOW`** (100k–1M) sets the auto-compaction window.
  The same setting is available as `/autocompact <n>` and `claude --autocompact <n>`.
  Without it, 1M-window models compact at about 967k *[doc: model-config]*.
  Whether it's honoured from the project `.claude/settings.json` `env` block is
  *[unverified]*, so verify it live. At which fraction of the window compaction
  fires is also *[unverified]*.
- Hooks **cannot run** `/compact` or `/clear` *[doc: hooks-guide]*. They can only
  surface `systemMessage` to the operator or `additionalContext` to the model.
- Best practice is `/clear` between unrelated tasks and `/compact <focus>` within
  a task. Plain-language "when compacting, preserve …" text in CLAUDE.md steers the
  summary, but there's no formal schema for it *[doc: best-practices]*. CLAUDE.md
  is reloaded after compaction; instructions given only in conversation are lost
  *[doc: memory, context-window]*.

**Gap in R3 (fix in US1)**: the snapshot is keyed by `session_id`, which `/clear`
changes. Suppose a turn is interrupted (Esc, so Stop may not fire) and then the
operator runs `/clear`. The next `turn-start` writes a *fresh* snapshot that
already contains the interrupted turn's edits, so the Stop gate never checks
them; only AF-COMMIT would. **Decision**: `turn-start` first **adopts** any
pending `turn-*.tsv` in the state dir, choosing the oldest (widest baseline), by
renaming it to the current session's key. Only if none exists does it take a new
snapshot. This is safe because of FR-011 (one session per worktree), and it fails
toward checking more.

**Design for US4 (to be specified)**:
1. **Cap**: `.claude/settings.json` `env.CLAUDE_CODE_AUTO_COMPACT_WINDOW = "150000"`.
   This lands in the same final settings step as T037 (AF-HARNESS bootstrap
   rule; T031 before the tasks were regenerated), and gets a live check of when compaction fires. If the `env` block
   isn't honoured, the fallback is to document `claude --autocompact 150k` /
   `export CLAUDE_CODE_AUTO_COMPACT_WINDOW=150000` as the launch convention.
2. **Warn**: `py-check.sh turn-start` reads the usage figure above. At ≥ a warn
   level (default 120k; budget and warn level as constants in `lib.sh`) it emits
   one `systemMessage` per threshold crossing per session, for example:
   `context at 131k of 150k budget: /compact <focus> at the next task boundary, or
   /clear between tasks`. If the transcript is unreadable or unparseable it does
   nothing, and it always exits 0 (the turn-start contract).
3. **Continuity**: a new `SessionStart` hook (matcher `compact|clear`) runs
   `.claude/hooks/session-context.sh` and emits `additionalContext` with:
   - the branch;
   - the active `specs/NNN-*` directory;
   - the next 3 unchecked `- [ ] T…` lines from its `tasks.md`;
   - whether a gate snapshot is pending;
   - the AF-* rule IDs.

   It always exits 0 and is a no-op off a feature branch. PreCompact gets no hook
   (blocking is harmful; logging adds nothing).
4. **Rules (CLAUDE.md "Context budget" section)**:
   - budget 150k, with the cap and warn mechanisms named;
   - `/clear` between Spec Kit phases (specify → plan → tasks → implement) and
     after each feature commit, because `specs/NNN-*/` on disk is the handoff;
   - `/compact <focus>` only at a task boundary with the gate green, never mid-task
     or with the gate red;
   - tick `tasks.md` checkboxes as each task finishes, so progress never lives only
     in the conversation;
   - a "When compacting, preserve: current task ID, files modified this task,
     failing test IDs, decisions not yet written to the spec dir" paragraph.
5. **Tests**: turn-start warns at or above the warn level and is silent below it,
   or on a malformed or missing transcript (fixture transcripts with synthetic
   `usage`); snapshot adoption after a `session_id` change; session-context output
   on a feature branch with a `tasks.md`, and a no-op off one; a settings test for
   the env var and the SessionStart wiring.

### R14 details pinned during the replan (`/speckit-plan`, 2026-10-10)

The R14 sketch left these open. They are now normative in `data-model.md` and
`contracts/hook-interface.md`.

- **Adoption is a shared step, used by both `turn-start` and `stop`.** It's a
  `resolve_snapshot` helper in `lib.sh`:
  1. If `turn-<own id>.tsv` exists, use it.
  2. Otherwise, delete `turn-*.tsv` files older than 7 days.
  3. Then rename the oldest remaining `turn-*.tsv` to the own key, and delete any
     others, which are superseded because the oldest is the widest baseline.

  Running it at `stop` too covers the *[unverified]* case where compaction changes
  `session_id` mid-turn. Without it, Stop would find no own-key file and fall back
  to HEAD.
- **Prune *before* adopt, not after.** A snapshot older than 7 days predates edits
  the operator made outside any session. Adopting it would put those files in the
  lint set and falsely block a clean turn, against SC-001. Discarding it means a turn
  interrupted more than a week before `/clear` escapes the Stop gate, but AF-COMMIT
  still catches it. Both directions were weighed: prune-first keeps SC-001, and the
  only cost is a gap that the commit gate already covers.
- **Bounded transcript read.** The warn step runs
  `tail -n 200 "$transcript_path"`, then
  `jq -R 'fromjson? | select(.type=="assistant" and (.isSidechain != true) and .message.usage)'`,
  and keeps the last match. The context size is
  `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`.
  - Cost is constant whatever the transcript size. A long session's JSONL runs to
    megabytes, and turn-start has a 30s timeout.
  - `fromjson?` skips a partially written last line.
  - Any failure (missing path, no match, non-numeric) means silent and exit 0.
  - If the last 200 lines hold no assistant entry, no warning is emitted for that
    prompt. That's acceptable.
- **Two levels, re-armed.** The levels are warn (120k) and budget (150k), defined as
  `CTX_WARN`/`CTX_BUDGET` in `lib.sh`. The marker `ctx-<session_id>.level` holds the
  highest level already announced. It's deleted when a reading is below `CTX_WARN`,
  for example after compaction, so a later crossing warns again.
- **Warning reaches both audiences.** The output is one JSON object:
  - `systemMessage` for the operator;
  - `hookSpecificOutput.additionalContext` for the agent, which can persist state to
    the spec dir but can't run `/compact` itself.

  This changes turn-start's contract from "never stdout" to "only ever a single valid
  JSON object on stdout". Under UserPromptSubmit, plain stdout would be injected as
  raw context.
- **`session-context.sh` is its own script**, sourcing `lib.sh`. It resolves the spec
  dir from the **branch** (same grammar as AF-SPEC; first match of
  `specs/<NNN>-*/` sorted), not from `.specify/feature.json`, which is a tracked file
  that can be stale. If `jq` or `git` is missing, or the branch doesn't match, it
  prints nothing and exits 0. It is informational, so failing closed would add
  nothing.
- **Cap value has one source of truth.** A settings test asserts that
  `.claude/settings.json` `env.CLAUDE_CODE_AUTO_COMPACT_WINDOW` equals `CTX_BUDGET`
  parsed from `lib.sh`.

### Handoff: remaining Spec Kit updates (fresh session after `/clear`)

Done in the replan, except `tasks.md`:

- [x] spec.md: add **User Story 4 - Context budget and continuity (P3)**, with
  acceptance scenarios from items 1–5 above. Add FRs (next free numbers,
  FR-027+) for cap, warn, continuity, rules and snapshot adoption. Add the
  adoption rule to FR-001, edge cases for `/clear` after an interrupted turn and
  for mid-turn auto-compaction, and SCs for the warning and continuity. Update the
  Context section and Key Entities ("Context budget").
- [x] plan.md: Summary + Source Code (`session-context.sh`, settings env +
  SessionStart) + Implementation Order (env and SessionStart wiring join the final
  settings step; session-context.sh before T030's review pass).
- [x] data-model.md: snapshot state machine (adopt transition), warn-notice
  marker, context budget.
- [x] contracts/hook-interface.md: SessionStart wiring + payload (`source`,
  `transcript_path`), turn-start warn output, session-context.sh output.
- [x] quickstart.md: live checks for the cap (does compaction fire near 150k?), the
  warning, `/clear` continuity and adoption.
- [x] Regenerate tasks.md with `/speckit-tasks`. Keep the T001–T039 phase-order
  rationale and the doc-fix anchors, and add US4 tasks plus the US1 adoption tasks.

## R15. Blocker found during T006 (2026-10-10): live-Temporal tests race

**Finding** *[measured]*: with Temporal up, `orchestration/tests/test_pipeline_workflow.py`
is flaky. In 3 back-to-back solo runs it gave 1 failure
(`test_budget_exhaustion_after_repeated_rejection_raises`, "condition not met within
10.0s"), 1 pass, and 1 hang (stuck in
`test_idempotent_hit_skips_charge_and_goes_straight_to_gate` until killed). Each test
passes alone. Parallel suite runs (four `.py` edits, each firing the old per-edit hook)
made it worse, but it also happens with one run.

**Root cause** (feature 005 tests, commit `787cfe2`, outside 010): the workflow
deliberately clears `_plan_decision` right before `wait_condition`
(`orchestration/workflows/pipeline_workflow.py` ~L133-140, FR-016: a signal received
during the activity is stale). The tests send `plan_approved`/`plan_rejected` as soon
as the stub `architect_stage_activity` is *entered*. If the signal is processed before
the workflow reaches the reset, it is wiped. Approve tests then wait forever
(`handle.result()` has no timeout, so the run hangs); the reject loop misses a call
and times out after 10s.

**Impact on 010**: the Stop gate and AF-COMMIT run the full orchestration suite, so
while Temporal is up they can block a clean turn, or hang until the 300s Stop timeout.
R6's "gates don't filter on the marker" assumed these tests are deterministic. They
aren't.

**Second race, same run**: `test_e2e_pipeline_gate.py` ran its stub Worker on the
production queue `agent-factory-pipeline`. Another session's live `worker.py` took
one test workflow and ran a real `ensure_target_pr_activity` (`gh pr list --repo
owner/repo`, failed harmlessly; no stray workflow left running).

**Resolution (operator decision 2026-10-10: fix the 005 tests first, separately)**:
commit `889785f` "fix(005): remove races in live-Temporal pipeline and bridge e2e
tests". Signals wait for a `WorkflowTaskCompleted` after the N-th architect
completion in workflow history; `handle.result()` is bounded (30s); each run has an
`execution_timeout` (60s); the e2e tests use a per-run task queue. Verified: 5 full
orchestration runs and 10 runs of both modules green with Temporal up. Lesson for the
gates: assume suite runs overlap (parallel tool calls, other sessions, live workers),
so `.py` edits stay serial while Temporal is up. R6's "gates don't filter on the
marker" stands.
