# Quickstart / Validation: Seat Pool Hardening (011)

Usage Constraint (binding, from 009): internal, single-operator use only. The seats are the operator's own Claude Max subscriptions and are never offered to third parties.

## Prerequisites

As in `specs/009-credential-pool-handoff/quickstart.md`:
- Temporal on `localhost:7233` (`docker compose up -d temporal`);
- `CLAUDE_OAUTH_SEAT_A`, `E2B_API_KEY` and `GH_TOKEN` in `.env` (check presence only, never print values);
- the rebuilt `swe-agent-sandbox` E2B template.

## V1: Unit tests

```
uv run pytest tests/ -q
uv run ruff check .
```

Expected:
- the checkpointer commits on a new tick with a dirty tree, records without committing on a clean tree, makes one commit for a batched tick, retries after a failed commit, and commits leftover edits at the end;
- forced exhaustion after 1 commit fires right after `checkpoint: T001`, and the pushed branch holds it;
- `SEAT_HANDOFF_INDEX=1` skips `verify_new_commit`, while `0` still fails;
- `utilization_resets_at` is the max window's reset;
- the `seat_guard` copies are identical.

## V2 + V3: Pool and workflow (live Temporal)

```
(cd orchestration && uv run pytest -q)    # 0 skipped
```

Expected:
- the `select_seat` matrix: a past reading reset counts as 0, a future one counts as is, no reset counts as is, an expired exhaustion counts as 0, and old state upgrades;
- `release` stores `utilization_resets_at`, and `seats()` shows it plus `expires_in_days`;
- the F3 wait: a stub returns "no seat, reset in 2 s" once, then the run finishes on a seat with no budget charged; a reset more than 6 h away (the 009 tests with 2099) still fails at once;
- the Build activity receives its handoff index, and `_sandbox_envs` arms the force hook by handoff index or by seat name;
- the worker expiry warning fires for seats 14 or fewer days from expiry.

## V5: Live mid-task resume (two logical seats on one token)

1. If `harness/swe-agent/*.py` changed, rebuild the template from the repo root with `E2B_API_KEY` exported:
   `e2b template create swe-agent-sandbox -p . -d sandbox/swe-agent/Dockerfile --cpu-count 2 --memory-mb 1024`.
   Then compare the sha256 of `/app/agent.py` and `/app/seat_guard.py` in a credential-less sandbox against the repo files.
2. Cut a fixture branch `v5-seat-handoff-3` from scratch-repo commit `fe874169`:
   - `git mv specs/v5-seat-handoff specs/v5-seat-handoff-3`;
   - set `.specify/feature.json` to `{"feature_directory":"specs/v5-seat-handoff-3"}`;
   - update the branch name in `spec.md`;
   - push it from a temporary clone, with the token in the URL only and redacted from all output.
3. Headroom: `cd orchestration && uv run python scripts/seat_smoke.py` must print PASS, with utilization below about 0.8.
4. Worker (from `orchestration/`):
   ```
   CREDENTIAL_POOL_CONFIG=<repo>/.handoff/v5/pool-v5.yaml CREDENTIAL_POOL_ID=credential-pool-v5b \
   SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS=1 SEAT_GUARD_FORCE_EXHAUST_HANDOFF=0 \
   FACTORY_REPO=aheumaier/pm-agent-scratch-test PYTHONUNBUFFERED=1 uv run python worker.py
   ```
   Do **not** set `SEAT_GUARD_FORCE_EXHAUST_SEAT`.
5. `V5_WF_ID=v5-seat-handoff-run-3 V5_BRANCH=v5-seat-handoff-3 uv run python ../.handoff/v5/v5_driver.py start`. Watch `status`. Once the architect stage is done and no activity is pending, check that the generated `tasks.md` is a checklist, then run `approve`.
6. When the run completes, run `v5_verify.py <worker log>`, with its workflow IDs set to `v5-seat-handoff-run-3` and `credential-pool-v5b`.

