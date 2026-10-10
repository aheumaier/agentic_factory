---
description: "Task list for 009-credential-pool-handoff"
---

# Tasks: Subscription-Seat Credential Pool with Checkpointed Agent Handoff

**Input**: Design documents from `specs/009-credential-pool-handoff/`

**Prerequisites**: plan.md, spec.md, research.md (R1–R9), data-model.md, contracts/credential-pool-interface.md, contracts/seat-guard-and-agent-protocol.md, quickstart.md

**Tests**: These are included. The spec's success criteria and quickstart V1–V3 call for them, and `.claude/hooks/py-check.sh` enforces ruff and both pytest suites on every `.py` edit.
- Root suite: `uv run pytest tests/`
- Orchestration suite: `cd orchestration && uv run pytest`. Its Temporal tests use the real `localhost:7233` with `_connect_or_skip` (research R9).
- **Every test that starts a `CredentialPoolWorkflow` MUST `terminate()` its handle in a `finally`**, the same pattern as `test_e2e_pipeline_gate.py`. The pool never completes, so a missed terminate leaks a live workflow onto the dev server for every test run.
- **Order within a task:** the PostToolUse hook runs both suites with `-x` on every `.py` save. Write the implementation first and then its test, or expect exit-2 feedback while a test exists before its code.

**Organization**: Tasks are grouped by user story. Run `py-codereviewer` at the end of every phase, before its commit.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US5 from spec.md

---

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 Create the `orchestration/credentials/` package: an empty `orchestration/credentials/__init__.py`, and `orchestration/credentials/pool.yaml` with a single seat `seat-a: {token_env: CLAUDE_OAUTH_SEAT_A, max_concurrent: 2, token_expires_on: 2027-10-10}` and assignments `swe-agent: [seat-a]`, `architect-agent: [seat-a]`, `pm-agent: [seat-a]`. Add a header comment restating the single-operator usage constraint (spec "Usage Constraint") and that only the env var *name* lives here.
- [X] T002 [P] Add `CLAUDE_OAUTH_SEAT_A=` and `CLAUDE_OAUTH_SEAT_B=` placeholders to `.env.example`, with a comment on how to get a token (`claude setup-token`), its one-year expiry, and the single-operator constraint.
- [X] T003 [P] Pin `claude-agent-sdk>=0.2.152` in `harness/swe-agent/pyproject.toml` and `harness/architect-agent/pyproject.toml` (run `uv lock` in each), and on the pip line in `sandbox/swe-agent/Dockerfile`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the pool core, the pool workflow and its activities, and the seat guard. Every user story depends on these.

- [X] T004 Implement `orchestration/credentials/pool.py`:
  - `load_pool(path=None)`: reads `CREDENTIAL_POOL_CONFIG`, else `pool.yaml` next to the module. It validates unknown, duplicate or `max_concurrent<1` seats and fails fast, and returns `{"seats":…, "assignments":…}` with plain JSON-safe types.
  - `select_seat(seats, state, assignments, agent, now, lease_ttl)`, pure, per data-model.md "Selection rule".
  - `active_leases(seat_state, now, lease_ttl)`.
  - `earliest_reset(state)`.
  - `token_for(seat_id, pool)`: raises `KeyError` naming only the env var name if it is unset.
  - `LEASE_TTL = timedelta(hours=2)` and `DEFAULT_EXHAUST_WINDOW = timedelta(hours=1)`.

  Keep it free of Temporal imports so the workflow can import it through `imports_passed_through`.
- [X] T005 [P] Write base tests for `load_pool` (valid file, unknown seat in assignments, duplicate, `max_concurrent=0`) and `token_for` (set, unset, and an error message that never contains a value) in `orchestration/tests/test_credential_pool.py`.
- [X] T006 Implement `CredentialPoolWorkflow` in `orchestration/workflows/credential_pool.py` per contracts/credential-pool-interface.md:
  - updates `acquire` (idempotent per `lease_key`, prunes expired leases), `release`, `mark_exhausted`, `mark_invalid`, `reset_seat` and `reload_config`;
  - query `seats()`;
  - a main loop that calls `continue_as_new` with the config and state once `workflow.info().is_continue_as_new_suggested()`, after `workflow.all_handlers_finished()`.

  Use `workflow.now()` only, keep timestamps as ISO strings in state, import `credentials.pool` through `workflow.unsafe.imports_passed_through()`, and add the `§3.5` cross-reference in the module docstring.
