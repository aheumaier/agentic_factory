# Quickstart: validating 012

These scenarios show that 012 works once it is built. The rules they check are in
[`contracts/hook-interface.md`](./contracts/hook-interface.md),
[`contracts/drift-conventions.md`](./contracts/drift-conventions.md) and
[`data-model.md`](./data-model.md). This guide does not repeat them.

- **V1 and V2 are live checks** for the operator. They need a real Claude Code session,
  because tests cannot show what Claude Code itself does with a hook's exit code.
- **V3 to V9** can be run by hand or by an agent. Most are also pinned by automated
  tests. Running them by hand is a spot check, not a substitute.

All commands run from the root of a worktree that has 012 built in, unless a step says
otherwise.

## Prerequisites

| Tool | Why | Check |
|---|---|---|
| `jq`, `git`, `uv` | as in 010 | `command -v jq git uv` |
| GNU `timeout` or `gtimeout` | **new**: bounds the gate. Without it every commit is denied | `command -v timeout gtimeout`; install with `brew install coreutils` |
| `shellcheck` (optional) | lints the hook scripts. Without it the lint test is skipped, and the skip shows in the summary | `command -v shellcheck` |
| Temporal (`make up`) | the `@pytest.mark.temporal` tests. Without it they skip | `nc -z localhost 7233` |

The hook config is read when a session starts. A session started before 012's
`settings.json` landed still runs the old commands: start a new one for V1 and V2.

## V1: a session that loses its launch worktree (SC-001, live)

This repeats the 2026-10-11 failure. Use only disposable worktrees.

1. From a terminal outside Claude Code, make two disposable worktrees of a branch that
   has 012:

   ```sh
   git worktree add ../af-v1-a -b v1-a <012-branch>
   git worktree add ../af-v1-b -b v1-b <012-branch>
   ```

2. Start `claude` in `../af-v1-a`. In the session, ask Claude to run the Bash command
   `cd ../af-v1-b` (`EnterWorktree` makes a new worktree, so it does not fit here).
   Then ask for the Bash command `pwd`. It must print the path of `af-v1-b`; if not,
   step 4 would show AF-HOOKS and prove nothing, so stop and start again.
3. From the outside terminal, remove the launch worktree:
   `git worktree remove --force ../af-v1-a`.
4. In the session, ask Claude to run the Bash command `cat .ENV` in `../af-v1-b`. The
   worktree has no such file, and the deny comes before the command runs.
   **Expected:** `[AF-SECRET] Shell commands may not name .env …`. Only 012's
   `policy.sh` has this message, so it shows that the scripts of `af-v1-b` ran. (A
   Read of `.env` would not show it: the `permissions.deny` rules also refuse that,
   without any hook.)
5. From the outside terminal, move `../af-v1-b/.claude/hooks` aside (for example to
   `../af-v1-hooks`).
6. In the session, ask for any Bash call, for example `git status`.
   **Expected:** an `[AF-HOOKS] … were not found …` deny. Nothing runs.
7. End the turn. **Expected:** a `[AF-HOOKS]` notice, not a block.
8. Move the hooks back (`mv ../af-v1-hooks ../af-v1-b/.claude/hooks`). In the session,
   ask Claude to Edit `../af-v1-b/.claude/hooks/policy.sh` (any one-character change)
   and record whether the AF-HARNESS ask prompt appears. Decline it. This settles the
   AF-HARNESS gap in the hook contract; either result is recorded, not failed.
9. Clean up from the outside terminal: end the session, then
   `git worktree remove --force ../af-v1-b`, `git branch -D v1-a v1-b`,
   `rm -rf ../af-v1-hooks`.

**Pass:** in steps 4 and 6 no covered call was allowed without a rule. Record the
result of steps 4, 6 and 8 with the date in the feature's PR.

## V2: a commit gate that runs too long (FR-003, live)

1. Make a disposable worktree on a feature branch that has a `tasks.md`, and change one
   `.py` file there.
2. Start the session with a tiny limit: `AF_GATE_LIMIT=5 claude`.
3. Ask Claude to commit the change.
   **Expected:** `[AF-COMMIT] The commit gate timed out after 5s …`, and
   `git log -1` is unchanged.
4. End the turn. **Expected:** Stop reports red, and its text starts
   `=== gate TIMED OUT after`.
5. Clean up the worktree and branch.

## V3: policy input and git verbs (FR-004, FR-005)

Feed `policy.sh` by hand. `AF_GATE_LIMIT=1` makes every gated command deny fast with
"timed out", so no full gate run is needed to see which commands are gated.
Precondition: `git config --get pull.rebase` prints nothing or `false`; otherwise
`git pull --ff-only` is gated too.

```sh
printf '' | bash .claude/hooks/policy.sh; echo "rc=$?"
printf 'not json' | bash .claude/hooks/policy.sh; echo "rc=$?"
```

**Expected:** `rc=2` and an `[AF-HOOKS] … no valid input …` line on stderr, both
times.

