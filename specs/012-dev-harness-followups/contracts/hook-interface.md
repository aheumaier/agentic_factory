# Contract: Hook Interface, 012 amendments

This file amends `specs/010-dev-harness-hardening/contracts/hook-interface.md`. Each
section below names the 010 section it replaces or extends. Anything not named here
stays as 010 states it. 010's contract gets one pointer line at the top, added by the
tasks of this feature:

> Amended by `specs/012-dev-harness-followups/contracts/hook-interface.md` (launcher,
> AF-HOOKS, gate time limit, stop steps 1-5, matching rules).

Field-level detail (launcher fields, state files, gate outcomes, matching algorithms)
is in [`../data-model.md`](../data-model.md). This contract states what a caller sees.

---

## Wiring (replaces 010 "Wiring": the command column)

Events, matchers and the `permissions` block are unchanged. Every hook `command` is
now the launcher below, with `<script>` and `<args>` filled in per entry. It is POSIX
`sh`, because Claude Code runs hook commands under `/bin/sh`.

```sh
p=$(cat)
d=$(printf '%s' "$p" | jq -r '.cwd // empty' 2>/dev/null)
t=$(cd "${d:-.}" 2>/dev/null && c=$(git rev-parse --show-cdup 2>/dev/null) && cd "./$c" && pwd)
for r in "$t" "$CLAUDE_PROJECT_DIR"; do
  if [ -n "$r" ] && [ -f "$r/.claude/hooks/<script>" ]; then
    printf '%s' "$p" | bash "$r/.claude/hooks/<script>" <args>; exit $?
  fi
done
<not-found branch>
```

In `settings.json` this is one line, joined with `;`. The `<not-found branch>` is:

| Event | Not-found branch |
|---|---|
| `PreToolUse` | `echo '<AF-HOOKS missing>' >&2; exit 2` (the call is denied) |
| `PostToolUse`, `UserPromptSubmit`, `Stop`, `SessionStart` | `echo '{"systemMessage":"<AF-HOOKS missing>"}'; exit 0` (a notice, nothing is blocked) |

| Entry | `<script>` | `<args>` | `timeout` (s) |
|---|---|---|---|
| PreToolUse | `policy.sh` | — | 300 (unchanged; above the 240 s gate limit) |
| PostToolUse | `py-check.sh` | `edit` | unchanged |
| UserPromptSubmit | `py-check.sh` | `turn-start` | unchanged |
| Stop | `py-check.sh` | `stop` | 300 (unchanged; above the 240 s gate limit) |
| SessionStart(compact\|clear) | `session-context.sh` | — | unchanged |

Order of lookup: the worktree that holds the payload's `cwd` first, then
`$CLAUDE_PROJECT_DIR` (the launch directory). The first one that has the script wins.
So a session that moved into another worktree runs that worktree's scripts, and a
session whose launch worktree was removed still finds the scripts of the worktree it
is in (FR-001, FR-002).

Not covered: the hook config itself is read once at launch. A change to
`.claude/settings.json` takes effect in the next session only.

Known gaps, recorded, not fixed (2026-10-12):

- **Trust of the found scripts.** The launcher runs whatever `.claude/hooks/<script>`
  the payload's worktree holds. A session can edit those files from the shell, which
  010 FR-026 already leaves open, so this is no worse than 010. Checking that the
  toplevel shares this repo's git common dir is left for later.
- **The launcher's own failure.** `p=$(cat)` has no read limit of its own (the
  entry's `timeout` bounds it), and `bash` is found on `PATH`. If `bash` cannot run,
  the PreToolUse entry exits 127, which Claude Code treats as a non-blocking error.
  That is the same fail-open class as a hook timeout, and with no `bash` no hook rule
  can run at all (2026-10-13, review finding).
- **AF-HARNESS after a worktree move.** `permissions.ask` rules are anchored at the
  launch directory. After `EnterWorktree` or `cd` into another worktree, an Edit of
  that worktree's `.claude/hooks/**` may not prompt. Only a live run settles this
  (quickstart V1 step 8).
- **Transition.** A worktree made before 012 still holds 010's scripts. The launcher
  runs them as they are until that worktree is rebased onto 012. 010's `policy.sh`
  takes its root from `CLAUDE_PROJECT_DIR`, so in such a worktree it still judges the
  launch worktree's branch and still allows empty input: the FR-002 and FR-004 holes
  stay open there until the rebase.