**Pass** means all of:
- Build handoff 0 failed with `SeatExhausted` after exactly one task commit (`checkpoint: T001`, or the model's own commit for T001);
- the remote branch holds that commit;
- handoff 1 ran on the other seat, and its first task commit is T002 or later, so T001 was not redone;
- there is exactly one feature PR;
- the secrecy check finds 0 hits in every source.

Afterwards, stop the worker and terminate `credential-pool-v5b`.

## Results

Run on 2026-10-10 on branch `011-seat-pool-hardening`, with local Temporal up.

| Step | Result |
|---|---|
| V1 unit tests | `uv run pytest tests/ -q`: **126 passed**. `uv run ruff check .`: **All checks passed!** The `seat_guard.py` copies are byte-identical (`cmp`). |
| V2 + V3 (Temporal) | `cd orchestration && uv run pytest -q`: **167 passed, 0 skipped**. |
| Code review | `py-codereviewer`, round 1: 2 major and 5 minor findings, all fixed (see below). Round 2: **APPROVE, no findings**. |
| Live seat smoke | `scripts/seat_smoke.py` (21:12 UTC): **PASS**, `utilization=0.5` (`seven_day`). The live usage signal carries a per-window reset, and the new `utilization_resets_at` key came back filled (the seven-day window's reset). This confirms F2's assumption against the real API. |

### Review findings and what was done (2026-10-10)

1. **Major.** F5 skipped the "no new commit" check on any successor. The Eval-Gate never looks at the diff, so a no-op successor could pass. Now the check is skipped only when every task is done. research.md R6 was corrected.
2. **Major.** `token_expires_on` was never validated, but F4 parses it at boot and in `seats()`. `validate_pool` now rejects a non-date and names the seat. This covers boot and `reload_config`.
3. **Minor.** The earliest reset was taken over every seat. Now it comes from the new `earliest_reset_for(agent)` query: assigned, non-invalid seats only.
4. **Minor.** Done-task keys were not per file, so in fallback mode an older spec's T001 hid this feature's T001. They are now keyed by `(path, id)`.
5. **Minor.** The checkpoint git calls blocked the event loop. They now run via `asyncio.to_thread`; the ordering with `force_check` is kept.
6. **Minor.** A later reading could keep an older reading's reset time. `_merge_usage` now updates the two as a pair.
7. **Minor.** `reset_seat` left the exhaustion's 1.0 reading in place. It now clears the reading.

The reviewer's test gap "a past reset counts as one wait" is now covered by a test.

**Deploy note:** terminate or restart any existing long-lived `credential-pool` workflow before deploying 011 (research R3). On 2026-10-10 none exists on the local server.

### V5 re-run 3 (2026-10-10, 21:34–21:46 UTC): mechanics pass, mid-task resume **not shown**

Target `aheumaier/pm-agent-scratch-test`, branch `v5-seat-handoff-3` (fixture `c1deff6`, cut from `fe87416`). Pool `credential-pool-v5b` (two logical seats on seat-a's token). Worker env: `SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS=1`, `SEAT_GUARD_FORCE_EXHAUST_HANDOFF=0`. The E2B template was rebuilt from `a8d9f0c`, and the in-sandbox sha256 of `agent.py` and `seat_guard.py` matched the repo.

| Event | Seat | Detail |
|---|---|---|
| Architect stage (lease `architect/1/0`) | seat-a | Released with `utilization=0.51` (`seven_day`) and `utilization_resets_at=2026-10-12T19:00:00+00:00`. F2 live: the reading carries its own window's reset. |
| Build handoff 0 (`build/1/0`, activity arg `handoff=0`) | seat-b | Picked by utilization (0.0 < 0.51) and **forced by handoff index** (F6): `SeatExhausted`. It pushed one commit, `cfaecde checkpoint: T001 T002 T003`, authored by the harness fallback identity `swe-agent` (F1). |
| `report_seat_failure` | seat-b | `exhausted_until ≈ now+1h`, reading 1.0 with the same reset. |
| Build handoff 1 (`build/1/1`, `handoff=1`) | seat-a | Every task was `[X]`, so it took the all-done shortcut: no model call, no commit, PR opened. |
| Eval-Gate, Register | — | Passed. Exactly **one** feature PR: **#6**. |

Secrecy (SC-007): 0 hits for every `.env` secret value and the `sk-ant-oat` prefix in each of: the `v5-seat-handoff-run-3` history, the `credential-pool-v5b` history, the worker log, and all scratch-repo PR comments.

**Why mid-task resume is not shown.** The model implemented all three tasks, then marked all three `[X]` in one edit, despite the prompt's "one task at a time". The harness checkpointed that tick, so nothing was lost: before 011, this depended on the model committing at all. But one tick event can only become one checkpoint. The force hook fired after that one commit, and the successor had nothing left to do. Run 2 of 009 failed the same way, so batching is the model's consistent behavior on this three-task fixture. A prompt instruction does not prevent it.

**What the checkpoint holds.** `cfaecde` changes `tasks.md` (+3/-3), the three `wordstats/*.py` modules, `wordstats/__init__.py` and the three test files. So the model really did implement all three tasks before ticking; it did not tick without working. There is no sandbox transcript to show the order of the edits: the sandbox gets no Braintrust key, and on exit 75 only the status line is kept. That gap is worth closing if per-task behavior needs auditing later.

**Next step (done):** the operator ruled F7-a on 2026-10-11 (spec.md, "Fork F7"). See "V5 re-run 4" below.

**Side effect during the run (fixed for this session, not in code).** The Stop hook re-ran the orchestration suite because `.handoff/v5/*.py` are untracked `.py` files. Main's `webhook_bridge` e2e test (the leaky version; 010's fix `889785f` is not on main yet) then put `pipeline/owner/repo/demo-widget-1b73f10c/v1` on `agent-factory-pipeline`. The V5 worker ran its `ensure_target_pr_activity`, which failed harmlessly on the fake `owner/repo`, and the test terminated the workflow. To stop a repeat, `.handoff/` was added to `.git/info/exclude` (local only) for the rest of the run.

### V5 re-run 4 (2026-10-10, 22:53–22:55 UTC; 2026-10-11 local): **pass**, mid-task resume shown

Code: `b8e39df` (F7-a, one model session per open task). Target `aheumaier/pm-agent-scratch-test`, branch `v5-seat-handoff-4` (fixture `a6610a6`, cut from `fe87416`). Pool `credential-pool-v5c` (two logical seats on seat-a's token). Worker env: `SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS=1`, `SEAT_GUARD_FORCE_EXHAUST_HANDOFF=0`. The E2B template was rebuilt from `b8e39df`, and in a credential-less sandbox the sha256 of `/app/agent.py` (`04ef42b9…`) and `/app/seat_guard.py` (`2d87abb2…`) matched the repo. Seat smoke before the run: PASS, `utilization=0.52` (`seven_day`).

The architect stage wrote a `tasks.md` with three open tasks (T001–T003), all with IDs, in `specs/v5-seat-handoff-4/`. So the Build took the per-task path.

| Event | Seat | Detail |
|---|---|---|
| Architect stage (`architect/1/0`) | seat-a | Released with `utilization=0.53` (`seven_day`), `utilization_resets_at=2026-10-12T19:00:00+00:00`. |
| Build handoff 0 (`build/1/0`, `handoff=0`) | seat-b | T001 session: pushed exactly **one** commit, `4bc7544 checkpoint: T001` (22:54:06; `conftest.py`, `wordstats/count.py`, `tests/test_count.py`, `tasks.md`). The force hook then raised `SeatExhausted`, so T002's session never started. |
| `report_seat_failure` | seat-b | `exhausted_until` 23:54:13 UTC (now + 1 h), reading 1.0. |
| Build handoff 1 (`build/1/1`, `handoff=1`) | seat-a | T001 was already `[X]`, so it got no session. First commit: `09e8114 checkpoint: T002` (22:54:39; `wordstats/unique.py`, `tests/test_unique.py`, `tasks.md`). Then `66ede3f checkpoint: end of T002` and `1654d94 checkpoint: T003`. Released with `utilization=0.54` (`five_hour`). |
| Eval-Gate, Register | — | Passed. Exactly **one** feature PR: **#7**. |

Pass criteria:
1. Handoff 0 failed with `SeatExhausted` after exactly one commit, `checkpoint: T001`. **Met.**
2. The remote branch holds that commit. **Met.**
3. Handoff 1 ran on the other seat, and its first commit is T002. T001 was not redone. **Met.**
4. Exactly one feature PR (#7). **Met.**
5. Secrecy (SC-007): 0 hits for every `.env` secret value and for the `sk-ant-oat` prefix in each source: `v5-seat-handoff-run-4` history, `credential-pool-v5c` history, the worker log, and all scratch-repo PR comments. **Met.**

This closes SC-001 of this spec and 009's SC-002 on the live path.

**Observed, not fixed here.**
- `66ede3f checkpoint: end of T002` holds only `__pycache__/*.pyc` files, left by the model's test run. Two things combine here: the scratch repo has no `.gitignore`, and both the harness and the model use `git add -A`. A target repo with a normal Python `.gitignore` would not see this. A harness-side ignore list would be a separate change.
- The Eval-Gate still does not look at the diff (specs 006/008).
- There is still no sandbox transcript on exit 75 (the sandbox has no Braintrust key).

**Gate after cleanup:** `uv run pytest tests/ -q`: **140 passed**. `cd orchestration && uv run pytest -q`: **167 passed, 0 skipped**. `uv run ruff check .`: **All checks passed!** The `seat_guard.py` copies are byte-identical (`cmp`).

**F7-a review (2026-10-11).** `py-codereviewer` ran two rounds. Round 1 had 6 minor findings and 1 nit, all fixed:
1. the task-ID boundary (`T001a`);
2. a deleted `tasks.md` crashed the run;
3. single-session paths were tested only by accident;
4. the branch-named `tasks.md` was untested;
5. the usage reading across sessions was untested;
6. the stderr note when a task is left open;
7. the timeout sentence in R10.

Round 2 had 2 minor findings (the docstring wording and a test for the `OSError` branch), both fixed. Verdict: **APPROVE**.

Cleanup: the worker is stopped, `credential-pool-v5c` is terminated, `.git/info/exclude` is restored, and the fixture clone is deleted.

