# Contract: GitHub → bridge HTTP interface

## `POST /webhook`

**Request** (GitHub `issue_comment` webhook delivery):

| Header | Required | Notes |
|---|---|---|
| `X-Hub-Signature-256` | yes | `sha256=<hex hmac>` over the exact raw body, keyed by `GH_WEBHOOK_SECRET` |
| `X-GitHub-Delivery` | yes | UUID, dedup key. Missing entirely → `202`, `outcome="malformed"` — never passed to `DeliveryCache` (undefined for a missing key) |
| `X-GitHub-Event` | yes | Only `issue_comment` is processed; any other value → `202 Accepted`, no-op, no audit log (not this bridge's event) |

Body: GitHub's `issue_comment` (created) JSON payload. The server MUST
bound the accepted body size (aiohttp `client_max_size`, e.g. 1MB) —
HMAC verification requires buffering the full raw body before any
validation can occur, so an unbounded body is a free memory-exhaustion
vector even behind loopback-only bind.

**Response codes** (bridge → smee.io/relay client, not directly to
GitHub): under the current smee.io-relay deployment, GitHub only ever
sees the relay edge's own `200` — it has no visibility into these codes
at all, and none of the retry semantics implied below actually reach
GitHub's delivery UI or redelivery logic today (see research.md's
best-effort-delivery decision). This table documents the codes the bridge
itself returns to whatever is calling it directly (the local
`smee-client` relay leg, and any future migration off smee.io to a
directly-addressed webhook endpoint, where GitHub would then be the
caller and would act on these codes):

| Status | Condition |
|---|---|
| `401` | Signature missing or does not verify (FR-002) — body/comment MUST NOT be parsed before this check |
| `202` | Any other outcome: wrong event type, `action != "created"`, not a PR comment, unauthorized author, unrecognized grammar, duplicate delivery, or a recognized command was successfully dispatched. GitHub only distinguishes 2xx (delivered) from non-2xx (retry); this bridge deliberately returns the same success code for "acted" and "ignored" so no internal detail leaks into GitHub's retry/delivery UI beyond the bridge's own logs (FR-011/FR-012 cover *why*, via logs, not via HTTP status). |
| `500` | Unexpected internal error (e.g. Temporal unreachable) — not visible to GitHub under the current smee.io relay (see above); only meaningful for a direct-to-GitHub deployment |

## Environment

| Var | Required | Used for |
|---|---|---|
| `GH_WEBHOOK_SECRET` | yes | HMAC verification; server MUST refuse to start if unset/empty (fail closed) |
| `WEBHOOK_PROXY_URL` | yes (dev) | `smee-client` relay target; the bridge itself just binds a local port — `smee-client` is the process that reads this var to know where to relay *from*. **Treat as a secret** — a smee.io-style channel is public/unauthenticated for reads; anyone with this URL can read every relayed delivery in full (research.md's confidentiality addendum) |
| `BRIDGE_PORT` | no (default `3000`, matching `WEBHOOK_PROXY_URL`/smee convention) | local bind port for `/webhook`; bound to `127.0.0.1` only, never all interfaces |
| `SWE_AGENT_APP_ID` | yes | GitHub App ID, for minting the installation token (research.md) |
| `SWE_AGENT_APP_PRIVATE_KEY` | yes | GitHub App private key, **base64-encoded PEM** (decode before use) — chosen over literal multi-line/`\n`-escaped PEM to avoid `.env`/shell quoting ambiguity (research.md); never logged |
| `BRIDGE_ALLOWED_REPOS` | yes | Comma-separated `owner/repo` allowlist, matched case-insensitively with entries trimmed of surrounding whitespace (FR-014). MUST list only a disposable/test repository until `specs/005-pipeline-mode-signals-escalation` ships its signal handlers — see FR-016 |

`make bridge` runs both `npx smee-client --url "$WEBHOOK_PROXY_URL" --target
"http://localhost:$BRIDGE_PORT/webhook"` and the bridge server as sibling
processes, with a `trap`/`wait` so a dead `smee-client` leg exits the
target non-zero instead of leaving the bridge orphaned and silently
unreachable.

**Temporal server prerequisite**: `TargetRepo` (`Keyword`) and
`PRNumber` (`Int`) custom search attributes must be registered once per
namespace (`temporal operator search-attribute create ...`) before the
bridge can tag runs or resolve gate-command targets (data-model.md's
`GateTargetResolution`, quickstart.md).
</content>
