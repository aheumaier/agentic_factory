---
description: "Task list for 012-dev-harness-followups"
---

# Tasks: Dev-Harness Follow-ups to 010

**Input**: Design documents from `specs/012-dev-harness-followups/`
**Prerequisites**: plan.md, spec.md, research.md (R1–R18), data-model.md, contracts/hook-interface.md, contracts/drift-conventions.md, quickstart.md (V1–V9)

**Tests**: Required. FR-010 and SC-005 ask for them, and plan.md says "tests first, per slice". Write each test task first and run it. It MUST fail on the old code before you write the matching implementation task. Run the root suite with `uv run --locked pytest tests/ -q` and the orchestration suite with `cd orchestration && uv run --locked pytest -q`. Run the suites one at a time, not in parallel: the live-Temporal tests time out under concurrency.

**Organization**: Tasks are grouped by user story, so each story can be built and tested on its own.

**Changing an existing test (SC-008)**: change one only where a requirement changes its expected result, and name that FR in a comment on the changed line. Each such change is its own task line below.

**Prompts you will see**:
- Every edit under `.claude/hooks/**` and to `.claude/settings.json` asks the operator to approve (AF-HARNESS).
- Edits under `harness/`, `orchestration/` and `eval/` need this branch to have `specs/012-dev-harness-followups/tasks.md` (AF-SPEC). This file satisfies it.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: the user story the task belongs to (US1–US4)
- Paths are relative to the repo root `/Users/aheumaier/Codebox/agentic_factory/.claude/worktrees/012-dev-harness-followups`

## Shared test helpers (reuse, do not duplicate)

`tests/test_harness_hooks.py` already has these helpers:
- `harness_repo`: a tmp git repo with copies of the real `.claude/hooks/*.sh` and a `uv` stub at `tmp/bin/uv`.
- `run_hook(repo, script, args, payload, env_extra=, path=)`
- `set_stub(repo, tool, rc, out)`, `uv_calls`, `calls_for`
- `turn_start`, `stop`, `snapshot`, `state_dir`
- `_path_without(tmp, repo, tool)`
- `policy(repo, payload)`, `bash(command)`, `assert_denied(result, rule)`, `assert_no_decision`
- `switch(repo, branch, tasks=)`, `feature(repo, branch, tasks)`, `_edit(repo, rel, tool)`
- `write_transcript`, `ctx_start`, `ctx_marker`, `_assistant(total)`
- `session_context(repo, source)`, `settings()` (the real `.claude/settings.json`), `_command(settings, event, matcher)`

`tests/test_context_drift.py` has `_tree(root, agents=, specs=)`.

The fixture copies the scripts into `<tmp>/repo/.claude/hooks/`, so `ROOT` taken from `$0` resolves to the tmp repo. No fixture change is needed for R2.

---

## Phase 1: Setup

**Purpose**: Start from current `main`, record baselines, and get the design reviewed before you build.

- [X] T001 Commit the 012 design docs on branch `worktree-012-dev-harness-followups`. The files are `specs/012-dev-harness-followups/{spec.md,plan.md,research.md,data-model.md,quickstart.md,tasks.md,contracts/,checklists/}` and `.specify/feature.json`. Message: `docs(012): plan and tasks`. This is a docs-only commit, so the reviewer agents are skipped; say so in the report.
- [ ] T002 Rebase onto the new `main` with `git fetch origin && git rebase origin/main`. PR #6 (feature 013, merge commit `91e1af0`, merged 2026-10-12) changed `CLAUDE.md` (the swe-agent row), `harness/swe-agent/SKILL.md`, `registry/agents/swe-agent/SKILL.md` and `orchestration/{activities.py,worker.py,webhook_bridge/github_app.py}`. Resolve any conflict in favour of `main`, then re-read those three docs before T033 (SKILL.md) and T056 (CLAUDE.md). The orchestration test line numbers in T050 may have shifted after the rebase; find them again by grep. Run `git log --oneline origin/main..HEAD` and confirm only your own commits are listed.
- [X] T003 Check the tools and record what is missing in `specs/012-dev-harness-followups/quickstart.md` under "Prerequisites": `command -v jq git uv shellcheck`, `command -v timeout || command -v gtimeout`, and `claude --version` (2.1.285 is expected; `onFailure` is not used). If `timeout`/`gtimeout` is missing, stop and ask the operator to run `brew install coreutils`. If `shellcheck` is missing, ask for `brew install shellcheck` (T048 would otherwise skip).
- [X] T004 Record the lockfile baseline (SC-009, FR-025): `shasum uv.lock orchestration/uv.lock > "$SCRATCH/af-lock-before"`, where `$SCRATCH` is the session scratchpad directory.
- [X] T005 Run the baseline gate one step at a time: `uv run --locked ruff check .`, then `uv run --locked pytest tests/ -q`, then `cd orchestration && uv run --locked pytest -q`. Record each step's pass count and wall time. The values seen while planning were 271 passed in 26 s and 167 passed in 27 s; the counts after T002 may differ. All three steps must be green before you go on.
- [X] T006 Run the `senior-architect-reviewer` agent on `specs/012-dev-harness-followups/plan.md`, `contracts/hook-interface.md` and `contracts/drift-conventions.md`, as the plan's review step asks. Fix confirmed findings in the spec docs. Record rejected findings, with the reason, at the end of `research.md`.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: Changes that every story builds on and that change no verdict.

**⚠️ CRITICAL**: Finish this phase before any story phase.

- [X] T007 Write the R2 test first (FR-002) in `tests/test_harness_hooks.py`: `test_root_comes_from_the_script_not_the_env`.
  1. Create a second `harness_repo`-like tmp repo B. Copy `tmp_path_factory.mktemp` and the fixture body, or factor the fixture body into a plain function and call it twice. Do not add a second fixture.
  2. Run `policy.sh` from repo A with `env_extra={"CLAUDE_PROJECT_DIR": str(B)}`, on an Edit of `A/harness/x.py`, while A is on `main` and B is on a planned `042-x` branch (`switch(B, "042-x", tasks=True)`).
  3. Assert AF-SPEC denies it, for an absolute and for a relative `file_path`. The old code judged the relative path on B's branch and allowed it; it treated the absolute A path as outside B and made no decision.