- **Spelling and nesting.** The toplevel keeps the `cwd`'s spelling: `--show-cdup`
  plus `cd` and `pwd` climb up lexically, so a `cwd` reached through a symlink stays
  spelled through it. `--show-toplevel` would print the physical path, `ROOT` would
  follow it, and `rel_path`'s plain prefix compare would never match a `file_path`
  spelled the way Claude Code reports it. Every guarded edit would then count as
  outside the repo, and AF-SPEC would make no decision (012 fix round, 2026-10-13).
  A worktree nested inside another worktree
  resolves to the inner one, so AF-SPEC judges the inner branch.
- **Deleted working directory** (T006 review, 2026-10-13). When the session's own
  working directory is a removed worktree (`ExitWorktree` remove, or
  `git worktree remove` from outside while the session is still in it), Claude Code
  cannot start the hook process at all: the spawn fails before the launcher runs.
  Claude Code 2.1.285 treats that as a non-blocking error, so every covered call is
  allowed. No hook command can fix this; only `onFailure` (Claude Code 2.1.295 and
  later) can. CLAUDE.md tells the operator not to remove the worktree a session is in.
  Quickstart V1 step 4a records what a live session shows.
- **Edits in another worktree** (T006 review, 2026-10-13). AF-SPEC judges a path
  against `ROOT`, the worktree whose scripts run. A file in the main checkout or in a
  sibling worktree resolves outside `ROOT` and is not judged, as the spec's edge case
  "Path spellings outside the repo" states. So a session on a spec branch can edit
  `harness/` in a checkout that is on `main`, and that checkout's turn gate never sees
  it. The same holds for FR-014's rebase lookup. Judging each path against the
  worktree that owns it (`git -C <nearest existing parent> rev-parse --show-toplevel`)
  would close this; it widens AF-SPEC and is left to the operator.

## Inputs (extends 010 "Inputs")

| Field | Used by | Notes |
|---|---|---|
| `cwd` | launcher | **new**. Picks the worktree whose scripts run. Missing or empty: the launcher's own working directory |

**Environment line, replaced.** 010 said the scripts read `CLAUDE_PROJECT_DIR`. Now
only the launcher reads it, as the second lookup. Each script sets
`ROOT=$(cd "$(dirname "$0")/../.." && pwd)`, the worktree whose script runs. Every
"outside `$CLAUDE_PROJECT_DIR`" in 010 now reads "outside `ROOT`".

## Outputs

### Common (amends 010 "Common")

- A missing `jq` or `git` still exits 2 with the 010 text.
- `policy.sh` refuses with **AF-HOOKS on stderr and exit 2** when:
  - `lib.sh` fails to load (missing file or syntax error);
  - the repo root cannot be resolved (the `cd` to `<script dir>/../..` fails);
  - the payload is empty, is not a JSON object, or has no string `tool_name`.

  There is no trusted input to answer in JSON, so this is the one deny that does not
  use 010's JSON shape. Claude Code shows stderr to the model and blocks the call.
- All other denies keep 010's JSON `permissionDecision: "deny"` with exit 0.

### `turn-start` (extends 010)

1. **New, first step:** prune `ctx-*.level` and `exception-*.notified` files in the
   state dir older than 7 days (`find -mmin +10080`). Errors are ignored.
2. The snapshot pathspecs gain the drift tier, plus the full-tier
   `.claude/hooks/*.sh` and `.claude/settings.json` (data-model "Turn snapshot").
3. The context reading resets at the transcript's last `compact_boundary` entry. With
   no usage after the boundary, nothing is printed and the marker is not touched
   (FR-017).

### `stop` (replaces 010 steps 1-5)

1. No usable snapshot for this session: compare against HEAD, as in 010 (FR-010).
2. Diff the tree against the snapshot (or HEAD). Nothing in either tier changed: delete the
   snapshot, exit 0.
3. Loop guard: read `stop_hook_active`. The guard is read **before** the `uv` and
   timeout-tool checks, so a missing `uv` cannot block twice (FR-012). `jq` and `git`
   are still checked first, as in 010: the guard cannot be read without `jq`. So a
   missing `jq` or `git` still blocks every Stop.
4. Run, under the gate time limit:
   - any **full-tier** change: ruff on the changed `.py` files that still exist, then
     both suites;
   - only **drift-tier** changes: `pytest tests/test_context_drift.py`.
