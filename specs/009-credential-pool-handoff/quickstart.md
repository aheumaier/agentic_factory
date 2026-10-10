# Quickstart / Validation: Credential Pool (009)

## Prerequisites

| For | Needs |
|---|---|
| Unit tests (V1) | nothing beyond `uv` |
| Temporal tests (V2, V3) | `make up` (Temporal on `localhost:7233`); otherwise they skip |
| Live seat smoke (V4) | `CLAUDE_OAUTH_SEAT_A` in `.env` (present today) |
| Live end-to-end (V5) | additionally `E2B_API_KEY`, `GH_TOKEN` (GitHub App installation token) in the worker env, the rebuilt `swe-agent-sandbox` E2B template, and a **disposable** target repo with a branch that has `specs/*/spec.md` + `specs/*/tasks.md` (≥ 2 open tasks) |

Seat config: `orchestration/credentials/pool.yaml` ships with `seat-a` only. For failover tests, point `CREDENTIAL_POOL_CONFIG` at a two-logical-seat file. Both seats use `token_env: CLAUDE_OAUTH_SEAT_A`, and each has its own `max_concurrent: 1`.

## V1: Unit tests (always)

```
uv run pytest tests/ -q
(cd orchestration && uv run pytest -q)
```

Expected outcomes:
- the `select_seat` matrix passes (SC-005);
- the `seat_guard` classification passes for 401, 429, "rejected" events and any other error;
- the `usage_from_rate_limit_info` max-window rule passes;
- `seat_status` parsing and the exit-code→`ApplicationError` mapping pass;
- the "no open tasks" resume check passes;
- the `seat_guard.py` copies are identical.

## V2: Pool workflow (local Temporal)

`orchestration/tests/test_credential_pool.py` uses a per-test `CREDENTIAL_POOL_ID`. It checks that:
- `acquire` → `release` updates `last_utilization`;
- `mark_exhausted` makes `seats()` show `exhausted_until`;
- an agent whose only seat is exhausted gets `None`;
- repeating `acquire` with the same `lease_key` returns the same seat.

## V3: Pipeline handoff (local Temporal, stubbed activities)

`orchestration/tests/test_pipeline_workflow.py` adds two cases.

**Two-seat pool.** The Build stub raises `SeatExhausted` on its first call and succeeds on its second. Expect:
- the second call got the other seat ID;
- there is exactly one Eval-Gate call;
- `MAX_BUILD_ATTEMPTS` and `MAX_PLAN_ATTEMPTS` were not charged;
- `seats()` shows the first seat exhausted (SC-004).

**One-seat pool, the same stub.** Expect the workflow to fail with `CredentialPoolExhausted`, with an earliest reset in its details (SC-008).

## V4: Live seat smoke (needs only seat-a)

Run a script, `orchestration/scripts/seat_smoke.py`, that reads the token itself and never prints it:
1. Poison `os.environ` with a bogus `ANTHROPIC_API_KEY` and `ANTHROPIC_BASE_URL`.
2. Run `guarded_query("Reply with exactly: OK", options(env=seat_options_env(token)))`.
3. Print the result and the `usage` snapshot.

Expect: result `OK`, and `usage.utilization` is a float, not `None` (SC-007, research R1 and R2).

## V5: Live end-to-end with forced handoff (two logical seats on one token)

1. Start `make up`, then `make worker` with `CREDENTIAL_POOL_CONFIG=<two-logical-seat file>`.
2. Set `SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS=1` and `SEAT_GUARD_FORCE_EXHAUST_SEAT=seat-a` in the worker env, then start an `AgentPipelineWorkflow` on the disposable repo. The activity forwards the hook into the sandbox **only** when it runs on `seat-a`. The first Build (on seat-a) is forced to exhaust after task 1. The successor (on seat-b) is not forced. seat-a is not picked again because it is marked exhausted.
3. Expect:
   - task 1's commit is on the remote branch after handoff 0;
   - the successor ran on the other seat ID and started at task 2 (check the sandbox log or the commit sequence);
   - exactly one open PR on the branch (SC-002, SC-003);
   - the `seats()` query shows the first seat as `exhausted_until ≈ now+1h` (no real reset time), and the second as released with a utilization figure.
4. Secrecy check (SC-006): `temporal workflow show -w <id> --output json | grep -c sk-ant-oat` should print `0`. Run the same grep over the worker log and the PR comments.

## Results

Run on 2026-10-10 on branch `009-credential-pool-handoff`, with local Temporal up (`docker compose up -d temporal`).

| Step | Result |
|---|---|
| V1 unit tests | `uv run pytest tests/ -q`: **108 passed**. `ruff check .` is clean. |
| V2 + V3 (Temporal) | `cd orchestration && uv run pytest -q`: **135 passed, 0 skipped**. This covers the pool workflow; Build and architect handoff; pool exhausted; handoff budget; pool unavailable; a failed release; and a cancel during a seat-backed stage or during its lease release. |
| V4 live seat smoke | `scripts/seat_smoke.py` against seat-a, with a poisoned parent `ANTHROPIC_API_KEY`/`BASE_URL`: **PASS**. `result='OK'`, `utilization=0.65` (`five_hour`). |
| T042 template rebuild | **Done.** `swe-agent-sandbox` was rebuilt with `e2b template create`, and the in-sandbox `agent.py`/`seat_guard.py` hashes match the commit. |
| V5 live end-to-end | **Pending.** Needs `GH_TOKEN` and a disposable target repo. |