- [X] T007 Add `acquire_seat_activity`, `release_seat_activity` and `report_seat_failure_activity` to `orchestration/activities.py`:
  - each resolves the pool through `activity.client().get_workflow_handle(os.environ.get("CREDENTIAL_POOL_ID", "credential-pool"))` and calls `execute_update`;
  - `acquire_seat_activity` returns `{"seat_id", "earliest_reset"}`, filling `earliest_reset` from the `seats()` query only when `seat_id` is None.
- [X] T008 Change `orchestration/worker.py`:
  - register `CredentialPoolWorkflow` and the three activities;
  - before `worker.run()`, start the pool with `client.start_workflow(CredentialPoolWorkflow.run, load_pool(), id=pool_id, task_queue=TASK_QUEUE, id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING)`;
  - call `load_dotenv(<repo>/.env)` explicitly at the top of `main()`. `make worker` loads no `.env`, and today the seat token only reaches `os.environ` as a side effect of `activities.py` loading the architect agent.
- [X] T009 Add pool-workflow tests against local Temporal, with `_connect_or_skip` and a per-test pool ID from `uuid`, in `orchestration/tests/test_credential_pool.py`:
  - acquire→release updates `last_utilization`;
  - a repeated acquire with the same `lease_key` returns the same seat;
  - `mark_exhausted`, after which `seats()` shows `exhausted_until`;
  - `mark_invalid`, after which `seats()` shows `invalid`;
  - `reset_seat` clears both.

  Run this task early: it is also the smoke test that the dev server accepts Workflow Updates. If it doesn't, set `frontend.enableUpdateWorkflowExecution` through dynamic config in `docker-compose.yml`.
- [X] T010 [P] Implement the canonical `harness/swe-agent/seat_guard.py` per contracts/seat-guard-and-agent-protocol.md:
  - `SeatExhausted`/`SeatInvalid`, subclassing `Exception` directly;
  - `seat_options_env`, `usage_from_rate_limit_info` (max over `raw["unifiedWindows"]`, fallback, research R2), `classify_result_error` (research R3 rules, in order);
  - `guarded_query(prompt, options, usage)` wrapping `claude_agent_sdk.query` inside `contextlib.aclosing(...)`, so that raising mid-stream (a rejected event, or task cancellation) tears down the CLI subprocess and stops hitting an exhausted seat;
  - an optional force hook: `SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS` plus a `force_check()` callable the caller passes in, so the guard stays git-agnostic.

  Never log the token.
- [X] T011 [P] Copy `harness/swe-agent/seat_guard.py` byte-for-byte to `harness/architect-agent/seat_guard.py`.
- [X] T012 Write unit tests in `tests/test_seat_guard.py`:
  - `classify_result_error`: 401, 403, "Failed to authenticate… OAuth access token is invalid", "login expired", 429, "usage limit reached", other → None;
  - `usage_from_rate_limit_info` with the R2 payload: max(0.26, 0.37) gives 0.37 / `seven_day`; missing `unifiedWindows` falls back; both missing gives None;
  - `seat_options_env` keys and values;
  - `guarded_query` with a fake `query`: a rejected event raises `SeatExhausted(resets_at)`; a `ResultError` with 401 data raises `SeatInvalid`; an unrelated error re-raises unchanged; `usage` is updated in place;
  - the two `seat_guard.py` copies are byte-identical.

  Extend the SDK stub in `tests/conftest.py` with `RateLimitEvent`, `ResultError` and `ResultMessage` where needed.
- [X] T013 Add `orchestration/scripts/seat_smoke.py` (quickstart V4). It:
  - reads `CLAUDE_OAUTH_SEAT_A` from the repo `.env` with `dotenv_values`, never printing it;
  - poisons `os.environ` `ANTHROPIC_API_KEY`/`ANTHROPIC_BASE_URL`;
  - imports `seat_guard` from `harness/swe-agent` by path, runs `guarded_query("Reply with exactly: OK", …)` with `tools=[]`, `setting_sources=[]`, `max_turns=1`;
  - prints the result and the usage snapshot with the token redacted.

  Run it once. It must print `OK` and a float utilization.