5. Verdict:

| Outcome | `stop_hook_active` = false | `stop_hook_active` = true |
|---|---|---|
| green | delete snapshot, exit 0 | delete snapshot, exit 0 |
| red | keep snapshot, exit 2, failures on stderr | **keep snapshot**, systemMessage "still RED", exit 0 |
| timed out | as red; the failures text starts `=== gate TIMED OUT after <N>s ===` | as red |
| no timeout tool | as red; text `timeout or gtimeout is required (brew install coreutils)` | as red |
| `uv` missing | as red; text `uv is required` | as red |

The kept snapshot is reused by the next `turn-start`, so the next turn is judged
against the same baseline (FR-013). It is removed by the first green Stop, or by a
Stop that finds no change against it. The 7-day prune in `resolve_snapshot` never
removes the session's own snapshot: that function returns as soon as the own file
exists. Only another session's `turn-start` or Stop prunes it after 7 days.

The cost of FR-013: until the tree is green, every later turn of the session runs the
gate at Stop and blocks once, a docs-only turn included. A new session that adopts the
snapshot (010 FR-001) inherits this. Not adopting across sessions was turned down: it
undoes the adoption step FR-013 relies on.

### AF-COMMIT gate run (extends 010 `policy.sh` AF-COMMIT)

- Limit: `GATE_LIMIT` = `${AF_GATE_LIMIT:-240}` s, below the PreToolUse `timeout`
  of 300 s. A value that is not a positive integer, or is above 240, is replaced by
  240, so a large `AF_GATE_LIMIT` cannot outlast the hook timeout. Small values stay
  (V2 uses 5).
- Runner: `timeout`, or `gtimeout` if `timeout` is missing. Each step runs as
  `<runner> --kill-after=5 <left>s <cmd…>`, where `<left>` is the time left before
  the deadline.
- Outcome `timed out` (exit 124 or 137) and outcome `no timeout tool` deny with their
  own messages below. A red run denies with the main AF-COMMIT message, as in 010.

### `session-context.sh` (amends 010)

The fixed rule list becomes `AF-SPEC AF-SECRET AF-COMMIT AF-REGISTRY AF-HARNESS
AF-HOOKS`. The feature number is found as in AF-SPEC, so a rebase shows the branch
being rebased.

## Rule messages (amends 010 "Rule messages")

Every first line still matches `^\[AF-[A-Z]+\] .+\. To proceed: .+$`. No message
contains a `'`: the launcher prints its message inside a single-quoted `sh` string.

| ID | Case | First line |
|---|---|---|
| AF-HOOKS | scripts missing (launcher) | `[AF-HOOKS] The repo hook scripts (.claude/hooks/<script>) were not found in this worktree or in the launch directory, so this call cannot be checked. To proceed: start a new Claude Code session in an existing worktree of this repo (the main checkout or claude --worktree), or restore .claude/hooks/ from a terminal outside Claude Code.` |
| AF-HOOKS | input empty or invalid | `[AF-HOOKS] The repo policy hook got no valid input, so it cannot judge this call. To proceed: retry the call; if it repeats, restart the session and report it.` |
| AF-HOOKS | repo root not resolved (`policy.sh`) | `[AF-HOOKS] policy.sh cannot resolve the repo root from <script path>, so this call cannot be checked. To proceed: check that the worktree directory exists and can be entered, or start a new Claude Code session in an existing worktree of this repo.` |
| AF-HOOKS | `lib.sh` not loaded | `[AF-HOOKS] .claude/hooks/lib.sh could not be loaded, so every covered tool call is refused. To proceed: from a terminal outside Claude Code, run git checkout HEAD -- .claude/hooks/lib.sh (in a stopped rebase or merge, run git rebase --abort or git merge --abort first, or fix the conflict or syntax error in an editor), then retry.` |
| AF-SECRET | Read, Grep, Glob | unchanged from 010 |
| AF-SECRET | Bash (**new**, `MSG_SECRET_SHELL`) | `[AF-SECRET] Shell commands may not name .env or .env.braintrust: these files hold live credentials, and reading, writing or copying them from the shell is refused. To proceed: use .env.example for variable names and ask the operator for any value you need. If the command only mentions the name as text (a commit message, a search string), write that text to a file and pass the file (git commit -F <file>, grep -f <file>), or ask the operator.` |
| AF-COMMIT | red run (verbs widened) | `[AF-COMMIT] git commands that write commits (commit, revert, cherry-pick, merge, am, rebase, pull) require ruff (whole repo) and both pytest suites to be green. To proceed: fix the failures below, then run the command again.` |
| AF-COMMIT | timed out (**new**) | `[AF-COMMIT] The commit gate timed out after <N>s, so this commit cannot be checked. To proceed: find the slow test (--durations=10), fix it, then commit again.` |
| AF-COMMIT | no timeout tool (**new**) | `[AF-COMMIT] The commit gate needs GNU timeout (timeout or gtimeout) to bound its run. To proceed: install it with brew install coreutils, then commit again.` |
| AF-SPEC | — | unchanged from 010 |

