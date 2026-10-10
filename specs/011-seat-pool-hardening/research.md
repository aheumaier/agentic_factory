# Research: Seat Pool Hardening (011)

Each entry gives the decision, why, and what else was considered. Design sources: 009's `contracts/`, `research.md` R2/R7, and `quickstart.md` "Follow-ups surfaced by V5".

## R1: Where the harness checkpoint runs, and its timing (F1)

**Decision.** `run_implement` takes an `on_message` callback, which is called after each streamed message, inside the `async for` body. `run()` passes a `TaskCheckpointer(checkout, branch)`. The checkpointer:
- reads the feature's task files (009's `_task_files`) and collects the done-task keys: the `T\d+` ID when present, else the line text;
- does nothing when no key is new;
- otherwise, if `git status --porcelain` is non-empty, runs `git add -A` and `git commit -m "checkpoint: <IDs>"`;
- marks the keys saved after a successful commit or on a clean tree;
- on a `CalledProcessError` (for example `index.lock` while the model commits at the same moment), leaves the keys unsaved, so the next message retries.

Keys already done at start-up (a predecessor's work) are seeded as saved.

**Why here and not in `seat_guard`.** The guard is byte-shared with architect-agent, which has no task list, and it must stay git-free. Ordering is the important property. `guarded_query` yields a message, the consumer's loop body runs (the checkpoint commit), and then the generator resumes and polls `force_check`. So the force hook "exhaust after 1 commit" fires right after `checkpoint: T001` (FR-005) and never before it.

**Why after every message.** The SDK streams a message after each tool round trip, so a tick written by an `Edit` call is on disk when its tool result arrives. Reading one small file per message costs little. Git runs only when the done set changed.

**End of stream.**
- *Seat outcome:* call the checkpointer once more, then `checkpoint_push`. Edits for a task not marked done are deliberately not committed; 009 accepted the loss of the task in progress.
- *Normal end:* `finish()` calls the checkpointer, then commits any remaining dirty tree as `checkpoint: end of run`. This covers verification fixes after the last tick.

**Prompt.** It changes to "mark each task `[X]` as soon as it is done; the harness saves a checkpoint commit for you; do not batch ticks". The end-of-run commit instruction stays: when the model commits itself, the harness sees a clean tree and only records the keys (FR-002). If the model's own commit then finds nothing to commit, that does not fail the run.

**Alternatives.**
- (b) Only warn when commits < tasks: detects the loss but does not prevent it.
- (c) A git hook in the sandbox: the trigger would be a model `git commit`, which is the very thing that may not happen.

## R2: Adding an activity argument is replay-safe (F2, F5)

**Decision.** `run_swe_agent_activity` gains a trailing `handoff: int = 0`, and `release_seat_activity` and the `release` update gain a trailing `utilization_resets_at: str | None = None`. They are passed unconditionally (no patch).

**Why.** Temporal's replay check compares the command sequence: command type, activity type and activity ID. It does not compare activity inputs. An old history that scheduled the activity with 4 arguments replays cleanly under code that schedules 5. A task already queued with 4 arguments runs with the default. The only new *command* in 011 is F3's timer, so only F3 gets a new patch ID.

**Alternative.** Gate the new arguments behind a patch as well. Rejected: it adds a marker and a second code path for no replay benefit.

## R3: Pool-workflow changes need no patch (F2, F4)

**Decision.** `CredentialPoolWorkflow`'s handlers, query and `select_seat` change in place. Old state is upgraded in `_apply_config` with `{**new_seat_state(), **old}`.

**Why.**
- Pool handlers issue no commands, so there is nothing for replay to mismatch.
- The one behavior change that could alter a replayed acquire's choice is "a 1.0 reading from an expired exhaustion now counts as 0". It needs an old history containing `mark_exhausted` followed by an `acquire` after the reset. On 2026-10-10 the live server has no `credential-pool` workflow at all; only per-test pools exist, and they are terminated after each test. A divergence would at worst leave a phantom lease that ages out via `LEASE_TTL`.
- `patched()` in a long-lived workflow would memoize `False` until the next continue-as-new, which almost never happens, so it would keep the fix off.

## R4: Which reset time belongs to a reading (F2)

**Decision.** `usage_from_rate_limit_info` adds `utilization_resets_at`, the `resetsAt` of the window that supplied the max utilization. Its fallback is the top-level `resets_at`, and then `None`. `resets_at` keeps its 009 meaning, because `SeatExhausted` depends on it.

**Why.** In 009 research R2's sample, `five_hour` was at 0.26 and `seven_day` at 0.37, and the top-level `resetsAt` was the five-hour one. Storing that with the 0.37 reading would expire it days too early.

**Pool rule.**
- `effective_utilization(state, now)` is 0.0 when `utilization_resets_at` is set and is earlier than or equal to `now`; otherwise it is `last_utilization`. `select_seat` sorts by it.
- `mark_exhausted` sets `utilization_resets_at = exhausted_until`.
- `release` with a non-null utilization overwrites `utilization_resets_at` too, even with `None`, so a new reading never inherits an old reading's reset time.

## R5: The F3 wait (horizon, count, timer)

**Decision.** This logic is inside `_with_seat`'s acquire step. When `seat_id is None`:
1. call `workflow.patched("seat-pool-wait-v1")`, only on this path;
2. parse `earliest_reset`;
3. wait when patched, when the reset is known, when it is at most `POOL_WAIT_HORIZON = 6h` after `workflow.now()`, and when `waits < MAX_POOL_WAITS = 2`. The sleep is `max(reset - now, 0) + 1s` with `workflow.sleep`, after which the stage acquires again with the same lease key;
4. otherwise raise `CredentialPoolExhausted` as in 009.

A wait does not advance the handoff counter.

**Why a horizon rather than a partial wait.** A reset 9 h away does not get closer by sleeping for 6 h. Failing at once names the time, so the operator can restart then. The 1 s margin is there because `is_eligible` needs `exhausted_until <= now`.

**Why `patched` only on this path.** That way successful runs gain no marker. On replay of a 009-era run that failed with `CredentialPoolExhausted`, the history has no marker, so `patched()` returns `False` and the run fails as before.

**Which reset.** `acquire_seat_activity` reads the earliest reset from a new pool query, `earliest_reset_for(agent)`, which considers only that agent's assigned, non-invalid seats. Otherwise an unrelated seat's sooner reset would make the stage sleep for nothing. *(Code-review fix, 2026-10-10.)*

**Test without time-skipping.** A stub `acquire_seat_activity` returns `{"seat_id": None, "earliest_reset": now+2s}` once and then a seat. The real sleep stays at about 3 s.

## R6: F5 condition (dropping "ahead of the original start")

**Decision.** Skip `verify_new_commit` only when `SEAT_HANDOFF_INDEX > 0` **and** the feature's `tasks.md` has no open task. A successor that leaves tasks open and commits nothing still fails with exit 1, exactly like the first seat. *(Narrowed after code review on 2026-10-10; the first version skipped on any handoff index > 0.)*

**Why.** A successor's clone already contains the predecessor's pushed commits, so "ahead of the original start" would need the first seat's start SHA. That SHA would have to travel through `SeatExhausted` details, then through `_with_seat`, and then into the next activity's arguments. That is a lot of plumbing for one rare case. The F5 case itself, a Gate-feedback retry, always has every task `[X]`.

**Remaining gap, stated plainly.** On a feedback retry where the predecessor pushed nothing *and* the successor commits nothing, the Build proceeds to the PR step. The Eval-Gate does **not** catch this: today's gate (`eval.config.py::run_eval`) checks the exit code, that a PR exists and that SC-NNN criteria are present, never the diff. So the unchanged branch can pass. That is no worse than 009, where a model's no-op commit also passed. Agent-decided, to confirm.

## R7: Git identity for harness commits (F1)

**Decision.** Before committing, the harness checks `git config user.email` in the checkout. When it is empty, the commit runs with `-c user.name=swe-agent -c user.email=swe-agent@users.noreply.github.com`.

**Why.** `sandbox/swe-agent/Dockerfile` sets no git identity. The model's own commits worked in 009 because the model ran `git config` when git refused. The harness cannot rely on that, especially when it commits before the model ever does. An identity the model or the repo configured always wins.

## R8: F6 force hook by handoff index

**Decision.** In `_sandbox_envs(seat_id, handoff)`, the force setting is forwarded when either of these holds:
- `seat_id == SEAT_GUARD_FORCE_EXHAUST_SEAT` (the 009 behavior);
- `SEAT_GUARD_FORCE_EXHAUST_HANDOFF` is set and equals `str(handoff)`.

`SEAT_HANDOFF_INDEX` is always forwarded.

**Why.** Selection by utilization can steer Build away from a named seat, as in run 1. The handoff index cannot be routed around.

**Caveat.** The hook arms handoff N of *every* Build invocation, including a Gate-feedback retry. It is a test hook, used only in V5.

## R9: Expiry warning (F4)

**Decision.**
- `expires_in_days(seat_cfg, today: date) -> int | None` is `(date.fromisoformat(token_expires_on) - today).days`, or `None` without a date.
- At worker boot, after `load_pool()`, the worker logs `WARNING seat <id>: credential expires on <date> (<n> days)` for each seat with `n <= EXPIRY_WARN_DAYS = 14`, expired seats included.
- `seats()` adds `expires_in_days`, computed from `workflow.now().date()`.

**Alternative.** (b) A PR or issue comment as well. Rejected: no natural PR exists at boot. Teams notices belong to docs/80.

## R10: One model session per open task (F7-a, operator-ruled 2026-10-11)

**Decision.** In `run()`, when there is no Gate feedback, the task list is one file, and every open task has a `T\d+` ID, the harness runs one `query()` per open task, in file order (`run_per_task`). The list of open IDs is read once. Before each session the harness checks again, and it skips a task the model already ticked in an earlier session. The per-task prompt (`TASK_PROMPT`) names the task and its checkout-relative `tasks.md` path. It does not start with `/speckit-implement`: that skill works through the whole list. The prompt says to read the spec and plan, implement only that task, verify it, mark it `[X]` and stop, and **not to commit**.

**Why "do not commit".** The forced-exhaustion hook counts commits. If the model commits its code *before* the tick, "exhaust after 1 commit" fires with the task still open, and the successor redoes it. When only the harness commits, the first commit is always `checkpoint: T001`. A model commit is still harmless (the checkpointer records a clean tree).

**Between sessions.** After each session the checkpointer runs `finish(<ID>)`. It saves a tick from the last message and commits leftover edits as `checkpoint: end of <ID>`, so a seat outcome in the next session cannot lose them. When a session ends with its task still open, the loop stops, with a note on stderr: a later task likely builds on it, and the seat should not pay for N stuck sessions. The usual end-of-run steps follow (the new-commit check, push, PR).

**Shared state.** One `TaskCheckpointer`, one `usage` dict, one `sha_before` and one `force_check` span all sessions. So the force count is cumulative, and the final `seat_status` line carries the last reading. One `try/except (SeatExhausted, SeatInvalid)` around the loop keeps the 009 push and exit 75/77.

**Where the single session stays.**
- A Gate-feedback retry: the feedback is about the whole change, and every task is already `[X]`.
- An open task without an ID: there is nothing to name.
- Several task files (the `specs/*/tasks.md` fallback): older specs' open boxes must not get sessions of their own.

**Cost.** N CLI sessions per Build instead of 1. Each session re-reads the spec and plan, so seat usage per Build is higher, and there is no shared context between tasks. The operator accepted this with the ruling. All N sessions also share the activity's one sandbox command timeout (`_COMMAND_TIMEOUT_SECONDS`, 3300 s), and a timeout kills the sandbox before its local checkpoints are pushed. That risk existed before (009 research R8), but N sessions make it more likely on long task lists.

**Alternatives.**
- (b) Change only the fixture or the scratch repo's implement skill. Rejected: it is unreliable and proves nothing about production runs.
- (c) Accept the model's tick granularity. Rejected: SC-001 would then hold only for models that tick per task.
