# Implementation Plan: Dev-Harness Follow-ups to 010

**Branch**: `worktree-012-dev-harness-followups` | **Date**: 2026-10-12 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/012-dev-harness-followups/spec.md`

## Summary

This feature closes the 21 follow-ups that 010's review and the 2026-10-11 incident
left open. The work comes in five parts.

### 1. Fail closed when the hooks are gone (FR-001, FR-002, FR-004, FR-015, P1)

**Cause, reproduced** (research R1). On 2026-10-11 a `git reset --hard origin/main` in
the launch worktree removed `policy.sh`. The session still fired the PreToolUse hook
from the configuration it loaded at launch. `/bin/sh` exited 127, which Claude Code
treats as a non-blocking error, so `git cherry-pick` ran with no rule applied.

**Fix.** Every hook `command` in `.claude/settings.json` becomes a short POSIX `sh`
launcher:

- It finds the script in the worktree named by the payload `cwd`, and falls back to
  `$CLAUDE_PROJECT_DIR`.
- If neither has the script, PreToolUse denies with `[AF-HOOKS]` and exit 2. The other
  events show a notice and never block.
- Scripts take their root from their own location.
- `policy.sh` denies when its input is empty or invalid.
- The message for an unloadable `lib.sh` gets an outside-the-session recovery.

### 2. Commit gate holes (FR-003, FR-005, FR-012, FR-013, FR-014)

- **Time limit.** The gate runs under one inner limit of 240 s, set by `GATE_LIMIT`,
  which is below the 300 s hook timeout. It uses GNU `timeout`/`gtimeout`, which kill
  the whole process group. A timeout is a deny that says so.
- **More git commands.** AF-COMMIT also gates `revert`, `cherry-pick`, `merge`, `am`,
  `rebase` (including `--continue`) and `pull` (unless fast-forward only). 010's
  whole-command match stays the floor. A command passes only when every
  `;`/`&&`/`||`/`|` segment with a verb is exactly `git <verb> --abort|--quit` or a
  plain `git pull --ff-only`. `--skip` is gated. On a red tree this also blocks a
  merge meant to bring in a fix: make the tree green first (research R5).
- **Stop gate.** A missing `uv` is treated as red, so the Stop gate never loops.
- **Double red.** A turn that is red twice keeps its snapshot.
- **Rebase.** AF-SPEC reads the branch being rebased and that branch's `tasks.md`.

### 3. AF-SECRET and AF-SPEC say what they do (FR-006 to FR-010)

- The contract states the shipped `is_secret_path` rules.
- Shell denials get their own message.
- The shell check folds case and knows more delimiters.
- AF-SPEC normalises `.` and `..` and folds the case of the top-level directory.
- Each behaviour has a test that fails on the old code.

### 4. swe-agent account of failing checks (FR-011)

- The model is no longer told to commit. It ends with a short account of the checks it
  ran.
- The harness puts that account in the PR body under `## Agent verification notes`.
- The checkpoint commit stays the only commit.

### 5. Drift, state and lint (FR-016 to FR-025)

- Old `ctx-*` and `exception-*` markers are pruned after 7 days.
- The context reading resets at `compact_boundary`.
- The drift contract states the shipped extractor rules.
- The drift corpus comes from `git ls-files`.
- Stop runs the drift test when a scope file changes.
- An orchestration `conftest.py` fails any unmarked test that connects to live
  Temporal.
- A shellcheck test lints the hook scripts and skips visibly when shellcheck is
  missing.
- CLAUDE.md is updated, and no lockfile changes.

## Technical Context

**Language/Version**: Bash 3.2 (hook scripts; macOS `/bin/bash`), POSIX `sh` (the
settings launcher, run by Claude Code under `/bin/sh`), Python 3.11+ (swe-agent, tests).

**Primary Dependencies**:

- Claude Code 2.1.285 hooks. Exit 2 blocks. Other non-zero exits and timeouts don't
  block. `onFailure` doesn't exist yet.
