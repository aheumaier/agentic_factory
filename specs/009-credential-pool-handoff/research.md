# Research: Subscription-Seat Credential Pool with Checkpointed Agent Handoff (009)

All items were resolved on 2026-10-10. Items marked **(empirical)** were settled by a live probe against seat-a, the operator's one real seat, using `claude-agent-sdk` 0.2.152 from `orchestration/.venv`. The probe script lived in the session scratchpad. It was not committed because it reads the real token.

---

## R1 (empirical): Does an empty-string `options.env` override beat an inherited `ANTHROPIC_API_KEY`/`ANTHROPIC_BASE_URL`?

**Probe.** The parent `os.environ` was poisoned with `ANTHROPIC_API_KEY=sk-bogus-not-a-key` and `ANTHROPIC_BASE_URL=http://127.0.0.1:9`, as if a worker were configured for LiteLLM. Three `query()` calls were made with `tools=[]`, `setting_sources=[]`, `max_turns=1` and the prompt "Reply with exactly: OK":

| Run | `options.env` | Result |
|---|---|---|
| treatment | `CLAUDE_CODE_OAUTH_TOKEN=<seat-a>` + `ANTHROPIC_API_KEY=""`, `ANTHROPIC_BASE_URL=""`, `ANTHROPIC_AUTH_TOKEN=""` | **success**, `is_error=False`, result `OK` |
| control: bogus token | as treatment, but with a syntactically valid, bogus `sk-ant-oat01-…` token | `ResultError`: "Failed to authenticate. API Error: 401 OAuth access token is invalid." |
| control: no blanking | `CLAUDE_CODE_OAUTH_TOKEN=<seat-a>` only | `ResultError`: "API Error: Connection refused" (it followed the poisoned base URL) |

**Decision.** `seat_options_env(token)` returns `{"CLAUDE_CODE_OAUTH_TOKEN": token, "ANTHROPIC_API_KEY": "", "ANTHROPIC_BASE_URL": "", "ANTHROPIC_AUTH_TOKEN": ""}`. No `os.environ` pop is needed.

**Rationale.**
- The bogus-token control proves that the token in `options.env` is what authenticates. The host's own logged-in keychain session never silently took over.
- The no-blanking control proves the precedence hazard is real: without blanking, an inherited base URL wins.
- Empty strings are enough. The process-wide `os.environ` pop that pm-agent uses would also work, but it is racy under `asyncio.gather`, because candidates share one process.