**Checkpoint**: The pool exists, can be leased, and is tested. The guard is proven live against seat-a.

---

## Phase 3: User Story 1 — Run a pipeline stage on a subscription seat (Priority: P1) 🎯 MVP

**Goal**: Build runs on a leased seat with no API key, then releases the seat with its usage. Seat IDs only, never credentials.

**Independent Test**: one-seat pool → one Build → success, seat free again with `last_utilization` recorded, no token in history or logs (SC-001, SC-006, SC-007).

- [X] T014 [US1] In `harness/swe-agent/agent.py`:
  - seat mode is **conditional**. When `CLAUDE_CODE_OAUTH_TOKEN` is set, `build_options` merges `seat_options_env(token)` into `options.env` and `run_implement` iterates `guarded_query(…, usage)`. When it is unset (the GitHub-comment path via `swe-agent-build.yml`, which still passes an API key), options and the plain `query()` stay exactly as today, the guard is off, and an API-key 429 never becomes exit 75 (spec Out of Scope);
  - `run_implement` returns the transcript and `usage`;
  - on success, `__main__` prints `{"seat_status":"ok","utilization":…,"rate_limit_type":…}` as JSON right before the PR URL, which stays the last line.
- [X] T015 [US1] Add `COPY seat_guard.py /app/` to `sandbox/swe-agent/Dockerfile`, next to the `agent.py` copy.
- [X] T016 [US1] Change `run_swe_agent_activity` in `orchestration/activities.py`:
  - new signature `(repo, branch, feedback, seat_id)`;
  - sandbox `envs={"CLAUDE_CODE_OAUTH_TOKEN": token_for(seat_id, load_pool()), "GH_TOKEN": …}`, with `ANTHROPIC_PLATFORM_API_KEY` removed;
  - `_COMMAND_TIMEOUT_SECONDS = 3300` for `sandbox.commands.run(…, timeout=…)`, and `_SANDBOX_TIMEOUT_SECONDS = 3500` for `AsyncSandbox.create`. That gives about 200 s of headroom so the sandbox can't expire during the push and PR tail, and both stay under the 60-min activity timeout (research R8);
  - a `_parse_seat_status(stdout)` helper;
  - return `{"pr_url", "seat_id", "utilization", "rate_limit_type"}`.

  Keep the existing `RuntimeError` for non-zero exits for now; US2 adds 75/77. Catch `e2b.CommandExitException`, which replaces the dead `if result.exit_code != 0` branch.
- [X] T017 [US1] Add `async def _with_seat(self, agent, stage, invocation, activity_fn, args, **opts)` to `AgentPipelineWorkflow` in `orchestration/workflows/pipeline_workflow.py`, following the contract pseudocode:
  - acquire;
  - run with `args + [seat_id]`;
  - release with the reported usage on success;
  - release in a `finally`-style path on any non-seat failure;
  - raise `ApplicationError(type="CredentialPoolExhausted", non_retryable=True, details=[earliest_reset])` when acquire returns no seat.

  The handoff loop body for `SeatExhausted`/`SeatInvalid` lands in T024. Import the seat activities through the existing `imports_passed_through` block.
- [X] T018 [US1] Wire the Build call in `orchestration/workflows/pipeline_workflow.py`. Under `workflow.patched("seat-pool-v1")`, call `self._with_seat("swe-agent", "build", attempt, run_swe_agent_activity, [repo, branch, feedback], start_to_close_timeout=timedelta(minutes=60), retry_policy=_NO_AUTO_RETRY)` and pass `result["pr_url"]` to `eval_gate_activity`. The unpatched branch keeps today's call unchanged.
- [X] T019 [US1] Update `orchestration/tests/test_pipeline_workflow.py`:
  - change the `run_swe_agent_activity` stub to the new signature and return the dict;
  - register a `CredentialPoolWorkflow` with a per-test ID, plus the real seat activities, using a test pool config written to `tmp_path` and exposed through `CREDENTIAL_POOL_CONFIG`/`CREDENTIAL_POOL_ID` monkeypatched env;
  - add a one-seat happy-path case asserting that the Build stub received `seat_id == "seat-a"` and that `seats()` afterwards shows 0 active leases and the stub's utilization.
