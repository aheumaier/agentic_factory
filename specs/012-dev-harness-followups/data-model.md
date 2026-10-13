# Data Model: Dev-Harness Follow-ups to 010 (012)

This file amends `specs/010-dev-harness-hardening/data-model.md`. Anything not named
here stays as 010 defines it. As in 010, there is no database. The entities are:

- hook resolution;
- the on-disk state files in the per-worktree state dir
  `$(git rev-parse --git-path claude-harness)/`;
- the rule catalogue;
- the gate run;
- the context reading;
- the swe-agent's verification notes.

---

## Hook resolution (new; FR-001, FR-002)

Each hook `command` in `.claude/settings.json` is a POSIX `sh` launcher. The text is
the same in every entry except for `script` and `args`.

| Field | Value |
|---|---|
| `script` | `policy.sh`, `py-check.sh` or `session-context.sh` |
| `args` | `turn-start`, `edit` or `stop` for `py-check.sh`, else none |
| `payload` | stdin, read once into a variable and passed on unchanged |
| `cwd` | `.cwd` from the payload, or `pwd` when jq fails or the field is empty |
| `candidates` | 1. `<toplevel>/.claude/hooks/<script>`, where `<toplevel>` is `<cwd>` plus `git rev-parse --show-cdup`, entered with `cd` and printed with `pwd`, so it keeps the `cwd`'s spelling (no symlink resolution); 2. `$CLAUDE_PROJECT_DIR/.claude/hooks/<script>` |
| run | the first candidate that is a regular file: `printf '%s' "$payload" \| bash <candidate> <args>`. The launcher exits with that status |
| none found, `PreToolUse` | `[AF-HOOKS]` "repo hooks not found" on stderr, exit 2 |
| none found, any other event | `{"systemMessage":"[AF-HOOKS] …"}` on stdout, exit 0 |

The scripts run under `bash <file>`, so a lost executable bit cannot cause exit 126.

**Inside a script**: `ROOT` = `$(cd "$(dirname "$0")/../.." && pwd)`. That is the
worktree whose script was chosen, spelled as the launcher spelled it. If that `cd`
fails, `policy.sh` (with `[AF-HOOKS]`) and `py-check.sh` in `edit` and `stop` modes exit 2
rather than run with an empty `ROOT`; `turn-start` exits 0, so the prompt is kept.
`CLAUDE_PROJECT_DIR` is no longer read by any script.

**Validation**:

- A settings test parses `.claude/settings.json` and asserts that every
  `hooks.*[].hooks[].command` contains the launcher's fixed parts, names its script,
  and runs under `/bin/sh -n`.
- The launcher's messages match the contract.

## State files and retention (amended; FR-013, FR-016)

| File | Written by | Removed by |
|---|---|---|
| `turn-<key>.tsv` | `turn-start` | Stop when there is no change, when green, or with a single red **only after a later green**. On a double red the file is **kept** (FR-013). `resolve_snapshot` never ages out the session's own file (it returns once the own file exists); only another session's `turn-start` or Stop prunes it after 7 days |
| `ctx-<key>.level` | `turn-start` (context notice) | `turn-start` when the level is `none`; **new**: `turn-start` prunes any older than 7 days |
| `exception-<key>.notified` | `policy.sh` (first bypassed AF-SPEC deny) | **new**: `turn-start` prunes any older than 7 days |

"7 days" is `find -mmin +10080`, the same rule `resolve_snapshot` already uses. The
prune runs before the snapshot step and never blocks: errors are ignored, and
turn-start still exits 0.

## Turn snapshot (amended; FR-013, FR-021, FR-023)

**File format unchanged**: `<blob-sha>\t<path>`, C-sorted. A snapshot from before 012
stays valid.

**Watched set**: two tiers, and a path's tier is worked out from the path when the diff
is read, so it is not stored:

| Tier | Pathspecs | Stop runs on change |
|---|---|---|
| `full` | `*.py`, `*pyproject.toml`, `*uv.lock`, `.claude/hooks/*.sh`, `.claude/settings.json` | ruff on changed `.py` files that still exist, then both suites under the gate limit |
| `drift` | `CLAUDE.md`, `.claude/agents/py-codereviewer.md`, `registry/agents/*/manifest.yaml`, `specs/*/spec.md` | `pytest tests/test_context_drift.py` only, under the gate limit |

If both tiers changed, the `full` run is enough, because the root suite already holds
the drift test.

**Transitions at Stop** (changes from 010 in bold):

```
 changed set empty                   → delete snapshot, exit 0
 run green                           → delete snapshot, exit 0
 run red, stop_hook_active = false   → keep snapshot, exit 2 with failures
 run red, stop_hook_active = true    → **keep snapshot**, systemMessage "still RED", exit 0
 uv missing                          → **counts as red** with "uv is required" (FR-012), same two rows above
```

The kept snapshot is found by the next `turn-start` through `resolve_snapshot` step 1
(own file exists) and reused, so the next turn is judged against the same baseline
(SC-006). Cost: until green, every later turn runs the gate at Stop and blocks once,
a docs-only turn included (contract "`stop`").

## Gate run (new; FR-003)

| Field | Value |
|---|---|
| `GATE_LIMIT` | `${AF_GATE_LIMIT:-240}` seconds, set in `lib.sh`. Clamped: a value that is not a positive integer, or is above 240, becomes 240 |
| deadline | the time the gate started plus `GATE_LIMIT`. Each step gets the time left, at least 1 s |
| runner | `timeout`, or `gtimeout` when `timeout` is not on `PATH`. It runs `--kill-after=5 <left>s <cmd…>`, so the step's whole process group is killed |
| step exit 124 or 137 | stop the gate, outcome `timed out` |
| no runner on `PATH` | outcome `no timeout tool` (fail closed) |
| outcomes | `green` · `red` (failures text) · `timed out` · `no timeout tool` · `uv missing` |

The same runner serves AF-COMMIT and Stop. How each outcome maps to a verdict is in
`contracts/hook-interface.md`.

**Validation**: settings tests assert `GATE_LIMIT` < the PreToolUse `timeout`, and
`GATE_LIMIT` < the Stop `timeout`, and that `AF_GATE_LIMIT=1000` and
`AF_GATE_LIMIT=abc` both give 240.

## Policy rule (amended; FR-004 to FR-009, FR-014, FR-015)

**Catalogue**: 010's five IDs plus **`AF-HOOKS`**. `AF-HOOKS` means "the harness cannot
judge this call". It is never a policy verdict on what the call does.

| ID | Mechanism | Triggers |
|---|---|---|
| AF-HOOKS | launcher (exit 2) · `policy.sh` (exit 2) | script missing in both places; `lib.sh` fails to load; repo root cannot be resolved; payload empty, not a JSON object, or without a string `tool_name` |
| AF-SECRET | `policy.sh` deny | Read/Grep/Glob path or filter matches (as shipped); Bash command matches the case-folded `SECRET_RE` |
| AF-SPEC | `policy.sh` deny | normalised path under `harness/`, `orchestration/` or `eval/` (top segment case-folded), and no tasks.md for the feature branch |
| AF-COMMIT | `policy.sh` deny | a gated git segment, and a gate outcome other than `green` |
| AF-REGISTRY, AF-HARNESS | `permissions.ask` | unchanged |

**Evaluation order in `policy.sh`**: lib load → input check (AF-HOOKS) → AF-SECRET →
AF-SPEC → AF-COMMIT. The first deny wins.

**Exit codes**:

- An AF-HOOKS refusal from `policy.sh` exits 2 with the message on stderr. There is no
  trustworthy input to answer in JSON.
- All other denies keep 010's JSON `permissionDecision: "deny"` with exit 0.

