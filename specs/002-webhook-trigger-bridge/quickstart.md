# Quickstart: Webhook Trigger Bridge

## Prerequisites

- `make up` already run (Temporal reachable at `localhost:7233`).
- **Register the `TargetRepo`/`PRNumber` custom search attributes** (one
  time per namespace — required for gate-comment routing, T004):
  `temporal operator search-attribute create --name TargetRepo --type Keyword`
  and `temporal operator search-attribute create --name PRNumber --type Int`.
- `GH_WEBHOOK_SECRET` set (shared secret configured on the `swe-agent`
  GitHub App's webhook settings — same App as `SWE_AGENT_APP_ID`).
- `WEBHOOK_PROXY_URL` set to a `smee.io/<channel>` URL, and that channel
  configured as the App's webhook URL, subscribed to `issue_comment`.
  **Treat this URL as a secret** — smee.io channels are public and
  unauthenticated for reads (research.md).
- `SWE_AGENT_APP_ID` and `SWE_AGENT_APP_PRIVATE_KEY` set (same App as
  above, private key **base64-encoded PEM**) — used to mint the
  installation token for both the permission-level check and the
  branch/fork-check API call (research.md).
- `BRIDGE_ALLOWED_REPOS` set to a comma-separated `owner/repo` allowlist
  including the target repo (FR-014). **Until `specs/005-pipeline-mode-signals-escalation`
  ships its signal handlers, this MUST be a disposable/test repo, never
  a real target repo** (FR-016) — `AgentPipelineWorkflow.run` has no
  human gate today, so a real repo here means any allowlisted
  commenter's run comment triggers an unsupervised build-and-register.
- The commenter account used below must actually have `write` or `admin`
  permission on the repo (or be its `OWNER`) — `author_association`
  alone is no longer sufficient (FR-003).
- `orchestration/`'s own env (`uv sync --directory orchestration`, or
  equivalent) — the bridge is part of that package, not the repo root.

## Run

```
make bridge   # runs `npx smee-client --url "$WEBHOOK_PROXY_URL" \
              #   --target "http://localhost:${BRIDGE_PORT:-3000}/webhook"`
              # and the bridge server, as sibling processes
```

The bridge refuses to start if `GH_WEBHOOK_SECRET` is empty/unset, or if
it cannot connect to Temporal at startup (fail closed in both cases).

## Validate — User Story 1 (start a run)

1. On a target-repo PR (a disposable/test repo per the prerequisites
   above) with no in-flight run for `agent=widget-export version=3`,
   comment: `@pipeline-agent run mode=full agent=widget-export version=3`
   (note: `version` is a bare number, no `v` prefix — the workflow-ID
   template supplies the `v`).
2. Expect: bridge logs show a `start_workflow` call issued with
   `id="pipeline/<owner>/<repo>/widget-export/v3"` and
   `search_attributes={"TargetRepo": ["<owner>/<repo>"], "PRNumber": [<pr_number>]}`
   (see `contracts/temporal-call-contract.md`). Confirm via Temporal UI
   (`localhost:8080`) that the workflow is running, and a 🚀 reaction
   appears on the comment.
3. Post the identical comment again (simulating a GitHub redelivery with
   the same `X-GitHub-Delivery`, or a genuine second comment). Expect: no
   second workflow start — bridge log shows the dedup path taken: a
   `outcome="duplicate_ignored"` line on a `DeliveryCache.reserve()` miss
   (no second reaction posted for this case), or `WorkflowAlreadyStartedError`
   caught on a cache miss (e.g. after a bridge restart).

## Validate — User Story 2 (gate signal routing)

With the run from above still active (note: no `@workflow.signal`
handler exists on `AgentPipelineWorkflow` until
`specs/005-pipeline-mode-signals-escalation` lands — this validates the
bridge's own resolution and call, not workflow advancement):

1. Comment `pm_approved` on the same PR. Expect: bridge log shows the
   `list_workflows` query resolving to the one workflow tagged with this
   PR's `TargetRepo`/`PRNumber`, then the bare `handle.signal("pm_approved")`
   (no payload argument) issued against `pipeline/<owner>/<repo>/widget-export/v3`,
   `outcome="signal_issued_no_handler"` (no `@workflow.signal` handler
   exists until 005 lands), and a 👀 reaction posted on the comment.
2. Comment `plan_rejected: use candidate C's approach` on the same PR.
   Expect: bridge log shows `handle.signal("plan_rejected", "use
   candidate C's approach")` and the same 👀 reaction.
3. Start a second run for a different `agent_name`/`version` **on a
   different PR** (the search-attribute resolution is keyed on `repo` +
   PR number, not `agent_name`/`version` — a gate comment never carries
   those); post a gate comment on the first PR only. Expect: only the
   first run's workflow ID appears in the signal call log — the second
   run's ID never appears, because the `list_workflows` query is scoped
   to the first PR's number.
4. Comment a gate keyword on a PR with no matching in-flight run.
   Expect: the `list_workflows` query returns zero matches,
   `outcome="signal_failed"` log entry, and a 😕 reaction on the comment,
   no crash.

## Validate — User Story 3 (rejection paths)

1. From an account whose repo permission is `read` (or lower) and whose
   `author_association` is not `OWNER`, comment
   `@pipeline-agent run mode=full agent=x version=1`. Expect: `202`
   response, structured log entry with `outcome="permission_denied"`, a
   😕 reaction on the comment, no `start_workflow` call.
2. Send a webhook payload with a deliberately wrong
   `X-Hub-Signature-256`. Expect: `401` response, no logging of comment
   content (signature check happens before body is parsed at all).
3. Comment `this looks great, pm_approved of it I think` (gate keyword
   inside prose, not a standalone command). Expect: `202`, log entry with
   `outcome="malformed"`, no signal call, no reaction (no confidently
   recognized command to attribute one to).
4. Post a run comment on a fork PR (`isCrossRepository: true`). Expect:
   `202`, log entry with `outcome="fork_rejected"`, a 😕 reaction, no
   `start_workflow` call.
5. Post a run comment on a PR belonging to a repo not in
   `BRIDGE_ALLOWED_REPOS` (try a case/whitespace variant of an allowed
   entry too — it MUST still be treated as allowed). Expect for a
   genuinely disallowed repo: `202`, log entry with
   `outcome="repo_not_allowed"`, no branch-resolution API call and no
   `start_workflow` call.
6. Post `@pipeline-agent run mode=vibe agent=x version=1`. Expect: `202`,
   log entry with `outcome="mode_not_supported"`, a 😕 reaction, no run
   started (pre-005 — `vibe` mode has no relaxed-rigor path to run yet).

## Tests

```
uv run --directory orchestration pytest webhook_bridge/
```

(`--directory` already changes into `orchestration/`, so the path is
`webhook_bridge/`, not `orchestration/webhook_bridge/`.)

Unit-level: HMAC verification, permission-level authorization (mocked
`github_client`), grammar parsing (research.md's order-insensitive
rule), repo-allowlist normalization, reserve-before-dispatch dedup
cache, audit-log/reaction outcome mapping. Contract-level: mocked
Temporal client asserts the exact `start_workflow`/`list_workflows`/
`signal` call shapes from `contracts/temporal-call-contract.md`.
Integration-level: one test against a real local Temporal instance
(`make up`), exercising the actual SDK surface rather than a mock.