- `jq` 1.8, `git`, `uv` 0.10, `ruff`, `pytest` (with `pytester`), `temporalio`
  (already an orchestration dependency).
- GNU `timeout`/`gtimeout`: new prerequisite on macOS, `brew install coreutils`.
  Debian and E2B ship it.
- `shellcheck`: optional. Without it the lint test skips and says so.

**Storage**: unchanged state dir `$(git rev-parse --git-path claude-harness)/`. It
holds `turn-<key>.tsv`, `ctx-<key>.level` and `exception-<key>.notified`, all pruned
after 7 days. See [data-model.md](./data-model.md).

**Testing**: root suite, mainly `tests/test_harness_hooks.py`:

- launcher, policy, Stop and shellcheck cases;
- `tests/test_context_drift.py` for the corpus change;
- `tests/test_swe_agent_seat.py` for the prompt and PR body.

The orchestration suite gets the new `orchestration/conftest.py` and its pytester
test.

**Target Platform**: the operator's macOS host. The swe-agent E2B sandbox (Debian)
runs `agent.py` and, when the target repo is this repo, the hooks.

**Project Type**: developer tooling (hook scripts, settings, tests) plus one swe-agent
prompt and PR-body change.

**Performance Goals**:

- The commit/Stop gate takes about 53 s today, measured on 2026-10-11 with Temporal
  up: ruff 0 s, root 26 s, orchestration 27 s. The inner limit is 240 s.
- A drift-only Stop runs one test file, in under 1 s.
- The launcher adds one `jq` and one `git rev-parse` per hook call, about 20 ms.

**Constraints**:

- Fail closed on every PreToolUse path. Never block a prompt, a compaction or a stop
  except through the existing red-once path.
- bash 3.2: no `mapfile`, no associative arrays, no `${x,,}`.
- No test-only seams. Tests stub `uv`/`timeout` through `PATH` and set `AF_GATE_LIMIT`.
- No lockfile or pyproject writes (FR-025).
- AF-HARNESS is active. Every edit to `.claude/settings.json` and `.claude/hooks/**`
  prompts the operator.

**Scale/Scope**:

- 3 hook scripts changed (`lib.sh`, `policy.sh`, `py-check.sh`), 1 settings file, 1
  new conftest;
- 4 test modules touched;
- `agent.py`, `docs/40`, the swe-agent `SKILL.md` and CLAUDE.md;
- pointer lines in 010's contracts and data model.

No `NEEDS CLARIFICATION` remains. All are resolved in [research.md](./research.md),
R1 to R18.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**N/A.** `.specify/memory/constitution.md` is still the unfilled Spec Kit template.
The binding constraints come from CLAUDE.md, and this plan is checked against them:

