# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A **skeleton** implementation of a two-tier system, and the two tiers are not
the same thing:

- **The product: a software-engineering SDLC pipeline.** Temporal-orchestrated,
  driven through Microsoft Teams (primary, planned — docs/80) and a GitHub
  App (secondary: issues, PR comments) — no direct Temporal call, taking a
  spec through PM review → architecture →
  build → quality/security gates → register. Its unit of output is a
  **merged pull request** in a target repo, not a deployed agent. This is
  what the repo is actually for; see `docs/70-multi-agent-pipeline-design.md`.
- **The foundation: the "agent factory."** An 8-layer pipeline that turns an
  agent spec into a deployed, versioned, monitored *agent worker* —
  repeatably. It is not itself an agent, and it is not the SDLC pipeline
  above; it's how that pipeline's own workers (`swe-agent`, `pm-agent`,
  `architect-agent`) get built and shipped in the first place.

The design rationale lives in two docs that every layer's code defers to
instead of re-arguing:

- `agent-factory-architecture.md` — the 8-layer *foundation* design (§1.1
  states the two-tier split above explicitly), building-block choices per
  layer, and why each was picked (buy vs. assemble-only per layer).
- `agent-swe-design.md` — one example foundation-tier *output*: a spec for a
  Claude-Agent-SDK software-engineer agent that consumes the factory's layers.

Nothing here is wired end-to-end. Each layer directory is a scaffold with
`TODO`s; see the layer table below for what's real vs. stub.

## Layer -> directory (matches README.md)