- [X] T008 Make every script take `ROOT` from its own path (R2, FR-002): `ROOT=$(cd "$(dirname "$0")/../.." && pwd)`. The lines are `.claude/hooks/policy.sh:35`, `.claude/hooks/py-check.sh:34` and `.claude/hooks/session-context.sh:29`. No script may read `CLAUDE_PROJECT_DIR` afterwards (`grep -n CLAUDE_PROJECT_DIR .claude/hooks/*.sh` prints nothing). Run `bash -n` on each script. T007 now passes. (AF-HARNESS prompt.)
- [X] T009 Add a test helper `deny_line(result) -> str` in `tests/test_harness_hooks.py` that returns the first non-empty stderr line. Add the deny-format check to the existing `assert_denied` (:576): the reason's first line must match `^\[AF-[A-Z]+\] .+\. To proceed: .+$`. Every existing policy deny already has this shape, so the suite stays green. From here on, every deny test checks the format (data-model validation).
- [X] T010 Add the gate-runner stubs to `tests/test_harness_hooks.py`, next to `_UV_STUB`. Put a `timeout` stub in `<tmp>/bin` that:
  - logs its argv to `<tmp>/timeout-calls.log`;
  - accepts `--kill-after=5 <n>s <cmd…>`;
  - exits with `<tmp>/timeout.rc` when that file exists (to fake 124/137);
  - otherwise runs `<cmd…>` and returns its exit code.

  Only `harness_repo` installs it, so existing tests keep passing. Add a helper `gate_limit(repo) -> list[str]` that returns the `<n>` values from the log. This is test infrastructure, not a verdict change.

**Checkpoint**: The root suite is green. Every hook test still passes, with ROOT taken from `$0`. FR-002 is met only once T022's launcher lands: until then `settings.json` still starts each script as `"$CLAUDE_PROJECT_DIR"/.claude/hooks/<script>`, so `$0` is still the launch worktree. Fix round (2026-10-13): `policy.sh` and `py-check.sh` exit 2 when that `cd` fails (`test_policy_and_edit_fail_closed_without_a_root`).

---

## Phase 3: User Story 1 — Hooks never fail open and never hang (Priority: P1) 🎯 MVP

**Goal**: A session whose hook scripts are gone is denied, not let through (FR-001). A gate that runs too long denies the commit (FR-003). Empty or invalid input is denied (FR-004). Every commit-making git verb is gated (FR-005).

**Independent Test**: Remove the launch worktree and write under `harness/`: the call is denied, or an AF-HOOKS notice is shown (quickstart V1). Feed `AF_GATE_LIMIT=1` with a slow `pytest` stub: the commit is denied with "timed out after" (quickstart V3).

### Tests for User Story 1 (write first, must fail) ⚠️

- [X] T011 [US1] Gate time-limit tests in `tests/test_harness_hooks.py` (FR-003, R3):
  - `test_gate_limit_is_clamped`: parametrize `AF_GATE_LIMIT` over unset, `"1000"`, `"abc"`, `"0"`, `"-5"`, `"30"`. Expect a first-step limit of `240`, 240, 240, 240, 240 and `30` respectively. Read it with `gate_limit(repo)` after a green `git commit` through `policy`.
  - `test_gate_steps_share_one_deadline`: every logged `<n>` is ≤ the limit; the second and third are ≤ the first; every one is ≥ 1.
  - `test_gate_timeout_denies_the_commit`: parametrize `timeout.rc` over 124 and 137. `assert_denied(..., "AF-COMMIT")`; the first line contains "timed out after". Do the same at Stop: exit 2 with "timed out" in stderr.
  - `test_gate_without_a_timeout_tool_denies`: use a `_path_without` that drops both `timeout` and `gtimeout`. The commit is denied and stderr names `brew install coreutils`. Stop exits 2 with the same text.
- [X] T012 [US1] Input-check tests in `tests/test_harness_hooks.py` (FR-004, R4). `test_policy_denies_empty_or_invalid_input`: parametrize the payload over `""`, `"{not json"`, `"[]"`, `'"x"'`, `{}` and `{"tool_name": 3}`. Each gives exit 2 and the AF-HOOKS "got no valid input" message from `contracts/hook-interface.md` (line ~171) on stderr. Also assert that `uv_calls(repo) == []`.
- [X] T013 [US1] Git-verb tests in `tests/test_harness_hooks.py` (FR-005, R5, SC-003), built from the command table in `contracts/hook-interface.md` "AF-COMMIT".
  - `test_commit_making_verbs_are_gated`: parametrize over every row the table marks "gated". This includes `git revert HEAD`, `git cherry-pick abc`, `git merge x`, `git am p.patch`, `git rebase main`, `git pull`, `git pull --rebase`, `git rebase --skip`, `git rebase --continue`, `git -c a=b merge x`, `git pull --ff-only; git commit`, `git pull --ff-only $(x)` and a backslash-newline-split `git com\\\nmit`. Each is `assert_denied(..., "AF-COMMIT")` with a red pytest stub.
  - `test_exempt_verbs_run_no_gate`: parametrize over every "exempt" row, including `git rebase --abort`, `git -C /x merge --quit`, `git cherry-pick --abort` and `git pull --ff-only` (with `pull.rebase` unset and with it set to `false`). For the "unset" case pass `env_extra={"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}`, so the developer's own git config cannot change the verdict (`run_hook` applies `env_extra` after `_clean_env`). Each gives `assert_no_decision` and `uv_calls == []`.
  - `test_pull_ff_only_is_gated_when_pull_rebase_is_set`: run `git(repo, "config", "pull.rebase", "true")`, then `git pull --ff-only` is gated.
  - `test_af_commit_message_names_the_verbs`: the deny's first line matches `^\[AF-COMMIT\] .+\. To proceed: .+$` and names `commit` and at least `merge`.
