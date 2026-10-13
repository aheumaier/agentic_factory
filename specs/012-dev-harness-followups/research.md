# Research: Dev-Harness Follow-ups to 010 (012)

Phase 0 of `/speckit-plan`, written 2026-10-12. Each item gives a decision, the
reason, and the options turned down. Nothing in the Technical Context is left open.

Facts used throughout:

- Claude Code on this machine is 2.1.285.
- A hook that exits 2 blocks. Any other non-zero exit is a "non-blocking error", and so
  is a hook that hits its `timeout`. Exit 127 counts too. In all of these cases the tool
  call goes ahead.
- `onFailure: "block"` only exists from Claude Code 2.1.295, so it is not available here.
- Hook scripts run under bash 3.2 (`/usr/bin/env bash` on macOS). Settings `command`
  strings run under `/bin/sh`.

---

## R1 — Cause of the 2026-10-11 fail-open (FR-001)

**Reproduced from the session record.** The transcript of the 010 implementation
session (`~/.claude/projects/-Users-aheumaier-Codebox-agentic-factory/6edc5564-….jsonl`)
holds one hook error:

```
2026-10-11T09:29:12.216Z  attachment.type = hook_non_blocking_error
hook: PreToolUse:Bash   statusMessage: "repo policy (AF-*)"   exitCode: 127
cwd: …/.claude/worktrees/010-dev-harness-hardening
stderr: /bin/sh: …/010-dev-harness-hardening/.claude/hooks/policy.sh: No such file or directory
tool call: git cherry-pick 889785f
```

The steps before it, all in the 010 worktree that the session was launched in:

1. 09:28:50Z: `git reset --hard origin/main`. At that moment `origin/main` was
   `40a2c40` (fetched 2026-10-11 01:10 +0200; next pushed 11:45 +0200). `40a2c40` holds
   only an older `.claude/hooks/py-check.sh`. It has no `policy.sh` and no `lib.sh`, and
   its `.claude/settings.json` has no `PreToolUse` entry. The 010 hooks commit `7d005ba`
   is not an ancestor of `40a2c40`.
2. 09:28:50Z: `git cherry-pick 889785f` stopped on a conflict. That commit only touches
   two orchestration test files, so it never brought the hooks back.
3. 09:29:12Z: the next Bash call fired `PreToolUse` → `"$CLAUDE_PROJECT_DIR"/.claude/hooks/policy.sh`.
   The file was gone, so `/bin/sh` exited 127. That is a non-blocking error, so the call
   ran with no rule applied.

**Cause.** The session kept the hook configuration it loaded at launch. The hook
still fired although the `settings.json` on disk no longer listed it. That
configuration names the script by path under `CLAUDE_PROJECT_DIR`. Once the tree under
that path lost the script, every covered call failed open with exit 127. Removing the
launch worktree fails the same way, because `CLAUDE_PROJECT_DIR` is fixed at launch and
does not follow `EnterWorktree` (Claude Code docs). The scratchpad probe
reproduces the command level: `/bin/sh -c '"/nonexistent/.claude/hooks/policy.sh"'` → rc 127.

Observed but not confirmed in Claude Code's source: that it snapshots the hook config at
launch. The evidence is that the hook fired after the on-disk entry was gone. The
design below does not depend on it. It only needs the config text to survive while the
script does not, and the 2026-10-11 record shows exactly that.

**Decision.** Move the "find the script" step out of the script and into the
`command` string in `.claude/settings.json`: a short POSIX `sh` launcher, the same for
every hook entry apart from the script name and mode. It works like this:

1. It reads the payload once (`p=$(cat)`) and passes it on to the script on stdin.
2. It takes the worktree from the payload's `cwd` (`jq -r '.cwd // empty'`, or `pwd`
   when jq is missing or the field is empty) and climbs to its toplevel with
   `git rev-parse --show-cdup`, `cd` and `pwd`. Unlike `--show-toplevel`, this keeps the
   `cwd`'s spelling, symlinks included, so `ROOT` still compares with `file_path` as text.
3. It runs `<toplevel>/.claude/hooks/<script>` if that file exists. If not, it runs
   `$CLAUDE_PROJECT_DIR/.claude/hooks/<script>` if that one exists.
4. If neither exists:
   - **PreToolUse**: print `[AF-HOOKS] …` on stderr and exit 2 (deny).
   - **Every other event**: print a `systemMessage` notice and exit 0 (never block).

The message text is in `contracts/hook-interface.md`.

**Rationale.**

- The 2026-10-11 record shows that the hook config outlives the tree change, and only
  the script vanished. A launcher written into the config is the one piece that is
  still there when the failure happens.
- FR-001 allows either "keep applying the rules from the current worktree" or "deny
  with the recovery". The launcher does the first when it can and the second when it
  can't.

**Alternatives turned down.**

- `onFailure: "block"`: needs Claude Code 2.1.295 or later. On 2.1.285 the key does
  nothing.
- A launcher script stored in the repo: it can vanish just like `policy.sh`.
- A launcher in `~/.claude/`: it is not in the repo, so other clones and the E2B
  sandbox would not have it.
- Only documenting "don't reset the launch worktree": this is what failed on
  2026-10-11.

**SC-001: what automated tests cover and what stays live.** Automated tests in
`tests/test_harness_hooks.py` run the launcher string read from `settings.json`
through `/bin/sh` with:

