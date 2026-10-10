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

To be filled in by the implementation run.