- [X] T020 [P] [US1] Write `orchestration/tests/test_seat_activities.py`, covering `_parse_seat_status`: valid ok line, missing line gives None fields, malformed JSON gives None fields. Also check that the `run_swe_agent_activity` sandbox envs contain `CLAUDE_CODE_OAUTH_TOKEN` and not `ANTHROPIC_PLATFORM_API_KEY`, with `AsyncSandbox.create` mocked.

**Checkpoint**: The one-seat happy path works end to end in the tests (SC-001). The live run needs E2B/GH (quickstart V5 prerequisites).

---

## Phase 4: User Story 2 — Lose no committed work when a seat runs out mid-task (Priority: P1)

**Goal**: per-task checkpoints; on a seat outcome, push and then exit 75/77; the successor on another seat resumes at the first `[ ]`; exactly one PR; no Build or plan budget charged.

**Independent Test**: two logical seats, forced exhaustion after task 1 → task 1 pushed, successor on the other seat starts at task 2, one PR, budgets untouched (SC-002, SC-003, SC-004).

- [X] T021 [US2] Rewrite `IMPLEMENT_PROMPT` in `harness/swe-agent/agent.py`:
  - tasks already marked `[X]` in tasks.md were done by a previous run, so skip them;
  - after finishing each task, mark it `[X]` in tasks.md and `git add -A && git commit`, with no push.

  Keep the existing "stop, don't push, don't open a PR" instruction and the local-verification instruction.
- [X] T022 [US2] In `harness/swe-agent/agent.py`:
  - add `has_open_tasks(checkout)`, which is true if any `specs/*/tasks.md` contains a `- [ ]` line;
  - in `run()`, when it is false, skip `run_implement` and `verify_new_commit` and go straight to `push_and_open_pr`;
  - wire the force hook: pass `force_check=lambda: commits_since(checkout, sha_before) >= N` to `guarded_query` when `SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS` is set.

  *Implemented with deviations:* the check reads only `specs/<branch>/tasks.md` when that file exists, because older specs may keep open boxes forever, and it needs at least one `[X]` line. The shortcut applies only when `feedback is None`. On a Gate-feedback retry every task is already `[X]` from the previous attempt, so the shortcut would re-push unchanged code forever. Known gap: feedback plus a handoff, where the predecessor already committed the fix, can still trip `verify_new_commit` on the successor.
- [X] T023 [US2] In `harness/swe-agent/agent.py` `__main__`, catch `SeatExhausted`/`SeatInvalid` from `run()`:
  1. `git push -u origin <branch>` in the checkout (skip if there are no commits beyond the cloned HEAD). If the push fails, exit 1, never 75/77.
  2. Print the `{"seat_status":"exhausted"|"invalid",…}` JSON line last.
  3. `sys.exit(75)` or `sys.exit(77)`.

  This requires `run()` to expose the checkout path and `sha_before` to the handler, for example through a small result or exception wrapper. Token scrubbing via `_scrubbed` applies to the push error.
- [X] T024 [US2] Extend `run_swe_agent_activity` in `orchestration/activities.py`:
  - on `CommandExitException` with `exit_code==75`, raise `ApplicationError("seat exhausted", type="SeatExhausted", non_retryable=True, details=[seat_id, resets_at_iso])`;
  - on 77, raise `type="SeatInvalid"`, `details=[seat_id]`;
  - any other code raises `RuntimeError` as before;
  - forward `SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS` into the sandbox env only when `seat_id == os.environ.get("SEAT_GUARD_FORCE_EXHAUST_SEAT")`.
- [X] T025 [US2] Complete the handoff loop in `_with_seat` in `orchestration/workflows/pipeline_workflow.py`:
  - add `MAX_SEAT_HANDOFFS = 4`;
  - on an `ActivityError` whose `cause.type` is in `{"SeatExhausted","SeatInvalid"}`, call `report_seat_failure_activity(seat_id, key, kind, resets_at)` and loop with `handoff+1`;
  - after the loop, raise `ApplicationError(type="SeatHandoffsExhausted", non_retryable=True, details=[stage, MAX_SEAT_HANDOFFS])`.
