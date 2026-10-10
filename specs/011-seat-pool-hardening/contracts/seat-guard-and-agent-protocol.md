# Contract delta: `seat_guard` and the swe-agent seat protocol (011)

Extends `specs/009-credential-pool-handoff/contracts/seat-guard-and-agent-protocol.md`. That contract still holds except where changed below.

**Usage Constraint (binding):** internal, single-operator use only. The seats are the operator's own, they are never offered to third parties, and seat rotation is a knowingly accepted Consumer-Terms grey area.

## `seat_guard.py` (both byte-identical copies)

`usage_from_rate_limit_info(info)` also returns `utilization_resets_at`, the max window's `resetsAt` (epoch s), falling back to `resets_at`. Nothing else changes.

## swe-agent process protocol

**Env in (new, all optional):**

| Var | Meaning |
|---|---|
| `SEAT_HANDOFF_INDEX` | Position of this seat run within one Build invocation (0 = first seat). `> 0` skips `verify_new_commit` (F5). |
| `SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS` | Unchanged test hook. It is now forwarded by the activity when the seat name **or** the handoff index matches (see the activity below). |

**stdout:** every `seat_status` line also carries `"utilization_resets_at": <int|null>`. Line order and exit codes (0 / 75 / 77 / other) are unchanged.

**Checkpointing (F1, replaces "the model commits after each task"):**
- After every streamed message (run in a worker thread, so git never blocks the SDK stream), the harness commits `checkpoint: <IDs>` when the feature's done-task IDs grew and the tree is dirty. A clean tree only records the IDs as saved. A failed commit is retried on the next message and never fails the run.
- On a seat outcome: one more checkpoint, then the 009 checkpoint push.
- On a normal end: one more checkpoint, then any dirty tree is committed as `checkpoint: end of run`, before `verify_left_main`/`verify_new_commit`/push.
- The commit uses the repo's git identity, or `swe-agent <swe-agent@users.noreply.github.com>` when none is configured.
- The force hook's commit count includes harness checkpoints, and it is polled after the checkpoint for the same message.

**One session per task (F7-a, R10):** a Build without feedback, whose task list is one file with an ID on every open task, runs one model session per open task, in file order. The prompt is `TASK_PROMPT` (not `/speckit-implement`): implement only `<ID>` from `<tasks.md>`, mark it `[X]`, stop, do not commit. A task ticked before its session is skipped. A session that leaves its task open ends the loop. After each session, `finish(<ID>)` commits leftovers as `checkpoint: end of <ID>`. The checkpointer, `usage`, the force count and the seat-outcome handling span all sessions. A feedback retry, an open task without an ID, and several task files keep the single `/speckit-implement` session.

**Resume behavior:** as in 009, plus `verify_new_commit` is skipped when `SEAT_HANDOFF_INDEX > 0` **and** no task is left open. This closes 009's "known gap". A successor with open tasks and no commit still exits 1. In the remaining case, where no one committed on a feedback retry, the Build reaches the PR step, and today's Eval-Gate does not check the diff (research R6).

`usage_from_rate_limit_info` pairs: whenever a later event carries a utilization, `utilization_resets_at` is replaced too, even with `None`. A reading never keeps an older reading's reset time.

## `run_swe_agent_activity(repo, branch, feedback, seat_id, handoff=0) -> dict`

- Sandbox env: as in 009, plus `SEAT_HANDOFF_INDEX=str(handoff)`. It forwards `SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS` from the worker env when `seat_id == SEAT_GUARD_FORCE_EXHAUST_SEAT` **or** `str(handoff) == SEAT_GUARD_FORCE_EXHAUST_HANDOFF`.
- Result: as in 009, plus `"utilization_resets_at": <ISO|None>`.

## `architect_stage_activity(...)`

Result also carries `"utilization_resets_at": <ISO|None>` when seat-backed. Its signature is unchanged.