```sh
for c in 'git revert HEAD' 'git cherry-pick abc' 'git merge topic' 'git am x.patch' \
         'git rebase --continue' 'git pull' 'git cherry-pick --skip' \
         'git commit -m "allow git rebase --abort"' \
         'git rebase --abort' 'git merge --quit' 'git pull --ff-only'; do
  out=$(jq -nc --arg c "$c" --arg d "$PWD" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d}' |
    AF_GATE_LIMIT=1 bash .claude/hooks/policy.sh |
    jq -r '.hookSpecificOutput.permissionDecisionReason' | head -1)
  printf '%-24s %s\n' "$c" "${out:-allowed}"
done
```

`policy.sh` prints nothing when it allows, so an empty result means allowed.

**Expected:** the first eight print `[AF-COMMIT] The commit gate timed out …`. The
last three print `allowed`. The table in the hook contract has more cases.

**Repair on a red tree.** In a disposable worktree, break one `.py` file so the gate
is red, then feed `git merge main` without `AF_GATE_LIMIT`. **Expected:** the main
`[AF-COMMIT]` deny. This is by design (research R5): make the tree green first, for
example `git checkout -- <file>`, then merge.

## V4: secret and path spellings (FR-006 to FR-009)

Use the same `jq … | bash .claude/hooks/policy.sh` pattern as V3.

- Bash `cat .ENV`, `` echo `cat .env` ``, `cp {.env,x}`, `scp host:.env .`,
  `git show HEAD:.env`, `echo $(<.env)`: each gives the shell message
  `[AF-SECRET] Shell commands may not name .env …`.
- Bash `cat .env.example` and `cat .ENV.EXAMPLE`: allowed.
- Read `X/.Env`: the file-tool AF-SECRET message (unchanged).
- On a branch with no `tasks.md` (for example a disposable worktree of `main`):
  `Write` to `docs/../harness/a.py`, `./harness/a.py` and `Harness/a.py` each gives the
  same `[AF-SPEC]` deny as `harness/a.py`.

## V5: AF-SPEC during a rebase (FR-014)

1. In a disposable worktree on a branch `NNN-x` that has `specs/NNN-*/tasks.md`, start
   a rebase that stops with HEAD detached, for example
   `git rebase --exec false HEAD~1`.
2. Feed `policy.sh` a `Write` to `harness/a.py`, as in V3.
   **Expected:** allowed. Before 012 this was an `[AF-SPEC]` deny.
3. `git rebase --abort`, then remove the worktree and branch.

The session-context resume block during a rebase is covered by an automated test.

## V6: Stop after two red runs, missing `uv`, compaction (FR-012, FR-013, FR-016, FR-017)

These need a crafted transcript and state dir, so they are automated only:

```sh
uv run --locked pytest tests/test_harness_hooks.py -q
```

**Expected:** green. The cases are named in `tasks.md` by requirement: double red keeps
the snapshot (SC-006), a docs-only turn after a double red still runs the gate and
blocks once, `uv` missing blocks once, stale `ctx-*`/`exception-*` files are
pruned, a `compact_boundary` with no later usage stays silent, and one with a low
usage after it re-arms.

## V7: drift test at Stop and the git corpus (FR-020, FR-021)

1. In a session on a feature branch, change one word in `CLAUDE.md` that breaks a
   drift rule, for example rename a `specs/0NN-…` reference to a spec dir that does
   not exist.
2. End the turn. **Expected:** Stop is red, and its failures name only
   `tests/test_context_drift.py`. The run takes a few seconds, not the ~53 s of the
   full gate.
3. Undo the change. The next Stop is green.

The ignored-file corpus case is automated in `tests/test_context_drift.py`.

## V8: swe-agent verification notes, Temporal guard, shell lint (FR-011, FR-022, FR-023)

- **swe-agent:** `uv run --locked pytest tests/test_swe_agent_seat.py -q`. On the next
  supervised swe-agent run, check that the PR body ends with
  `## Agent verification notes` when the agent reported anything, and that the only
  commits are the harness's own.
- **Temporal guard:** with Temporal down (`make down`), run
  `cd orchestration && uv run --locked pytest -q`.
  **Expected:** green, the live tests skip, and the guard's own tests pass. Repeat with
  `make up`: still green.
- **Shell lint:** `uv run --locked pytest tests/test_harness_hooks.py -q -rs -k shellcheck`.
  **Expected:** a pass with shellcheck installed, or one skip that reads
  `shellcheck not installed: hook scripts were not linted`.

## V9: lockfiles untouched (FR-025, SC-009)

```sh
shasum uv.lock orchestration/uv.lock > "${TMPDIR:-/tmp}/af-lock-before"
uv run --locked ruff check . && uv run --locked pytest tests/ -q
(cd orchestration && uv run --locked pytest -q)
shasum -c "${TMPDIR:-/tmp}/af-lock-before"
```

**Expected:** `shasum -c` prints `OK` for both files.
