# Implementation Plan: Webhook Trigger Bridge

**Branch**: `002-webhook-trigger-bridge` | **Date**: 2026-09-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-webhook-trigger-bridge/spec.md`

## Summary

Add `orchestration/webhook_bridge/`: a persistent local HTTP server that
receives GitHub `issue_comment` webhook deliveries (relayed via
`smee-client` from `WEBHOOK_PROXY_URL`), verifies each delivery's
`X-Hub-Signature-256` HMAC, enforces the same `author_association`
allowlist `swe-agent-build.yml` enforces today, parses PR comments into
either a run command (`@pipeline-agent run mode=<full|vibe>
agent=<name> version=<version>`) or one of six gate-decision commands,
and issues the corresponding Temporal call — `start_workflow` (with
`WorkflowAlreadyStartedError`-based dedup) or `get_workflow_handle(...).signal(...)`
— against `AgentPipelineWorkflow`, connecting to Temporal exactly as
`orchestration/worker.py` does. A `make bridge` target runs the smee
relay and the bridge server together.

**Scope boundary** (confirmed by reading all of `run()`, not just
grepping: no `@workflow.signal` handlers exist on `AgentPipelineWorkflow`
today, `run()` has no `mode` parameter, and — critically — `run()` has no
`workflow.wait_condition` anywhere, so it executes Build → Eval-Gate →
Register straight through with no human gate at all): this feature stops
at issuing the correctly-shaped Temporal call. Making those signals
actually do anything, adding the pause points, and threading `mode`
through the workflow, is `specs/005-pipeline-mode-signals-escalation/`'s
job — a dependency, not something this plan re-implements.

**Shipping-order constraint (FR-016)**: because `run()` has no gate
today, this bridge MUST NOT be pointed at a real target repository via
`BRIDGE_ALLOWED_REPOS` until 005 ships. Before then, any allowlisted
commenter's run command would trigger an unsupervised build-and-register
run — contradicting `registry/agents/swe-agent/`'s own
`requires_human_supervision: true`. `BRIDGE_ALLOWED_REPOS` is limited to
a disposable/test repo for the duration of this feature's rollout.

## Technical Context

**Language/Version**: Python 3.11+ (matches `orchestration/pyproject.toml`'s `requires-python`)

**Primary Dependencies**: `aiohttp` (new — async HTTP server, matches
`worker.py`'s asyncio shape), `temporalio>=1.32.0` (existing dep, now
version-floor pinned — research.md/H6, matching what `uv.lock` already
resolves), `PyJWT` + `cryptography` (new — sign the GitHub App JWT and
mint an installation token; see research.md), stdlib
`hmac`/`hashlib`/`logging` (no new dep for signature verification or
audit logging)

**Storage**: N/A — in-memory delivery-ID cache only (single persistent
process, not distributed; see research.md)

**Testing**: `pytest` + `pytest-asyncio`, added to
`orchestration/pyproject.toml`'s `dependency-groups.dev` (not the root
`pyproject.toml`, which is scoped to `tests/` per `CLAUDE.md`), with
`[tool.pytest.ini_options] asyncio_mode = "auto"` also added there (no
such section exists in `orchestration/pyproject.toml` today — without
it, async tests error or silently skip); run via
`uv run --directory orchestration pytest webhook_bridge/` (path is
relative to `--directory`, not repeated)

**Target Platform**: Linux/macOS developer laptop — same host as `make up` (local process, no public exposure of its own beyond the smee relay leg)

**Project Type**: Single component (new package inside the existing `orchestration/` project)

**Performance Goals**: Not specified — this is a low-volume, human-comment-triggered endpoint (no throughput target in spec)

**Constraints**: Must not require exposing Temporal's own port publicly (FR-010); must verify signature before any other processing (FR-002); the HTTP server MUST bind loopback-only (`127.0.0.1`), since the smee relay is the only intended path in — GitHub never calls the bridge's port directly; the server MUST fail closed (refuse to start) if `GH_WEBHOOK_SECRET` is empty/unset or if the initial `Client.connect("localhost:7233")` call fails, never fall back to "accept unsigned" or "start anyway, fail per-request"; the aiohttp app MUST bound request body size (`client_max_size`) since HMAC verification requires buffering the full raw body first; the server MUST handle `SIGTERM` gracefully (close the Temporal client, stop accepting new connections) since `make bridge` runs it under a `trap`/`wait`; authorization (FR-003) requires a permission-level check via the installation token, not `author_association` alone

**Scale/Scope**: One process, one HTTP route (`/webhook`), one repo's worth of PR comment traffic

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

N/A — `.specify/memory/constitution.md` is still the unfilled
`[PRINCIPLE_N_NAME]` template (no ratified principles), so there are no
gates to evaluate against. Re-checked after Phase 1: still N/A, template
unchanged.

## Project Structure

### Documentation (this feature)

```text
specs/002-webhook-trigger-bridge/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/            # Phase 1 output
│   ├── webhook-http-contract.md
│   └── temporal-call-contract.md
└── tasks.md              # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
orchestration/
├── pyproject.toml         # add aiohttp, PyJWT, cryptography (runtime), pytest/pytest-asyncio (dev)
├── worker.py              # unchanged
├── activities.py          # unchanged
├── workflows/              # unchanged (owned by 005 for mode/signals)
└── webhook_bridge/          # NEW
    ├── __init__.py
    ├── server.py            # aiohttp app, POST /webhook route, env var wiring, loopback bind, fail-closed secret/Temporal checks, SIGTERM handling
    ├── auth.py              # HMAC verification + installation-token permission-level check (write/admin, or OWNER fast-path)
    ├── grammar.py            # comment -> RunCommand | GateCommand | None (data-model.md), order-insensitive tokens, slug validation
    ├── dedup.py              # in-memory delivery-ID cache, reserve-before-dispatch (mark at check time)
    ├── audit.py               # structured AuditLogEntry logging (own module — avoids a server.py <-> temporal_client.py circular import, research.md/M3)
    ├── temporal_client.py    # start_workflow (with TargetRepo/PRNumber search attrs) / list_workflows resolution / signal calls (temporal-call-contract.md)
    ├── github_app.py         # GitHub App JWT signing + installation-token minting/caching (research.md/A5), reactions POST helper
    └── tests/
        ├── test_auth.py
        ├── test_grammar.py
        ├── test_dedup.py
        ├── test_audit.py
        ├── test_temporal_client.py   # against a fake/mocked Client
        ├── test_github_app.py       # against a mocked HTTP client
        ├── test_server.py           # startup fail-closed/bind, fork/allowlist rejection
        └── test_integration.py       # one real-Temporal test against `make up` (research.md/H6)

Makefile                    # add `bridge` target (smee-client + webhook_bridge.server, sibling processes)
```

**Structure Decision**: Single new package under the existing
`orchestration/` project (own `pyproject.toml` already exists there),
mirroring how `activities.py`/`worker.py` already live flat in that
directory. No new top-level project — this is a component of the
existing Orchestration layer (architecture doc §3.5), not a new layer.

## Complexity Tracking

*No violations — Constitution Check is N/A (unratified template).*
</content>