**Validation**: unchanged. Every deny's first line matches
`^\[AF-[A-Z]+\] .+\. To proceed: .+$`, including all AF-HOOKS messages.

### AF-SECRET matching

**File tools (Read, Grep, Glob)**: unchanged, now stated:

- The path's basename is lower-cased (`LC_ALL=C tr`) and must equal `.env` or
  `.env.braintrust`.
- The check runs in any directory.
- Grep checks `path` and `glob`. Glob checks `path` and `pattern`.
- A `glob` or `pattern` basename is also denied when it matches `SECRET_RE`, so
  `.env*` and `.env{,.braintrust}` are denied. `SECRET_RE` is shared with Bash, so
  the wider Bash delimiters below apply here too (benign: more glob spellings denied).
- Grep's `pattern` is never checked.

**Bash**:

1. The command is lower-cased (`LC_ALL=C tr '[:upper:]' '[:lower:]'`) and matched
   against:

   ```
   (^|[[:space:]/'"=<`@{,:(])\.env(\.braintrust)?($|[[:space:];|&)'"<>*?[{`,])
   ```

2. `.env.example` never matches: the `.` after `.env` is not in the trailing class.
3. A match gets the shell message (`MSG_SECRET_SHELL`).

### AF-SPEC path

`rel_path ROOT PATH` (normative; research R7 follows it):

1. If `PATH` is relative, prefix it with `ROOT/`.
2. Split the whole absolute path on `/`. Drop empty and `.` segments. Each `..` pops
   one segment off the path built so far. A `..` with nothing left to pop (above `/`)
   returns *outside*. `ROOT` plays no part in this step.
3. Rejoin. Only now compare with `ROOT`: if the result starts with `ROOT/`, return the
   rest. Otherwise return *outside* (empty). So `ROOT/../<rootname>/harness/a.py`
   returns `harness/a.py`.
4. AF-SPEC lower-cases the **first** segment of the result before the
   `harness/*|orchestration/*|eval/*` match.

Nothing is looked up on disk (no symlink resolution).

### Feature branch during a rebase (FR-014)

`feature_number`, in order:

1. `git symbolic-ref --short -q HEAD`.
2. If HEAD is detached: the first readable file among
   `$(git rev-parse --git-path rebase-merge/head-name)` and
   `$(git rev-parse --git-path rebase-apply/head-name)`, with `refs/heads/` stripped.
3. Match the result against `^(worktree-)?([0-9]{3})-`.

`tasks.md` is found when either:

- the working tree has `ROOT/specs/<NNN>-*/tasks.md` (as in 010); or
- the branch is known and
  `git ls-tree -r --name-only refs/heads/<branch> -- specs/` lists a path matching
  `^specs/<NNN>-[^/]*/tasks\.md$`.

`session-context.sh` uses the same `feature_number`. Its fixed rule list gains
`AF-HOOKS`.

### AF-COMMIT command match (FR-005)

1. **Floor (010)**: the whole command has the word `git` and one of the verb words
   `commit`, `revert`, `cherry-pick`, `merge`, `am`, `rebase` or `pull`. If not, it
   is not gated.
2. **Segments**: join each backslash-newline, then split on `;`, `&&`, `||`, `|` and
   newline. There is no quote handling.
3. **Exempt segment**, one of:
   - after `git` and any `-C <path>` / `-c <key=value>` pairs, the segment's tokens
     are exactly `(rebase|cherry-pick|merge|am|revert) (--abort|--quit)`;
   - the segment starts `git pull` (no option between), `--ff-only` is the only
     token after `pull` that starts with `-`, and
     `git -C ROOT config --get pull.rebase` is unset or `false`. The `pull.ff`
     config is not read.

   Both shapes also need exactly one verb word in the segment and none of `$`, a
   backtick, `(`, `)`, `<` or `>`. `commit` and `--skip` are never exempt.
4. **Verdict**: a command that passes step 1 is gated unless at least one segment
   has a verb word and every segment with a verb word is exempt.
5. "Word" uses 010's boundary: `(^|[^[:alnum:]_.-])WORD($|[^[:alnum:]_.-])`. That
   boundary counts `-` as a word character, so options are matched as whole tokens
   (`--abort`, `--ff-only`, `--rebase`), never as the bare word after the dashes.

## Context reading (amended; FR-017)

This replaces 010's "reading" row and its "Re-arm likely lags compaction" paragraph.

| Field | Notes |
|---|---|
| window | last 200 lines of `transcript_path` (unchanged) |
| reading | walk the window in order with candidate = *unknown*. A `type=="system"` entry with `subtype=="compact_boundary"` sets candidate := *unknown*. A non-sidechain `type=="assistant"` entry with `.message.usage` sets candidate := `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`. The result is the final candidate |

The transitions stay as in 010. Two consequences:

- **First prompt after compaction**: no reply yet after the boundary, so the reading is
  *unknown*. Nothing is printed and the marker is untouched.
- **Re-arm**: on the first reading below `CTX_WARN` after that, as before.

Tests MUST pin both cases: a boundary with no usage after it gives silence, and a
boundary followed by a low usage gives re-arm.

## Verification notes (new; FR-011)

These are in-memory only in `harness/swe-agent/agent.py`, and are never written to the
target repo.

| Field | Notes |
|---|---|
| source | `IMPLEMENT_PROMPT` path: `.result` of its last `ResultMessage`. Per-task path: `TASK_PROMPT` gains the same "list the checks you ran and why any still fail" sentence, and each task session's last `.result` is kept under a `### <task ID>` header, in task order. Not carried across seats (research R8) |
| empty | `None` or whitespace only, or no model session ran (the all-done shortcut) → the section is left out |
| size cap | 4 000 characters for the notes text, all task headers included, before the fence is added. Longer text is cut and ends with `\n\n… (truncated)` |
| format | the fixed header, then the notes inside a `~~~` fence: `## Agent verification notes\n\n~~~text\n<text>\n~~~`. Each `~~~` inside the text becomes `~~\~`, so no line of the text can close the fence. The fence keeps model text such as `Fixes #12` or `@someone` from being read as GitHub markup, and shows the reviewer which text is the model's (T006 review, 2026-10-13) |
| placement, new PR | `gh pr create` succeeds: the section is appended to the PR body written to `.pr-body.md`, after `\n\n`. The body before the section is unchanged (the first `specs/*/spec.md`, as today) |
| placement, PR exists | `gh pr create` fails with "already exists" (the architect stage's `ensure_target_pr_activity` opened the PR before Build, or this is build attempt 2 or 3): the same section is posted as a PR comment, `gh pr comment <branch> --repo <repo> --body-file <file>`. The comment's first line is the fixed header, and the webhook bridge's `parse` reads only the first non-empty line, so text below it is never read as a command. One comment per build attempt. A failed `gh pr comment` is printed to stderr as a warning and does not fail the run: the commits and the PR are already in place |

## Temporal marker guard (new; FR-022)

| Field | Notes |
|---|---|
| location | `orchestration/conftest.py`, so it covers `orchestration/tests/` and `orchestration/webhook_bridge/tests/` |
| fixture | autouse, function-scoped. It monkeypatches `temporalio.client.Client.connect` |
| marked test | `request.node.get_closest_marker("temporal")` is set → the original `connect` runs |
| unmarked test | `pytest.fail("<nodeid> connects to live Temporal but is not marked @pytest.mark.temporal")` before any network call |
| guard's own test | `orchestration/tests/test_temporal_marker_guard.py` uses `pytester`. It is enabled by `pytest_plugins = ["pytester"]` in `orchestration/conftest.py` (the suite's top-level conftest, where `pytest_plugins` is allowed). Each case copies the guard into the temp dir with `pytester.makeconftest(...)`, because the outer conftest does not apply there |
