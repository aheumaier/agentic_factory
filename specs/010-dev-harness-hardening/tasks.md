---

description: "Task list for 010 Dev-Harness Hardening"
---

# Tasks: Dev-Harness Hardening

**Input**: Design documents from `specs/010-dev-harness-hardening/`

**Prerequisites**: plan.md, spec.md, research.md (R1–R14), data-model.md,
contracts/hook-interface.md, contracts/drift-conventions.md, quickstart.md

**Regenerated 2026-10-10** after the replan, which added User Story 4 (context
budget and continuity) and the FR-001 snapshot-adoption fix in US1. Tasks that
existed before keep their text; their IDs shifted (old T014 → T015, old T030 → T036,
old T039 → T046).

**Tests**: Required. SC-004/SC-005 need an allow and a refuse test per rule.
FR-020/SC-006 make the drift test itself a deliverable, and SC-008–SC-010 need
automated warn, continuity and adoption tests. Tests go in the root suite (`tests/`),
so the Stop gate runs them.

**Organization**: Tasks are grouped by user story. The `[US1]`–`[US4]` labels match
the spec's story numbers.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: The user story the task belongs to (US1, US2, US3, US4)

## ⚠️ Phase order is deliberate. Don't "fix" it to P1 → P2 → P3

plan.md "Implementation Order" and research R2 ("Implementer bootstrap") require this
order:

1. Setup and foundations (`lib.sh`, `temporal` marker, test fixture).
2. **US1** (P1): turn-scoped gate, including snapshot adoption (FR-001, SC-010).
3. **US3** (P3): doc fixes **first**, *then* the drift test, so the suite never goes
   red mid-feature.
4. **US2** (P2): `policy.sh` and its tests, with the hook **not wired yet**.
5. **US4** (P3): the turn-start context warning and `session-context.sh`, with tests,
   also **not wired yet**.
6. **Pre-activation hook review** (T036) of every `.claude/hooks/**` script.
7. **Activation**: one final `.claude/settings.json` change wires PreToolUse, the
   `permissions.ask`/`deny` rules, SessionStart (`compact|clear`) and
   `env.CLAUDE_CODE_AUTO_COMPACT_WINDOW`. This activates AF-HARNESS, so every later
   edit to `.claude/settings*.json` or `.claude/hooks/**` prompts the operator.
   That is why every `.claude/hooks/**` task, including the T036 review pass, comes
   before T037.
8. Polish (review, full validation, commit).

**Live-hook caveat while building**: until T009 rewrites `py-check.sh`, today's
`PostToolUse` hook runs ruff **and both full suites (`-x`)** after every edit-tool
`.py` change. So Phases 1–2 touch only one-line `.py` edits, and each new test
module is written in a single Write that is already green. Bash, JSON and Markdown
edits never trigger the per-edit hook. After T010, `turn-start` runs on every prompt
of the implementing session itself. A broken `turn-start` must still exit 0 with
empty-or-JSON stdout (contract), or the operator's prompts get garbage context.

**Shell constraint for every hook script task**: bash 3.2-compatible, because
macOS `/bin/bash` runs them and the tests invoke them through `/bin/bash`. That
means no `mapfile`/`readarray`, no associative arrays, no `${var,,}`, and no
`declare -n`. Pass arguments as argv arrays, never through `eval` or `bash -c`
re-parsing (FR-009).

---

## Phase 1: Setup

**Purpose**: Confirm a green baseline and make the live-Temporal tests a selectable group (FR-008).

