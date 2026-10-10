# Contract: `seat_guard` and the swe-agent seat protocol (009)

## `seat_guard.py`

Copies are **byte-identical** at:
- `harness/swe-agent/seat_guard.py`, imported normally, since `agent.py` runs as a script with its directory on `sys.path`, both in `/app` in the sandbox and in local tests;
- `harness/architect-agent/seat_guard.py`, loaded by file path from `agent.py`, because the worker loads `agent.py` itself by path.

A root test asserts the two copies are equal.

```python
class SeatExhausted(Exception):      # NOT RuntimeError/ValueError (FR-011)
    resets_at: int | None             # epoch seconds
    usage: dict                       # last UsageSnapshot

class SeatInvalid(Exception):
    usage: dict

def seat_options_env(token: str) -> dict[str, str]
    # {"CLAUDE_CODE_OAUTH_TOKEN": token, "ANTHROPIC_API_KEY": "",
    #  "ANTHROPIC_BASE_URL": "", "ANTHROPIC_AUTH_TOKEN": ""}   (research R1)

def usage_from_rate_limit_info(info) -> dict
    # {"utilization", "rate_limit_type", "resets_at"} — max over raw["unifiedWindows"],
    # fallback info.utilization (research R2)

def classify_result_error(data: dict) -> Literal["exhausted", "invalid"] | None   # research R3

async def guarded_query(prompt, options, usage: dict) -> AsyncIterator[Message]
    # yields every message from claude_agent_sdk.query(); updates `usage` in place on each
    # RateLimitEvent; raises SeatExhausted on status == "rejected"; on ResultError classifies
    # e.data → SeatExhausted / SeatInvalid, else re-raises unchanged.
```

The guard never logs, prints or embeds the token. Exception messages carry seat-neutral text only.

## swe-agent process protocol (in the sandbox, `python3 /app/agent.py <repo> <branch> [feedback]`)

**Env in:** `CLAUDE_CODE_OAUTH_TOKEN` (the seat credential) and `GH_TOKEN`. `ANTHROPIC_PLATFORM_API_KEY` is no longer passed.
Optional: `SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS=N`, a test hook. The guard raises `SeatExhausted` once the checkout has N commits beyond the starting HEAD. `run_swe_agent_activity` forwards it from the worker env only when `seat_id == os.environ.get("SEAT_GUARD_FORCE_EXHAUST_SEAT")`, so exactly one seat is forced and the successor runs normally.

**stdout**, with the final two lines fixed:

| Outcome | Second-to-last line | Last line | Exit code |
|---|---|---|---|
| success | `{"seat_status":"ok","utilization":<float\|null>,"rate_limit_type":<str\|null>}` | PR URL | 0 |
| seat exhausted | (anything) | `{"seat_status":"exhausted","resets_at":<int\|null>,"utilization":…,"rate_limit_type":…}` | **75** |
| seat invalid | (anything) | `{"seat_status":"invalid","utilization":…,"rate_limit_type":…}` | **77** |
| any other failure | — | — | non-zero, not 75 or 77 (traceback on stderr) |

On 75 and 77, the agent has already run `git push -u origin <branch>` for every commit it made. If that push fails, it exits 1 instead, because a seat outcome must not hide lost work.

**Resume behavior:**
- `IMPLEMENT_PROMPT` tells the agent to skip `[X]` tasks and to mark and commit after each task, without pushing.
- If the feature's tasks.md (`specs/<branch>/tasks.md` when it exists, else every `specs/*/tasks.md`) has at least one `- [X]` line and no `- [ ]` line left, the agent skips `run_implement` and `verify_new_commit` and goes straight to `push_and_open_pr`. That function already reuses an existing PR on "already exists". The shortcut applies only when no Gate feedback was passed: a feedback retry always runs `run_implement`, because its tasks are already `[X]` from the previous attempt.
- The checkpoint push counts and pushes the `<branch>` ref (`git rev-list --count <sha_before>..<branch>`), not HEAD, and is skipped when that count is 0. A push error is scrubbed of `GH_TOKEN`. It refuses to push `main`/`master`, the same invariant `verify_left_main` guards on the normal path.
- Known gap: on a feedback retry that hands off after the predecessor already committed the fix, the successor may make no new commit and fail `verify_new_commit` (exit 1).

## `run_swe_agent_activity(repo, branch, feedback, seat_id) -> dict`

Returns `{"pr_url", "seat_id", "utilization", "rate_limit_type"}`. Parses the `seat_status` line from stdout, or from `CommandExitException.stdout`:

| Exit | Raised |
|---|---|
| 0 | — (returns dict) |
| 75 | `ApplicationError("seat exhausted", type="SeatExhausted", non_retryable=True, details=[seat_id, resets_at_iso])` |
| 77 | `ApplicationError("seat invalid", type="SeatInvalid", non_retryable=True, details=[seat_id])` |
| other | `RuntimeError(f"sandbox run failed ({code}): …")`, as today. stderr/stdout are included; they never contain the token. |

## `architect_stage_activity(repo, branch, pr_url, attempt, feedback, seat_id) -> dict`

- It resolves the token with `token_for(seat_id)` and passes it to `run_architect_stage(..., seat_token=token)`.
- It maps `SeatExhausted` and `SeatInvalid` to the same typed `ApplicationError`s as above, **before** the existing `RuntimeError`/`ValueError` mapping.
- It adds `seat_id`, `utilization` and `rate_limit_type` to the returned dict. `run_architect_stage` exposes its last `UsageSnapshot`.

Fan-out: a seat outcome in any candidate cancels the sibling candidate tasks (FR-013).
