# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A **skeleton** implementation of a two-tier system, and the two tiers are not
the same thing:

- **The product: a software-engineering SDLC pipeline.** Temporal-orchestrated,
  driven entirely through a GitHub App (issues, PR comments — no bespoke UI,
  no direct Temporal call), taking a spec through PM review → architecture →
  build → quality/security gates → register. Its unit of output is a
  **merged pull request** in a target repo, not a deployed agent. This is
  what the repo is actually for; see `docs/70-multi-agent-pipeline-design.md`.
- **The foundation: the "agent factory."** An 8-layer pipeline that turns an
  agent spec into a deployed, versioned, monitored *agent worker* —
  repeatably. It is not itself an agent, and it is not the SDLC pipeline
  above; it's how that pipeline's own workers (`swe-agent`, `pm-agent`, the
  planned `architect-agent`) get built and shipped in the first place.

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
| Spec/Intake          | `.specify/` + `specs/`    | GitHub Spec Kit                      | **Official flow — the old bespoke `spec/` schema/triage-policy design is retired, not supported.** `/speckit-specify` → `/speckit-plan` → `/speckit-tasks` produce `specs/NNN-slug/`; enforced at runtime by `swe-agent`'s `verify_spec_exists()`. `tests/test_agent_spec_schema.py` still tests the deleted `spec/` schema and fails unconditionally — cleanup candidate, pending deletion                                                                                           |
| Harness/Runtime      | `harness/template-agent/` | Claude Agent SDK (Python)            | `agent.py` is a stub `query()` call, no tool binding                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Harness/Runtime      | `harness/swe-agent/`      | Claude Agent SDK (Python) + Spec Kit | Real, implement-only agent: runs `/speckit-implement` on a pre-planned feature branch, commits, pushes, opens a PR. Registered in `registry/agents/swe-agent/`. See its `SKILL.md` for deferred scope                                                                                                                                                                                                                                                                                 |
| Harness/Runtime      | `harness/pm-agent/`       | Claude Agent SDK (Python)            | Real, two independently callable capabilities in one `agent.py`: `shape_issue()` (zero bound tools, direct-to-Anthropic — target-repo GitHub-hosted runner can't reach the LiteLLM proxy) and `review_spec()` (`Read`/`Grep`/`Glob` only, `setting_sources=[]`, `GH_TOKEN`/`GITHUB_TOKEN` popped from the parent process for the model call, LiteLLM-routed). Registered in `registry/agents/pm-agent/`. See its `SKILL.md` for known gaps (no `pr_url` producer, no Temporal wiring). |
| Harness/Runtime      | `harness/architect-agent/` | Claude Agent SDK (Python)          | Real, one stage entrypoint `run_architect_stage()` (`specs/004-architect-fanout-judge`) sequencing fan-out (N candidates, `Read`/`Grep`/`Glob` only, no cross-candidate visibility, one process-wide credential-scrub window around all model calls since candidates run under `asyncio.gather`) → scoring (SC-NNN coverage map + 1-5 consistency rating, validated in Python) → synthesis (one winner, Python-computed via `pick_winner()`) → an independent completeness-critic (at most one gap round) → persist/push (code-side commit) → one idempotent-per-attempt PR comment. No E2B sandbox for any role (§6.1 carve-out). Registered in `registry/agents/architect-agent/`. See its `SKILL.md` for known gaps (no Temporal wiring, not automatically gated, `MAX_PLAN_ATTEMPTS` not owned here) |
| Execution Sandbox    | `sandbox/`                | E2B                                  | Real, and now the only execution path — both triggers (Temporal's `run_swe_agent_activity` via the `e2b` SDK, and the GitHub-comment path's `.github/workflows/swe-agent-build.yml` via `@e2b/cli`) run `agent.py` inside the `swe-agent-sandbox` template; no host-tempdir path remains                                                                                                                                                                                              |
| Inference Routing    | `litellm/`                | LiteLLM proxy (self-hosted)          | Runnable via docker-compose, two routes configured (`claude-sonnet`, `claude-sonnet-5` — the latter added for the Agent SDK CLI's default model-id lookup); not used by `swe-agent` (goes direct to Anthropic, see below) — a documented-by-omission deviation, not a stub                                                                                                                                                                                                                                                                                                     |
| Orchestration        | `orchestration/`          | Temporal (self-hosted)               | Real Build→Eval-Gate→Register loop in `AgentPipelineWorkflow` (`orchestration/workflows/pipeline_workflow.py`), up to `MAX_BUILD_ATTEMPTS=3`, feeding gate failures back as agent feedback. Deploy is a separate, code-complete `RegistryPromotionWaiterWorkflow` (`orchestration/workflows/registry_promotion_waiter.py`) that waits on a `pr_merged` signal — **nothing in this repo starts that workflow or fires the signal yet**, so Deploy is unreachable end-to-end. `orchestration/webhook_bridge/` (specs/002-webhook-trigger-bridge) is real: an aiohttp server that verifies GitHub `issue_comment` webhook deliveries (relayed via `smee-client`, `make bridge`), authorizes by installation-token permission level, parses run/gate PR comments, and issues the matching `start_workflow`/`signal` call against `AgentPipelineWorkflow` by registered name string — it stops at issuing that call; `AgentPipelineWorkflow` itself still has no `mode` param or `@workflow.signal` handlers (that's `specs/005-pipeline-mode-signals-escalation`'s job), so `BRIDGE_ALLOWED_REPOS` MUST stay disposable-repo-only per FR-016 until 005 ships. `specs/006-quality-gate` and `specs/007-automated-security-review` (both Draft, spec.md only) would add further blocking stages after Eval-Gate — no `quality_gate_activity` or review-stage wiring exists in `activities.py`/`pipeline_workflow.py` yet. Once 004-007 land, the workflow's intended terminus is a **merged target-repo PR**, not a registry entry — today it still ends every run in `register_activity` (writes `registry/agents/<agent_name>/manifest.yaml`), which is the *foundation* tier's terminus grafted onto a run whose real output is a shipped feature; known mismatch, not yet fixed in code |
| Eval/Gating          | `eval/`                   | Braintrust + Langfuse                | `eval.config.py::run_eval` is a real v1 **binary coverage gate** (sandbox exit 0 + PR opened + ≥1 `SC-NNN` criterion found in the branch's `specs/*/spec.md`) — it does not yet score any criterion's content. `gate-policy.md` defines the eventual threshold. Runs only as a Temporal activity (`eval_gate_activity`); its own `__main__` still refuses to run standalone                                                                                                           |
| Deployment/Lifecycle | `registry/`               | git-backed catalog + CI gate         | CI check (`registry-gate.yml`) works. Register is automated: `register_activity` opens a factory-repo PR writing `manifest.yaml`/`versions/<version>.yaml` from the real gate result. `registry/agents/{swe-agent,pm-agent}/` are the two entries; swe-agent's checked-in `manifest.yaml` (`status: experimental`, `eval_gate_passed: false`, `requires_human_supervision: true`) predates this automation and was hand-written                                                                         |
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
uv run pytest              # run the repo-root test suite (tests/), from root pyproject.toml + uv.lock
cd orchestration && uv run pytest   # separate suite: orchestration/webhook_bridge/tests/, from orchestration/pyproject.toml + uv.lock — NOT covered by the root `uv run pytest`
```

The root `pyproject.toml`/`uv.lock` is dev/test tooling only (`pytest`,
`pyyaml`) for the repo root — it is not a package meant to be installed.
Each agent under `harness/<agent>/` has its own separate `pyproject.toml`
for its own runtime deps (e.g. `harness/swe-agent/pyproject.toml` declares
just `claude-agent-sdk`); don't conflate the two when adding a dependency —
add runtime deps to the agent's own file, test/dev tooling to the root one.

No linter is configured yet.

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
  PRs touching `registry/**` or `spec/**`) that every dir under
  `registry/agents/` has a `manifest.yaml` and a non-empty `versions/`. The
  `spec/**` half of that path filter is stale — `spec/` no longer exists;
  left as a follow-up, not fixed in this pass.
- **Spec/Intake is Spec Kit, full stop.** The old bespoke `spec/`
  schema + `triage-policy.md` design is retired — don't resurrect it or
  point anyone at it. See "Feature work in this repo is planned with
  GitHub Spec Kit" below for the actual, in-use flow.
- **Model calls never take a provider key directly** — they route through
  the LiteLLM proxy (`litellm/config.yaml`), keyed by `LITELLM_MASTER_KEY`.
  `harness/template-agent/agent.py` and any new agent should follow the same
  pattern (`LITELLM_BASE_URL` env var), not read `ANTHROPIC_PLATFORM_API_KEY` itself.
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
  + `registry/agents/architect-agent/`, no Temporal wiring and not
  automatically gated, per its `SKILL.md`) → `005-pipeline-mode-signals-escalation`
  (adds the `mode` param, the `@workflow.signal` gate handlers, and
  retry-budget escalation that 002's bridge and 004's own Consumer
  obligations (`contracts/architect-agent-interface.md`'s CO-1..CO-4)
  depend on) → `006-quality-gate` (outcome-traceability + docstring +
  coverage gate) → `007-automated-security-review` (bundled review
  subagents + always-blocking security clearance). `005`-`007` are
  spec.md-only today; don't assume any of their described activities,
  signals, or registry entries exist until their own PR lands.
- **`swe-agent` has two independent trigger paths that diverge in
  capability**: a Temporal `AgentPipelineWorkflow` run gets the full
  Build→Gate→Register loop; the GitHub-comment path
  (`@swe-agent build`, `.github/workflows/swe-agent-build.yml`) only runs
  Build, with no Gate/Register/Deploy of its own. Both now run inside the
  same E2B sandbox template, just via different callers (`e2b` Python SDK
  vs. `@e2b/cli`) with no shared code between them.
- `prompts/agentic-swe.json` is the system-prompt-as-data for the SWE agent
  (`harness/swe-agent/`) designed in `agent-swe-design.md` — treat it as
  that design doc's implementation artifact, keep the two in sync if
  either changes.
- **Feature work in this repo is planned with GitHub Spec Kit
  (`.specify/`), not ad hoc.** `/speckit-specify` → `/speckit-plan` →
  `/speckit-tasks` produce a `specs/NNN-slug/` directory (spec, plan,
  tasks, checklists) *before* any implementation branch exists; only then
  does `/speckit-implement` (or `harness/swe-agent`, which wraps that same
  skill) write code. `specs/001-agent-spec-schema-test/` is the existing
  example. Don't hand-write a feature's code without a matching
  `specs/NNN-slug/` behind it — that directory is what `swe-agent` and any
  human reviewer expect to diff the implementation against.
- **`harness/swe-agent` is a real, runnable agent, not a stub** — one of the
  two entries in `registry/agents/` (alongside `pm-agent`). It starts at `/speckit-implement`
  (spec/plan/tasks are done upstream, manually), runs inside an E2B sandbox
  (not a host tempdir — see the Execution Sandbox row above), goes
  direct-to-Anthropic (not LiteLLM-routed), and authenticates git/`gh` via a
  `GH_TOKEN` env var (GitHub App installation token) when set, falling back
  to the host's ambient `gh` credential helper otherwise. Its manifest
  marks `status: experimental` and `requires_human_supervision: true` —
  treat every run as supervised, not autonomous, per its `SKILL.md`'s "Known
  gap" section.