| Layer                | Dir                       | Building block                       | State                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| -------------------- | ------------------------- | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Spec/Intake          | `.specify/` + `specs/`    | GitHub Spec Kit                      | **Official flow — the old bespoke `spec/` schema/triage-policy design is retired, not supported.** `/speckit-specify` → `/speckit-plan` → `/speckit-tasks` produce `specs/NNN-slug/`; enforced at runtime by `swe-agent`'s `verify_spec_exists()`.                                                                                           |
| Harness/Runtime      | `harness/template-agent/` | Claude Agent SDK (Python)            | `agent.py` is a stub `query()` call, no tool binding                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Harness/Runtime      | `harness/swe-agent/`      | Claude Agent SDK (Python) + Spec Kit | Real, implement-only agent: implements a pre-planned feature branch, one model session per open task (specs/011 F7-a; a Gate-feedback retry, an ID-less task or several task files keep one `/speckit-implement` session), commits, pushes, opens a PR. Registered in `registry/agents/swe-agent/`. See its `SKILL.md` for deferred scope. On the Temporal path it runs on a credential-pool seat (`CLAUDE_CODE_OAUTH_TOKEN`, specs/009-credential-pool-handoff): the harness itself commits a `checkpoint: <task IDs>` each time the model ticks a task `[X]` (specs/011, not left to the model), and on a seat outcome pushes its commits and exits 75 (exhausted) / 77 (invalid), so the next seat resumes from the pushed checkpoint; a successor (`SEAT_HANDOFF_INDEX` > 0) with no task left open skips the "no new commit" check. The sandbox's `GH_TOKEN` is a GitHub App installation token minted per sandbox for the target repo only (contents and pull requests write, metadata read; specs/013-sandbox-app-token), so the agent's PRs are authored by the App's bot and a failed mint fails the run with `SandboxTokenMintFailed`, never falling back to the worker's own `GH_TOKEN`. Internal, single-operator use only (spec.md's Usage Constraint).                                                                                                                                                                                                                                                                                 |
| Harness/Runtime      | `harness/pm-agent/`       | Claude Agent SDK (Python)            | Real, two independently callable capabilities in one `agent.py`: `shape_issue()` (zero bound tools, direct-to-Anthropic — target-repo GitHub-hosted runner can't reach the LiteLLM proxy) and `review_spec()` (`Read`/`Grep`/`Glob` only, `setting_sources=[]`, `GH_TOKEN`/`GITHUB_TOKEN` popped from the parent process for the model call, LiteLLM-routed). Registered in `registry/agents/pm-agent/`. See its `SKILL.md` for known gaps (no `pr_url` producer, no Temporal wiring). |
| Harness/Runtime      | `harness/architect-agent/` | Claude Agent SDK (Python)          | Real, one stage entrypoint `run_architect_stage()` (`specs/004-architect-fanout-judge`) sequencing fan-out (N candidates, `Read`/`Grep`/`Glob` only, no cross-candidate visibility, one process-wide credential-scrub window around all model calls since candidates run under `asyncio.gather`) → scoring (SC-NNN coverage map + 1-5 consistency rating, validated in Python) → synthesis (one winner, Python-computed via `pick_winner()`) → an independent completeness-critic (at most one gap round) → persist/push (code-side commit) → one idempotent-per-attempt PR comment. No E2B sandbox for any role (§6.1 carve-out). Registered in `registry/agents/architect-agent/`. See its `SKILL.md` for known gaps (Temporal-wired as a narrow plan-review slice of feature 005, not automatically gated, `MAX_PLAN_ATTEMPTS` not owned here). On seats (specs/009, `architect_stage_activity`'s `seat_id`) every model call runs direct to Anthropic on that seat's OAuth token; a seat outcome cancels sibling candidates and the whole stage re-runs on another seat. |
| Execution Sandbox    | `sandbox/`                | E2B                                  | Real, and now the only execution path — both triggers (Temporal's `run_swe_agent_activity` via the `e2b` SDK, and the GitHub-comment path's `.github/workflows/swe-agent-build.yml` via `@e2b/cli`) run `agent.py` inside the `swe-agent-sandbox` template; no host-tempdir path remains                                                                                                                                                                                              |
| Inference Routing    | `litellm/`                | LiteLLM proxy (self-hosted)          | Runnable via docker-compose, two routes configured (`claude-sonnet`, `claude-sonnet-5` — the latter added for the Agent SDK CLI's default model-id lookup); not used by `swe-agent` (goes direct to Anthropic, see below) — a documented-by-omission deviation, not a stub. Seat-backed calls (specs/009: Build and the architect stage on Claude Max subscription seats) also go direct to Anthropic — a documented §3.4 deviation, since LiteLLM can forward but not pool or rotate OAuth tokens (specs/009 research R4)                                                                                                                                                                                                                                                                                                     |
| Orchestration        | `orchestration/`          | Temporal (self-hosted)               | Real architect stage → Build→Eval-Gate→Register loop in `AgentPipelineWorkflow` (`orchestration/workflows/pipeline_workflow.py`). The architect stage (`ensure_target_pr_activity` + `architect_stage_activity`, behind `workflow.patched("architect-stage-v1")`) is gated by `plan_approved`/`plan_rejected(feedback)` signals with a `MAX_PLAN_ATTEMPTS=3` budget; Build→Eval-Gate runs up to `MAX_BUILD_ATTEMPTS=3`, feeding gate failures back as agent feedback. Deploy is a separate, code-complete `RegistryPromotionWaiterWorkflow` (`orchestration/workflows/registry_promotion_waiter.py`) that waits on a `pr_merged` signal — **nothing in this repo starts that workflow or fires the signal yet**, so Deploy is unreachable end-to-end. `orchestration/webhook_bridge/` (specs/002-webhook-trigger-bridge) is real: an aiohttp server that verifies GitHub `issue_comment` webhook deliveries (relayed via `smee-client`, `make bridge`), authorizes by installation-token permission level, parses run/gate PR comments, and issues the matching `start_workflow`/`signal` call against `AgentPipelineWorkflow` by registered name string — it stops at issuing that call; `AgentPipelineWorkflow` has the `plan_approved`/`plan_rejected` signal handlers but still no `mode` param, and the rest of `specs/005-pipeline-mode-signals-escalation` is pending, so `BRIDGE_ALLOWED_REPOS` MUST stay disposable-repo-only per FR-016 until 005 ships. `specs/006-quality-gate` and `specs/007-automated-security-review` (both Draft, spec.md only) would add further blocking stages after Eval-Gate — no `quality_gate_activity` or review-stage wiring exists in `activities.py`/`pipeline_workflow.py` yet. Once 004-007 land, the workflow's intended terminus is a **merged target-repo PR**, not a registry entry — today it still ends every run in `register_activity` (writes `registry/agents/<agent_name>/manifest.yaml`), which is the *foundation* tier's terminus grafted onto a run whose real output is a shipped feature; known mismatch, not yet fixed in code. **Credential pool (specs/009-credential-pool-handoff):** a long-lived `CredentialPoolWorkflow` (`orchestration/workflows/credential_pool.py`, ID `credential-pool`, started by the worker) leases Claude Max subscription seats configured in `orchestration/credentials/pool.yaml` (tokens stay in `.env`; only seat IDs reach Temporal). Build and the architect stage run through `_with_seat` under the `seat-pool-v1` patch: a `SeatExhausted`/`SeatInvalid` stage hands off to another seat (up to `MAX_SEAT_HANDOFFS=4`, never charging `MAX_BUILD_ATTEMPTS`/`MAX_PLAN_ATTEMPTS`); no eligible seat fails the run with `CredentialPoolExhausted` (earliest reset in its details), a spent handoff budget with `SeatHandoffsExhausted`, an unreachable pool with `CredentialPoolUnavailable`. The plan loop has its own patch ID, `architect-seat-pool-v1`. **Hardening (specs/011-seat-pool-hardening):** an empty pool waits durably (`workflow.sleep`) for the earliest seat reset when it is ≤ 6 h away, at most twice per stage, under patch `seat-pool-wait-v1`; selection ignores a usage reading once its own window has reset (`utilization_resets_at`); the worker logs a warning at boot for seats within 14 days of `token_expires_on`, and `seats()` shows `expires_in_days`. |
| Eval/Gating          | `eval/`                   | Braintrust + Langfuse                | `eval.config.py::run_eval` is a real v1 **binary coverage gate** (sandbox exit 0 + PR opened + ≥1 `SC-NNN` criterion found in the branch's `specs/*/spec.md`) — it does not yet score any criterion's content. `gate-policy.md` defines the eventual threshold. Runs only as a Temporal activity (`eval_gate_activity`); its own `__main__` still refuses to run standalone                                                                                                           |
| Deployment/Lifecycle | `registry/`               | git-backed catalog + CI gate         | CI check (`registry-gate.yml`) works. Register is automated: `register_activity` opens a factory-repo PR writing `manifest.yaml`/`versions/<version>.yaml` from the real gate result. `registry/agents/{architect-agent,pm-agent,swe-agent}/` are the three entries; swe-agent's checked-in `manifest.yaml` (`status: experimental`, `eval_gate_passed: false`, `requires_human_supervision: true`) predates this automation and was hand-written                                                                         |
| Observability        | `observability/`          | Langfuse (self-hosted)               | Just env template; Langfuse itself runs via docker-compose                                                                                                                                                                                                                                                                                                                                                                                                                            |

When implementing a layer, wire it per that layer's section in
`agent-factory-architecture.md` §3.x — the doc's rationale, not local
convenience, decides the building block.

## Commands

```
cp .env.example .env      # fill in ANTHROPIC_PLATFORM_API_KEY, BRAINTRUST_API_KEY, E2B_API_KEY, etc.
make up                   # docker compose up -d: temporal, temporal-ui, postgres x2, clickhouse, langfuse, litellm
make down                 # docker compose down
make logs                 # docker compose logs -f
make worker                # runs orchestration/worker.py (Temporal worker; requires `make up` first)
make gate                  # runs eval/braintrust/eval.config.py; its __main__ refuses to run standalone — the gate only runs as the Temporal `eval_gate_activity`
make bridge                 # runs the webhook_bridge (specs/002-webhook-trigger-bridge): smee-client relay + aiohttp server as sibling processes; needs GH_WEBHOOK_SECRET, WEBHOOK_PROXY_URL, SWE_AGENT_APP_ID/PRIVATE_KEY in .env
uv run --locked pytest tests/ -q     # run the repo-root test suite (tests/), from root pyproject.toml + uv.lock
cd orchestration && uv run --locked pytest -q   # separate suite: orchestration/tests/ + orchestration/webhook_bridge/tests/, from orchestration/pyproject.toml + uv.lock — NOT covered by the root suite
uv run --locked ruff check .         # lint the whole repo (config: root pyproject.toml [tool.ruff], covers harness/* and orchestration/ too)
cd orchestration && uv run --locked python scripts/seat_smoke.py [SEAT_ENV_VAR]   # live check of one subscription seat (specs/009 quickstart V4): one tiny model call, never prints the token
```

The root `pyproject.toml`/`uv.lock` is dev/test tooling only (`pytest`,
`pyyaml`, `ruff`) for the repo root — it is not a package meant to be installed.
Each agent under `harness/<agent>/` has its own separate `pyproject.toml`
for its own runtime deps (e.g. `harness/swe-agent/pyproject.toml` declares
just `claude-agent-sdk`); don't conflate the two when adding a dependency —
add runtime deps to the agent's own file, test/dev tooling to the root one.

Ruff (`uv run --locked ruff check .`) is the linter; its rule set is pinned in
the root `pyproject.toml`. Keep the baseline at zero. `ruff format` is not
enforced. Every `uv run` in the hooks and in these docs uses `--locked` (the
per-edit lint uses `--frozen`), so nothing rewrites `uv.lock` or
`orchestration/uv.lock`. Before committing a Python change, run the
`py-codereviewer` subagent (`.claude/agents/py-codereviewer.md`) on it.

**Ruff and both pytest suites are enforced by Claude Code hooks**
(`.claude/settings.json` → `.claude/hooks/py-check.sh` and
`.claude/hooks/policy.sh`, feature 010):

- **Per edit** (`PostToolUse`): ruff on the edited `.py` file only. No pytest.
- **Per turn** (`UserPromptSubmit` + `Stop`): at the start of a turn the hook
  snapshots every Python-relevant file (`*.py`, `*pyproject.toml`,
  `*uv.lock`). A snapshot left by an interrupted turn is adopted after
  `/clear`. At `Stop` the tree is diffed against that snapshot. Only if the
  turn changed Python-relevant files (through any tool, shell commands
  included) does it run ruff on the changed `.py` files and both suites. Red
  blocks the stop once with the failures. If it is still red on the retry, the
  turn ends with a notice instead of looping.
- **Per commit** (AF-COMMIT): a Bash command containing `git` and `commit`
  first runs whole-repo ruff and both suites. Red denies the commit.

**Repo rules.** A refusal starts with its rule ID, e.g. `[AF-SPEC] … To
proceed: …`. A permission prompt names its pattern.

| ID | Mechanism | Covers | How to satisfy it |
|---|---|---|---|
| AF-SPEC | `policy.sh` (deny) | Edit/Write/MultiEdit/NotebookEdit under `harness/`, `orchestration/`, `eval/` | Work on a feature branch `NNN-slug` (or `worktree-NNN-slug`) that has `specs/NNN-*/tasks.md` |
| AF-SECRET | `policy.sh` (deny) + `permissions.deny` `Read(/.env)`, `Read(/.env.braintrust)` | Read/Grep/Glob of `.env` or `.env.braintrust` in any directory; a Bash command naming either. `.env.example` is allowed | Read `.env.example` for names; ask the operator for values |
| AF-COMMIT | `policy.sh` (deny) | `git commit` from Bash | Make ruff and both suites green, then commit again |
| AF-REGISTRY | `permissions.ask` `Edit(/registry/agents/*/manifest.yaml)`, `Edit(/registry/agents/*/versions/**)` | Edits to registry manifests and version files | The operator approves the prompt |
| AF-HARNESS | `permissions.ask` `Edit(/.claude/settings.json)`, `Edit(/.claude/settings.local.json)`, `Edit(/.claude/hooks/**)` | Edits to the harness settings and hook scripts | The operator approves the prompt |

The one exception: launch with `AF_SPEC_EXCEPTION="<reason>" claude`. It
lifts AF-SPEC only, for that session, and is announced once. It never lifts
AF-SECRET or AF-COMMIT.

Known gaps, by design:

- Shell writes under `harness/`, `orchestration/` and `eval/` are not checked
  before they run. The `Stop` gate still judges them (FR-013).
- Shell reads of `.env` are denied by pattern match only, best effort. It is
  not a security boundary (FR-016).
- Shell edits to `.claude/settings*.json` and `.claude/hooks/**` are not
  covered (FR-026).
- `permissions.ask` has no human to ask under `bypassPermissions`, as in the
  E2B sandbox, so AF-REGISTRY and AF-HARNESS don't apply there.

Concurrent agent sessions are supported only as **one session per git
worktree** (`claude --worktree` / `EnterWorktree`): the turn gate fingerprints
the working tree, so it can't tell two sessions' edits apart inside one
checkout, and a branch switch by another session shows up as this turn's change.

### Context budget

- **Budget and enforcement.** A session's context budget is 150k tokens, with a
  warning at 120k (`CTX_BUDGET`/`CTX_WARN` in `.claude/hooks/lib.sh`). The cap
  is `env.CLAUDE_CODE_AUTO_COMPACT_WINDOW` in `.claude/settings.json`, which is
  protected by AF-HARNESS. The warning comes from `turn-start`. It is best
  effort, because it reads Claude Code's internal transcript. After `/compact`
  or `/clear`, the `SessionStart(compact|clear)` hook
  (`.claude/hooks/session-context.sh`) tells the new context where to resume.
  On a feature branch with a spec dir, that is the branch, the spec dir, the
  next unchecked tasks, whether a turn snapshot is pending, and the rule IDs.
  Anywhere else it adds nothing.
- **`/clear`** between Spec Kit phases (specify → plan → tasks → implement) and
  after each feature commit. The feature's `specs/NNN-*/` directory on disk is
  the handoff.
- **`/compact <focus>`** only at a task boundary with the gate green. Never
  mid-task, never with the gate red.
- **`tasks.md`**: tick each checkbox as its task finishes.

When compacting, preserve: current task ID, files modified in this task,
failing test IDs, and decisions not yet written to the spec directory.

Service ports (docker-compose): Temporal 7233, Temporal UI 8080, Langfuse
3000, LiteLLM proxy 4000.

## Working in this repo

- **Read the two design docs before adding code to a layer.** Section
  numbers (`§3.4`, etc.) in code comments and other docs refer to
  `agent-factory-architecture.md`; keep that cross-referencing convention —
  it's how a scaffold this thin stays navigable.
- **The registry is the portability boundary.** Per architecture doc §1.4 /
  §3.7, every agent's skill/tool definitions must live in `SKILL.md` /
  MCP-manifest format under `registry/agents/<name>/`, not in a
  vendor-specific format. `.github/workflows/registry-gate.yml` enforces (on
  PRs touching `registry/**`) that every dir under `registry/agents/` has a
  `manifest.yaml` and a non-empty `versions/`.
- **Spec/Intake is Spec Kit, full stop.** The old bespoke `spec/`
  schema + `triage-policy.md` design is retired — don't resurrect it or
  point anyone at it. See "Feature work in this repo is planned with
  GitHub Spec Kit" below for the actual, in-use flow.
- **Model calls never take a provider key directly** — they route through
  the LiteLLM proxy (`litellm/config.yaml`), keyed by `LITELLM_MASTER_KEY`.
  `harness/template-agent/agent.py` and any new agent should follow the same
  pattern (`LITELLM_BASE_URL` env var), not read `ANTHROPIC_PLATFORM_API_KEY` itself.
  Exception: seat-backed calls (specs/009) authenticate with a subscription
  seat's OAuth token direct to Anthropic — see architecture §3.4.
- **The pipeline's own sequencing is a Temporal workflow**
  (`orchestration/workflows/pipeline_workflow.py`), separate from any
  individual agent's task loop. Don't conflate the two: the workflow
  sequences *spec -> build -> sandbox -> gate -> register -> deploy ->
  monitor*; an agent's own plan/tool-call/observe loop runs inside the Build
  and Sandbox Test steps via the Claude Agent SDK.
- **Deploy is its own long-lived workflow, deliberately not part of
  `AgentPipelineWorkflow`** — `RegistryPromotionWaiterWorkflow`
  (`orchestration/workflows/registry_promotion_waiter.py`) waits on a
  `pr_merged` signal (human merges the Register PR, an SLA of days/weeks
  vs. Build/Gate's minutes) before flipping the registry entry to active.
  Nothing currently starts this workflow or signals it — wiring that
  (e.g. a GH Actions step on PR merge) is open work, not a bug in the
  workflow itself.
- **This build order is the SDLC-pipeline product tier, not a side
  extension of the foundation.** Per "What this repo is" above and
  `docs/70-multi-agent-pipeline-design.md` (now the primary product
  narrative, per its own status line), specs 004-007 are what turn today's
  Build→Gate→Register loop into the actual multi-agent SDLC pipeline this
  repo exists to build. Build order after `003-pm-agent-review-gate`
  (done): `004-architect-fanout-judge` (done — fan out N candidate plans
  from distinct stated angles, score + synthesize one winner,
  completeness-critic gap-checks once; `harness/architect-agent/agent.py`
  + `registry/agents/architect-agent/`, Temporal-wired via 005's narrow
  plan-review slice and not automatically gated, per its `SKILL.md`) →
  `005-pipeline-mode-signals-escalation`
  (adds the `mode` param, the `@workflow.signal` gate handlers, and
  retry-budget escalation that 002's bridge and 004's own Consumer
  obligations (`contracts/architect-agent-interface.md`'s CO-1..CO-4)
  depend on) → `006-quality-gate` (outcome-traceability + docstring +
  coverage gate) → `007-automated-security-review` (bundled review
  subagents + always-blocking security clearance). `005` is partially
  implemented (the narrow architect plan-review slice: the
  `plan_approved`/`plan_rejected` signals and `MAX_PLAN_ATTEMPTS`, but no
  `mode` param, no PM-stage wiring, no security signal, and budget
  exhaustion still raises a bare `ApplicationError` rather than the
  escalation pair); `006`-`007` are spec.md-only today. Don't assume any
  of their remaining described activities, signals, or registry entries
  exist until their own PR lands. Outside that product sequence: features
  009 (credential-pool handoff) and 011 (seat-pool hardening) are merged;
  `specs/008-gate-decision-core/` is Draft (spec only); feature 010
  (dev-harness hardening) is in flight.
- **`swe-agent` has two independent trigger paths that diverge in
  capability**: a Temporal `AgentPipelineWorkflow` run gets the full
  Build→Gate→Register loop; the GitHub-comment path
  (`@swe-agent build`, `.github/workflows/swe-agent-build.yml`) only runs
  Build, with no Gate/Register/Deploy of its own. Both now run inside the
  same E2B sandbox template, just via different callers (`e2b` Python SDK
  vs. `@e2b/cli`) with no shared code between them.
- `.github/workflows/` also has `swe-agent-trigger.yml` — a ~10-line
  `issue_comment` caller wrapper every opted-in repo copies, which calls
  `swe-agent-build.yml` as a reusable workflow (`uses:`) — and the same
  caller/reusable-workflow split for `pm-agent`'s `shape_issue()`
  capability: `pm-agent-shape-trigger.yml` calls `pm-agent-shape.yml`.
  Both pairs exist so a target repo only ever copies the trigger file;
  all real logic stays in this repo's reusable workflow.
- `prompts/agentic-swe.json` is the system-prompt-as-data for the SWE agent
  (`harness/swe-agent/`) designed in `agent-swe-design.md` — treat it as
  that design doc's implementation artifact, keep the two in sync if
  either changes.
- **Feature work in this repo is planned with GitHub Spec Kit
  (`.specify/`), not ad hoc.** `/speckit-specify` → `/speckit-plan` →
  `/speckit-tasks` produce a `specs/NNN-slug/` directory (spec, plan,
  tasks, checklists) *before* any implementation branch exists; only then
  does `/speckit-implement` (or `harness/swe-agent`, which wraps that same
  skill) write code. `specs/004-architect-fanout-judge/` is a complete
  example (spec, plan, research, contracts, tasks). Don't hand-write a feature's code without a matching
  `specs/NNN-slug/` behind it — that directory is what `swe-agent` and any
  human reviewer expect to diff the implementation against.
- **`harness/swe-agent` is a real, runnable agent, not a stub** — one of the
  three entries in `registry/agents/` (alongside `pm-agent` and `architect-agent`). It starts at `/speckit-implement`
  (spec/plan/tasks are done upstream, manually), runs inside an E2B sandbox
  (not a host tempdir — see the Execution Sandbox row above), goes
  direct-to-Anthropic (not LiteLLM-routed), and authenticates git/`gh` via a
  `GH_TOKEN` env var (GitHub App installation token) when set, falling back
  to the host's ambient `gh` credential helper otherwise. On the Temporal
  path the worker mints that token per sandbox, for the target repo only
  (specs/013-sandbox-app-token). Its manifest
  marks `status: experimental` and `requires_human_supervision: true` —
  treat every run as supervised, not autonomous, per its `SKILL.md`'s "Known
  gap" section.