## Matching rules (amends 010 "Matching rules")

### AF-SECRET, file tools (states shipped behaviour; FR-006)

This is the ruling T042 item 7 asked for. `SECRET_RE` is shared with the Bash
check: the `glob`/`pattern` match below uses the same regex, so FR-009's wider
delimiters widen it too. That is benign: a Glob pattern such as `{.env,x}`,
`{x,.env}` or `x:.env` is now denied as well. One regex stays, not two. The only
file-tool code change is the whole-glob match below (2026-10-13, after the
implementation review).

- The basename of the path is lower-cased, then compared with `.env` and
  `.env.braintrust`. So `.ENV` and `.Env.Braintrust` are denied.
- The check applies in any directory, not only at the repo root.
- Grep checks `path` and `glob`. Glob checks `path` and `pattern`. A `glob` or
  `pattern` is lower-cased, its `*` and `?` become spaces, and then the **whole**
  string (not only its basename) is matched against the secret pattern. So `.env*`,
  `.env{,.braintrust}`, `*.env`, `**/*.env` and `{.env,pkg/x.py}` are denied, and
  `**/*.env.example` passes.
- Known gap: a glob is a small language of its own, so a spelling with a wildcard
  inside the name (`[.]env`, `.en?`, `.e*`) still gets through. Like the Bash check,
  this is a best-effort pattern match (010 FR-016), not a boundary.
- Grep's search `pattern` is never checked.
- `.env.example` passes in every spelling.

### AF-SECRET, Bash (FR-007, FR-009)

- The command is lower-cased before matching, so `.ENV` is denied.
- `.env` or `.env.braintrust` is matched when it follows the start of the command, a
  space, or one of `/ ' " = <` and, **new**, `` > ` @ { , : ( ``. The `>` covers
  shell writes such as `echo x >.env`; the `:` covers `scp host:.env` and
  `git show HEAD:.env`; the `(` covers `less (.env)`. It must be
  followed by the end of the command, a space, or one of `; | & ) ' " < > * ? [ { } , `
  and the backtick. The `}` covers `cat {x,.env}`. The exact regex is in data-model
  "AF-SECRET matching".
- `.env.example` passes: the `.` after `.env` is not a trailing delimiter.
  `.environment` passes for the same reason (a letter is not a delimiter), in Bash
  and in the file tools.
- A Bash deny uses `MSG_SECRET_SHELL` ("may not name"); a file-tool deny keeps
  010's `MSG_SECRET`.
- This is a best-effort pattern match, not a security boundary (010 FR-016 stands).

### AF-SPEC path (FR-008, FR-014)

- The path is made absolute against `ROOT`, then empty (`//`) and `.` segments are
  dropped and `..` segments are resolved as text on the whole absolute path. A `..` at
  `/` stays at `/`, as the kernel reads it, so `/..<root>/harness/a.py` is guarded.
  Nothing is looked up on disk, so symlinks are not followed.
- Only the resolved path is compared with `ROOT`. A path that resolves outside `ROOT`
  is ignored, as in 010. `<root>/../<rootname>/harness/a.py` resolves inside `ROOT`
  and is guarded.
- The first segment is lower-cased before the `harness/`, `orchestration/`, `eval/`
  match. `docs/../harness/a.py`, `./harness/a.py` and `Harness/a.py` all get the
  verdict of `harness/a.py`. `harness/../pkg/a.py` and `harnessx/a.py` are not
  guarded.