- [X] T026 [P] [US2] Write `tests/test_swe_agent_seat.py` with the SDK and git mocked:
  - `has_open_tasks` true/false and multiple spec dirs;
  - the all-done shortcut skips `run_implement`;
  - a `SeatExhausted` raised from `run_implement` leads to push, the JSON line and exit 75;
  - `SeatInvalid` leads to exit 77;
  - a failed push leads to exit 1;
  - the force hook triggers after N commits;
  - **no-token branch:** with `CLAUDE_CODE_OAUTH_TOKEN` unset, options carry no seat env and the plain `query` is used.

  Load swe-agent's `agent.py` **by path under a distinct module name** with `tests/conftest.py`'s `_load_agent` (as `swe_agent`), never with `import agent`, which is already pm-agent in `sys.modules`. Put `harness/swe-agent` on `sys.path` first, or pre-load `seat_guard` by path, so its `import seat_guard` resolves.
- [X] T027 [P] [US2] Extend `orchestration/tests/test_seat_activities.py`: exit 75 → `SeatExhausted` with details; 77 → `SeatInvalid`; 1 → `RuntimeError`; the force hook is forwarded only for the matching seat.
- [X] T028 [US2] Add a handoff case to `orchestration/tests/test_pipeline_workflow.py`. Use a two-logical-seat test pool (`seat-a`, `seat-b`, both `token_env: CLAUDE_OAUTH_SEAT_A`, `max_concurrent: 1`). The Build stub raises `ApplicationError(type="SeatExhausted", non_retryable=True, details=["seat-a", None])` on the first call and succeeds on the second. Assert that:
  - the second call got `seat-b`;
  - Eval-Gate was called exactly once;
  - Build-attempt and plan-attempt counters are unchanged;
  - `seats()` shows `seat-a` with `exhausted_until` set.

  Add a `SeatHandoffsExhausted` case where the stub always raises `SeatInvalid`, with `MAX_SEAT_HANDOFFS` monkeypatched low.

**Checkpoint**: lossless handoff verified in the tests. The live variant is quickstart V5.

---

## Phase 5: User Story 3 — Choose seats by remaining usage, respecting assignments and sharing (Priority: P2)

**Goal**: selection honors assignment order, sharing, the concurrency cap, exhaustion expiry, invalid seats and lease TTL. The seat table is inspectable.

**Independent Test**: the `select_seat` matrix (SC-005), plus the `seats()` query contents.

- [X] T029 [P] [US3] Add the full `select_seat` matrix to `orchestration/tests/test_credential_pool.py`:
  - lowest utilization wins (0.7 vs 0.2);
  - tie → assignment order;
  - a seat shared across two agents;
  - `max_concurrent` reached → skipped;
  - `exhausted_until` in the future → skipped, in the past → eligible;
  - `invalid` → skipped regardless of time;
  - a lease older than `LEASE_TTL` doesn't count;
  - an agent with no assignment → None;
  - every seat ineligible → None.
- [X] T030 [US3] Add a pool-workflow test to `orchestration/tests/test_credential_pool.py` for the `seats()` query shape, which must not include the `token_env` value, plus `reload_config`: state is kept for surviving seat IDs, removed seats are dropped and new seats initialized.

**Checkpoint**: The selection rules are fully covered.

---

## Phase 6: User Story 4 — Fail clearly when every seat is unavailable (Priority: P2)

**Goal**: a distinct `CredentialPoolExhausted` failure with the earliest reset time, no budget charged, and committed work published.

**Independent Test**: a one-seat pool plus forced exhaustion → `CredentialPoolExhausted` with earliest reset, work pushed, no budget charged (SC-004, SC-008).

- [X] T031 [US4] Add a one-seat case to `orchestration/tests/test_pipeline_workflow.py`. The Build stub raises `SeatExhausted(details=["seat-a", "<iso>"])`. Assert that the workflow fails with cause type `CredentialPoolExhausted`, that its details carry that ISO reset time, and that Eval-Gate was never called.
- [X] T032 [US4] Check `earliest_reset` in `orchestration/credentials/pool.py`. It returns the minimum future `exhausted_until` across seats, and None when no seat is exhausted, for example when all are invalid. Add a unit test for it in `orchestration/tests/test_credential_pool.py`.