- (a) `CLAUDE_PROJECT_DIR` pointing at a removed directory and the payload `cwd` in a
  second worktree that has the hooks. Expected: the second worktree's rules apply,
  e.g. an AF-SECRET deny.
- (b) both locations without the scripts. Expected: PreToolUse exits 2 with
  `[AF-HOOKS]`, and the other events exit 0 with a notice.
- (c) `cwd` outside any git repo. Expected: fall back to `CLAUDE_PROJECT_DIR`.

Tests cannot show what Claude Code itself does: that it really runs the launcher with
the payload `cwd` after `EnterWorktree`, and that exit 2 really refuses the call. That
part is the live scenario in `quickstart.md` V1.

## R2 — Repo root inside the scripts (FR-002)

**Decision.** Each script takes `ROOT` from its own location
(`$(cd "$(dirname "$0")/../.." && pwd)`), no longer from `CLAUDE_PROJECT_DIR`. The
launcher (R1) already picked the script that belongs to the current worktree, so its
location is the current worktree.

**Rationale.** One line per script, and there is one source of truth for the root.

**Edge cases.**

- A turn can start in worktree A and stop in worktree B. B then has no snapshot, so
  Stop falls back to HEAD (010 FR-010). Its result can only be wider, never narrower.
- A `cwd` inside an unrelated repo that ships its own `.claude/hooks/<script>` would
  run that repo's script. The same goes for a script the session itself edited from
  the shell. This is no worse than 010, whose FR-026 already leaves shell edits of the
  hook scripts open. It is recorded in the plan's Risks. A check that the toplevel
  shares this repo's git common dir is left for later.

**Alternative turned down.** Keep `CLAUDE_PROJECT_DIR` and also compare it with the
payload `cwd`: two roots to reconcile, and it still breaks once the launch directory
is gone.

## R3 — Inner time limit for the commit gate (FR-003)

**Measured** on 2026-10-11 on this Mac, Apple Silicon, with Temporal up:

| Step | Time | Result |
|---|---|---|
| ruff | 0 s | clean |
| root suite | 26 s | 271 passed |
| orchestration suite | 27 s | 167 passed |
| **total** | **about 53 s** | |

010 measured about 6 s before the live-Temporal tests ran.

**Decision.**

- The hook `timeout` stays at 300 s.
- The gate's own limit is `GATE_LIMIT=240` s, set in `lib.sh` and overridable by
  `AF_GATE_LIMIT` so tests can use 1 s. A value above 240 or not a positive integer
  becomes 240, so the override cannot outlast the 300 s hook timeout.
- The limit covers ruff plus both suites, measured from the start of the gate. Each
  step gets the time that is left.
- Each step runs under GNU `timeout` (or `gtimeout`). GNU timeout puts the command in
  its own process group and kills the whole group, so pytest children don't outlive it.
- An exit of 124 (or 137, after the kill-after) from any step ends the gate. AF-COMMIT then denies with "timed out
  after 240 s".
- If neither `timeout` nor `gtimeout` is installed, AF-COMMIT denies (fail closed)
  and names `brew install coreutils`. This works the same way as the existing
  missing-`uv` check.
- The Stop gate uses the same runner, so a slow turn reports "timed out" as red
  instead of tripping its own 300 s hook timeout.
- A settings test asserts `GATE_LIMIT` is below the PreToolUse and Stop `timeout`s
  and is clamped to 240, the same way the `CTX_BUDGET` test works.

**Rationale.**

- 240 s is about 4.5 times today's run, so normal growth is still allowed.
- The 60 s left over covers the path checks, building the deny and process cleanup.
  The edge case "the inner limit must leave room to print the deny" is met.
- Without the inner limit, a 300 s hook timeout is non-blocking, so a slow red gate
  would let the commit through. That is the bug FR-003 closes.
- The operator's Mac has `/opt/homebrew/bin/gtimeout`, and `timeout` is also on PATH
  through coreutils gnubin. Linux, including the E2B image, ships `timeout`.

**Alternatives turned down.**

- A bash 3.2 watchdog (`sleep N; kill -- -$pgid` with `set -m`): about 15 lines of job
  control to replace one coreutils call.
- `perl -e alarm`: kills `uv` but not its pytest child, which is left orphaned.
- Raising the hook timeout to 600 s: it does not close the fail-open, it only moves it.

## R4 — Policy input that is empty or invalid (FR-004)

**Decision.** After the bounded read, if `jq -e 'type == "object" and (.tool_name | type == "string")'`
fails on the input, policy.sh denies with exit 2 and
`[AF-HOOKS] The repo policy hook got no valid input, so it cannot judge this call. To proceed: retry the call; if it repeats, restart the session and report it.`

**Rationale.** Claude Code always sends a JSON object with `tool_name`. Anything else
means the harness is broken, and FR-001 says broken means deny.

**Alternative turned down.** Treat empty input as "hand run, allow". That is today's
behaviour, and it fails open.

## R5 — Which git commands AF-COMMIT gates (FR-005, edge case `git pull`)

**Decision.**

1. **Floor, as in 010.** A command that has the word `git` and one of the words
   `commit`, `revert`, `cherry-pick`, `merge`, `am`, `rebase` or `pull` anywhere is
   gated, unless step 3 exempts it.
2. **Segments.** Join each backslash-newline, then split the command into segments on
   `;`, `&&`, `||`, `|` and newlines.