- During a rebase (detached HEAD), the branch comes from `rebase-merge/head-name` or
  `rebase-apply/head-name`. Its `specs/NNN-*/tasks.md` counts when it is in the
  working tree or on the tip of the branch being rebased.

### AF-COMMIT command (FR-005)

- **Floor, as in 010:** the command is gated when it has the word `git` and one of
  the verbs `commit`, `revert`, `cherry-pick`, `merge`, `am`, `rebase`, `pull`
  anywhere. Word boundaries as in 010.
- **Exemption:** after joining backslash-newlines, the command is split into segments
  on `;`, `&&`, `||`, `|` and newlines. Quotes are not parsed. The command is not
  gated only when every segment that has one of the verbs is an exempt segment:
  - exactly `git [-C <path> | -c <key=value>]… (rebase|cherry-pick|merge|am|revert)
    (--abort|--quit)`, with nothing after it; or
  - `git pull` with no option before `pull`, where `--ff-only` is the only token after
    `pull` that starts with `-`, and the repo's `pull.rebase` config is unset or
    `false`. Such a pull cannot create a commit. The `pull.ff` config alone exempts
    nothing.

  Both shapes also need: exactly one of the seven verb words in the segment, and only
  plain tokens: each token holds nothing but letters, digits and `_ . / : @ + = -`.
  So a `-C` value cannot hide a command substitution, and `--no-ff` or `--rebase`
  cannot ride along with `--ff-only` (git keeps the last of `--ff-only`/`--ff`/`--no-ff`),
  not even quoted or backslash-escaped, which the shell strips, nor brace- or
  glob-expanded (`{--no-ff,}`, `[-]-no-ff`), which the shell expands (quotes and
  backslash added 2026-10-13; the plain-token list replaced a list of refused
  characters on 2026-10-13, after braces and globs got through it). A `-C ~/x` path
  is therefore gated too, which errs toward gating.
- `commit` is never exempt. `--skip` is never exempt: it resumes the replay and writes
  the remaining commits.
- **What it judges.** The gate judges the tree **before** the command runs. On a red
  tree it blocks every history write, including a merge or cherry-pick meant to bring
  in a fix: make the tree green first (for example `git checkout -- <file>`). It does
  not vet the content a merge, rebase or pull brings in; the next Stop judges that
  (research R5).
- **Best-effort gap.** A verb the floor cannot see, such as a git alias (`git ci`) or
  a quoted verb (`git c''ommit`), was never gated in 010. Next to an exempt segment,
  as in `git rebase --abort; git ci -m x`, the floor no longer catches it either,
  because the only verb word sits in the exempt segment. Gating every command where
  another `git` segment shares the line would put the full gate on
  `git merge --abort && git status`, so this is left open (2026-10-13).

| Command | Gated |
|---|---|
| `git commit -m x` | yes (as in 010) |
| `git commit -m "allow git rebase --abort"` | yes: a `commit` segment is never exempt |
| `git merge topic -m "see --abort"` | yes: not an exact exempt segment |
| `git rebase --continue` | yes |
| `git rebase --abort` | no |
| `git -C ../wt merge --quit` | no |
| `git rebase --abort && git commit -m x` | yes |
| `git cherry-pick --skip` | yes |
| `git merge --no-ff topic` | yes |
| `git pull` | yes |
| `git pull --ff-only` (`pull.rebase` unset) | no |
| `git -c pull.rebase=true pull --ff-only` | yes: an option before `pull` |
| `git pull --rebase` | yes |
| `git pull --ff-only -r` | yes |
| `git pull --ff-only --no-ff` | yes: a second option after `pull` |
| `git pull --ff-only "--no-ff"` | yes: a quote in the segment |
| `git pull --ff-only {--no-ff,}` | yes: braces are not plain; the shell expands them to `--no-ff` |
| `git pull --ff-only [-]-no-ff` | yes: a glob is not plain |
| `git pull --ff-only origin main` | no |
| `git -C $(git${IFS}commit${IFS}-qam${IFS}x) rebase --abort` | yes: `$` and `(` in the segment |
| `git rebase --abort 2>/dev/null` | yes: not an exact exempt segment |
| `git status && git am x.patch` | yes |
| `git log --grep=merge` | yes: `=` is not a word character in 010's boundary, so this errs toward gating |
| `echo commit; git status` | yes: the 010 floor, and no segment is exempt |
| `for v in commit; do git $v; done` | yes: the 010 floor |