**Checkpoint**: pool exhaustion is a first-class, budget-neutral failure.

---

## Phase 7: User Story 5 — Run the Architect stage on seats (Priority: P3)

**Goal**: the architect runs on a seat. On a seat outcome, the sibling candidates stop and the whole stage re-runs on another seat, with no plan budget charged and no duplicate comment.

**Independent Test**: the stub's first seat is exhausted → the stage re-runs on another seat, `MAX_PLAN_ATTEMPTS` is untouched, one comment per attempt.

- [X] T033 [US5] In `harness/architect-agent/agent.py`:
  - load the sibling `seat_guard.py` by file path (importlib, `_load_module_by_path` style), because the worker loads `agent.py` by path;
  - add a `seat_token: str | None = None` parameter to `_candidate_options` and to the score, synth and critic option builders (around lines 269, 484, 562 and 603). Seat mode uses `seat_guard.seat_options_env(token)`; `None` keeps the LiteLLM env unchanged;
  - switch `_model_text` to `seat_guard.guarded_query`, accumulating into a stage-level `usage` dict;
  - thread `seat_token` through `run_architect_stage(…, seat_token=None)` and expose the final usage snapshot to the caller, for example on the returned dict under a `_seat_usage` key that the activity strips.
- [X] T034 [US5] Change `generate_candidates` in `harness/architect-agent/agent.py` from `asyncio.gather` to `asyncio.TaskGroup`, so that a `SeatExhausted`/`SeatInvalid` in one candidate cancels its siblings (FR-013). Unwrap the resulting `ExceptionGroup` to re-raise the single seat exception. Make sure `generate_candidate`'s `except (ValueError, RuntimeError)` and the timeout handling still swallow only what they did before.
- [X] T035 [US5] Change `architect_stage_activity` in `orchestration/activities.py`:
  - new signature `(repo, branch, pr_url, attempt, feedback, seat_id)`;
  - resolve the token with `token_for`;
  - map `SeatExhausted`/`SeatInvalid` to typed `ApplicationError`s **before** the existing `RuntimeError`/`ValueError` mapping;
  - add `seat_id`/`utilization`/`rate_limit_type` from `_seat_usage` to the result, leaving `idempotent_hit` handling intact (CO-4 still branches on `.get("idempotent_hit")` first).
- [X] T036 [US5] Wire the architect call in the plan loop of `orchestration/workflows/pipeline_workflow.py` through `self._with_seat("architect-agent", "architect", plan_attempt, architect_stage_activity, [repo, branch, pr_url, plan_attempt, plan_feedback], start_to_close_timeout=timedelta(minutes=30), retry_policy=_TRANSIENT_RETRY)` under the same `seat-pool-v1` patch. In the existing `except`, re-raise `CredentialPoolExhausted`/`SeatHandoffsExhausted` causes **before** the CO-2 budget-charging branch, the same way as `MalformedRetriesExhausted`.
- [X] T037 [P] [US5] Extend `tests/test_architect_agent.py`:
  - seat-mode option builders carry `CLAUDE_CODE_OAUTH_TOKEN` and blank `ANTHROPIC_*`;
  - non-seat mode is unchanged (LiteLLM env);
  - a fake `query` that raises `SeatExhausted` for one angle cancels the other candidates and propagates `SeatExhausted`, not a candidate `error` dict.
- [X] T038 [US5] Add architect handoff cases to `orchestration/tests/test_pipeline_workflow.py`:
  - the architect stub raises `SeatExhausted` on its first call → the stage re-runs on the other seat and the plan-attempt budget is not charged;
  - a one-seat `CredentialPoolExhausted` during the architect stage → the run fails without charging `MAX_PLAN_ATTEMPTS`.

  Update the existing architect stub signature to the new `seat_id` argument.

  *Implemented note:* on seats, the lease release runs after the architect result, so the test helper `_wait_plan_parked` also waits for no pending activities. The production side of this is the pre-existing plan-signal race (a `plan_approved` arriving before the post-stage reset is dropped), now with a slightly wider window: the release activity. It stays a 005 follow-up.