3. **Exemption.** The command is not gated only when **every** segment that has one
   of the seven verb words is an exempt segment. An exempt segment is exactly one of:
   - `git`, then any `-C <path>` or `-c <key=value>` pairs, then
     `rebase|cherry-pick|merge|am|revert` and then `--abort` or `--quit`, with nothing
     after it;
   - `git pull` with no options between `git` and `pull`, where `--ff-only` is the
     only token after `pull` that starts with `-`, and
     `git -C ROOT config --get pull.rebase` is unset or `false`. A second option
     could undo it: git keeps the last of `--ff-only`, `--ff` and `--no-ff`, so
     `--ff-only --no-ff` makes a merge commit.

   Both shapes also need exactly one of the seven verb words in the segment and only
   plain tokens (letters, digits and `_ . / : @ + = -`). Otherwise
   `git -C $(git${IFS}commit${IFS}-qam${IFS}x) rebase --abort` would pass, which
   010's floor gates, and so would `git pull --ff-only {--no-ff,}`, which the shell
   expands to `--ff-only --no-ff` (a list of refused characters was replaced by this
   allow-list on 2026-10-13, after quotes, braces and globs got through it). `commit` is never exempt. `--skip` is never exempt: it resumes the replay and
   writes the remaining commits.
4. The `pull` checks are token checks, not word checks: 010's word boundary counts
   `-` as a word character, so the word `rebase` does not match inside `--rebase`.
   A `pull.ff=only` config alone does not exempt a pull (2026-10-12: it would let
   `git pull --rebase` through). A `-c pull.rebase=true` before `pull` is not read by
   the config check, so any option before `pull` removes the exemption.

The word-boundary style stays as in 010: `(^|[^[:alnum:]_.-])WORD($|[^[:alnum:]_.-])`.

**What the gate judges.** AF-COMMIT judges the working tree **before** the command
runs. So it blocks history writes while the tree is red. It does not vet the content
a merge, cherry-pick, rebase, am or pull brings in: Stop judges the tree afterwards.
The cost: on a red tree, `git merge main` to pick up a fix from `main` is denied. The
repair is to make the tree green first, for example with `git checkout -- <file>`
(2026-10-12; gating only `commit` and the `--continue` forms was turned down, because
it adds a false-negative path and contradicts FR-005).

**Rationale.**

- `pull.rebase` and `pull.ff` are unset in this repo (checked 2026-10-11). With git's
  defaults, a pull on a diverged branch creates a merge commit, so the edge case
  "gated only if it can create a merge commit here" means gate it.
- Splitting into segments stops `git rebase --abort && git commit` from passing as an
  abort.
- 010's rule stays: false positives (e.g. `git log --grep merge`) are accepted, false
  negatives are not. A false positive costs one green gate run of about 53 s, or a
  deny on a red tree.

**Alternative turned down.** Parse the command with a shell parser: there is none in
bash 3.2, and a hand-written one would be far more code than the regex.

## R6 — AF-SECRET: contract as shipped, shell wording, case and delimiters (FR-006, FR-007, FR-009)

**Decision.**

- **FR-006, contract only, no code change.** The 012 contract states what
  `is_secret_path` does today:
  - the path's basename is lower-cased (`LC_ALL=C tr`);
  - it matches `.env` or `.env.braintrust` in any directory;
  - for Grep, both `path` and the `glob` filter are checked;
  - for Glob, both `path` and `pattern` are checked;
  - a `glob` or `pattern` is also denied when the whole string, with `*` and `?`
    read as spaces, matches `SECRET_RE`, e.g. `.env*`, `.env{,.braintrust}`,
    `{.env,pkg/x.py}`, `*.env` or `**/*.env` (2026-10-13, implementation review:
    a basename-only match missed a brace list with a `/` and a leading `*`; this
    one code change makes the contract true). `**/*.env.example` stays allowed.
    Spellings such as `[.]env`, `.en?` or `.e*` still pass, best effort as in
    010 FR-016;
  - Grep's `pattern` is file content and is not checked.
- **FR-007.** A new `MSG_SECRET_SHELL` is used for Bash:
  `[AF-SECRET] Shell commands may not name .env or .env.braintrust: these files hold live credentials, and reading, writing or copying them from the shell is refused. To proceed: use .env.example for variable names and ask the operator for any value you need. If the command only mentions the name as text (a commit message, a search string), write that text to a file and pass the file (git commit -F <file>, grep -f <file>), or ask the operator.`
  The last sentence was added 2026-10-13 after the implementation review.
  The Read/Grep/Glob message stays as it is.