| CLAUDE.md constraint | Status |
|---|---|
| Feature work planned with Spec Kit before code | ✔ this directory. AF-SPEC needs `tasks.md` before any code under `harness/` or `orchestration/` |
| Root `pyproject.toml` is dev/test tooling only, each agent keeps its own deps | ✔ no dependency added anywhere (FR-025) |
| Ruff and both suites green, enforced by hooks | ✔ strengthened: time limit, more git commands, drift tier, shell lint |
| Registry is the portability boundary, edits are AF-REGISTRY | ✔ only `registry/agents/swe-agent/SKILL.md` prose changes. No manifest or version file changes |
| Model calls via LiteLLM (swe-agent's direct-to-Anthropic is a documented deviation) | ✔ unchanged. FR-011 changes the prompt text and PR body only |
| `prompts/agentic-swe.json` kept in sync with the agent design | n/a: `IMPLEMENT_PROMPT` lives in `agent.py`, not in that file (checked 2026-10-12) |
| One session per worktree | ✔ the launcher follows the payload `cwd`, which is what makes per-worktree sessions safe after `EnterWorktree` |

**Post-design re-check (after data-model and contracts)**: unchanged.

- The design adds no service, layer or dependency.
- The new message ID `AF-HOOKS` goes into the CLAUDE.md rule table (FR-024).
- `orchestration/conftest.py` is test-only code in that suite's own directory.

## Project Structure

### Documentation (this feature)

```text
specs/012-dev-harness-followups/
├── spec.md
├── plan.md                       # this file
├── research.md                   # R1–R18 decisions, FR-001 and FR-017 evidence
├── data-model.md                 # launcher resolution, state files, watched tiers, rule catalogue, rebase branch, context reading
├── quickstart.md                 # validation scenarios, incl. the live SC-001 reproduction
├── contracts/
│   ├── hook-interface.md         # 012 amendments to 010's hook contract
│   └── drift-conventions.md      # 012 amendments to 010's drift contract
├── checklists/requirements.md
└── tasks.md                      # /speckit-tasks (not created here)
```

### Source Code (repository root)

```text
.claude/
├── settings.json                 # every hook command → POSIX launcher (cwd worktree → CLAUDE_PROJECT_DIR → AF-HOOKS)
└── hooks/
    ├── lib.sh                    # GATE_LIMIT + timed run_check/run_suites, rel_path normalisation,
    │                             #   feature_number rebase fallback, WATCHED tiers, shellcheck directives
    ├── policy.sh                 # ROOT from $0, AF-HOOKS input check + lib message, MSG_SECRET_SHELL,
    │                             #   case fold + delimiters, segment-wise AF-COMMIT verbs, timeout deny,
    │                             #   AF-SPEC tasks.md on rebased branch
    ├── py-check.sh               # ROOT from $0, uv-missing = red, keep snapshot on double red,
    │                             #   prune ctx/exception markers, compact_boundary reset, drift tier
    └── session-context.sh        # ROOT from $0 only (gets the rebase branch through feature_number)

tests/
├── test_harness_hooks.py         # launcher, AF-HOOKS, timeout, git verbs, secret spellings, path spellings,
│                                 #   rebase, uv-missing, double-red, pruning, compact_boundary, drift tier, shellcheck
├── test_context_drift.py         # corpus from git ls-files + ignored-file case
└── test_swe_agent_seat.py        # prompt no longer asks to commit; PR body carries verification notes

orchestration/
├── conftest.py                   # NEW: autouse guard on temporalio Client.connect for unmarked tests
└── tests/test_temporal_marker_guard.py   # NEW: pytester cases for the guard

harness/swe-agent/agent.py        # IMPLEMENT_PROMPT/TASK_PROMPT/FEEDBACK suffix, keep result texts, PR-body section,
                                  #   verify_new_commit wording
docs/40-sequence-swe-agent-runtime.md   # :47, :86 commit wording
registry/agents/swe-agent/SKILL.md      # commit and verification-notes prose
CLAUDE.md                         # FR-024: launcher, AF-HOOKS row, gated git verbs, coreutils, drift tier, lib.sh recovery
specs/010-dev-harness-hardening/{contracts/hook-interface.md,contracts/drift-conventions.md,data-model.md}
                                  # one pointer line each to the 012 amendments (FR-006, FR-017)
```

**Structure Decision**: no new directories, and no new hook script. The launcher lives
in `settings.json` because that is the one copy that survives a tree change (research
R1). The guard sits in `orchestration/conftest.py` so it covers both orchestration test
trees.

## Implementation Order (constraints for `/speckit-tasks`)

1. **Tests first, per slice.** Each FR-003 to FR-009 behaviour gets a test that fails
   on today's code before the fix (FR-010, SC-005). Write it, see it fail, fix it.
2. **`lib.sh` first, and with care.** A syntax error in `lib.sh` makes `policy.sh`
   deny every Bash call in this session (FR-015). So:
   - run `bash -n .claude/hooks/lib.sh` right after each edit;
   - keep one edit per change;
   - the recovery runs from a terminal outside Claude Code:
     `git checkout -- .claude/hooks/lib.sh`.
3. **Policy fixes (P1/P2)**, each with its tests:
   - `policy.sh`: ROOT from `$0`, input check, git verbs, secret message and
     spellings, path normalisation, rebase, timeout.
4. **Stop and turn-start fixes**, in `py-check.sh`: uv, double red, pruning,
   `compact_boundary`, drift tier.
5. **Settings launcher last among the harness edits.** The running session keeps its
   launch-time hook config (research R1), so the new launcher only applies to sessions
   started after it lands. Its tests run the launcher string from `settings.json`
   through `/bin/sh`. Add a settings test that every hook entry uses the launcher and
   passes `shellcheck -s sh`, and one that `GATE_LIMIT` is below the PreToolUse and
   Stop timeouts and is clamped to 240.
6. **Orchestration guard.** Add the conftest and its pytester test, then run the
   orchestration suite with Temporal down and with it up. With Temporal down, every
   marked test must skip and no test may fail on the guard.
7. **swe-agent (FR-011)**: `agent.py`, then `tests/test_swe_agent_seat.py`, then
   `docs/40` and `SKILL.md`, in one commit so the drift test stays green.
8. **Docs last**: CLAUDE.md (FR-024) and the 010 pointer lines. Then run the drift test.
9. **Reviews before each code commit**:
   - `shell-reviewer` on `.claude/hooks/*` and the settings launcher;
   - `py-codereviewer` on `.py`.

   `senior-architect-reviewer` runs on this plan before tasks start.
10. **Live checks** (operator, quickstart V1 and V2): the SC-001 reproduction in a
    disposable worktree, and a real `git commit` timing out under a lowered
    `AF_GATE_LIMIT`.

## Risks

| Risk | Mitigation |
|---|---|
| Hook config snapshot at launch is observed, not documented | The design needs only "the config text outlives the script", which the 2026-10-11 record shows. Quickstart V1 re-checks it live |
| A `cwd` inside another repo with the same script names, or a script the session edited from the shell, runs as the hook | Accepted (research R2): no worse than 010 FR-026, which leaves shell edits of the hook scripts open. A git common-dir check is left for later |
| AF-HARNESS may not prompt for an Edit of another worktree's hooks after a `cd` | Not settled by reading. Quickstart V1 step 8 records it live; the operator decides then |
| Worktrees made before 012 keep running 010's scripts, which judge the launch worktree's branch and allow empty input | Transitional: gone once each worktree is rebased onto 012. Recorded in the hook contract |
| A red tree blocks a repair merge, cherry-pick or pull | By design (research R5): AF-COMMIT judges the tree before the command. Make it green first, e.g. `git checkout -- <file>` |
| A double red keeps the gate on for every later turn, docs-only ones included | Accepted (research R9): that is what FR-013 asks for. Cleared by the first green Stop |
| Launcher quoting in JSON is error-prone | One string shape for all entries, a settings test that parses and runs each entry through `/bin/sh`, and `shell-reviewer` on it |
| `timeout`/`gtimeout` missing on a fresh Mac | AF-COMMIT denies with `brew install coreutils`, and Stop reports red. CLAUDE.md and quickstart list it as a prerequisite |
| Timeout kills pytest mid-run with Temporal state left over | Temporal tests use fresh workflow IDs per run (existing practice). A killed run leaves only a workflow that times out |
| Segment split misreads quoted `;` or `&&`, or a loop or variable hides the verb | 010's whole-command match is the floor, and only an exact `--abort`/`--quit` or plain `pull --ff-only` segment is exempt, with one verb word and no `$`, backtick, `(`, `)`, `<` or `>`. So a misread can only add a gate (an extra 53 s), never a pass. Matches 010's "false positives accepted" |
| Drift tier misses a non-scope file that holds a D-ID name | Recorded in the drift contract. AF-COMMIT runs the whole root suite as the backstop |
| Notes from an earlier seat are dropped on handoff | Accepted (research R8): they describe a tree the successor changed |
| Model's final message is long or empty | The PR-body section is capped (data-model), and is left out when empty |
| Editing `lib.sh` in this session locks the session on a syntax error | Implementation Order step 2 |

## Complexity Tracking

No constitution violations to justify (constitution not ratified; see Constitution
Check).