**Alternatives considered.** A scoped `os.environ` pop (pm-agent's pattern) was rejected: it is process-global, and the architect already needs one credential-scrub window around concurrent calls.

---

## R2 (empirical): What does the usage signal actually carry?

`RateLimitEvent.rate_limit_info` from the treatment run:

```
status='allowed', rate_limit_type='five_hour', resets_at=1791655200,
utilization=None,                                   # <-- parsed field is EMPTY
overage_status='rejected', overage_disabled_reason='org_level_disabled',
raw.unifiedWindows = {
  "five_hour": {"utilization": 0.26, "resetsAt": 1791655200},
  "seven_day": {"utilization": 0.37, "resetsAt": 1791831600}
}
```

**Decision.**
- Last-seen utilization is `max(w["utilization"] for w in raw["unifiedWindows"].values())`, because the tightest window is the one that binds.
- `rate_limit_type` is the name of that maximum window.
- If `unifiedWindows` is missing, fall back to `rate_limit_info.utilization`, then to "no update".
- `resets_at` comes from top-level `resetsAt`, the binding window. For an exhausted seat, it comes from the rejected window's `resetsAt`.

**Rationale.** The SDK's typed `utilization` field was `None`, while the raw payload had real per-window figures. Reading only the typed field would leave every seat at 0, and selection would silently degrade to preference order.

**Additional finding.** `overage_status='rejected'` with `org_level_disabled` means there is no pay-as-you-go overflow. A seat that reaches 100% in any window gets a hard rejection, which is the exhaustion signal this feature handles.

---

## R3 (empirical, partial): Failure result shapes for classification

**Observed.**
- An invalid or expired token raises `claude_agent_sdk.ResultError`.
- `e.data` is the result dict. It has `api_error_status == 401` and `result == "Failed to authenticate. API Error: 401 OAuth access token is invalid."`.
- `ResultError → ProcessError → ClaudeSDKError → Exception`. It does **not** derive from `RuntimeError` or `ValueError`.

**Not observable without exhausting a real seat:** the exact 429 / usage-limit shape.

**Decision.** The classifier checks these rules in order, all against `ResultError.data`:
1. `api_error_status in (401, 403)`, or a `result` matching `/failed to authenticate|oauth .*invalid|login expired|token .*(expired|revoked)/i`, means **invalid**.
2. `api_error_status == 429`, or a `result` matching `/rate.?limit|usage limit|limit reached|quota/i`, means **exhausted**.
3. Separately, any `RateLimitEvent` with `status == "rejected"` seen during the stream means **exhausted**, with that event's `resetsAt`.
4. Anything else is re-raised unchanged.

The 429 branch is unit-tested with a synthetic payload. Its real shape is checked during the live failover smoke test only if a seat genuinely exhausts. Otherwise `SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS` exercises the downstream path.

**Alternatives considered.** Matching on exception message text alone was rejected because `api_error_status` is structured and more stable.

---

## R4: Can LiteLLM front subscription seats, and would rotation there be cheaper?

**Finding** (LiteLLM docs, "Claude Code Max subscription" tutorial):
- Since v1.81.14, LiteLLM forwards a client's `Authorization: Bearer sk-ant-oat…` subscription token to `anthropic/*` deployments.
- The client authenticates to LiteLLM separately with `x-litellm-api-key`, set through `ANTHROPIC_CUSTOM_HEADERS`.
- The token is **per request and client-held**. Quoting the docs: "LiteLLM stores nothing: the token is used for the one upstream request it arrived with, it is not cached across requests". LiteLLM **cannot hold a pool of OAuth tokens or rotate between them** server-side.

**Decision.** Seat rotation lives in our own `CredentialPoolWorkflow`; LiteLLM can't do it. Seat-backed calls go **direct to Anthropic** in v1:
- **swe-agent:** forced. It runs in E2B, which can't reach the local proxy. This is already a documented deviation for swe-agent.
- **architect:** chosen, to keep one code path and because it is not yet verified that LiteLLM passes Anthropic's unified rate-limit headers, and so the usage signal, back to the client.

**Follow-up (not in this feature).** The in-process architect could route seat calls through LiteLLM pass-through for §3.4 observability. That would mean setting `ANTHROPIC_BASE_URL=<litellm>`, `ANTHROPIC_CUSTOM_HEADERS=x-litellm-api-key: Bearer <master>` and `ANTHROPIC_API_KEY=""`. It requires two things first: LiteLLM ≥ 1.81.14 with an `anthropic/*` wildcard route, which `litellm/config.yaml` lacks today, and a confirmed check that `RateLimitEvent` still arrives through the proxy.

**Alternatives considered.** Rotation in LiteLLM was rejected because it is not supported. A LiteLLM pass-through for architect only was deferred as above.

---

## R5: How do other workflows reach the pool, given that workflows can't call updates on other workflows?

**Decision.**
- Use three thin activities: `acquire_seat_activity`, `release_seat_activity` and `report_seat_failure_activity`.
- Each calls `activity.client().get_workflow_handle(pool_id).execute_update(...)`. `temporalio.activity.client()` exists in 1.32.0.
- The worker starts the pool with `start_workflow(..., id=pool_id, id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING)`.

**Rationale.** `ExternalWorkflowHandle` inside a workflow offers only `signal` and `cancel`. A signal would be fire-and-forget and couldn't return the chosen seat.

**Alternatives considered.**
- *Signal plus a query-polling loop:* rejected as racy, and as more history.
- *A pool as a plain in-memory object in the worker:* rejected because it doesn't survive restarts and can't be shared across workers.

---

## R6: Lease identity, idempotency, and leaked leases

**Lease key.** Each lease is keyed by a key built deterministically in the workflow: `f"{workflow_id}/{stage}/{invocation}/{handoff}"`.
- A Temporal-retried acquire with the same key returns the same seat (FR-007).
- A release for a key that isn't held is a no-op.

**Leaked leases.** A lease is not released if, for example, a pipeline workflow is terminated mid-stage. To handle this, every lease stores `acquired_at` (`workflow.now()`), and `acquire` ignores leases older than `LEASE_TTL` (default 2h). That is longer than the longest stage `start_to_close_timeout`, which is 30 min for architect and ≤ 60 min for build after the timeout alignment.

**Release in all paths.** `_with_seat` releases in a `finally` for every non-seat failure path, so a timeout or other error never strands a lease.

**Rationale.** A TTL is the simplest leak bound that needs no heartbeat channel between workflows.

---

## R7: Default exhaustion window when no reset time is known

**Decision.** If a seat is exhausted and no `resetsAt` is available (the classifier matched on text only), use `exhausted_until = now + 1h`.

**Rationale.** It is conservative but short. A wrong guess only delays reuse by one hour, while a seat that is really still exhausted just fails again and gets re-marked. `CredentialPoolExhausted.details` reports the earliest `exhausted_until`, so the operator sees the estimate.

---

## R8: Sandbox command timeout and exit codes

**Findings.**
- `AsyncSandbox.commands.run(cmd, timeout=60)` defaults to **60 s**. Today's call passes no timeout, so a real Build would be killed after one minute.
- A non-zero exit raises `e2b.CommandExitException`, a subclass of both `SandboxException` and `CommandResult`, with `.exit_code`, `.stdout`, `.stderr` and `.error`. The existing `if result.exit_code != 0` branch is therefore dead code.

**Decisions.**
- Call `commands.run(..., timeout=_SANDBOX_TIMEOUT_SECONDS)`.
- Raise `_SANDBOX_TIMEOUT_SECONDS` to 3300 s (55 min) and the activity's `start_to_close_timeout` to 60 min. The sandbox lifetime must be at least the command timeout, and both must be less than the activity timeout.
- Catch `CommandExitException` and map exit codes:
  - **75** (`EX_TEMPFAIL`) means `SeatExhausted`;
  - **77** (`EX_NOPERM`) means `SeatInvalid`;
  - anything else raises `RuntimeError`, as today.
- Agent stdout carries one JSON line, `{"seat_status": "ok"|"exhausted"|"invalid", "utilization": …, "rate_limit_type": …, "resets_at": …}`, before the final PR-URL line.

---

## R9: Temporal test convention

**Decision.** Temporal tests run against a real `localhost:7233` with `_connect_or_skip`, following `orchestration/tests/test_pipeline_workflow.py`. No `WorkflowEnvironment.start_time_skipping()` exists anywhere in the repo. The pool workflow tests use a per-test `CREDENTIAL_POOL_ID`. Exhaustion expiry is tested in the pure `select_seat` with an injected `now`, not through workflow time skipping.
