Implement feature 010 (dev-harness hardening) end to end from
`specs/010-dev-harness-hardening/`. This is a resumable driver. The same prompt is
pasted into each new session, and each session continues where the last one stopped.

## Resume protocol

1. Confirm you are in the `010-dev-harness-hardening` worktree, on branch
   `010-dev-harness-hardening`.
2. Read `tasks.md` and find the **first unchecked task**. That's where you start.
   Then read the spec docs that task cites (plan.md, research.md R-sections,
   data-model.md, contracts/hook-interface.md, contracts/drift-conventions.md,
   quickstart.md). Read only the sections you need, not every file every time.
3. Work through the tasks **strictly in tasks.md order**. Each task's text is the
   spec. Follow it literally, including its "verify with grep first" and "don't
   touch X" clauses.
4. When a task is done and green, tick its checkbox in tasks.md (`- [ ]` → `- [x]`)
   right away. If the task asks for a completion note (T023 triage, T019's
   feature-008 resolution, T043 docker result), append it to the task line.
5. **Stop at the next checkpoint**, and also if context nears ~130k. The
   checkpoints are:
   - the end of Phase 3 (after T015);
   - the end of Phase 4 (after T024);
   - after T036.

   At a stop, make sure tasks.md is ticked and any findings are written into the
   spec dir. Then tell me "checkpoint reached: run `/clear` and re-paste the
   prompt", and end the turn. Don't push past a checkpoint.

## Hard constraints (non-negotiable)

- **Phase order is deliberate**: Setup → Foundational → US1 → US3 → US2 → US4 →
  pre-activation review (T036) → activation (T037) → polish. Don't reorder by
  priority (see tasks.md "⚠️ Phase order is deliberate").
- **T001 baseline**: if ruff or either suite is red before you start, stop and
  report. Don't fix unrelated failures.
- **Live-hook caveat, before T009**: the old PostToolUse hook runs ruff and both full
  suites after every `.py` edit-tool change. In Phases 1–2, `.py` edits are
  one-liners, and each new test module is a single Write that is already green.
- **Gate discipline**: after every task, `uv run --locked ruff check .`,
  `uv run --locked pytest tests/ -q` and `(cd orchestration && uv run --locked pytest -q)`
  must be green. Run them yourself; don't rely on the hooks alone. Every `uv run`
  you add to hooks or docs uses `--locked`/`--frozen`. Never rewrite `uv.lock` or
  `orchestration/uv.lock`.
- **Smoke tests (T011, T026, T033, the T044 SC-007 check)** run only in the scratch
  clone from quickstart §1 (refresh its `rsync` first). Never run hand-made
  `turn-start`/`stop` calls in the live worktree: they would adopt and delete this
  session's own snapshot.
- **Shell**: bash 3.2-compatible (no `mapfile`, assoc arrays, `${v,,}` or
  `declare -n`). Pass argv arrays, never `eval`/`bash -c`. No test-only env vars
  or seams in hook code: tests control behaviour only through the stub `uv` on
  `PATH`, fixture transcripts and the fixture repo.
- **Fail-safe contracts**: `turn-start` and `session-context.sh` always exit 0, and
  their stdout is either empty or exactly one valid JSON object.
- **Docs**: CLAUDE.md and the reviewer prompt refer to in-flight features (008,
  009, 010) **by number only**, never as `specs/NNN-…` paths. Invent nothing: grep
  every identifier before writing it.
- **One session per worktree**: work sequentially. Subagents may run in parallel only
  on the `[P]` pairs tasks.md lists (T003–T005; T020/T021 next to T016–T019;
  T031/T032; T039/T040). Every edit to `tests/test_harness_hooks.py` stays serial.
- **Activation (T037) is the last `.claude/settings.json` change.** After it,
  AF-HARNESS makes every edit to `.claude/settings*.json` or `.claude/hooks/**`
  prompt me. So all hook-script work and the T036 review must be finished
  before T037. From T037 on, run in the foreground and expect my approvals.
- **Reviews**: run the `py-codereviewer` subagent where tasks.md says (T036, T042),
  naming the `.sh` files and `settings.json` explicitly. Fix its findings
  before moving on.
- **Hands off**:
  - leave the existing uncommitted `sandbox/swe-agent/Dockerfile` diff (FR-025)
    and `.specify/feature.json` unchanged;
  - no bare `git stash`;
  - no `e2b template build` (T043 does a local `docker build` only, or notes it
    as unrun);
  - no `git push`.
- **T045**: run the scenarios that need no relaunch (quickstart §4 injections,
  reverted after each one). Give me the rest of §2/§3/§6 as an operator-pending
  checklist.
- **T046**: one feature commit on this branch, through the live AF-COMMIT gate,
  with the repo's commit conventions and attribution trailer. Then stop and
  report:
  - T044 results;
  - the T023 triage;
  - the T019 feature-008 resolution;
  - the T045 pending items.

## If blocked

If a task's instructions conflict with the code as it is, or a check is red and the
cause is outside this feature, stop. Write the finding into research.md or the task
line, then ask me. Don't improvise around the spec.