- [X] T014 [US1] Change `test_non_commit_commands_run_no_gate` in `tests/test_harness_hooks.py:767` only if a row now flips. Keep `git status`, `git log --grep=committee` and `echo gitcommit`. Add `echo rebase` as a plain-word row that stays ungated (no word `git`). `git log --grep=merge` is gated, not ungated: `=` is not a word character in 010's boundary, so it errs toward gating (`contracts/hook-interface.md` AF-COMMIT table), and its row belongs in `test_commit_making_verbs_are_gated` (T013). (Corrected 2026-10-13 to match the contract.) If a row has to change, comment `# FR-005` on it.
- [X] T015 [US1] Launcher and settings tests in `tests/test_harness_hooks.py` (FR-001, R1):
  - Replace `test_settings_wire_every_hook` (:1167) and the `session-context` assertion in `test_settings_wire_context_continuity_and_cap` (:1180). Their `.endswith("py-check.sh stop")`-style checks no longer hold, so mark the change `# FR-001`.
  - New `test_every_hook_uses_the_launcher`, for each of PreToolUse→`policy.sh` (timeout 300), PostToolUse→`py-check.sh edit`, UserPromptSubmit→`py-check.sh turn-start`, Stop→`py-check.sh stop` (timeout 300) and SessionStart(`compact|clear`)→`session-context.sh`:
    - the command contains `git rev-parse --show-cdup` and no `--show-toplevel` (the root keeps the `cwd`'s spelling; 012 fix round), `"$CLAUDE_PROJECT_DIR"` and `bash "$r/.claude/hooks/<script>" <args>`;
    - it contains no `'` inside the AF-HOOKS message;
    - `sh -n -c <command>` exits 0;
    - `shellcheck -s sh -` on the command exits 0 (skip only that assertion if shellcheck is missing).
  - New `test_gate_limit_is_below_the_hook_timeouts`: `GATE_LIMIT` default (read `\$\{AF_GATE_LIMIT:-(\d+)\}` from `lib.sh`) + 10 < the PreToolUse and Stop `timeout` values.
- [X] T016 [US1] Launcher behaviour tests in `tests/test_harness_hooks.py` (FR-001, SC-001). They run the real launcher strings from `settings()` with `subprocess.run(["/bin/sh", "-c", cmd], input=payload, env=…)`. Use `test_launcher_finds_scripts` parametrized over:
  - (a) the payload's `cwd` is a `harness_repo` and `CLAUDE_PROJECT_DIR` points to a deleted dir: the repo's hook runs (a policy deny for an Edit of `harness/x.py` on `main`);
  - (b) `cwd` is a non-repo tmp dir and `CLAUDE_PROJECT_DIR` is the repo: the repo's hook runs;
  - (c) neither has `.claude/hooks/<script>`: PreToolUse exits 2 with the AF-HOOKS "were not found" text on stderr; Stop, PostToolUse, UserPromptSubmit and SessionStart exit 0 with stdout `{"systemMessage":"[AF-HOOKS] …"}`, which is valid JSON;
  - (d) the payload's `cwd` is a symlink to a `harness_repo` (create one: `tmp_path` is already a physical path on macOS), the repo is on `main`, and the Edit's `file_path` is spelled through the symlink: AF-SPEC denies. A launcher built on `--show-toplevel` would give the physical root, and the edit would get no decision (012 fix round, 2026-10-13).
- [X] T017 [US1] Deny format for the stderr-only denies in `tests/test_harness_hooks.py` (data-model validation). Policy denies already get the format check through `assert_denied` (T009). In T012 and T016(c), also assert that `deny_line(result)` matches `^\[AF-[A-Z]+\] .+\. To proceed: .+$`. Then run the suite and confirm T011–T017 fail for the expected reasons, and nothing else fails.

### Implementation for User Story 1

- [X] T018 [US1] Gate runner in `.claude/hooks/lib.sh` (FR-003, R3; data-model "Gate run"):
  - Add `GATE_LIMIT=${AF_GATE_LIMIT:-240}`. If it is not a positive integer, or is above 240, set it to 240.
  - Add a `gate_runner` function that echoes `timeout` or `gtimeout`, or returns 1 when neither exists.
  - Make `run_check` (:45) and `run_suites` (:59) share one deadline (`SECONDS` at gate start + GATE_LIMIT). Run each step as `<runner> --kill-after=5 <left>s <cmd>`, where `<left>` is the time left, at least 1.
  - Map exit 124 or 137 to the outcome "timed out after <GATE_LIMIT> s" and stop the gate there.
  - With no runner, return the outcome "no timeout tool: brew install coreutils".
  - Keep `uv run --locked` in every command.

  Run `bash -n .claude/hooks/lib.sh`. (AF-HARNESS prompt.)
- [X] T019 [US1] Input check in `.claude/hooks/policy.sh` (FR-004, R4). Right after the bounded stdin read and before any rule, run `jq -e 'type == "object" and (.tool_name | type == "string")'` on the input. On failure, print the AF-HOOKS "got no valid input" message from the contract on stderr and `exit 2`. The order is: lib load → input check → AF-SECRET → AF-SPEC → AF-COMMIT. (AF-HARNESS prompt.)
- [X] T020 [US1] AF-COMMIT matching in `.claude/hooks/policy.sh` (FR-005, R5), replacing the commit match near :130-139:
  - Floor: the word `git` plus one of commit, revert, cherry-pick, merge, am, rebase, pull, using the boundary `(^|[^[:alnum:]_.-])WORD($|[^[:alnum:]_.-])`, after joining backslash-newlines.
  - Split into segments on `;`, `&&`, `||`, `|` and newline. Exempt the command only if every segment that has a verb word is one of the two exempt shapes in R5: `git [-C p|-c k=v]… (rebase|cherry-pick|merge|am|revert) (--abort|--quit)`, or `git pull --ff-only` with `git -C "$ROOT" config --get pull.rebase` unset or `false`. Both shapes need exactly one verb word and none of `$`, a backtick, `(`, `)`, `<` or `>`.
  - `commit` and `--skip` are never exempt.
  - Widen `MSG_COMMIT` (:39) to the contract text that names the verbs.
  - Run the gate through T018's runner, and deny with the timed-out or no-runner outcome text.
  - bash 3.2 only: no `${x,,}`, no `mapfile`. (AF-HARNESS prompt.)
- [X] T021 [US1] Stop gate in `.claude/hooks/py-check.sh` (stop mode, :144-214). Run ruff and the suites through T018's runner (FR-003). A timed-out or no-runner outcome goes down the existing red path: exit 2 with the outcome, then "still RED" on the retry. Run `bash -n`. (AF-HARNESS prompt.) T011 and T012–T014 now pass.
- [X] T022 [US1] Launcher in `.claude/settings.json` (FR-001, R1). Replace each hook `command` with the one-line POSIX sh launcher from `contracts/hook-interface.md` "Launcher", joined with `;`:
  `p=$(cat); d=$(printf '%s' "$p" | jq -r '.cwd // empty' 2>/dev/null); t=$(cd "${d:-.}" 2>/dev/null && c=$(git rev-parse --show-cdup 2>/dev/null) && cd "./$c" && pwd); for r in "$t" "$CLAUDE_PROJECT_DIR"; do if [ -n "$r" ] && [ -f "$r/.claude/hooks/<script>" ]; then printf '%s' "$p" | bash "$r/.claude/hooks/<script>" <args>; exit $?; fi; done; <not-found>`
  - PreToolUse (`policy.sh`, timeout 300): not-found is `echo '<AF-HOOKS missing>' >&2; exit 2`.
  - Others: not-found is `echo '{"systemMessage":"<AF-HOOKS missing>"}'; exit 0`. The entries are PostToolUse `py-check.sh edit`, UserPromptSubmit `py-check.sh turn-start`, Stop `py-check.sh stop` (timeout 300) and SessionStart(`compact|clear`) `session-context.sh`.
  - `<AF-HOOKS missing>` is the "were not found" text from the contract, with no `'`.
  - Leave `permissions` and `env` untouched.

  Validate with `jq . .claude/settings.json`. (AF-HARNESS prompt.) T015–T017 now pass.
- [X] T023 [US1] Run quickstart V3 (input check and git verbs with `AF_GATE_LIMIT=1`) by hand, as `specs/012-dev-harness-followups/quickstart.md` describes, and note the result. Then run the root suite: all of US1 is green.

**Checkpoint**: US1 is complete and testable on its own. This is the MVP. The live check (V1/V2) is in T058.

---

## Phase 4: User Story 2 — Rules match what they say (Priority: P2)

**Goal**: AF-SPEC judges normalised, case-folded paths (FR-008). AF-SECRET folds case, knows more separators and says "naming" for shell commands (FR-007, FR-009). The 012 contract states every rule the tests pin (FR-006, FR-010). swe-agent no longer tells the model to commit and puts its verification notes in the PR (FR-011).

**Independent Test**: The path and spelling tables in `contracts/hook-interface.md` give their stated verdict (quickstart V4). A swe-agent run's PR body has an "Agent verification notes" section (quickstart V8).

### Tests for User Story 2 (write first, must fail) ⚠️

- [X] T024 [US2] Path spelling tests in `tests/test_harness_hooks.py` (FR-008, R7, SC-004). `test_path_spellings_are_normalised`: parametrize over the contract's path table:
  - `harness/./x.py`, `pkg/../harness/x.py`, `./harness/x.py`, `harness//x.py`, `Harness/x.py` and `HARNESS/x.py` are guarded, so AF-SPEC denies them on `main`;
  - `harness/../pkg/x.py` and `harnessx/x.py` are not guarded;
  - `../../outside.py` (popping past the root) is outside the repo, so there is no decision.
  - Absolute only: `<root>/../<rootname>/harness/x.py` climbs out and back in, so it is guarded and denied on `main` (data-model "AF-SPEC path" step 2 runs on the whole path; T006 review, finding 5).

  Use `_edit(repo, rel)` with both a relative and an absolute `file_path`.
- [X] T025 [US2] Secret spelling tests in `tests/test_harness_hooks.py` (FR-007, FR-009, R6). Extend `_SECRET_DENIED` (:600) and `_SECRET_ALLOWED` (:617) only by adding rows; do not edit existing ones.
  - Denied for Bash: `cat .ENV`, `cat .Env.Braintrust`, `x=$(cat .env)`, `` `cat .env` ``, `scp a@b:.env .`, `cp {.env,x}`, `echo a,.env`, `less (.env)`, `cat <.env`, `cat .env*`.
  - Denied for the file tools, because they share `SECRET_RE` (FR-009, contract "AF-SECRET, file tools"): Glob `pattern` `{.env,x}` and `x:.env`, and Grep `glob` `x,.env`. Each passes on the old regex (checked 2026-10-12), so the test fails before T030.
  - Allowed for Bash, Read, Grep and Glob: `.env.example` in each of those spellings, and `.environment`.
  - New `test_shell_secret_message_says_naming`: a Bash deny's first line is `MSG_SECRET_SHELL` (contains "naming") and matches the deny-format regex. A Read deny still uses `MSG_SECRET`.
- [X] T026 [P] [US2] swe-agent prompt tests in `tests/test_swe_agent_seat.py` (FR-011, R8). In `test_prompt_carries_resume_and_checkpoint_rules` (:322), replace `assert "git add -A && git commit" in prompt` with `# FR-011` and assert:
  - `"Do not commit: the harness commits your work."` in the whitespace-joined prompt;
  - `"list the checks you ran"` in the prompt;
  - `"git commit"` not in the prompt.

  Add `test_task_and_feedback_prompts_do_not_ask_to_commit`: `TASK_PROMPT` contains "list the checks you ran"; `FEEDBACK_PROMPT_SUFFIX` does not contain "committing".
- [X] T027 [US2] swe-agent PR-body tests in `tests/test_swe_agent_seat.py` (FR-011, R8). Reuse the module's existing fake `query` and `origin` fixtures, and follow the shape of `test_checkpoint_push_follows_branch_not_head`.
  - `test_pr_body_has_verification_notes_after_one_session`: one IMPLEMENT run whose last `ResultMessage.result` is "ran pytest: 3 passed". `.pr-body.md` ends with `\n\n## Agent verification notes\n\n~~~text\nran pytest: 3 passed\n~~~` (data-model "Verification notes", fenced per the T006 review).
  - `test_notes_go_to_a_comment_when_the_pr_exists`: `gh pr create` fails with "already exists". `gh pr comment <branch> --body-file <f>` runs, and `<f>`'s first line is `## Agent verification notes`. A failing `gh pr comment` does not fail the run (T006 review, finding 1).
  - `test_notes_are_fenced`: notes with `Fixes #1`, `@someone` and a `~~~` line. Both strings sit between the opening and the closing fence, and the `~~~` line became `~~\~` (T006 review, finding 9).
  - `test_per_task_notes_keep_task_order`: two per-task sessions, T001 then T002, each returning text. The section holds `### T001` before `### T002`.
  - `test_notes_are_capped`: 5000 chars of result. The section is at most 4000 chars and ends with `\n\n… (truncated)`.
  - `test_notes_are_omitted_when_empty`: an empty result, and a run with no session. Neither has the heading.

  Run `uv run --locked pytest tests/test_swe_agent_seat.py -q`: the new tests fail.

### Implementation for User Story 2

- [X] T028 [US2] `rel_path` normalisation in `.claude/hooks/lib.sh:89` (FR-008, R7). Normalise lexically, as data-model "AF-SPEC path" says:
  - make the path absolute against ROOT, then work on the whole absolute path;
  - drop `.` and empty segments;
  - each `..` pops one segment; a `..` at `/` stays at `/`, as the kernel reads it (amended 2026-10-13 by the implementation review; `test_dotdot_at_the_filesystem_root_stays_there`);
  - only then compare with `ROOT/`; no match means outside (return 1).

  No disk lookups and no symlink resolution. bash 3.2 only. Run `bash -n`. (AF-HARNESS prompt.)
- [X] T029 [US2] AF-SPEC case fold in `.claude/hooks/policy.sh` (FR-008, R7). Lower-case only the first path segment (`tr '[:upper:]' '[:lower:]'`) before matching `harness/`, `orchestration/` or `eval/`. T024 now passes. (AF-HARNESS prompt.)
- [X] T030 [US2] AF-SECRET in `.claude/hooks/policy.sh` (FR-007, FR-009, R6):
  - Set `SECRET_RE` to ``(^|[[:space:]/'"=<>`@{,:(])\.env(\.braintrust)?($|[[:space:];|&)'"<>*?[{}`,])`` (`>` and `}` added 2026-10-13 by the implementation review). Use it for both the Bash check and the file-tool glob/pattern check, and keep the existing `is_secret_path` checks (:78-85).
  - Lower-case the Bash command before matching (:90).
  - Add `MSG_SECRET_SHELL` with the contract's "naming" text and deny Bash with it.

  T025 now passes. (AF-HARNESS prompt.)
- [X] T031 [P] [US2] swe-agent prompts in `harness/swe-agent/agent.py` (FR-011, R8):
  - In `IMPLEMENT_PROMPT` (:38-58), replace the "Then commit your changes locally with `git add -A && git commit` …" sentence with: "Do not commit: the harness commits your work. In your final message, list the checks you ran and, for any that still fail, why. That message goes into the pull request for the human reviewer."
  - Append "In your final message, list the checks you ran and, for any that still fail, why." to `TASK_PROMPT` (:61).
  - Change `FEEDBACK_PROMPT_SUFFIX` (:73-78) to end "…before re-running verification."
  - Fix the comment at :59 if it still describes a model commit.
  - Change the `verify_new_commit` failure text to "the harness commits any change, so none was made".

  T026 now passes.
- [X] T032 [US2] swe-agent notes in `harness/swe-agent/agent.py` (FR-011, R8):
  - `run_implement` (:340) keeps the last `ResultMessage.result` of its session.
  - `run_per_task` (:379) keeps each one under `### <task ID>`, in task order.
  - Pass the joined text to `push_and_open_pr`. It caps the text at 4000 chars (cut text ends with `\n\n… (truncated)`), fences it as data-model "Verification notes" says, and appends the section to `.pr-body.md`. When `gh pr create` says "already exists", it posts the same section with `gh pr comment <branch> --repo <repo> --body-file`, and a failure there is a stderr warning only.
  - Leave the section out when the text is empty or no session ran.
  - Do not carry notes across seats.

  T027 now passes, and so does `uv run --locked pytest tests/ -q`.
- [X] T033 [P] [US2] Docs for the swe-agent change: replace the "commit your changes" wording in `docs/40-sequence-swe-agent-runtime.md:47` and `:86` with "the harness commits", and mention the PR's "Agent verification notes". Update the prose in `registry/agents/swe-agent/SKILL.md` (and `harness/swe-agent/SKILL.md` if it says the model commits). This is prose only: do not touch `manifest.yaml` or `versions/`.
- [X] T034 [US2] Contract check (FR-006, FR-010, SC-005). Read `specs/012-dev-harness-followups/contracts/hook-interface.md` "Matching rules" next to T024, T025 and T030, and add any rule the tests pin that the contract does not state. Add the pointer line `> Amended by \`specs/012-dev-harness-followups/contracts/hook-interface.md\` (launcher, AF-HOOKS, gate time limit, stop steps 1-5, matching rules).` at the top of `specs/010-dev-harness-hardening/contracts/hook-interface.md`. Add a second pointer line under 010's `### \`py-check.sh stop\`` heading: `> Steps 1-5 are replaced by 012's contract, "\`stop\`" (a red-twice turn keeps its snapshot, FR-013).`
- [X] T035 [US2] Run quickstart V4 (secret and path spellings) by hand and note the result.

**Checkpoint**: US1 and US2 both pass. swe-agent's change is committed together with its docs (plan: agent.py, tests, docs/40 and SKILL.md in one commit).

---

## Phase 5: User Story 3 — Recovery paths don't trap the operator (Priority: P2)

**Goal**:
- A missing `uv` blocks Stop once, not forever (FR-012).
- A double red keeps the baseline (FR-013).
- A rebase on a planned branch still allows edits (FR-014).
- An unloadable lib.sh says how to recover (FR-015).
- Stale state files are pruned (FR-016).
- The context warning ignores usage recorded before a compaction (FR-017).

**Independent Test**: After a turn that is red twice, the next turn is still judged against the first baseline (SC-006). During `git rebase -i` on `042-x` with tasks, an Edit of `harness/x.py` is allowed (quickstart V5).

### Tests for User Story 3 (write first, must fail) ⚠️

- [X] T036 [US3] Change `test_missing_uv_fails_closed_only_where_uv_runs` in `tests/test_harness_hooks.py:437` (FR-012). Keep the edit-mode assertions. For the stop path, add `# FR-012`; the first `stop_no_uv()` after a change gives exit 2 with "uv is required", and a second call with `stop_hook_active: true` gives exit 0 with "still RED" in `systemMessage`. Also add a payload with `stop_hook_active: true` and no `uv`, which must not be blocked before the guard is read.
- [X] T037 [US3] Change `test_red_blocks_once_then_lets_go_with_a_notice` in `tests/test_harness_hooks.py:301` (FR-013). The last line becomes `assert snapshot(repo).exists()  # FR-013: a double red keeps the baseline`. Add `test_double_red_keeps_the_baseline_for_the_next_turn` (SC-006):
  1. Red, then red again.
  2. `turn_start`.
  3. Make a docs-only change (`notes.md`) and set the stubs green.
  4. `stop` runs the gate (because the pkg change from turn 1 is still in the diff) and passes. The snapshot is then deleted.

  Add a variant where the stubs stay red: the docs-only turn still blocks once.
- [X] T038 [US3] Rebase tests in `tests/test_harness_hooks.py` (FR-014, R10):
  - `test_rebase_on_a_planned_branch_allows_guarded_edits`: on `042-x` with `specs/042-x/tasks.md` committed, fake a rebase in progress. Run `git checkout --detach`, then write `refs/heads/042-x` into the file at `git rev-parse --git-path rebase-merge/head-name`, creating the directory. A real `git rebase` with nothing to replay finishes at once and leaves no such file. `policy` on `_edit(repo, "harness/x.py")` gives `assert_no_decision`. Repeat with `rebase-apply/head-name`, written the same way.
  - `test_rebase_reads_tasks_from_the_branch_tip`: `tasks.md` exists only on the branch tip, not in the detached worktree. The edit is allowed.
  - `test_rebase_of_an_unplanned_branch_is_denied`: same, but with no tasks.md. AF-SPEC denies.
  - `test_session_context_names_the_branch_during_a_rebase`: `session_context(repo, "compact")` during the rebase names `042-x`, and its rule list contains `AF-HOOKS`. Update `_RULES` at :931 to include `"AF-HOOKS"` with `# FR-014`.
- [X] T039 [US3] Lib-load test in `tests/test_harness_hooks.py` (FR-015, R11). `test_policy_without_lib_names_the_recovery`: parametrize over lib.sh deleted and lib.sh with a syntax error (`echo 'if then' >> lib.sh`). `policy` exits 2 and stderr's first line equals the contract's AF-HOOKS "could not be loaded" text, which contains `git checkout HEAD -- .claude/hooks/lib.sh` and `git rebase --abort` (T006 review: `git checkout --` fails on an unmerged file). The existing `test_turn_start_and_session_context_never_fail[no-lib]` stays unchanged: those two hooks still exit 0.
- [X] T040 [US3] Prune test in `tests/test_harness_hooks.py` (FR-016, R12). `test_turn_start_prunes_stale_ctx_and_exception_files`: create `ctx-old.level` and `exception-old.notified` in `state_dir(repo)` and age them 8 days with `_age(path, 8 * DAY)`; also create a fresh `ctx-new.level`. After `turn_start`, the old two are gone and the fresh one remains. A read-only state dir must not make `turn_start` fail.
- [X] T041 [US3] Compaction tests in `tests/test_harness_hooks.py` (FR-017, R13). Use `write_transcript` with a dict entry `{"type": "system", "subtype": "compact_boundary"}`:
  - `test_context_after_compaction_with_no_usage_is_silent`: a high usage (`_assistant(130000)`), then a boundary, then `_FILLER`. No warning, and `ctx_marker(repo)` is left untouched.
  - `test_context_after_compaction_rearms_on_low_usage`: a high usage warns once, then a boundary, then `_assistant(10000)`, then later `_assistant(125000)`. Warns again.

  Run the suite: T036–T041 fail for the expected reasons.

### Implementation for User Story 3

- [X] T042 [US3] `.claude/hooks/py-check.sh` stop mode (FR-012, FR-013, R9):
  - Read `stop_hook_active` before the `uv` check and the T018 runner check.
  - Replace `require_tools py-check.sh uv` (:178) with: if `uv` is missing, add `=== uv FAILED ===` and "uv is required" to the failures and take the normal red path.
  - In the `stop_hook_active` branch, remove `rm -f "$snap"` so a double red keeps the snapshot.
  - Edit mode keeps `require_tools uv` (:131).

  Run `bash -n`. (AF-HARNESS prompt.) T036 and T037 now pass.
- [X] T043 [US3] Rebase support in `.claude/hooks/lib.sh` and `.claude/hooks/policy.sh` (FR-014, R10):
  - `feature_number` (:141): when HEAD is detached, fall back to the file at `git rev-parse --git-path rebase-merge/head-name`, then `rebase-apply/head-name`, and strip `refs/heads/`.
  - `feature_spec_dir` / AF-SPEC: also accept a tasks.md on the branch tip, using `git ls-tree -r --name-only "refs/heads/<branch>" -- specs/` filtered to `^specs/NNN-[^/]*/tasks\.md$`.
  - Add `AF-HOOKS` to the rule list in `.claude/hooks/session-context.sh`.

  Run `bash -n` on each. (AF-HARNESS prompt.) T038 now passes.
- [X] T044 [US3] Remaining hook changes:
  - `.claude/hooks/policy.sh:26-27` (FR-015): replace the "cannot load lib.sh" echo with the contract's AF-HOOKS "could not be loaded" message, and keep exit 2.
  - `py-check.sh` turn-start (FR-016, R12): run `find "$sd" -maxdepth 1 \( -name 'ctx-*.level' -o -name 'exception-*.notified' \) -mmin +10080 -delete 2>/dev/null || true` before the snapshot step.
  - The context warning's jq walk in `.claude/hooks/py-check.sh` (around :68) (FR-017, R13): reset the candidate to unknown at a `type=="system"` and `subtype=="compact_boundary"` entry. A non-sidechain assistant usage sets it to `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`. If the candidate is unknown at the end, stay silent and leave the marker untouched.

  Run `bash -n`. (AF-HARNESS prompt.) T039–T041 now pass.
- [ ] T045 [US3] Add the pointer line `> Amended by \`specs/012-dev-harness-followups/data-model.md\` (context warning after compaction, R13; replaces the "Re-arm likely lags compaction by one prompt" paragraph below).` above line 141 of `specs/010-dev-harness-hardening/data-model.md`. Run quickstart V5 (rebase) by hand and note the result.
  - 2026-10-13: pointer line done. V5 not run yet. It needs a disposable worktree and its removal, which the implementing run excludes. An attempt in a disposable clone was refused by the session's worktree-isolation guard (running the hook from outside the worktree). The rebase path is covered by the `fake_rebase` tests and `test_branch_tip_tasks_count_only_during_a_rebase`. Tick this task once V5 has been run by hand and its result noted here.

**Checkpoint**: US1–US3 all pass.

---

## Phase 6: User Story 4 — Drift and lint checks see what they claim to (Priority: P3)

**Goal**:
- The drift contract states the extractor's real rules (FR-018, FR-019).
- The D-ID corpus is tracked plus non-ignored files only (FR-020).
- Stop runs the drift test on a docs turn (FR-021).
- Unmarked live-Temporal tests fail (FR-022).
- The hook scripts are shellchecked in the gate (FR-023).

**Independent Test**: A docs-only edit that makes CLAUDE.md stale is reported at Stop (quickstart V7). A file that is untracked and git-ignored does not affect the corpus.

### Tests for User Story 4 (write first, must fail) ⚠️

- [X] T046 [P] [US4] Corpus test in `tests/test_context_drift.py` (FR-020, R14). `test_ignored_file_is_not_in_the_corpus`:
  1. In a `_tree(tmp_path)` that is also a git repo (`git init -q`, plus a `.gitignore` with `secret_mod.py`), write `secret_mod.py` defining `def only_here(): ...`.
  2. `check_reg`/`_in_code` on text naming `only_here` reports it missing.
  3. A tracked or untracked-but-not-ignored file with the same name is found.

  The old `os.walk` corpus finds it, so the test fails. (T051 makes `_tree` run `git init`.)
- [X] T047 [US4] Drift-tier Stop tests in `tests/test_harness_hooks.py` (FR-021, FR-023, R15):
  - `test_docs_turn_runs_only_the_drift_test`: parametrize over `CLAUDE.md`, `.claude/agents/py-codereviewer.md`, `registry/agents/a/manifest.yaml` and `specs/001-x/spec.md`. Commit the file first, then `turn_start`, edit it, and `stop`. Exactly one pytest call, whose argv contains `tests/test_context_drift.py`; no ruff call.
  - `test_hook_or_settings_turn_runs_the_full_gate`: editing `.claude/hooks/lib.sh` (the fixture copy) or a committed `.claude/settings.json` runs both suites.
  - `test_both_tiers_changed_runs_the_full_gate_once`: a `.py` and `CLAUDE.md` both changed give both suites and no separate drift call.
  - `test_old_snapshot_runs_the_full_gate_once` (upgrade): a snapshot holding only `*.py` lines makes the first Stop run both suites. This works because the old snapshot lacks the new pathspecs, so `.claude/hooks/*.sh` and `.claude/settings.json` show up as added full-tier paths. Do not add a version marker to the snapshot.
- [X] T048 [US4] Shellcheck test in `tests/test_harness_hooks.py` (FR-023, R17). It must fail first, on SC2034 (CTX_BUDGET/CTX_WARN) and the unfollowed `source`. `test_hook_scripts_pass_shellcheck`:
  - Skip with `pytest.skip("shellcheck not installed: hook scripts were not linted")` when `shutil.which("shellcheck")` is None.
  - Otherwise run `shellcheck -x .claude/hooks/*.sh` from `REPO_ROOT` and assert exit 0, showing stdout on failure.
- [X] T049 [P] [US4] Temporal guard test in `orchestration/tests/test_temporal_marker_guard.py` (FR-022, R16). Use `pytester.makeconftest(<the guard's source, read from orchestration/conftest.py>)` and `pytester.makepyfile(...)` with:
  - an unmarked test that calls `temporalio.client.Client.connect("localhost:1")`, which must fail with "connects to live Temporal but is not marked @pytest.mark.temporal" and its nodeid;
  - a `@pytest.mark.temporal` test whose connect error is caught and turned into a skip, which must be skipped, not failed.

  Run with `cd orchestration && uv run --locked pytest tests/test_temporal_marker_guard.py -q`. It fails, because there is no conftest yet.
- [X] T050 [US4] Marker coverage (FR-022). Check every function that reaches `_connect_or_skip` and confirm it is under `@pytest.mark.temporal` or a module `pytestmark`:
  - `orchestration/tests/test_credential_pool.py:200` (the helper at :209 and every caller; only :224, :241 and :251 are marked today);
  - `orchestration/tests/test_pipeline_workflow.py:36`;
  - `orchestration/webhook_bridge/tests/test_integration.py:18`;
  - `orchestration/webhook_bridge/tests/test_e2e_pipeline_gate.py:84`.

  Add the mark to any test that lacks it, with `# FR-022`.

### Implementation for User Story 4

- [X] T051 [US4] `_corpus` in `tests/test_context_drift.py:67` (FR-020, R14):
  - Replace `os.walk` with `git -C <root> ls-files -co --exclude-standard -z`.
  - Keep the excluded prefixes (`specs/`, `.claude/`, `.specify/`, `.git/`, any `.venv/`, `node_modules/`) and read regular files only.
  - Keep `functools.cache` and the return shape.
  - Make `_tree` (:259) run `git init -q` in the tmp tree, because `git ls-files` sees nothing outside a repo. This is test infrastructure for the new corpus and changes no expected result, so the existing synthetic drift tests stay unchanged.

  T046 now passes, and `uv run --locked pytest tests/test_context_drift.py -q` is green on the real repo.
- [X] T052 [US4] Turn tiers in `.claude/hooks/lib.sh` `python_fingerprint` (:105) and `.claude/hooks/py-check.sh` stop (FR-021, FR-023, R15; data-model "Turn snapshot"):
  - Add the pathspecs `.claude/hooks/*.sh`, `.claude/settings.json`, `CLAUDE.md`, `.claude/agents/py-codereviewer.md`, `registry/agents/*/manifest.yaml` and `specs/*/spec.md` to the fingerprint. The file format is unchanged.
  - At Stop, work out each changed path's tier from the path. A full-tier change runs ruff on the changed `.py` files that still exist, then both suites. A drift-only change runs only `uv run --locked pytest tests/test_context_drift.py -q`, through the T018 runner.

  Run `bash -n`. (AF-HARNESS prompt.) T047 now passes.
- [X] T053 [US4] Guard in the new `orchestration/conftest.py` (FR-022, R16):
  - Set `pytest_plugins = ["pytester"]`.
  - Add an autouse, function-scoped fixture that monkeypatches `temporalio.client.Client.connect`. For a test without the `temporal` marker it calls `pytest.fail(f"{request.node.nodeid} connects to live Temporal but is not marked @pytest.mark.temporal")`; for a marked test it calls the original.

  No dependency change. Run `cd orchestration && uv run --locked pytest -q` twice: once with Temporal down (`make down`), where marked tests skip and none fails; and once with it up (`make up`), where all pass. T049 now passes.
- [X] T054 [US4] Shellcheck directives (R17), which make T048 pass:
  - `# shellcheck disable=SC2034` on the line above `CTX_BUDGET=` and above `CTX_WARN=` in `.claude/hooks/lib.sh:11-12`.
  - `# shellcheck source-path=SCRIPTDIR` just below the header comment of `.claude/hooks/policy.sh`, `.claude/hooks/py-check.sh` and `.claude/hooks/session-context.sh`.
  - Fix any other finding that `shellcheck -x .claude/hooks/*.sh` reports in lines 012 changed.

  Run `bash -n` on each script. (AF-HARNESS prompt.)
- [X] T055 [US4] Drift contract (FR-018, FR-019, SC-005). Make sure `specs/012-dev-harness-followups/contracts/drift-conventions.md` states the extractor's rules as shipped: the non-private lowercase names such as `shape_issue`, the git-ls-files corpus and Stop coverage, including the YAML gap from R15. Add the pointer line `> Amended by \`specs/012-dev-harness-followups/contracts/drift-conventions.md\` (extractor rules as shipped, D-ID corpus, Stop coverage).` at the top of `specs/010-dev-harness-hardening/contracts/drift-conventions.md`. Run quickstart V7 by hand.

**Checkpoint**: All four stories pass.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T056 Update the harness section of `CLAUDE.md` (FR-024):
  - Describe the launcher, and that hooks resolve from the session's worktree.
  - Add an AF-HOOKS row to the Repo-rules table.
  - List the gated git verbs in the AF-COMMIT row.
  - Add the `brew install coreutils` (timeout) and `shellcheck` prerequisites.
  - Describe the drift tier at Stop.
  - Add the lib.sh recovery sentence: from a terminal outside Claude Code, `git checkout HEAD -- .claude/hooks/lib.sh`; in a rebase or merge stopped on a hook-file conflict, `git rebase --abort` or `git merge --abort` first, or fix the file in an editor.
  - Correct the "Known gaps" bullets that 012 closes.
  - Add two "Known gaps" bullets from the hook contract (T006 review): a session whose own working directory was removed runs no hooks at all (fixed only by `onFailure` from Claude Code 2.1.295), so do not remove the worktree a session is in; and AF-SPEC does not judge edits in another worktree or in the main checkout.

  Keep the swe-agent row as merged by PR #6, and add only the "harness commits" wording. Run `uv run --locked pytest tests/test_context_drift.py -q` (green).
- [ ] T057 Reviews, in parallel and in the background: `shell-reviewer` on `.claude/hooks/*.sh` and the settings.json launcher strings; `py-codereviewer` on `tests/test_harness_hooks.py`, `tests/test_context_drift.py`, `tests/test_swe_agent_seat.py`, `harness/swe-agent/agent.py`, `orchestration/conftest.py` and `orchestration/tests/test_temporal_marker_guard.py`; `senior-architect-reviewer` on the finished feature (contract change). Fix confirmed findings and re-run once. Record each rejected finding, with its reason, in the PR description.
- [ ] T058 Live operator checks V1 and V2 from `quickstart.md`. These are operator-only, because they remove a worktree and hang a gate in a real session. Record the results in the PR description. V1 is SC-001: a removed launch worktree gives a deny or an AF-HOOKS notice. V2: a real commit with `AF_GATE_LIMIT=5` is denied as timed out.
- [ ] T059 Run quickstart V6, V8 and V9:
  - V6: run the full root and orchestration suites one at a time, and record the counts.
  - V8: the swe-agent tests, the Temporal guard and shellcheck.
  - V9: `shasum -c "$SCRATCH/af-lock-before"`. Both lockfiles must be unchanged (SC-009, FR-025), and `git diff --stat origin/main -- '*uv.lock' '*pyproject.toml'` must be empty.
- [ ] T060 Traceability check (SC-007, SC-008). For each of the 21 in-scope items in `spec.md`'s traceability table, write the task ID and test name that covers it into a new "Coverage" section at the end of this file. List every existing test changed, with the FR named in its comment (T014, T015, T026, T036, T037, T038, T050). Tick every task above.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: none. Do T002 (rebase) before T004/T005 so the baselines reflect the new `main`.
- **Foundational (Phase 2)**: needs Setup. Blocks every story, because T008 changes how every script finds the repo.
- **US1 (Phase 3)**: needs Foundational. T018 (gate runner) is used by T021, T042 and T052.
- **US2 (Phase 4)**: needs Foundational. The hook part (T024, T025, T028–T030) edits `policy.sh`/`lib.sh`, as US1 does, so run it after US1. The swe-agent part (T026, T027, T031–T033) is independent and can run at any time after Phase 2.
- **US3 (Phase 5)**: needs US1 (T042 reads the T018 runner outcome on the red path).
- **US4 (Phase 6)**: T052 needs US1's T018 and US3's T042 (same stop code). T046, T049, T050, T051 and T053 are independent of US1–US3.
- **Polish (Phase 7)**: needs every story. T056 (CLAUDE.md) goes last among the edits, because the drift test judges it.

### Within each story

Tests first, and they must fail. Then `lib.sh` (run `bash -n` after each edit), then `policy.sh`, then `py-check.sh`, then `settings.json` last (T022), so a broken launcher cannot lock the session out mid-feature.

### Parallel opportunities

- T026, T027, T031 and T033 (swe-agent files) run alongside any hook task.
- T046 and T051 (`tests/test_context_drift.py`) and T049, T050 and T053 (orchestration) touch no hook file.
- T034, T045 and T055 (spec-doc pointer lines) touch different files.
- Hook tasks are **not** parallel: they share `lib.sh`, `policy.sh`, `py-check.sh` and `tests/test_harness_hooks.py`.

---

## Parallel Example

```text
# While US1's hook work (T011–T023) is under way, in a second worktree or subagent:
T026 [US2] swe-agent prompt tests in tests/test_swe_agent_seat.py
T027 [US2] swe-agent PR-body tests in tests/test_swe_agent_seat.py   (same file as T026: run after it)
T049 [US4] orchestration/tests/test_temporal_marker_guard.py
T046 [US4] tests/test_context_drift.py corpus test

# Then:
T031 + T032 [US2] harness/swe-agent/agent.py
T053 [US4] orchestration/conftest.py
T051 [US4] _corpus in tests/test_context_drift.py
```

---

## Implementation Strategy

### MVP first (US1 only)

1. Phase 1 (Setup, including the rebase onto `91e1af0`) and Phase 2 (ROOT from `$0`, the deny-format check, the timeout stub).
2. Phase 3 (US1): the launcher, the input check, the gate time limit and the git verbs.
3. **Stop and validate**: the root suite is green, quickstart V3 passes, and the operator runs V1/V2. This closes the 2026-10-11 fail-open, the main risk.

### Incremental delivery

1. US1: no fail-open, no hang (MVP).
2. US2: the rules match their contract; swe-agent stops self-committing.
3. US3: the recovery paths (uv, double red, rebase, lib.sh, pruning, compaction).
4. US4: drift and lint coverage.

Each story is committed on its own after its reviewers run. That needs AF-COMMIT green, and it now enforces the gate time limit too.

### Parallel team

After Phase 2: one agent takes the hook chain (US1 → US2 hooks → US3 → US4 T047/T048/T052/T054). Another takes the swe-agent slice (T026, T027, T031–T033). A third takes the drift and Temporal slices (T046, T049–T051, T053).

---

## Notes

- [P] means different files and no dependency on an unfinished task.
- Never weaken or delete a test, or lower a threshold, to get green. A changed test names its FR (SC-008).
- Hook scripts run under bash 3.2. Launcher strings run under `/bin/sh`: POSIX only, no `'` inside messages.
- Never read `.env` or `.env.braintrust` (AF-SECRET). Test fixtures use synthetic names inside tmp repos.
- `/clear` between stories. The `specs/012-dev-harness-followups/` directory and the ticked boxes here are the handoff.
- Before any push, run `git log --oneline origin/<branch>..<branch>` and check for commits you did not make (shared repo).