**Checkpoint**: both seat-backed stages run on the pool.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T039 [P] Update `CLAUDE.md`:
  - **Inference Routing row:** the seat path goes direct to Anthropic, a documented §3.4 deviation, with a pointer to research R4.
  - **Orchestration row:** `CredentialPoolWorkflow`, `_with_seat`, the `seat-pool-v1` patch, and the handoff and pool-exhausted failure types.
  - **swe-agent and architect-agent Harness rows:** seat-backed, checkpointed handoff.
  - **Commands:** a note on `orchestration/scripts/seat_smoke.py`.

  Stage only these hunks: CLAUDE.md has unrelated uncommitted operator edits.
- [X] T040 [P] Update `agent-factory-architecture.md` §3.4: the seat-path deviation, why LiteLLM can't pool OAuth tokens (R4), the LiteLLM pass-through follow-up, and the single-operator usage constraint.
- [X] T041 [P] Update `harness/swe-agent/SKILL.md` and `harness/architect-agent/SKILL.md`: the seat-backed runtime, the exit codes 75/77 and the resume behavior, the usage constraint, and "Known gaps" (the GitHub-comment path still uses the API key; no durable sleep-until-reset; no expiry alert).
- [ ] T042 Rebuild the E2B template (`cd sandbox/swe-agent && e2b template build`). This is a **manual** step that needs the operator's E2B credentials, so record the outcome in this task when it is run.

  *Pending (2026-10-10):* `E2B_API_KEY` is empty in `.env` and the `e2b` CLI isn't installed on this host. Until the template is rebuilt, the sandbox runs the old image without `seat_guard.py`, so the seat path can't run live.
- [X] T043 Run quickstart V1–V3 locally (`make up`, then both suites with no skips) and V4 against seat-a. Record the results in `specs/009-credential-pool-handoff/quickstart.md` under a "Results" heading.
- [ ] T044 Run quickstart V5 (live end-to-end with forced handoff and the secrecy grep) once `E2B_API_KEY`, `GH_TOKEN` and a disposable target repo are available. Until then, record it as pending with the missing prerequisites listed.

  *Pending (2026-10-10):* missing `E2B_API_KEY`, `GH_TOKEN`, a disposable target repo, and the T042 template rebuild.
- [X] T045 Run `py-codereviewer` over the full 009 diff and resolve the findings before the PR.

---

## Dependencies & Execution Order

- **Setup (T001–T003)** → **Foundational (T004–T013)**, which blocks every story.
  - Within Foundational, T004 comes before T005/T006, T006 before T007/T008/T009, and T010 before T011/T012/T013.
- **US1 (T014–T020)** needs Foundational. It is the MVP.
- **US2 (T021–T028)** needs US1. It extends the same files (`agent.py`, `run_swe_agent_activity`, `_with_seat`).
- **US3 (T029–T030)** needs only Foundational. It can run in parallel with US1 and US2.
- **US4 (T031–T032)** needs US1's `_with_seat` (T017). It can run in parallel with US2.
- **US5 (T033–T038)** needs US2's `_with_seat` handoff loop (T025).
- **Polish (T039–T045)** comes after all stories. T042 is manual and gates the live part of T044.

## Parallel Opportunities

- **Setup:** T002 ∥ T003.
- **Foundational:** the guard track T010 → (T011 ∥ T012) can run alongside the pool track T004 → T006 → T007/T008/T009.
- **US1:** T020 ∥ T019, once T016 has landed.
- **US2:** T026 ∥ T027 (test files are disjoint).
- **Across stories:** US3 (T029, T030) ∥ US1/US2. US4 T032 ∥ US2.
- **Polish:** T039 ∥ T040 ∥ T041.

## Implementation Strategy

1. **MVP = Setup + Foundational + US1.** Build runs on today's single real seat with no API key, and the seat is released with its usage recorded. Stop there and validate with quickstart V1, V2, V4 and the US1 workflow test.
2. **Add US2.** This is the feature's core promise, lossless handoff, testable with two logical seats on one token.
3. **Add US3 and US4.** Harden selection and pool exhaustion. They are cheap: mostly tests on logic that already exists.
4. **Add US5.** Architect on seats.
5. **Polish.** Docs, the manual template rebuild and the live V5 run.