- [x] T001 Verify the starting baseline from the worktree root. Check that `git branch --show-current` is `010-dev-harness-hardening` and that `specs/010-dev-harness-hardening/tasks.md` exists (it satisfies AF-SPEC later). Run `uv run --locked ruff check .`, `uv run --locked pytest tests/ -q` and `(cd orchestration && uv run --locked pytest -q)`; all must be green. Record `shasum uv.lock orchestration/uv.lock` into the session scratchpad for the SC-007 check in T044. If anything is red, stop and report it; don't fix unrelated failures.
- [x] T002 Register the `temporal` pytest marker in the **existing** `[tool.pytest.ini_options]` section of `orchestration/pyproject.toml` (line ~23, next to `asyncio_mode = "auto"`; don't add a second section). Add `markers = ["temporal: needs a live Temporal server at localhost:7233; skipped via _connect_or_skip when unreachable"]`. Don't touch `orchestration/uv.lock`.
- [x] T003 [P] Add `pytestmark = pytest.mark.temporal` right after the imports in `orchestration/tests/test_pipeline_workflow.py`. `pytest` is already imported. If the module already defines `pytestmark`, extend it to a list.
- [x] T004 [P] Add `pytestmark = pytest.mark.temporal` right after the imports in `orchestration/webhook_bridge/tests/test_integration.py`, the same way as T003.
- [x] T005 [P] Add `pytestmark = pytest.mark.temporal` right after the imports in `orchestration/webhook_bridge/tests/test_e2e_pipeline_gate.py`, the same way as T003.
- [x] T006 Verify FR-008. `(cd orchestration && uv run --locked pytest -q -m temporal)` must select exactly the modules from T003–T005 (with Temporal down: 10 skipped, 7 + 1 + 2, per research R6). `-m "not temporal"` must deselect them, and plain `uv run --locked pytest -q` must give the same pass/skip counts as T001. **Done 2026-10-10**: `-m temporal` = 10 tests from the 3 modules (7+2+1; Temporal was up, so they ran and passed rather than skipped); `-m "not temporal"` = 62 passed, 10 deselected; plain = 72 passed, same as T001. First attempt was flaky — see research R15, fixed in separate commit `889785f`.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: The shared hook library and test fixture that US1, US2, US4 and the commit gate all build on.

**⚠️ CRITICAL**: US1, US2, US4 and the activation phase all source `lib.sh` and use this fixture.

- [x] T007 Create `.claude/hooks/lib.sh` (sourced, not executed; no shebang side effects, no `set -e`). It defines these bash 3.2-compatible functions and constants, per research R3–R5/R7/R14, data-model.md and contracts/hook-interface.md:
  - `require_tools <script-name> <tool>...`: for each missing tool, print `<script-name>: <tool> is required` to stderr and `exit 2` (fail closed, FR-009).
  - `run_check <label> <cmd> [args...]`: run argv, capture combined output, and on a non-zero exit append `=== <label> FAILED ===` plus the output to the global `failures`. The label `pytest*` gets its output passed through `trim_pytest`; others get `tail -n 40`.
  - `trim_pytest`: read stdin, print every line matching `^(FAILED|ERROR) ` first, then the tail of the remaining lines, 60 lines in total at most (FR-006, R5).
  - `run_suites <root>`: `run_check "pytest tests/" uv run --locked --directory <root> pytest tests/ -q --tb=short -rfE`, then `run_check "pytest orchestration/" uv run --locked --directory <root>/orchestration pytest -q --tb=short -rfE` (no `-x`; FR-007 `--locked`).
  - `state_dir <root>`: print the absolute path of `$(git -C <root> rev-parse --git-path claude-harness)`, resolved against `<root>` if relative, after `mkdir -p`.
  - `session_key <raw>`: sanitise to `[A-Za-z0-9_-]` and print `nosession` if empty.
  - `rel_path <root> <path>`: print the path relative to `<root>` (absolute or relative input), or nothing if it's outside `<root>`.
  - `python_fingerprint <root>`: `git -C <root> ls-files -co --exclude-standard -z -- '*.py' '*pyproject.toml' '*uv.lock'`. Keep only paths that exist on disk, hash them with `git hash-object --stdin-paths`, and print `<sha>\t<path>` lines sorted with `LC_ALL=C sort`.
  - `resolve_snapshot <state-dir> <key>`, the adoption step (data-model.md "Resolve step"; FR-001):
    1. If `turn-<key>.tsv` exists, return.
    2. Otherwise delete other `turn-*.tsv` older than 7 days (`find "$sd" -maxdepth 1 -name 'turn-*.tsv' -mmin +10080`; use `-mmin`, not `-mtime +7`, which rounds to 8 days).
    3. Then `mv` the oldest remaining one (`ls -tr`; names are sanitised) to `turn-<key>.tsv` and delete the rest.

    Never fails the caller; errors are ignored.
  - `feature_number <root>`: the branch from `git -C <root> symbolic-ref --short -q HEAD`. If it matches `^(worktree-)?([0-9]{3})-`, print the three digits, otherwise nothing. Detached HEAD prints nothing.
  - `feature_spec_dir <root>`: for `feature_number`'s NNN, print the first `LC_ALL=C`-sorted `specs/<NNN>-*/` dir (repo-relative, trailing `/`), or nothing.
  - Constants `CTX_BUDGET=150000` and `CTX_WARN=120000`, each on its own line as `NAME=<digits>` at column 0 (T038's settings test parses `CTX_BUDGET` by regex).
- [x] T008 Create `tests/test_harness_hooks.py` with the **shared fixture only** (no `test_` functions yet; a single Write that ruff and pytest already accept):
  - A `harness_repo` fixture builds a `tmp_path` git repo (`git init -b 010-x`, local user.name/email, one committed `pkg/clean.py`, `pyproject.toml` and `uv.lock`). It copies the real `.claude/hooks/*.sh` into `<repo>/.claude/hooks/` and puts a **stub `uv`** first on `PATH`.
  - The stub (a small bash script written by the fixture) appends its full argv as one line to `<tmp>/uv-calls.log`. It accepts and ignores `--locked`, `--frozen` and `--directory <d>`, and dispatches on the first remaining word: `ruff` or `pytest`. Exit code and stdout for each come from `<tmp>/ruff.rc`, `<tmp>/ruff.out`, `<tmp>/pytest.rc` and `<tmp>/pytest.out` (default rc 0, empty output).
  - A `run_hook(repo, script, args, payload: dict, env_extra=None, path=None)` helper runs `["/bin/bash", <repo>/.claude/hooks/<script>, *args]` with `input=json.dumps(payload)` and `CLAUDE_PROJECT_DIR=<repo>`. It returns the `CompletedProcess` (text mode), and `path` overrides `PATH` for the missing-tool tests.
  - Helpers `uv_calls()` (parsed log lines), `set_stub(tool, rc, out)` and `state_dir(repo)` (the resolved `git rev-parse --git-path claude-harness` dir).
  - Real `git` and `jq` are used, with no test-only env vars or seams in hook code (R11).

**Checkpoint**: `lib.sh` exists, the fixture imports cleanly, and both suites are still green.

---

## Phase 3: User Story 1 - A turn is judged only on what it changed (Priority: P1) 🎯 MVP

**Goal**: End-of-turn lint+tests run only when this turn changed Python-relevant files, through any tool. Per-edit feedback is file-local ruff only. A baseline left pending by an interrupted turn survives `/clear`.

**Independent Test**: On a tree with an unrelated failing `.py`, a clean turn ends unblocked. A turn that adds a lint error with a shell command is blocked, and the block names the file (spec US1 Independent Test; quickstart §2). An interrupted turn followed by a new `session_id` is still checked (SC-010).

### Implementation for User Story 1

- [x] T009 [US1] Rewrite `.claude/hooks/py-check.sh` to source `"$(dirname "$0")/lib.sh"`, with three modes per contracts/hook-interface.md. Keep the header comment, updated to describe the three modes and wiring.
  - `turn-start` (UserPromptSubmit) **always exits 0, with stdout empty or one JSON object** (empty for now; T031 adds the warning), even when tools are missing or the write fails. It runs `resolve_snapshot "$(state_dir)" "$(session_key …)"`. Then, **only if** `turn-<session_key>.tsv` still doesn't exist, it writes `python_fingerprint` to it atomically (tmp file in the same dir + `mv`). That's FR-001: no retake on a mid-turn message, and adopt instead of replace after `/clear`.
  - `edit` (PostToolUse): `require_tools jq uv`. File = `.tool_input.file_path // .tool_response.filePath`. Exit 0 unless it ends in `.py` and `rel_path` is non-empty. Then `run_check "ruff check <rel>" uv run --frozen --directory "$ROOT" ruff check --force-exclude --output-format concise "$file"`. If red, print `ruff failed after editing <rel>:` plus findings to stderr and exit 2. **Never call pytest** (FR-005).
  - `stop` (Stop): `require_tools jq git uv`. First run `resolve_snapshot` with this payload's `session_id`; that covers a `session_id` change mid-turn (R14).
    - **Changed set**: if the snapshot exists, is readable and is well-formed (every line `^[0-9a-f]{40}\t.+$`, and non-empty when Python-relevant files exist), the changed set is the paths from `comm -3 <snapshot> <current fingerprint>`. Otherwise fall back to HEAD (FR-010): `git diff --name-only HEAD -- '*.py' '*pyproject.toml' '*uv.lock'` plus `git ls-files --others --exclude-standard` with the same pathspecs.
    - **Empty set**: delete the snapshot and exit 0 with no `uv` call (FR-003).
    - **Otherwise**: lint set = changed `.py` paths that still exist. Run `uv run --locked --directory "$ROOT" ruff check --force-exclude --output-format concise <lint set>` only if the lint set is non-empty, then `run_suites "$ROOT"` (FR-004).
    - **Green**: delete the snapshot, exit 0.
    - **Red, `stop_hook_active` not true**: print `ruff/pytest gate is red for this turn's changes (<n> files) — fix before ending the turn:` plus failures to stderr, **keep** the snapshot, exit 2.
    - **Red, `stop_hook_active == true`**: print `{"systemMessage": "ruff/pytest gate is still RED at end of turn: …"}` via `jq -n` to stdout, delete the snapshot, exit 0 (FR-009).

    A branch switch that yields a large changed set must not crash; pass paths as argv arrays.
  - Unknown mode: stderr, exit 1.
- [x] T010 [US1] Update `.claude/settings.json` hooks (no `permissions`, PreToolUse, SessionStart or `env` yet; those land in T037):
  - add `UserPromptSubmit` → `"$CLAUDE_PROJECT_DIR"/.claude/hooks/py-check.sh turn-start`, timeout 30, statusMessage `"turn snapshot"`;
  - change the `PostToolUse` (`Edit|Write|MultiEdit`) entry to timeout 60, statusMessage `"ruff (edited file)"`;
  - keep `Stop` at timeout 300, statusMessage `"ruff + pytest (this turn's changes)"`.

  Validate with `jq . .claude/settings.json`. The change takes effect live (research R2).
- [x] T011 [US1] Smoke-test the hooks by hand before writing tests, **in the scratch clone** (quickstart §1 "Scratch clone for hand-run hook checks"; set it up first). **Never in the live worktree**: once T010 is live, this session's own `turn-<id>.tsv` sits in the live state dir, and a hand-run `turn-start`/`stop` with a made-up `session_id` would adopt and delete it. From inside `$SMOKE`: **Done 2026-10-10** (scratch clone): first turn-start wrote turn-smoke.tsv; second left mtime unchanged; smoke2 adopted it (renamed); stop exit 0 with no change and deleted it; warm clean `edit` took 0.05s (SC-003 < 2s); a lint-red file gave exit 2 with findings. Live state dir did not exist yet (no prompt since T010), so nothing of this session was touched.
  - `echo '{"session_id":"smoke"}' | .claude/hooks/py-check.sh turn-start` creates `$(git rev-parse --git-path claude-harness)/turn-smoke.tsv`;
  - a second call leaves its mtime unchanged;
  - `echo '{"session_id":"smoke2"}' | .claude/hooks/py-check.sh turn-start` renames it to `turn-smoke2.tsv` (adoption);
  - `echo '{"session_id":"smoke2","stop_hook_active":false}' | .claude/hooks/py-check.sh stop` exits 0, runs no checks and deletes the file;
  - an `edit` payload naming a clean `.py` exits 0 in under 2s (SC-003), measured on a second run after the venv is warm. Record the measured time in this task's completion note, because SC-003 has no automated timing test.

  Afterwards, confirm the live state dir still holds this session's own `turn-*.tsv`.

### Tests for User Story 1

- [x] T012 [US1] Add turn-scoping tests to `tests/test_harness_hooks.py` (fixture from T008; drive `turn-start`, change the tree directly with Python file writes standing in for shell edits, then `stop`). One test per item:
  - (a) Scenario 1 / SC-001: a pre-existing dirty `pkg/bad.py` exists before turn-start, the turn edits only `pkg/clean.py`, and ruff is stubbed green. Stop exits 0, and the ruff argv in `uv_calls()` contains `pkg/clean.py` but not `pkg/bad.py`.
  - (b) Scenario 2 / SC-002: after turn-start, write `pkg/new.py` directly (no edit hook) with ruff stubbed red, output `pkg/new.py:1:5: F821 undefined name`. Stop exits 2, and stderr names `pkg/new.py` and `F821`.
  - (c) Scenario 3: change only `pyproject.toml`, then only `uv.lock`. Each time both pytest suites appear in `uv_calls()` and no ruff call has file args.
  - (d) Scenario 4 / FR-003: no change. Stop exits 0, `uv_calls()` is empty, and the snapshot is deleted.
  - (e) Deletion: `git rm` or unlink `pkg/clean.py`. The suites run, and no ruff call names the deleted path.
  - (f) FR-001: turn-start, modify a file, turn-start again. The snapshot bytes are unchanged and the modified file is still reported at stop.
  - (g) FR-010: no snapshot, with a committed file modified on disk. Stop treats it as changed (HEAD fallback). A corrupt snapshot (garbage line) behaves the same way.
  - (h) Files outside the repo (a `.py` under a second `tmp_path` dir) are never in any ruff argv.
- [x] T013 [US1] Add gate-behaviour tests to `tests/test_harness_hooks.py`:
  - (a) Scenario 6 / FR-009: on red, the first stop (`stop_hook_active: false`) exits 2 and keeps the snapshot. The second stop (`true`) exits 0, stdout is JSON whose `systemMessage` contains `still RED`, and the snapshot is gone.
  - (b) Scenario 7 / FR-006: stub pytest red with 300 lines of traceback and three `FAILED tests/test_x.py::test_n` lines at the **end**. The stderr block contains all three IDs, and that suite's block is ≤ 60 lines.
  - (c) Scenario 5 / FR-005: `edit` with a `.py` `file_path` produces exactly one `uv` call, a `ruff` one, and no `pytest`. `edit` with a `.md` path, or a `.py` outside the repo, produces zero calls.
  - (d) FR-007 / SC-007: across all modes, every logged `uv` argv contains `--locked`, except `edit`'s, which contains `--frozen`. Also, `uv.lock` bytes in the fixture repo are identical before and after a stop run.
  - (e) Fail closed: with `PATH` lacking `jq` (a dir holding only symlinks to `git`, `uv`-stub and coreutils), `edit` and `stop` exit 2 with `jq is required` on stderr, while `turn-start` still exits 0 with empty stdout.
  - (f) `session_id` with `../` and spaces is sanitised: the snapshot file stays inside the state dir.
- [x] T014 [US1] Add snapshot-adoption tests (FR-001, SC-010; data-model.md "Resolve step") to `tests/test_harness_hooks.py`:
  - (a) **`/clear` after an interrupted turn**: turn-start `A`, write `pkg/new.py` with red ruff stubbed, no stop, then turn-start `B`. `turn-B.tsv` holds `A`'s original bytes and `turn-A.tsv` is gone. Stop `B` exits 2 and names `pkg/new.py`.
  - (b) **`session_id` change mid-turn**: turn-start `A`, modify `pkg/clean.py`, then stop `B` with no turn-start `B`. The changed set includes `pkg/clean.py` (adopted at stop, not the HEAD fallback). Prove it by also leaving a pre-existing dirty file that was in `A`'s baseline, and check it's absent from the ruff argv.
  - (c) **Prune before adopt**: a pending `turn-A.tsv` with mtime 8 days back (`os.utime`) is deleted by turn-start `B`, which writes a fresh snapshot of the current tree. A file modified before that turn-start is not reported at stop `B`.
  - (d) **Multiple pending**: `turn-A.tsv` (older) and `turn-C.tsv` (newer, both under 7 days). Turn-start `B` yields `turn-B.tsv` with `A`'s bytes, and both `A` and `C` are gone.
  - (e) **Own snapshot wins**: with `turn-B.tsv` and `turn-A.tsv` both pending, turn-start `B` leaves both byte-identical (step 1 short-circuits).
- [x] T015 [US1] Document FR-011 in `CLAUDE.md`. In the harness paragraph (currently lines ~76-82, "**Ruff and both pytest suites are enforced by Claude Code hooks**…"), add one or two sentences: concurrent agent sessions are supported only as **one session per git worktree** (`claude --worktree` / `EnterWorktree`). The turn gate fingerprints the working tree, so it can't tell two sessions' edits apart inside one checkout, and a branch switch by another session shows up as this turn's change. Leave the rest of the paragraph for T040.

**Checkpoint**: Story 1 is fully functional and independently testable. `uv run --locked pytest tests/test_harness_hooks.py -q` is green, and edit-tool `.py` changes now trigger ruff only.

---

## Phase 4: User Story 3 - The always-loaded context can't silently drift (Priority: P3)

**Why before US2**: plan.md step 3. The stale facts (FR-023) must be fixed before the drift test exists, and the drift test only blocks turns through US1's gate. US2's `policy.sh` has no dependency on this phase.

**Goal**: The facts in CLAUDE.md and the reviewer prompt are true, and a pytest module keeps them true.

**Independent Test**: The drift test passes on the fixed tree. Each of quickstart §4's injections (wrong count, missing spec path, renamed identifier, dropped `(pending 009)`) makes it fail with `file:line` and the token.

### Stale-fact fixes (FR-023), before any drift test

- [x] T016 [US3] FR-023(a), architect-agent Temporal wiring, in `CLAUDE.md`. Commit `787cfe2` ("feat(005): wire architect-agent into Temporal (narrow plan-review slice)") added `ensure_target_pr_activity` + `architect_stage_activity`. `AgentPipelineWorkflow` now runs the architect stage ahead of Build behind `workflow.patched("architect-stage-v1")`, gated by `plan_approved`/`plan_rejected(feedback)` signals with a `MAX_PLAN_ATTEMPTS=3` budget. Still **not** done from 005: no `mode` param, no PM-stage wiring, no security signal, and budget exhaustion raises a bare `ApplicationError` rather than the escalation pair. Verify each name with `grep` in `orchestration/` before writing it, then update:
  - line ~20 "the planned `architect-agent`": it's built now;
  - the layer-table row at line ~42 ("known gaps (no Temporal wiring, not automatically gated, `MAX_PLAN_ATTEMPTS` not owned here)"): replace "no Temporal wiring" with "Temporal-wired as a narrow plan-review slice of feature 005", and check that "`MAX_PLAN_ATTEMPTS` not owned here" still holds (it's owned by the workflow);
  - the Orchestration row at line ~45: the loop is now architect stage → Build→Eval-Gate→Register. Replace "`AgentPipelineWorkflow` itself still has no `mode` param or `@workflow.signal` handlers" with: it has the `plan_approved`/`plan_rejected` signal handlers but still no `mode` param; the rest of 005 is pending. Keep the `BRIDGE_ALLOWED_REPOS` FR-016 caveat unless the code shows otherwise;
  - the build-order bullet at lines ~124-139: `004` "no Temporal wiring" → wired via 005's narrow slice. Change "`005`-`007` are spec.md-only today" so it says 005 is partially implemented (narrow slice) and 006-007 are spec.md-only.
- [x] T017 [US3] FR-023(b), registry entry count, in `CLAUDE.md`:
  - line ~47: "`registry/agents/{swe-agent,pm-agent}/` are the two entries" → "`registry/agents/{architect-agent,pm-agent,swe-agent}/` are the three entries". D-REG requires the brace list to equal the exact directory set, so all three names are needed in sorted order;
  - line ~161: "one of the two entries in `registry/agents/` (alongside `pm-agent`)" → "one of the three entries in `registry/agents/` (alongside `pm-agent` and `architect-agent`)".

  Then `grep -n "entries\|entry" CLAUDE.md` and check no other number word sits before `entries`/`entry` in a sentence that mentions `registry/agents`.
- [x] T018 [US3] FR-023(c), example spec, in `CLAUDE.md` line ~156. Replace "`specs/001-agent-spec-schema-test/` is the existing example" with "`specs/004-architect-fanout-judge/` is a complete example (spec, plan, research, contracts, tasks)". It exists, with `tasks.md`. If `specs/001-…` is mentioned anywhere else as a model to follow, re-point it the same way.
- [x] T019 [US3] FR-023(d), build order, in `CLAUDE.md`'s build-order bullet (lines ~124-139, the same bullet as T016). Add **feature 009** (credential-pool handoff, branch `009-credential-pool-handoff`, unmerged) and **feature 010** (this dev-harness hardening) **by number only**, never as `specs/00N-…` paths, because D-SPEC would fail on an absent directory (drift-conventions D-SPEC). For **feature 008**: no `008-*` branch or `specs/008-*` directory exists locally as of 2026-10-10, so run `git ls-remote --heads origin '008-*'`. If one exists, name it by number plus a one-phrase description from its spec. If not, don't invent one: leave 008 out and say so in the T044 report so the operator can resolve it. **Done 2026-10-10, feature-008 resolution:** `git ls-remote --heads origin '008-*'` returned nothing (exit 0; origin has one head, `main`), and no local `008-*` branch or `specs/008-*` dir exists. So 008 is left out of CLAUDE.md, and the operator must resolve it (T044 report). 009 and 010 are added by number only, as "Also in flight, outside that product sequence".
- [x] T020 [P] [US3] FR-023(e): rewrite the "Promotion threshold" section of `eval/gate-policy.md` (lines 8-10, which cite the retired schema's `success_criteria` and `guardrails.requires_human_approval`). Describe the actual v1 gate implemented by `eval/braintrust/eval.config.py::run_eval` and run only as the Temporal `eval_gate_activity`. It's a **binary coverage gate**: sandbox exit 0, a PR opened, and ≥ 1 `SC-NNN` criterion found in the branch's `specs/*/spec.md`. It doesn't score any criterion's content yet. Read `run_eval` first and state exactly its conditions. Keep "On fail" and "Ongoing" as they are, and mark per-criterion scoring as the eventual threshold, not current behaviour. This file is not drift-checked.
- [x] T021 [P] [US3] FR-023(f) and FR-021 in `.claude/agents/py-codereviewer.md`:
  - append ` (pending 009)` immediately after the closing backtick of each feature-009-only token: `pool.yaml` (line ~24), `CLAUDE_CODE_OAUTH_TOKEN` (lines ~57 and ~90), `CLAUDE_OAUTH_SEAT_*` (line ~57) and `seat_guard.py` (line ~100). On line ~57 the tokens are separate backtick spans in a comma list, so each 009 span gets its own marker and `GH_TOKEN` gets none;
  - add one sentence near the top defining the convention: "a backticked identifier followed by `(pending NNN)` belongs to unmerged feature NNN; the drift test exempts it until it exists, then demands the marker's removal";
  - in the commands block (lines ~38-40), use `uv run --locked ruff check .`, `uv run --locked pytest tests/ -q` and `(cd orchestration && uv run --locked pytest -q)` (R4).

### Drift test (FR-020, FR-022, SC-006)

- [x] T022 [US3] Create `tests/test_context_drift.py` with the **extractor only**: pure functions, a `collect_violations(repo_root: Path) -> list[str]`, and an `if __name__ == "__main__":` that prints violations. Add **no `test_` functions yet**. Implement contracts/drift-conventions.md exactly, using stdlib `re`/`pathlib` only. Each checker takes `(repo_root, text, source_name)` so tests can feed synthetic text:
  - **D-REG** (CLAUDE.md): path refs `registry/agents/<name>`, skipping `<…>` placeholders and globs, must be dirs. A brace list `registry/agents/{…}` must equal the dir set exactly. A number word `one`…`ten` directly before `entries`/`entry`, in a sentence (split on `. ` or a blank line) containing `registry/agents`, must equal the dir count.
  - **D-SPEC** (both files): `specs/(\d{3}-[a-z0-9][a-z0-9-]*)` must be a dir.
  - **D-ID** (reviewer prompt only): single-backtick spans, tokens split on whitespace, `,` and `/`, classified per the contract table (private name, UPPER_SNAKE, `PREFIX_*` wildcard, `*.py|yaml|toml` filename, repo path; dotted names and other text skipped). Searched over repo files, excluding `specs/`, `.claude/`, `.specify/`, `.git/`, `**/.venv/` and `node_modules/`, with tests included; word-boundary match in `*.py`.
  - **`(pending NNN)`**: a span followed by optional spaces then `(pending \d{3})` is exempt when its check fails, and is a violation when it passes (`now exists; remove the "(pending NNN)" marker`).
  - Messages use the FR-022 format exactly: `<file>:<line>: [D-…] …` with the expected value.

  Cache the `*.py` corpus once per run.
- [x] T023 [US3] Run the extractor in **report-only mode**: `uv run --locked python tests/test_context_drift.py`. Triage **every** hit (research R10 requires this before enabling). For each, either fix the doc (a genuinely stale fact) or fix the extractor (a false positive, e.g. a token class the contract excludes). The expected end state is zero violations, with the four 009 tokens exempt via `(pending 009)`. Also print the full candidate list once and check by hand that `_scrubbed()`, `_REPO_RE`, `_BRANCH_RE`, `_validate_*`, `_NO_AUTO_RETRY`, `_load_module_by_path`, `_connect_or_skip`, `MAX_*_ATTEMPTS`, `GH_TOKEN`, `ANTHROPIC_*`, `LITELLM_*`, `activities.py`, `agent.py`, `eval.config.py` and `pyproject.toml` are all classified and found. Record the triage outcome (hits and resolutions) in the task's completion note. **Done 2026-10-10, triage:** the report-only run gave **0 violations** on the fixed tree (after T016-T021); the four 009 tokens (`pool.yaml`, `CLAUDE_CODE_OAUTH_TOKEN` x2, `CLAUDE_OAUTH_SEAT_*`, `seat_guard.py`) are exempt via `(pending 009)`. No doc fix was needed at this step. Extractor fixes: (1) the hand check of `--candidates` showed span line numbers 3 too low below the fenced commands block. Fenced lines were blanked to `""`, which shifted offsets. They are now blanked to spaces of equal length, so the lines are correct. (2) The contract says tokens split on `/` but also has a 'repo path' class for tokens that contain `/`. Resolved as follows: split on whitespace and `,`. A token with `/` is a repo path when its first segment is an existing top-level dir; otherwise each `/` part is classified alone. Hand list: `_scrubbed()`, `_REPO_RE`, `_BRANCH_RE`, `_NO_AUTO_RETRY`, `_load_module_by_path` and `_connect_or_skip` are private and found. `_validate_*` is spelled out in the prompt as `_validate_target`/`_validate_repo`/`_validate_branch`, all private and found. `MAX_*_ATTEMPTS` is spelled out as `MAX_BUILD_ATTEMPTS`/`MAX_PLAN_ATTEMPTS`, both constants and found. `GH_TOKEN`, `LITELLM_MASTER_KEY`, `LITELLM_BASE_URL`, `ANTHROPIC_API_KEY` and `ANTHROPIC_BASE_URL` are constants and found; `ANTHROPIC_*` is a wildcard and found. `pyproject.toml` is a filename and found. `activities.py`, `agent.py` and `eval.config.py` appear only inside full paths (`orchestration/activities.py`, `harness/architect-agent/agent.py`, `eval/braintrust/eval.config.py`), so they are classified as paths and found. Per the contract, lowercase non-private names (`shape_issue`, `execute_activity`, `retry_policy`) fall under 'anything else' and are not checked, so a rename of those would go unnoticed. (3) The D-REG sentence split uses `\.\s` (a dot followed by any whitespace, newline included) for the contract's "`.` + space", plus blank lines, so a sentence that ends at a line wrap is split there too.
- [x] T024 [US3] Enable the drift test: add `test_` functions to `tests/test_context_drift.py`. **Done 2026-10-10:** 8 tests pass. An injected "two entries" in the live CLAUDE.md made (a) fail with `CLAUDE.md:47: [D-REG] "two entries" but registry/agents/ has 3: …`, and the file was restored. The placeholder test first passed vacuously: its tmp tree had no `specs/`, so `specs/NNN-slug/` was never classified as a path. With `specs/` present, D-ID flagged it. Fix: the path class now also skips `NNN` as a placeholder (`\bNNN\b`), next to globs and `<…>`, matching D-SPEC's treatment. The test now builds `specs/`. The contract doesn't list `NNN` for the path class, so this is open for the operator together with the `/`-split question in T023.
  - (a) `test_context_files_match_tree`: `collect_violations(REPO_ROOT)` is empty, and the assertion message lists every violation one per line.
  - (b) Injected-staleness tests (SC-006), each feeding synthetic text plus a `tmp_path` tree to the checkers:
    - "two entries" with three dirs gives `[D-REG]` with the count and names;
    - a brace list missing one dir gives `[D-REG]`;
    - `specs/099-nope` gives `[D-SPEC] specs/099-nope does not exist`;
    - `` `_validate_targets` `` absent from code gives `[D-ID]`;
    - `` `seat_guard.py` (pending 009) `` absent from code passes;
    - the same token present in a `*.py` gives the "remove the marker" violation;
    - a dotted name `` `workflow.now()` `` and the placeholder `specs/NNN-slug` are not flagged.
  - (c) Each violation string matches `^.+:\d+: \[D-(REG|SPEC|ID)\] ` (FR-022).

**Checkpoint**: Story 3 is complete. The drift test is green on the tree, and quickstart §4 injections each turn it red.

---

## Phase 5: User Story 2 - Repo rules are enforced before the action (Priority: P2)

**Goal**: AF-SECRET, AF-SPEC and AF-COMMIT run as one PreToolUse script. Each refusal names the rule and the fix.

**Independent Test**: Run `policy.sh` with synthetic payloads (no live wiring needed). Each rule has an allow and a refuse path, and each refusal's first line matches `^\[AF-[A-Z]+\] .+\. To proceed: .+$`. The live check is quickstart §3, after T037.

**Not wired in this phase.** `policy.sh` is wired into `.claude/settings.json` only in T037.

### Implementation for User Story 2

- [x] T025 [US2] Create `.claude/hooks/policy.sh` (bash, executable, sources `lib.sh`, bash 3.2-compatible) per contracts/hook-interface.md "`policy.sh` (PreToolUse)" and "Matching rules": **Done 2026-10-10:** one reading made explicit: the contract lists `tool_input.glob` for AF-SECRET, but the Glob tool has no `glob` field, so `.glob` is checked for Grep too (Grep's file filter); Grep's `pattern` (file content) is not checked. Pinned by a Grep `glob: ".env"` deny case in T027.
  - **Setup**: read the stdin payload, then `require_tools policy.sh jq git` (`uv` is required only on the AF-COMMIT path). Set `ROOT="${CLAUDE_PROJECT_DIR:-<script>/../..}"`. Paths outside `ROOT` (via `rel_path`) never match AF-SPEC or a Read-path secret check.
  - **Order**: AF-SECRET → AF-SPEC → AF-COMMIT. The first deny wins. If none matches: exit 0, no stdout.
  - **Deny output**: `jq -n` producing `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason": <msg>}}`, then exit 0. The first line of `<msg>` is the **exact** text from the contract's "Rule messages" table.
  - **AF-SECRET**:
    - Read: basename of `.tool_input.file_path` ∈ {`.env`, `.env.braintrust`}.
    - Grep/Glob: the same check on `.tool_input.path`, plus `.tool_input.pattern`/`.glob` for Glob.
    - Bash: `.tool_input.command` matches `(^|[[:space:]/'"=<])\.env(\.braintrust)?($|[[:space:];|&)'"<>*?[{])` (use `[[ =~ ]]` with the regex in a variable).
    - `.env.example` must never match.
  - **AF-SPEC**:
    - Applies to tools Edit/Write/MultiEdit/NotebookEdit (`.file_path // .notebook_path`) with `rel` matching `^(harness|orchestration|eval)/`.
    - NNN = `feature_number "$ROOT"` (lib.sh); empty means no feature branch, which includes detached HEAD.
    - Pass iff NNN is non-empty and some `specs/<NNN>-*/tasks.md` exists. Otherwise deny, with detail line(s) naming the observed branch (`git symbolic-ref --short -q HEAD`, or `(detached)`) and whether tasks.md was found.
    - `.claude/`, `docs/`, `specs/`, `CLAUDE.md` and `README.md` never match (FR-019).
  - **AF-SPEC exception (FR-018)**: if AF-SPEC would deny and `AF_SPEC_EXCEPTION` is non-empty, allow instead. If `exception-<session_key>.notified` is absent in `state_dir`, print `{"systemMessage":"[AF-SPEC] exception active for this session (AF_SPEC_EXCEPTION=<value>)."}` and touch the marker; otherwise print nothing. The exception is never consulted by AF-SECRET or AF-COMMIT.
  - **AF-COMMIT**:
    - Match: Bash command contains both `(^|[^[:alnum:]_.-])git($|[^[:alnum:]_.-])` and `(^|[^[:alnum:]_.-])commit($|[^[:alnum:]_.-])`.
    - On a match: `require_tools policy.sh uv`, then `run_check "ruff check ." uv run --locked --directory "$ROOT" ruff check --output-format concise .` and `run_suites "$ROOT"`.
    - If red, deny with the AF-COMMIT first line followed by `$failures`. If green, no decision.
  - **Header comment**: list the rule IDs, the evaluation order and the documented gaps: shell writes under guarded dirs are not pre-checked (FR-013), and shell secret reads are best-effort (FR-016).
- [x] T026 [US2] Smoke-test `policy.sh` by hand (it's unwired, so call it directly):
  - `echo '{"tool_name":"Read","tool_input":{"file_path":"'"$PWD"'/.env"}}' | .claude/hooks/policy.sh` denies with `[AF-SECRET]`;
  - the same with `.env.example` prints nothing;
  - an Edit payload for `$PWD/harness/template-agent/agent.py` on this branch prints nothing (010 has tasks.md);
  - `{"tool_name":"Bash","tool_input":{"command":"git commit --dry-run"}}` runs the real gate and prints nothing, because the tree is green.

### Tests for User Story 2 (SC-004, SC-005)

- [x] T027 [US2] Add AF-SECRET tests to `tests/test_harness_hooks.py` (fixture from T008):
  - deny: Read `<repo>/.env`, Read `<repo>/.env.braintrust`, Grep with `path: <repo>/.env`, Glob with `pattern: ".env"`, and Bash `cat .env`, `grep KEY .env`, `cat ./.env`, `cat .env*`, `cat .env{,.braintrust}`, `source .env`, `x=$(<.env)`;
  - allow (no stdout): Read `.env.example`, Bash `cat .env.example`, `echo $HOME`, `ls`.

  Every deny asserts the parsed JSON `permissionDecision == "deny"` and a reason whose first line matches `^\[AF-SECRET\] .+\. To proceed: .+$`. No `uv` call is logged.
- [x] T028 [US2] Add AF-SPEC tests to `tests/test_harness_hooks.py`. Switch branches with `git switch -c` in the fixture repo and create `specs/<NNN>-x/tasks.md` as needed.
  - deny: branch `scratch` + Edit `harness/a.py`; branch `042-x` with no `specs/042-*/tasks.md`; detached HEAD; Write to `orchestration/x.py`; NotebookEdit `eval/n.ipynb`;
  - allow: `042-x` with `specs/042-x/tasks.md`; `worktree-042-x` with the same; branch `scratch` editing `docs/a.md`, `specs/a.md`, `.claude/hooks/x.sh`, `CLAUDE.md`, `README.md`, `tests/a.py`; a path outside the repo.

  Denies assert the `[AF-SPEC]` + `To proceed:` first line and that the detail names the branch.
- [x] T029 [US2] Add FR-018 exception tests to `tests/test_harness_hooks.py`, with `env_extra={"AF_SPEC_EXCEPTION": "hotfix"}` and the same `session_id`:
  - the first would-be AF-SPEC deny produces no `permissionDecision`, a `systemMessage` containing `exception active` and `hotfix`, and the `exception-<sid>.notified` marker file;
  - the second call produces empty stdout;
  - with the exception set, Read `.env` is **still** denied (`[AF-SECRET]`), and a commit with red stubs is **still** denied (`[AF-COMMIT]`).
- [x] T030 [US2] Add AF-COMMIT tests to `tests/test_harness_hooks.py`:
  - **green stubs**: `git commit -m x` produces no decision, and `uv_calls()` shows `ruff check … .` plus both pytest suites, all with `--locked`;
  - **red pytest stub**: deny; the first line matches `^\[AF-COMMIT\] .+\. To proceed: .+$` and the reason contains the stubbed `FAILED` id;
  - **matching shapes** (each red → deny): `git -C /x commit -m y`, `cd a && git commit --amend`, `git add . && git commit`, `git  commit`;
  - **non-matching** (zero `uv` calls): `git status`, `git log --grep=committee`, `echo gitcommit`;
  - **fail closed**: `PATH` without `uv` + a commit command → exit 2, `uv is required`, while a `git status` payload under the same `PATH` exits 0;
  - **ordering**: `cat .env && git commit` is denied as `[AF-SECRET]` with zero `uv` calls.

**Checkpoint**: `policy.sh` is complete and fully tested, but not yet live.

---

## Phase 6: User Story 4 - Context budget and continuity (Priority: P3)

**Goal**: The operator and the agent are warned once per level as context nears the 150k budget. After `/compact` or `/clear` on a feature branch, the agent gets a continuity block. Nothing ever blocks (FR-028, FR-029, FR-031). The cap itself (FR-027) and the SessionStart wiring land in T037. CLAUDE.md's rules (FR-030) land in T041.

**Independent Test**: Feed `turn-start` fixture transcripts at 100k / 125k / 140k / 152k / 40k / 121k: notices appear exactly at 125k (warn), 152k (budget) and 121k (re-armed warn), and every run exits 0 with empty-or-JSON stdout. Feed `session-context.sh` a `compact` payload on a `042-x` fixture branch with a `tasks.md`: it emits the branch, spec dir and the first three unchecked tasks. On `main` it emits nothing (SC-008, SC-009).

**Not wired in this phase**, except that `turn-start` is already live from T010. Its warn path only ever emits a notice, never a block.

### Implementation for User Story 4

- [x] T031 [US4] Add the context warning (FR-028) to `turn-start` in `.claude/hooks/py-check.sh`, after the snapshot step, per contracts/hook-interface.md "`py-check.sh turn-start`" and data-model.md "Context budget":
  - **Read**: if `jq` is missing, `transcript_path` is empty or the file isn't readable, skip silently. Otherwise run `tail -n 200 "$transcript_path" | jq -R -c 'fromjson? | select(.type=="assistant" and (.isSidechain != true) and .message.usage) | .message.usage | (.input_tokens // 0) + (.cache_read_input_tokens // 0) + (.cache_creation_input_tokens // 0)'` and keep the last line. Not a non-negative integer → skip.
  - **Level**: `budget` if ≥ `CTX_BUDGET`, `warn` if ≥ `CTX_WARN`, else `none`. The marker is `"$(state_dir)"/ctx-<session_key>.level`.
  - **Transitions**:
    - `none` → delete the marker (re-arm), no output;
    - level above the marker (`warn` > nothing, `budget` > `warn`) → print the notice and write the level to the marker;
    - otherwise → no output.
  - **Notice**: one `jq -n` object with `systemMessage` and `hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext}`. Use the exact wording from the contract, with sizes as whole k rounded down (`$((n / 1000))k`). At the `budget` level, say `at or over the 150k budget`.
  - **Exit**: still always exit 0. Stdout is either empty or exactly that one object, with nothing else echoed. Guard every command so a failure in this block can't stop the snapshot step that already ran.
- [x] T032 [US4] Create `.claude/hooks/session-context.sh` (bash, executable, sources `lib.sh`, bash 3.2-compatible) per contracts/hook-interface.md "`session-context.sh`" and data-model.md "Continuity context":
  - **Exit**: always exit 0. Do **not** use `require_tools`, which exits 2. If `command -v jq`/`git` fails, exit 0 silently.
  - **Source**: read `.source` from the payload. Anything but `compact`/`clear` → exit 0, no output.
  - **Inputs**: `ROOT="${CLAUDE_PROJECT_DIR:-<script>/../..}"`, `branch=$(git symbolic-ref --short -q HEAD)`, `dir=$(feature_spec_dir "$ROOT")`. Empty `dir` → exit 0, no output. **Don't** read `.specify/feature.json`.
  - **Next tasks**: `grep -m 3 -E '^- \[ \] T[0-9]+' "$ROOT/$dir/tasks.md"`, each line cut to 160 characters, or `no tasks.md` if the file is absent.
  - **Gate**: `snapshot pending (this turn's changes will be checked at Stop)` if any `turn-*.tsv` exists in `state_dir`, else `clear`.
  - **Output**: build the continuity block in the contract's exact layout (`[harness] Context was compacted|cleared. Resume from disk, not memory:` … `policy rules: AF-SPEC AF-SECRET AF-COMMIT AF-REGISTRY AF-HARNESS (see CLAUDE.md)`). Print `{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext": <block>}}` via `jq -n --arg`.
  - **Header comment**: states that the script never blocks (FR-029/FR-031) and that there's deliberately no PreCompact hook.
- [x] T033 [US4] Smoke-test both by hand **in a freshly refreshed scratch clone** (quickstart §1 "Scratch clone…"; re-run its `rsync` so T031/T032 are included). The `turn-start` call would otherwise adopt this session's live snapshot (see T011). From inside `$SMOKE`: **Done 2026-10-10** (scratch clone): (a) the real transcript parsed to 138,476 tokens, matching the session's actual use (~140k); turn-start printed one warn notice (`139k of 150k`), exit 0, and wrote `ctx-smoke.level` next to `turn-smoke.tsv`. (b) `compact` gave branch `010-dev-harness-hardening`, `specs/010-dev-harness-hardening/`, T031-T033 as next tasks and `snapshot pending`; `startup` printed nothing, exit 0. T031 note: the jq filter adds `objects` and wraps the sum in `try … catch "invalid"` so one malformed entry can't abort the stream; "invalid" fails the integer check (= unknown, skip). T032 note: no `set -u` (an unbound variable would exit non-zero); a tasks.md with no unchecked line prints `(no unchecked tasks)`.
  - (a) **Real transcript**: find this session's own transcript (the newest `*.jsonl` under `~/.claude/projects/<this worktree's project slug>/`; reading it from the clone is fine). Run `echo '{"session_id":"smoke","transcript_path":"<that path>"}' | .claude/hooks/py-check.sh turn-start`. Expect empty output below 120k, or a notice at or above it. Either way, confirm that the parsed number is close to `/context`'s figure; that proves the parse works on the real format, not just fixtures.
  - (b) **Continuity**: `echo '{"source":"compact"}' | .claude/hooks/session-context.sh | jq -r .hookSpecificOutput.additionalContext` shows branch `010-dev-harness-hardening`, `specs/010-dev-harness-hardening/` and the next three unchecked tasks of this file.

### Tests for User Story 4

- [x] T034 [US4] Add context-warning tests (SC-008) to `tests/test_harness_hooks.py`. Add a fixture helper `write_transcript(path, entries)` that writes JSONL assistant entries with `usage` split across the three token fields, plus optional raw lines. Every case asserts exit 0, stdout empty or `json.loads`-able, and that the turn snapshot was still written.
  - (a) **Below warn**: 100k → empty stdout, no marker.
  - (b) **Warn**: 125k → `systemMessage` contains `125k` and `150k`, `hookSpecificOutput.hookEventName == "UserPromptSubmit"`, non-empty `additionalContext`, and the marker holds `warn`.
  - (c) **No repeat**: then 140k → empty.
  - (d) **Budget**: then 152k → a notice containing `at or over`, and the marker holds `budget`. Then 155k → empty.
  - (e) **Re-arm**: then 40k → empty and the marker is deleted. Then 121k → a warn notice again.
  - (f) **Silent cases**: no `transcript_path`; a nonexistent path; only `user` entries; a high entry with `isSidechain: true` as the only assistant entry; non-numeric usage. Each gives empty stdout.
  - (g) **Partial last line**: a truncated last line after a valid 130k entry → the 130k entry is used (warn notice).
  - (h) **Bounded read**: 5,000 filler lines then a 130k entry → notice. A 130k entry followed by 300 filler lines → no notice (outside the 200-line tail).
- [x] T035 [US4] Add continuity tests (SC-009) to `tests/test_harness_hooks.py`, driving `session-context.sh`:
  - (a) Branch `042-x` with `specs/042-x/tasks.md` holding one checked and five unchecked `T…` lines, and `source: compact` → `hookEventName == "SessionStart"`. `additionalContext` contains `compacted`, `042-x`, `specs/042-x/`, the first three unchecked IDs in order, neither the fourth nor the checked one, and all five rule IDs.
  - (b) `source: clear` → `cleared`.
  - (c) A `turn-x.tsv` in the state dir → `snapshot pending`; none → `clear`.
  - (d) `worktree-042-x` works the same as `042-x`.
  - (e) **Empty output, exit 0** in each of these cases: branch `main`; branch `043-y` with no `specs/043-*`; `source` `startup` or `resume`; detached HEAD; `PATH` without `jq`.
  - (f) Spec dir without `tasks.md` → output containing `no tasks.md`.
  - (g) A 300-character task line is truncated to 160 characters.

**Checkpoint**: The US4 scripts are complete and tested. The warning is live through T010's UserPromptSubmit wiring. Continuity and the cap go live in T037.

---

## Phase 7: Pre-activation hook review

**Purpose**: The last chance to edit `.claude/hooks/**` without operator prompts.

- [x] T036 Run the `py-codereviewer` subagent (`.claude/agents/py-codereviewer.md`) on `.claude/hooks/lib.sh`, `.claude/hooks/py-check.sh`, `.claude/hooks/policy.sh`, `.claude/hooks/session-context.sh`, `tests/test_harness_hooks.py` and `tests/test_context_drift.py`, naming the `.sh` files explicitly. Ask it to check in particular:
  - bash 3.2 compatibility;
  - argv-only arguments;
  - that `turn-start` and `session-context.sh` can never exit non-zero or print non-JSON;
  - that `resolve_snapshot` can't delete the caller's own snapshot.

  Apply its findings **now**, because after T037 every `.claude/hooks/**` edit prompts the operator. Re-run both suites.

  **Done 2026-10-11.** On the four questions, the reviewer found no bash 3.2 or argv-only violations. `turn-start`/`session-context.sh` hold the never-block contract (one transcript hole, see 4). `resolve_snapshot` keeps the caller's own snapshot within a call. Six findings, all fixed. Gates after the fixes: ruff clean, `tests/` 176 passed, `orchestration/` 72 passed.
  1. **Major, AF-SECRET bypass.** `is_secret_path` ran `rel_path` first, so a `..` path (`<root>/pkg/../.env`) and any path outside the repo were never checked. That was stricter than the contract's "basename of `file_path`", and it opened a hole. `.ENV` (case-insensitive volume) and a Grep `glob: ".env*"` also got through. Fix in `policy.sh`: it now takes the basename of the raw value, lower-cases it, and checks it against {`.env`, `.env.braintrust`} in any directory. For Grep `glob` and Glob `pattern`, a basename that matches `SECRET_RE` (`.env*`, `.env{,.braintrust}`) is denied too. **Contract extensions for the operator to approve** (hook-interface.md "Matching rules" doesn't say this yet): case-folding, and `SECRET_RE` on the glob fields. Dropping the inside-the-repo restriction is the contract's literal reading, and `/elsewhere/.env` is now pinned as denied. 5 deny cases and 2 allow cases added. **Not fixed, left open:** AF-SPEC has the same `..`/case gap (`<root>/docs/../harness/a.py`, `<root>/Harness/a.py` skip the check). It is lower severity because shell writes already bypass AF-SPEC (FR-013) and the turn gate still judges them at Stop.
  2. Corrupt-snapshot test: it now commits an unchanged `pkg/other.py` and asserts it isn't linted, so a garbage snapshot taken as usable would fail it.
  3. Tests that couldn't fail: (a) added a FAILED-first + 300-line-tail trimming case next to T013(b)'s, which a plain `tail` also passes; (b) the shell-made-file test now checks ruff's argv, and the deleted-file test asserts ruff isn't called; (c) the drift test's synthetic D-ID case now uses made-up `_frob_target(s)`, because this file is in the live D-ID corpus and `_validate_target` there masked a rename in `activities.py`.
  4. `context_warn`: jq's `+` concatenated digit strings (`"13"+"0000"` → a false 130k warn; `"0"+"9"+"99999"` → an octal error in `$(( ))`). The filter now gives `"invalid"` unless all three fields are numbers, and the integer regex rejects leading zeros. Two cases added.
  5. Added never-fail tests: `turn-start` and `session-context.sh` exit 0 with empty stdout on non-JSON stdin, empty stdin, a missing `lib.sh` and no `git`. Added fail-closed tests: `stop` without git, and `policy.sh` without git or without jq, give exit 2. **Skipped:** the reviewer's "state dir mode 0500" case. It passes vacuously when run as root, and the never-fail path is already covered.
  6. `resolve_snapshot` no longer word-splits `$(ls -tr)`. It finds the oldest snapshot with a glob loop and `-ot`, and every loop skips the caller's own file by name. A tie on mtime falls to glob order. The T014 adoption tests pass unchanged.

---

## Phase 8: Activation (completes US2 and US4; last `.claude/settings.json` change)

**Purpose**: Wire PreToolUse, the permission rules, SessionStart and the compaction cap. After T037, AF-HARNESS is live, and edits to `.claude/settings*.json` and `.claude/hooks/**` prompt the operator. That is the intended steady state.

- [x] T037 [US2] (+US4) Make the final edit to `.claude/settings.json` (contracts/hook-interface.md "Wiring"). Make it in **one** edit, because it covers both US2 and US4:
  - add a `PreToolUse` entry with matcher `Edit|Write|MultiEdit|NotebookEdit|Read|Grep|Glob|Bash` → `"$CLAUDE_PROJECT_DIR"/.claude/hooks/policy.sh`, timeout 300, statusMessage `"repo policy (AF-*)"`;
  - add a `SessionStart` entry with matcher `compact|clear` → `"$CLAUDE_PROJECT_DIR"/.claude/hooks/session-context.sh`, timeout 10 (FR-029). **No** `PreCompact` entry (FR-031);
  - add `"env": {"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "150000"}` (FR-027; must equal `CTX_BUDGET`);
  - add `"permissions": {"deny": ["Read(./.env)", "Read(./.env.braintrust)"], "ask": ["Edit(./registry/agents/*/manifest.yaml)", "Edit(./registry/agents/*/versions/**)", "Edit(./.claude/settings.json)", "Edit(./.claude/settings.local.json)", "Edit(./.claude/hooks/**)"]}`.

  Validate with `jq .`. Confirm live that a Read of `.env` is now refused with `[AF-SECRET]`.

  **Done 2026-10-11.** `jq` validates the file: 8 tool names in the PreToolUse matcher, no `PreCompact`, cap `"150000"`. Live in the same session, without a relaunch: a `Read` of `./.env` was refused by `permissions.deny` ("denied by your permission settings"), which runs before the hook, so no `[AF-SECRET]` line appeared there. The PreToolUse hook itself is live too: a `Bash` command that mentioned `.env` was refused with the full `[AF-SECRET] … To proceed: …` line. No `.env` exists in the worktree, so no secret was at risk.
- [x] T038 [US2] (+US4) Add settings tests (R11) to `tests/test_harness_hooks.py`. Load the **real** repo `.claude/settings.json` and assert each `deny`/`ask` string above is present. Then, with a small gitignore-style matcher written in the test (`*` doesn't cross `/`, `**` does, leading `./` = repo root), assert:
  - AF-REGISTRY covers `registry/agents/swe-agent/manifest.yaml` and `registry/agents/pm-agent/versions/0.1.0.yaml`, but not `registry/agents/swe-agent/SKILL.md`;
  - AF-HARNESS covers `.claude/settings.json`, `.claude/settings.local.json` and `.claude/hooks/policy.sh`, but not `.claude/agents/py-codereviewer.md`;
  - the deny rules cover `.env` and `.env.braintrust`, but not `.env.example`;
  - the PreToolUse matcher includes all eight tool names, and the UserPromptSubmit, PostToolUse and Stop wiring from T010 is present;
  - **US4**: a `SessionStart` entry with matcher `compact|clear` runs `session-context.sh`; there's no `PreCompact` key (FR-031); and `env.CLAUDE_CODE_AUTO_COMPACT_WINDOW` equals the `CTX_BUDGET` value parsed from `.claude/hooks/lib.sh` with `^CTX_BUDGET=(\d+)$`.
- [x] T039 [P] [US2] Add a short "Repo harness" section to `.claude/agents/py-codereviewer.md` for reviewing the hook scripts. Cover:
  - bash 3.2 compatibility;
  - argv-only arguments;
  - fail-closed exit 2 for missing tools in `edit`/`stop`/`policy.sh`;
  - `--locked`/`--frozen` on every `uv run`;
  - the exact `[AF-…] … To proceed: …` first-line contract;
  - `turn-start` and `session-context.sh` must always exit 0, with empty-or-single-JSON stdout.

  Reference `.claude/hooks/lib.sh`, `.claude/hooks/py-check.sh`, `.claude/hooks/policy.sh` and `.claude/hooks/session-context.sh` by path (they exist now, so D-ID path checks pass). Re-run `uv run --locked pytest tests/test_context_drift.py -q`.
- [x] T040 [P] [US2] FR-024 + FR-013/FR-016/FR-026 documentation in `CLAUDE.md`. Rewrite the harness paragraph at lines ~76-82, keeping T015's worktree sentences, to describe the shipped behaviour:
  - per-edit ruff on the edited file only;
  - a `UserPromptSubmit` snapshot (adopted across `/clear`) plus a `Stop` gate that runs ruff on the turn's changed `.py` files and both suites only when the turn changed Python-relevant files (including shell edits), with the one-block loop guard;
  - the AF-COMMIT commit gate;
  - `uv run --locked` everywhere.

  Add a **rule catalogue** table: ID | mechanism (`policy.sh` / `permissions.ask` / `permissions.deny`) | what it covers | how to satisfy it, for AF-SPEC, AF-SECRET, AF-COMMIT, AF-REGISTRY and AF-HARNESS. Give the ask patterns verbatim so the operator can tell which rule prompted.

  Document the single exception: `AF_SPEC_EXCEPTION="<reason>" claude`, set at launch, AF-SPEC only, announced once.

  State the known gaps explicitly:
  - shell writes under `harness/`, `orchestration/` and `eval/` are not pre-checked but are caught at Stop (FR-013);
  - shell reads of `.env` are denied best-effort only (FR-016);
  - shell edits to `.claude/settings*.json` and `.claude/hooks/**` are uncovered (FR-026);
  - `permissions.ask` has no human under `bypassPermissions` in the E2B sandbox (R1).

  Also update the Commands block's `uv run pytest`/`uv run ruff check .` lines to `--locked` (R4). Keep "Before committing a Python change, run `py-codereviewer`". Re-run the drift test.

  **Done 2026-10-11.** Also fixed a stale fact in a Commands line already being edited: the orchestration suite covers `orchestration/tests/` as well as `orchestration/webhook_bridge/tests/`.
- [x] T041 [US4] FR-030: add a **"Context budget"** section to `CLAUDE.md` next to the harness paragraph. It comes after T040 because both edit the same file. It covers:
  - **Budget and enforcement**: budget 150k, warn at 120k (`CTX_BUDGET`/`CTX_WARN` in `.claude/hooks/lib.sh`). The cap is `env.CLAUDE_CODE_AUTO_COMPACT_WINDOW` in `.claude/settings.json`, AF-HARNESS-protected per FR-026. The warning comes from `turn-start` and is best-effort, reading Claude Code's internal transcript. Continuity is the `SessionStart(compact|clear)` hook.
  - **`/clear`** between Spec Kit phases (specify → plan → tasks → implement) and after each feature commit; the `specs/NNN-*/` directory on disk is the handoff.
  - **`/compact <focus>`** only at a task boundary with the gate green, never mid-task or with the gate red.
  - **`tasks.md`** checkboxes are ticked as each task finishes.
  - **Compaction paragraph**: "When compacting, preserve: current task ID, files modified in this task, failing test IDs, and decisions not yet written to the spec directory."

  Refer to features by number only (D-SPEC). Re-run the drift test. **If** T045's live check shows the `env` cap isn't honoured, this section names `claude --autocompact 150k` (or `export CLAUDE_CODE_AUTO_COMPACT_WINDOW=150000`) as the launch convention instead (FR-027).

  **Done 2026-10-11** with the contract's default wording (the `env` cap). Whether the cap is honoured from project settings is T045 §6.1, operator-pending; the fallback wording is not applied yet.

**Checkpoint**: All four stories are live. `uv run --locked pytest tests/ -q` and the orchestration suite are green.

---

## Phase 9: Polish & cross-cutting

- [x] T042 Run the `py-codereviewer` subagent on everything changed since `28221cc` that T036 didn't cover: `orchestration/pyproject.toml`, the three `pytestmark` modules, `tests/test_harness_hooks.py` additions from T038, and `.claude/settings.json` (named explicitly). Fix findings. Any fix to `.claude/settings.json` or `.claude/hooks/**` now prompts the operator; that's expected.
  **Done 2026-10-11.** Three reviewers ran: py-codereviewer, shell-reviewer and senior-architect-reviewer. The operator decided each item on 2026-10-11.
  - **py-codereviewer: APPROVE**, with one minor finding. **Fixed:** the seven `permissions` rules used `./…`, which Claude Code resolves against the session's start directory, so a session started in `orchestration/` got no AF-REGISTRY or AF-HARNESS prompt. All seven now use `/…` (project root). Changed: `settings.json`, `_DENY`/`_ASK`/`_rule_covers` in `tests/test_harness_hooks.py`, the CLAUDE.md rule table, the hook-interface.md Wiring block and research.md. The T037/T038 text above is kept as written.
  - **shell-reviewer #1 (contract breach). Fixed:** `py-check.sh` checked `uv` before it knew it would run it. Without `uv`, a Markdown edit exited 2, and Stop exited 2 on turns with no Python change. `uv` is now checked after the `*.py` filter in `edit` and after the nothing-changed exit in `stop`. New test: `test_missing_uv_fails_closed_only_where_uv_runs`.
  - **Re-review of both fixes (one round): no findings.** py-codereviewer APPROVE. shell-reviewer confirmed the new test fails on the old order of either mode. Still open: only a live session started in a subdirectory proves that the `/` rules prompt there (T045).
  - **Before merge** (the operator chose to commit on 889785f now and rebase later):
    1. Rebase onto `origin/main`, which has 009 and 011 merged and `specs/008-gate-decision-core/`. Expect conflicts in CLAUDE.md, `sandbox/swe-agent/Dockerfile`, `orchestration/pyproject.toml`, `orchestration/tests/test_pipeline_workflow.py` (011 added seat-pool wait tests) and `test_e2e_pipeline_gate.py`. Keep 889785f's race fixes.
    2. Re-run `uv lock` for both pyproject/uv.lock pairs. Then drop the five `(pending 009)` markers.
    3. In CLAUDE.md: 009 and 011 merged, 008 cited by path (this closes T019). Fix main's pyproject comment that says the hook runs the suite "on every .py edit".
    4. Mark `orchestration/tests/test_credential_pool.py` as `temporal`.
    5. Rebuild the `swe-agent-sandbox` E2B template with the merge. Until then, `policy.sh` fails closed (no `jq`/`uv`) for any sandbox run that targets this repo. Pin `jq` too.
    6. Operator decision: AF-COMMIT denies the red commit that swe-agent's `IMPLEMENT_PROMPT` asks for ("commit even if verification doesn't pass"). Either record that as a known gap, or exempt the sandbox through an env marker.
    7. Operator ruling: settle AF-SECRET's code against the contract. Case-folding and the Grep `glob`/Glob `pattern` checks already ship in `policy.sh`.
  - **Before-merge status, 2026-10-11 (rebased onto `origin/main` 40a2c40):**
    1. Done. The feature commit was replayed first (as 7d005ba), so `specs/010-*` existed for AF-SPEC; 889785f followed as 6a11de4. Conflicts: CLAUDE.md keeps 010's rows plus main's 009/011 text and `seat_smoke.py` command; `orchestration/pyproject.toml` keeps main's `timeout = 60` next to the `temporal` marker. 889785f's `test_pipeline_workflow.py` half was dropped: main fixed the same signal race its own way (`_wait_plan_parked`, `_result`, `EXECUTION_TIMEOUT`). The Dockerfile replayed without conflict. Leftover: 7d005ba's message still says "Based on 889785f; must be rebased onto origin/main before merge". Rewording it needs a reset, which was denied in this session, so it is left for the operator.
    2. Done. `--locked` passes for both pairs, so `uv lock` was not re-run and both lockfiles equal main's. The five `(pending 009)` markers are dropped; the drift test failed on them right after the rebase, as designed.
    3. Done. CLAUDE.md: 009 and 011 merged, `specs/008-gate-decision-core/` (Draft) cited by path, 010 in flight. T019 is closed. The pyproject comment now names the Stop gate and AF-COMMIT.
    4. Done. The module mixes pure and live tests, so the 18 `_running_pool` tests carry a per-test `@pytest.mark.temporal`, not a `pytestmark`.
    5. Done 2026-10-11 (88862ba, after the merge). The `swe-agent-sandbox` E2B template was rebuilt and runs `jq-1.7` and `uv 0.10.0`. uv now comes from pip; see T043.
    6.–7. Open. Moved to the follow-up spec, specs/012 (operator decision, 2026-10-11).
    Gates: ruff clean; `tests/` 271 passed; `orchestration/` 167 passed; with `-m "not temporal"` 120 passed, 47 deselected. Local arm64 `docker build` of the sandbox image prints `jq-1.7` and `uv 0.10.0`; image removed afterwards.
  - **Deferred follow-ups** (the operator chose to record them all, with no further hook edits in this commit):
    - Gate overrun: the policy hook has a 300s timeout. A timeout is a non-blocking error, so a slow live-Temporal suite lets the commit through. Wrap the suites in a shorter inner timeout that denies on overrun.
    - Without `uv`, a turn that changed Python is blocked on every Stop retry: `require_tools` exits before the `stop_hook_active` guard.
    - The second red Stop deletes the snapshot (`py-check.sh` loop-guard path), so the next turn adopts a red tree as its baseline. Keep it, and update contract step 5.
    - The AF-SECRET message says ".env files are never read" even for Bash writes such as `cp .env.example .env`. Use Bash-specific wording.
    - The Bash secret regex doesn't fold case and misses the `` ` `` `@` `{` `,` delimiters (FR-016 best effort).
    - `lib.sh` prunes only `turn-*.tsv`. Prune `ctx-*.level` and `exception-*.notified` too.
    - No gate runs shellcheck. It reports only SC2034 (a false positive, `lib.sh:11-12`) and SC1091.
    - An unsourceable `lib.sh` makes `policy.sh` deny every tool call. Document the manual recovery, or allow edits under `.claude/hooks/**` in that case.
    - The D-ID corpus walks untracked and ignored files. Use `git ls-files -co --exclude-standard`.
    - Add a test that every test reaching `_connect_or_skip` carries the `temporal` mark (per test, since `test_credential_pool.py` mixes pure and live tests).
    - AF-SPEC denies edits during a `git rebase` conflict: HEAD is detached (no `NNN-` branch name), and `specs/NNN-*/tasks.md` may not exist yet mid-replay.
    - Docs-only edits don't trigger the drift test at Stop, so drift first fails at the next AF-COMMIT.
    - Verify that ROOT follows a mid-session `EnterWorktree`; until then, recommend `claude --worktree`.
    - AF-COMMIT misses `revert`, `cherry-pick`, `merge`, `am` and `rebase`.
    - `policy.sh` allows on unreadable or empty stdin (theoretical).
    - The context warning may read a stale pre-compaction usage value (uncertain).
- [x] T043 Verify FR-025 without editing it: `git diff sandbox/swe-agent/Dockerfile` shows `jq` in the apt line and `COPY --from=ghcr.io/astral-sh/uv:0.10.0 /uv /uvx /bin/` (research R13). Leave it **unchanged**; it's committed with the feature in T046. If Docker is available, run quickstart §5 (`docker build … && docker run … 'jq --version && uv --version'` → uv 0.10.0); otherwise note it as unrun. The operator has `E2B_API_KEY` and the `e2b` CLI set up (2026-10-10). Rebuilding the real `swe-agent-sandbox` template (`e2b template build` in `sandbox/swe-agent/`) changes what live `swe-agent` runs use, so do it **only with explicit operator approval**, after the feature is merged or on the operator's instruction. A local `docker build` is the default check.
  **Superseded 2026-10-11 by 88862ba:** E2B's builder rejects the multi-stage `COPY --from`, so uv 0.10.0 now comes from `pip install --no-cache-dir "uv==0.10.0"` (research R13).

  **Done 2026-10-11.** The diff shows both lines; the Dockerfile is unchanged. Local arm64 build (Docker 29.2.1, aarch64) printed `jq-1.7` and `uv 0.10.0`. Quickstart §5's build command used `sandbox/swe-agent` as the context, which fails on `COPY harness/swe-agent/agent.py`; it now builds from the repo root with `-f`, as the Dockerfile's own header says, and removes the image afterwards. `e2b template build` not run.
- [x] T044 Run quickstart §1 (automated) from the worktree root:
  - `uv run --locked pytest tests/ -q`;
  - `(cd orchestration && uv run --locked pytest -q)`;
  - `(cd orchestration && uv run --locked pytest -q -m "not temporal")`;
  - `uv run --locked ruff check .`;
  - the SC-007 lockfile check, **in a refreshed scratch clone** per quickstart §1 (`shasum` before, real `py-check.sh stop` and `policy.sh` with `git commit --dry-run`, `shasum -c`). Also compare the live worktree's `uv.lock`/`orchestration/uv.lock` against T001's recorded sums.

  Report results, the T023 triage outcome and T019's feature-008 resolution.

  **Done 2026-10-11.** ruff clean; `tests/` 190 passed; `orchestration/` 72 passed; with `-m "not temporal"` 62 passed, 10 deselected. SC-007 in a fresh rsync scratch clone (`.git`, `.venv`, `.env*` excluded, then `uv sync --locked`): `py-check.sh stop` rc 0, `policy.sh` with `git commit --dry-run` rc 0, `shasum -c` OK for both lockfiles. T001's sums were lost, so the live check is `git status --porcelain -- uv.lock orchestration/uv.lock`, which is empty: both lockfiles equal HEAD 889785f. T023 triage: 0 violations after the extractor fixes; the four 009 identifiers are exempt as `(pending 009)`. T019: 008 is still left out on this base; `specs/008-gate-decision-core/` exists on `origin/main`, so it closes with the rebase (T042 before-merge item 3).
- [x] T045 Hand the live-session scenarios to the operator as a checklist. They need a fresh session, a scratch branch, `/clear` or a relaunch, so the agent can't fully self-verify them:
  - quickstart §2 (Story 1, steps 1–6);
  - quickstart §3 (Story 2, steps 1–7, including the `AF_SPEC_EXCEPTION` relaunch and both permission prompts);
  - quickstart §4 (Story 3, injections 1–4);
  - quickstart §6 (Story 4: cap, warn, continuity on and off a feature branch, adoption after Esc + `/clear`).

  Run the ones that need no relaunch (§4 injections, reverted after each) and mark the rest as operator-pending.

  Two §6 results feed back into the docs:
  - **§6.1, the cap isn't honoured from project settings**: apply T041's fallback wording in `CLAUDE.md`.
  - **§6.5, whether Stop fires on Esc**: record the answer in research.md R3.

  **Done 2026-10-11 for the agent's part.** §4 injections 1–4 each failed `tests/test_context_drift.py` with `file:line` and the token: `CLAUDE.md:47 [D-REG] "two entries"`, `CLAUDE.md:234 [D-SPEC] specs/099-nope`, `.claude/agents/py-codereviewer.md:68 [D-ID] _validate_targets`, `.claude/agents/py-codereviewer.md:104 [D-ID] seat_guard.py`. Each was reverted by an edit; both files match their pre-injection backups byte for byte, and the drift test is green (8 passed).

  **Operator-pending** (needs a fresh session, a relaunch or `/clear`):
  - [ ] §2 Story 1, steps 1–6 (turn-scoped gate). Revert the step 1/2 edits.
  - [ ] §3 Story 2, steps 1–7 (policy, both permission prompts, the `AF_SPEC_EXCEPTION` relaunch). Delete `scratch-nospec` afterwards. Also start one session in `orchestration/` and check that the AF-HARNESS prompt still appears with the `/`-anchored rules (T042).
  - [ ] §6.1 Cap: if auto-compaction doesn't fire by about 150k, apply T041's fallback (`claude --autocompact 150k`) in CLAUDE.md.
  - [ ] §6.2 Warn, §6.3–6.4 Continuity on and off a feature branch.
  - [ ] §6.5 Adoption after Esc + `/clear`: record in research.md R3 whether Stop fired on Esc.
- [x] T046 Commit the feature on `010-dev-harness-hardening`: the hooks (incl. `session-context.sh`), settings, tests, `orchestration/` marker changes, CLAUDE.md, the reviewer prompt, `eval/gate-policy.md`, `sandbox/swe-agent/Dockerfile` (FR-025) and `specs/010-dev-harness-hardening/`. The commit itself goes through AF-COMMIT, which serves as a final live check that the gate is green. Use the repo's commit-message conventions and attribution trailer. Don't push without operator approval.
  Ticked inside the commit it describes, so no second commit is needed; `git log` holds the SHA.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: none. T002 comes before T003–T005; those three are parallel; T006 comes after them.
- **Foundational (Phase 2)**: T007 comes before T008, because the fixture copies `lib.sh`. This phase blocks everything after it.
- **US1 (Phase 3)**: depends on Phase 2. Order: T009 → T010 → T011 → T012 → T013 → T014. T015 is independent (CLAUDE.md) and can run any time in this phase.
- **US3 (Phase 4)**: depends on US1. It needs US1's gate to block on red, and T021's `--locked` matches R4. T016 → T017 → T018 → T019 are sequential (same file, CLAUDE.md). T020 and T021 can run in parallel with them. T022 waits on T016–T021, and T022 → T023 → T024 are strictly sequential.
- **US2 (Phase 5)**: depends on Phase 2 (`lib.sh`, fixture) and US1 (`run_suites` behaviour). It doesn't depend on US3. Order: T025 → T026 → T027–T030 (same file, sequential).
- **US4 (Phase 6)**: depends on Phase 2 (`resolve_snapshot`, `feature_spec_dir`, `CTX_*`) and US1 (`turn-start` exists, T009). It doesn't depend on US2 or US3. Order: T031 and T032 (different files, parallel-safe) → T033 → T034 → T035 (same test file, sequential). It is placed after US2 only so that one review pass (T036) covers every hook script.
- **Pre-activation review (Phase 7)**: T036 depends on US1, US2 and US4 (all hook scripts written).
- **Activation (Phase 8)**: depends on T036 and on US3 (the drift test exists, so T039–T041 are checked). T037 → T038. T039 and T040 can run in parallel after T037 (different files). T041 comes after T040 (same file).
- **Polish (Phase 9)**: depends on all phases. T042 → T043/T044 → T045 → T046.

### User story dependencies

- **US1 (P1)**: the base layer. It's the MVP and stands alone, including adoption (SC-010).
- **US3 (P3)**: needs US1 for "red drift test → blocked turn", and is otherwise self-contained.
- **US2 (P2)**: needs US1's `lib.sh`/`run_suites` for AF-COMMIT. It ends with the Activation phase.
- **US4 (P3)**: needs US1's `turn-start` and the Phase 2 helpers. Its wiring (SessionStart, cap) and docs (FR-030) complete in the Activation phase.

### Parallel opportunities

- T003, T004, T005: three different test modules.
- T020, T021: run alongside the CLAUDE.md chain T016–T019.
- T031, T032: `py-check.sh` and the new `session-context.sh`.
- T039, T040: the reviewer prompt and CLAUDE.md, after T037.
- **Phases 5 and 6 (US2 and US4)** touch disjoint scripts. `policy.sh` and `py-check.sh`/`session-context.sh` could be built by two agents in parallel. Their tests share `tests/test_harness_hooks.py`, so serialise the test tasks or merge carefully.
- Within each test task the cases are independent functions, but they share one file, so the tasks themselves stay sequential.

## Parallel Example: Phase 4 (US3 doc fixes)

```text
Agent A: T016 → T017 → T018 → T019   (CLAUDE.md, sequential)
Agent B: T020                         (eval/gate-policy.md)
Agent C: T021                         (.claude/agents/py-codereviewer.md)
→ then T022 → T023 → T024 (tests/test_context_drift.py)
```

## Parallel Example: Phase 6 (US4 scripts)

```text
Agent A: T031   (.claude/hooks/py-check.sh: turn-start warn)
Agent B: T032   (.claude/hooks/session-context.sh)
→ then T033 (smoke) → T034 → T035 (tests/test_harness_hooks.py, sequential)
```

## Implementation Strategy

### MVP first (User Story 1 only)

1. Phases 1–2 (setup + `lib.sh` + fixture).
2. Phase 3 (US1).
3. **Stop and validate**: quickstart §2 steps 1–6 and §6 step 5 (adoption). The gate is turn-scoped, catches shell edits, survives `/clear` after an interrupted turn, and no longer runs suites per edit. That alone fixes the shared-checkout false blocks and the shell-edit bypass.

### Incremental delivery

1. US1 → a reliable gate (MVP).
2. US3 → true context, guarded by the drift test.
3. US2 → deterministic policy rules (unwired).
4. US4 → context warning (live through turn-start) and continuity script (unwired).
5. Review + Activation → policy, continuity and the cap go live in one settings change. CLAUDE.md documents the harness and the context budget.
6. Polish → review, full validation, one feature commit.

### Context budget while implementing this feature

This feature is long, and the 150k budget applies to the implementing session too. Tick each checkbox as its task finishes. Natural `/clear` points: after the Phase 3 checkpoint, after the Phase 4 checkpoint, and after T036. The next session resumes from this file and the first unchecked task.

## Notes

- `[P]` = different files, no dependency on an unfinished task.
- After each task, both suites and ruff must stay green. The live Stop hook enforces this.
- No test-only env vars or seams in hook code. Tests control behaviour only through the stub `uv` on `PATH`, fixture transcripts and the fixture repo's state (R11).
- In-flight features are referenced **by number only** in CLAUDE.md and the reviewer prompt, never as `specs/NNN-…` paths (D-SPEC).