- **FR-009.**
  - The Bash command is lower-cased before matching (`LC_ALL=C tr`, as in
    `is_secret_path`).
  - The leading delimiter class gets `>`, `` ` ``, `@`, `{`, `,`, `:` and `(`. The new
    regex is
    `(^|[[:space:]/'"=<>`@{,:(])\.env(\.braintrust)?($|[[:space:];|&)'"<>*?[{}`,])`.
    The trailing class also gets `` ` ``, `,` and `}`, so `` `cat .env` ``, `{.env,x}`
    and `{x,.env}` match. The `:` covers `scp host:.env` and `git show HEAD:.env`
    (added 2026-10-12 after the architecture review). The `>` (shell writes such as
    `echo x >.env`) and the `}` were added 2026-10-13 after the implementation review.
  - `.env.example` still never matches, because a `.` is not in the trailing class.
  - `SECRET_RE` is shared with the file-tool `glob`/`pattern` check, so that check
    widens too. This is benign (more glob spellings denied) and keeps one regex.

**Rationale.**

- T042 item 7 asks for a ruling. The ruling is to keep the code and make the contract
  state it.
- Lower-casing matches the macOS case-insensitive volume. `is_secret_path` already
  does this, so the shell check only catches up.

**Alternative turned down.** A list of shell verbs (cat, cp, source, …): it can never
be complete, and 010 FR-016 already calls this check best effort.

## R7 — AF-SPEC path normalisation (FR-008)

**Decision.** `rel_path` normalises the path lexically before the prefix match:

- `.` segments are dropped;
- each `..` removes the segment before it. This runs on the whole absolute path, after
  a relative path is prefixed with the root, so `<root>/../<rootname>/harness/a.py`
  becomes `<root>/harness/a.py` and is guarded;
- a `..` with no segment left before it stays at `/`, as the kernel reads `/..`
  (amended 2026-10-13 after the implementation review: returning *outside* there let
  `/..<root>/harness/a.py` skip AF-SPEC);
- only then is the result compared with the root prefix. A result that does not start
  with `<root>/` is outside the root.

This matches data-model "AF-SPEC path", which is the normative rule (T006 review,
2026-10-13).

AF-SPEC then lower-cases the first segment of the relative path before matching
`harness/*`, `orchestration/*` or `eval/*`. Nothing is looked up on disk: no
`realpath` and no symlink resolution. A symlink is judged by its spelling, as the
spec's edge case says.

**Rationale.** It closes the three spellings named in FR-008 and stays inside bash
3.2 string handling. The `/var` vs `/private/var` note in `rel_path` still holds,
because the R1 launcher keeps the `cwd`'s spelling (`--show-cdup`, not
`--show-toplevel`) and `ROOT` follows the launcher's path.

**Alternatives turned down.**

- `realpath`/`python -c os.path.realpath`: this is a disk lookup, which breaks the
  "judged by spelling" ruling, and it fails for new files.
- Folding the case of the whole path: that would wrongly match a root spelled in a
  different case on a case-sensitive Linux volume. Only the top-level directory is
  named in FR-008.

## R8 — The swe-agent "checks still fail" account (FR-011, T042 item 6)

**Decision.**

- `IMPLEMENT_PROMPT` loses its commit sentence. New ending:
  "…run this repo's existing tests/verification locally. Do not commit: the harness
  commits your work. In your final message, list the checks you ran and, for any that
  still fail, why. That message goes into the pull request for the human reviewer.
  When you are done, STOP: …"
- `FEEDBACK_PROMPT_SUFFIX` ends with "…before re-running verification." The words
  "and committing" go.
- `TASK_PROMPT` (the per-task path, specs/011 F7-a) gets the same sentence: "In your
  final message, list the checks you ran and, for any that still fail, why."
- The harness keeps the `result` text of the last `ResultMessage` of each model
  session in this process. On the `run_implement` path that is one text. On the
  `run_per_task` path each task's text is kept under a `### <task ID>` header, in
  task order. `push_and_open_pr` puts the lot under `## Agent verification notes`,
  inside a `~~~` fence and cut to one 4 000-character cap (data-model "Verification
  notes"). A new PR gets the section in its body. When the PR already exists, the same
  section is posted as a PR comment (see "PR that already exists" below). When there
  is no such text (the all-done shortcut, or no result message), the section is left
  out.
- **This widens FR-011's mechanism.** FR-011 names the `IMPLEMENT_PROMPT` change
  only, but its aim is that the reason reaches the reviewer. One session per open task
  is the default path (specs/011 F7-a), so a change to `IMPLEMENT_PROMPT` alone would
  miss most runs
  (2026-10-12, architecture review). The operator can veto this before
  `/speckit-tasks`.
- The stale "rerun with the prompt's commit instruction" wording in
  `verify_new_commit` becomes "the harness commits any change, so none was made".
  When the tree is still dirty, the harness's own commit failed, and the message says
  so instead: "the harness's commit failed (see the checkpoint stderr above), so the
  work is uncommitted" (2026-10-13, implementation review).

**Paths traced.**

- **Normal run.** `checkpointer.finish()` commits the edits, the PR opens, and the
  notes are in the body.
- **Seat handoff (exit 75/77).** No PR on this seat. The successor seat opens the PR
  with its own final notes, which are the notes about the last verification run. An
  earlier seat's notes are not carried over. This is accepted, because those notes
  describe a tree that the successor has since changed.
- **No new commit** (first seat, or open tasks left). `verify_new_commit` raises
  before any PR exists. There is no change for a reviewer, so there is nothing to
  account for. The error goes to the activity result and the Temporal history, as it
  does today.
- **Successor with every task done.** The check is skipped (specs/011 F5) and the PR
  opens with this seat's notes.
- **GitHub-comment path** (`swe-agent-build.yml`). This is the same `agent.py`, so the
  behaviour is the same.
- **PR that already exists** (added 2026-10-13, T006 review). Under the
  `architect-stage-v1` patch, `ensure_target_pr_activity` opens the target PR before
  Build (`orchestration/activities.py`, `pipeline_workflow.py`), and on build attempts
  2 and 3 the PR exists too. `push_and_open_pr` then takes its "already exists" branch,
  and a `.pr-body.md` is never applied. So on the Temporal path the body alone would
  never carry the notes. The harness posts the section as a PR comment instead:
  `gh pr comment <PR URL> --body-file <file>`, with the fixed header as its first line.
  The URL comes from `gh pr list --head <branch>`, because gh reads an all-digit branch
  name such as `123` as PR #123 (2026-10-13, implementation review).
  The webhook bridge (`orchestration/webhook_bridge/grammar.py` `parse`) reads only the
  first non-empty line of a comment, so the model's text below the header cannot be
  parsed as a run or gate command. A failed comment call is a warning on stderr, not a
  failed run. That the per-sandbox App token (pull requests write) may post the
  comment is expected from GitHub's permission table, not yet seen in a run: the next
  supervised run checks it (quickstart V8).

**Rationale.**

- The PR body is the first thing the reviewer reads. Today the commit message is
  three clicks away.
- `run_implement` already loops over every message, so this needs a few lines and no
  new file in the target repo.
- The harness checkpoint commit stays the only commit, so AF-COMMIT has nothing to
  deny.
- It also removes the force-hook hazard that `TASK_PROMPT` already avoids: a model
  commit before the task is ticked counts toward the force check (specs/011 research
  R10).

**Alternatives turned down.**

- A notes file written by the model into the target repo: it gets committed by the
  checkpointer, it adds noise to the diff, and a run that only writes notes would
  count as "work" and pass `verify_new_commit`.
- The notes in the `checkpoint: end of run` commit message: still three clicks away,
  and the commit message is fixed by the harness.
- A PR comment *instead of* the body: needs one more `gh` call for every run. It was
  first turned down for every case; the "PR that already exists" trace above reopened
  it for the case where the body is never applied.
- The notes as plain Markdown or a `> ` quote: a `Fixes #12` line in a PR body closes
  issue 12 on merge, and an `@user` pings people, in a quote as well. A fenced block
  is not parsed for either (T006 review).

**Files that change with it:**

- `tests/test_swe_agent_seat.py:322-327`, which pins "git add -A && git commit";
- new tests for the PR-body section on both paths: one `IMPLEMENT_PROMPT` run, and a
  per-task run with two tasks (two `###` headers, one cap); one where `gh pr create`
  says "already exists" (the section goes to `gh pr comment`); one with `Fixes #1` and
  `@someone` in the notes (both stay inside the fence);
- `docs/40-sequence-swe-agent-runtime.md:47,86`;
- `registry/agents/swe-agent/SKILL.md` prose. Its `manifest.yaml` and versions do
  not change, so AF-REGISTRY does not apply.

## R9 — Missing `uv` and the double-red snapshot at Stop (FR-012, FR-013)

**Decision.**

- **FR-012.** In `stop`, `require_tools py-check.sh uv` is replaced. A missing uv adds
  `=== uv FAILED ===` with "uv is required" to `$failures` and skips the runs. The
  normal red path follows: block once, then the still-red notice when
  `stop_hook_active` is true. The edit-mode `require_tools uv` stays, because
  PostToolUse cannot loop.
- **FR-013.** In the `stop_hook_active` branch, drop `rm -f "$snap"`. The snapshot
  survives. The next `turn-start` finds its own pending file and keeps it (010 FR-001),
  so the next turn is judged against the same baseline.

**Rationale.**

- Both are one-line changes that reuse the existing red path.
- The kept snapshot is deleted by the next green Stop, or by a Stop that finds no
  change against it. The 7-day prune does **not** reach it: `resolve_snapshot`
  returns as soon as the session's own file exists (`lib.sh:120-137`). Only another
  session's `turn-start` or Stop prunes it after 7 days.
- **Cost.** Until green, every later turn runs the gate at Stop and blocks once, a
  docs-only turn included. A new session that adopts the snapshot inherits this. It is
  accepted: FR-013 asks for exactly this "stays red until fixed" behaviour. Not
  adopting snapshots across sessions was turned down, because it undoes 010 FR-001's
  adoption step that FR-013 relies on. A test pins the docs-only case.

**Alternative turned down.** Delete the snapshot but mark the files as dirty in a
side file: a second state file to do what keeping the first one already does.

## R10 — AF-SPEC during a rebase (FR-014)

**Decision.**

- When `git symbolic-ref` fails, `feature_number` reads
  `$(git rev-parse --git-path rebase-merge/head-name)`, then the `rebase-apply` one,
  and strips `refs/heads/`.
- AF-SPEC accepts a `specs/NNN-*/tasks.md` found in the working tree, as today, or one
  found on the rebased branch's tip:
  `git ls-tree -r --name-only refs/heads/<branch> -- specs/`, filtered to
  `^specs/NNN-[^/]*/tasks\.md$`.
- `session-context.sh` uses `feature_number` too, so it gets the rebase branch for
  free.

**Rationale.**

- In the middle of a rebase, HEAD is detached and the working tree may be at an
  upstream commit from before tasks.md existed.
- The branch tip is the planned feature the operator is rebasing.

**Alternative turned down.** Exempt AF-SPEC during any rebase: an unplanned branch
being rebased would then pass.

## R11 — Unloadable `lib.sh` (FR-015)

**Decision.** The policy.sh message becomes
`[AF-HOOKS] .claude/hooks/lib.sh could not be loaded, so every covered tool call is refused. To proceed: from a terminal outside Claude Code, run git checkout HEAD -- .claude/hooks/lib.sh (in a stopped rebase or merge, run git rebase --abort or git merge --abort first, or fix the conflict or syntax error in an editor), then retry.`
It keeps exit 2. CLAUDE.md gets one sentence in the harness section that says the
same thing.

**Rationale.** Claude's own Bash calls are denied in this state, so the recovery has
to happen outside the session. Whether `!` shell mode fires hooks is not documented,
so the message does not offer it.

The command is `git checkout HEAD -- <path>`, not `git checkout -- <path>`: when a
rebase or merge stops on a conflict in a hook file, the file holds conflict markers
and is unmerged, and `git checkout -- <path>` then fails with "path is unmerged"
(T006 review, 2026-10-13). Aborting the rebase or merge, or fixing the file in an
editor, works as well.

## R12 — Pruning hook state files (FR-016)

**Decision.** `turn-start` runs one `find "$sd" -maxdepth 1 \( -name 'ctx-*.level' -o -name 'exception-*.notified' \) -mmin +10080 -delete`,
with the same 7-day rule that `resolve_snapshot` uses. `policy.sh` creates the
exception marker but leaves the pruning to turn-start, which runs on every prompt.

## R13 — Stale context reading after compaction (FR-017)

**Confirmed on 2026-10-11** in transcript `c4ceff72-….jsonl`:

- `compact_boundary` is at line 1336 (2026-10-10T15:36:57Z, `preTokens` 470102).
- The last usage before the boundary is 469 415 tokens.
- The first assistant entry after it is at line 1376, 13 minutes later, at 79 099
  tokens.
- The 200-line tail read on the first prompt after compaction includes the entries
  before the boundary, so `context_warn` reads 469 415. The marker de-duplication
  hides that only when the earlier level was `budget`, or `warn` at a warn reading.
  With no marker, for example after a `/clear` that changed the session id, the reading
  sets off a false `budget` notice.

**Decision.** The jq filter tracks entries in order. A `type=="system"` entry with
`subtype=="compact_boundary"` resets the candidate to "none". A later main-thread
assistant usage sets it. "None" at the end means unknown, so nothing is printed and
the marker is left as it is.

This replaces 010 data-model.md lines 141-145 ("Re-arm likely lags compaction by one
prompt … Tests MUST NOT expect re-arm on the very first post-compaction prompt"). After
012, the first prompt after compaction is silent and leaves the marker as it is.
Re-arm still happens on the first reply below `CTX_WARN`. The 012 data model states
this, and the 010 data model gets a pointer.

**Alternative turned down.** Read more than 200 lines: it only moves the window, and
the boundary can still sit inside it.

## R14 — Drift extractor rules and the D-ID corpus (FR-018, FR-019, FR-020)

**Decision.**

- **FR-018, FR-019: contract text only.** The 012 drift contract states the shipped
  rules:
  - tokens are split on whitespace and `,`;
  - a token with `/` is a repo path when its first segment is an existing top-level
    directory, and otherwise each part is classified on its own;
  - `NNN` is a placeholder in the path class;
  - D-REG splits sentences on a `.` followed by any whitespace, newline included, and
    on blank lines;
  - lowercase non-private names (e.g. `shape_issue`, `execute_activity`) are
    unchecked by ruling. The cost is that a rename goes unnoticed.
- **FR-020.** `_corpus` lists `git ls-files -co --exclude-standard -z` instead of
  `os.walk`, then applies the same excluded prefixes (`specs/`, `.claude/`,
  `.specify/`, `**/.venv/`, `node_modules/`) and reads only regular files.
- The test gets a synthetic case: an identifier that exists only in a git-ignored file
  must count as missing.

**Rationale.** Git already knows what is ignored. The `os.walk` prunes were a
hand-copied, partial copy of `.gitignore`.

## R15 — Drift test at Stop (FR-021) and shell files (FR-023)

**Decision.** The turn fingerprint gets two more groups of pathspecs:

- **Full tier**: `*.py`, `*pyproject.toml` and `*uv.lock`, as today, plus
  `.claude/hooks/*.sh` and `.claude/settings.json`. A change here runs ruff on the
  changed `.py` files and both suites. The suites include the shellcheck test and the
  hook and settings tests.
- **Drift tier**: `CLAUDE.md`, `.claude/agents/py-codereviewer.md`,
  `registry/agents/*/manifest.yaml` and `specs/*/spec.md`. A change here, with no
  full-tier change, runs only `pytest tests/test_context_drift.py` (under a second).

A spec directory that is added, renamed or removed always moves its `spec.md`, so
D-SPEC is covered. A registry entry always has a `manifest.yaml`, so D-REG is covered.

**Gap that stays.** A non-Python, non-scope file can hold a D-ID identifier, for
example a YAML file. A change there is caught only at AF-COMMIT, which runs the whole
root suite. This is recorded in the contract.

**Upgrade path.** A snapshot from before 012 has no lines for the drift tier,
`.claude/hooks/*.sh` or `.claude/settings.json`. Its first Stop sees those files as
added, so it runs the full gate once (about 53 s). This is harmless.

**Rationale.**

- Without this, a Python-only Stop gate would run a 53 s gate for every CLAUDE.md
  edit.
- Running a single test file keeps docs turns cheap.
- `.claude/hooks/*.sh` sits in the full tier because FR-023 puts the shell lint "in
  the gate". Without it, a hook-only edit would never be linted at Stop.

**Alternative turned down.** Treat every tier the same (both suites on any watched
change): simpler, but every `/speckit-specify` turn would pay 53 s.

## R16 — Per-test check for the `temporal` mark (FR-022)

**Found.** `_connect_or_skip` is a plain async helper, not a fixture. It appears in
4 modules (`orchestration/tests/test_credential_pool.py:200`,
`test_pipeline_workflow.py:94`, `webhook_bridge/tests/test_integration.py:39`,
`webhook_bridge/tests/test_e2e_pipeline_gate.py:90`). Each copy calls
`Client.connect("localhost:7233")`. No fixture caches a client, and nothing uses
`WorkflowEnvironment`. So a collection-time check on `item.fixturenames` would see
nothing.

**Decision.** A new `orchestration/conftest.py` with one autouse fixture:

- It wraps `temporalio.client.Client.connect`.
- When the running test has no `temporal` marker, the wrapper calls
  `pytest.fail("<nodeid> connects to live Temporal but is not marked @pytest.mark.temporal")`
  before any network call. A missing mark therefore fails even when Temporal is down.
- The conftest sits at `orchestration/`, so it covers `orchestration/tests/` and
  `orchestration/webhook_bridge/tests/`.
- Its own test uses `pytester` to check both outcomes: an unmarked test fails, a marked
  one goes through.

**Alternative turned down.** Add the check inside each `_connect_or_skip`: four copies,
and a fifth helper would miss it.

## R17 — Shell lint (FR-023)

**Decision.**

- `tests/test_harness_hooks.py::test_hook_scripts_pass_shellcheck` runs
  `shellcheck -x .claude/hooks/*.sh`.
- When shellcheck is not installed, the test calls
  `pytest.skip("shellcheck not installed: hook scripts were not linted")`. The skip
  shows in the suite's summary line and with `-rs`.
- Known false positives are silenced on their own lines:
  - `# shellcheck disable=SC2034` above `CTX_BUDGET` and `CTX_WARN` in `lib.sh`, which
    are used by the scripts that source it;
  - `# shellcheck source-path=SCRIPTDIR` once near the top of each script, so
    `-x` finds `lib.sh` whatever the cwd of the test (`source=lib.sh` alone resolves
    against shellcheck's cwd).
- No `.shellcheckrc` and no global disable.
- The settings test also runs `shellcheck -s sh` on each launcher string, beyond
  `sh -n`, because a syntax check misses quoting errors.
- The skip shows in the pytest summary line and with `-rs` (quickstart V8). The Stop
  hook does not repeat it: that would need new gate plumbing for one line.

**Rationale.** It runs in both gates through the root suite and needs no new hook
wiring. shellcheck is at `/opt/homebrew/bin` on the operator's Mac and is missing in
E2B. A skip there is the "say so visibly" case.

## R18 — No lockfile changes (FR-025)

Every new piece uses tools that are already there:

- `jq`, `git`, GNU `timeout` and `shellcheck` are system tools;
- `pytester` ships with pytest;
- `temporalio` is already an orchestration dependency.

No pyproject is edited. SC-009 is checked with `shasum` before and after a full gate
run, as `quickstart.md` V9 shows.

## Rejected review findings (T006)

The `senior-architect-reviewer` reviewed `plan.md` and both contracts before the
tasks started. Ten findings came back. Findings 1, 2, 4, 5, 9 and 10 were applied
(plan, contracts, data-model, research R7, R8 and R11, quickstart and tasks).
Finding 7 was applied as a recorded known gap, as it suggested. These were not
applied as suggested:

- **Finding 3, AF-SPEC judges `ROOT`, not the worktree that owns the file.**
  Recorded as a known gap in the hook contract ("Edits in another worktree") and for
  CLAUDE.md (T056), not fixed here. The spec's edge case "Path spellings outside the
  repo" says a path outside the repo is not judged by AF-SPEC, and FR-008 only widens
  the spellings inside it. Judging each path against its own toplevel widens AF-SPEC
  beyond the spec, so it is the operator's call (open question, 2026-10-13).
- **Finding 6, the `ROOT` prefix compare is case-sensitive.** Rejected, for R7's
  reason: on a case-sensitive volume (Linux, the E2B sandbox), a root spelled in
  another case is a different directory, and folding it would judge that directory by
  this worktree's branch. The suggested `realpath` alternative is a disk lookup, which
  breaks the "judged by its spelling" edge case and fails for new files. Claude Code's
  file tools take the path the model writes, but the model works from the `cwd`
  spelling it is given, so a mis-cased root is an unlikely accident, not the 2026-10-11
  failure.
- **Finding 8, the Temporal guard patches `Client.connect`.** Rejected on both parts.
  (1) Nothing in the repo uses `WorkflowEnvironment` (R16), and the four
  `_connect_or_skip` copies are why the guard wraps `Client.connect` and not a helper.
  A future unmarked `WorkflowEnvironment` test fails loudly, naming itself, and is
  fixed by marking it or narrowing the guard then; it never passes silently.
  (2) The guard is already defined directly in `orchestration/conftest.py`, the
  orchestration suite's top-level conftest (data-model "Temporal marker guard");
  `pytest_plugins` is used there only for `pytester`, which is allowed in that file.

## Rejected review findings (implementation)

- **shell-reviewer, `.claude/hooks/session-context.sh:29`, "ROOT has no failure guard".**
  Rejected for this file only. The same guard was added to `policy.sh` and
  `py-check.sh`, where an empty ROOT made AF-SPEC and the per-edit ruff check fail
  open (tested by `test_policy_and_edit_fail_closed_without_a_root`).
  `session-context.sh` exits 0 on every path and never blocks. An empty ROOT there
  only skips the resume message, so a guard would add code with no change in what
  the operator sees (2026-10-13).
- **shell-reviewer, `.claude/settings.json:25`, "the launcher's `p=$(cat)` has no
  read limit and `bash` comes from PATH, so exit 127 fails open".** Rejected. The
  launcher text is fixed word for word by `contracts/hook-interface.md` "Wiring" and
  pinned by `test_every_hook_uses_the_launcher`, so changing it is a contract change
  for the operator, not a fix-round edit. Every hook script needs bash, so with no
  runnable `bash` no rule can run at all. The read is bounded by each entry's
  `timeout`, and a timeout already fails open the same way. Recorded as a known gap in
  the contract's "Wiring" section (2026-10-13).
- **shell-reviewer, `.claude/hooks/lib.sh:93`, "rc 137 from an OOM kill is reported
  as a timeout".** Rejected. `data-model.md` ("Gate run": step exit 124 or 137) and the
  contract map both codes to "timed out", and `test_gate_timeout_denies_the_commit[137]`
  pins that: its stub returns 137 at once, so the suggested `SECONDS >= gate_deadline`
  guard would fail an existing test. The commit is denied either way, so nothing fails
  open; only the hint in the message can mislead (2026-10-13).
- **shell-reviewer, `.claude/hooks/policy.sh:27`, "no shellcheck gate on the hook
  scripts".** Rejected for this round; the header part of the same finding was fixed
  (line 27 now names both contracts). The shellcheck test is T048 and the
  `source-path` directives are T054 (Phase 6, FR-023, R17). T048 must fail first on
  the unfollowed `source`, so adding the directives now would break that later task's
  test-first step (2026-10-13).
- **shell-reviewer, `.claude/hooks/policy.sh:133`, "`branch.<name>.rebase` is ignored,
  so `git pull --ff-only` can rebase ungated".** Rejected on evidence. In a scratch
  pair of repos under git 2.51.0, with `branch.main.rebase=true`, `pull.rebase`
  unset and the branches diverged, `git pull --ff-only` stopped with "Not possible to
  fast-forward, aborting" (exit 128) and wrote no commit. `--ff-only` on the command
  line wins over the branch's rebase setting, so FR-005's exemption holds as written
  (2026-10-13).
- **py-codereviewer, `.claude/hooks/policy.sh:144`, "the exemption ungates a compound
  command with an alias or quoted verb, e.g. `git rebase --abort; git ci -m x`".**
  Rejected as a best-effort gap, recorded next to FR-005 in the contract's AF-COMMIT
  section. A lone alias or quoted verb was never gated in 010 either. The suggested
  rule (every segment with `git` must be exempt) would put the full 240 s gate on
  common safe lines such as `git merge --abort && git status` (2026-10-13).
- **shell-reviewer, `.claude/hooks/lib.sh:163`, "the `ROOT` prefix is compared
  case-sensitively, so `/TMP/r/harness/x.py` skips AF-SPEC".** Rejected. This is
  finding 6 of the T006 review ("Rejected review findings (T006)" above): on a
  case-sensitive volume (Linux, the E2B sandbox) a root in another case is a
  different directory, folding it would judge that directory by this worktree's
  branch, and `realpath` is a disk lookup that the "judged by its spelling" edge case
  rules out. No new fact since then (2026-10-13).
- **shell-reviewer, `.claude/hooks/policy.sh:29`, "no shellcheck gate on the hook
  scripts".** Rejected for this round, as in the previous round (`policy.sh:27`
  above). The shellcheck test is T048 and the `source-path` directives are T054
  (Phase 6, FR-023, R17); T048 must fail first, so adding the gate now would break
  that task's test-first step. The reviewer's own run found only cross-file false
  positives, no real defect (2026-10-13).

## Rejected review findings (implementation)

Review of T036-T045 (Phase 5, User Story 3), 2026-10-13.

- **shell-reviewer, `.claude/hooks/py-check.sh:27`: "when lib.sh cannot be loaded,
  `stop` exits 2 on every Stop".** Rejected. Lines 27-32 are unchanged 010 code;
  T042 and T044 did not touch them. FR-015, the contract's "Common" section
  (`contracts/hook-interface.md`) and `data-model.md` (AF-HOOKS) scope the
  lib.sh load failure to the launcher and `policy.sh` only. The contract's Stop
  step 3 already accepts the same kind of block for a missing `jq` or `git`.
  Changing this is a contract change, not a fix-round repair. Follow-up candidate:
  the reviewer's suggested guard read for `stop` mode.
- **Not rejected, merged:** shell-reviewer `.claude/hooks/session-context.sh:56`
  (spec dir from the tip is not on disk) and py-codereviewer
  `.claude/hooks/session-context.sh:35` ("no tasks.md" while tasks.md is on the
  tip) are the same bug. One fix covers both: the resume block reads the next
  tasks from the branch tip and says so on the spec dir line.
