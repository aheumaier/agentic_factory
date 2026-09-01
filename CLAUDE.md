# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A **skeleton** implementation of an "agent factory" — a pipeline that turns an
agent spec into a deployed, versioned, monitored agent, repeatably. It is not
itself an agent. The design rationale lives in two docs that every layer's
code defers to instead of re-arguing:

- `agent-factory-architecture.md` — the 8-layer factory design, building-block
  choices per layer, and why each was picked (buy vs. assemble-only per layer).
- `agent-swe-design.md` — one example factory *output*: a spec for a
  Claude-Agent-SDK software-engineer agent that consumes the factory's layers.

Nothing here is wired end-to-end. Each layer directory is a scaffold with
`TODO`s; see the layer table below for what's real vs. stub.

## Layer -> directory (matches README.md)

| Layer | Dir | Building block | State |
|---|---|---|---|
| Spec/Intake | `spec/` | JSON Schema + triage policy | Schema + policy written; enforced only by `tests/test_agent_spec_schema.py` (template/schema key drift), no runtime intake enforcement |
| Harness/Runtime | `harness/template-agent/` | Claude Agent SDK (Python) | `agent.py` is a stub `query()` call, no tool binding |
| Harness/Runtime | `harness/swe-agent/` | Claude Agent SDK (Python) + Spec Kit | Real, implement-only agent: runs `/speckit-implement` on a pre-planned feature branch, commits, pushes, opens a PR. Registered in `registry/agents/swe-agent/`. See its `SKILL.md` for deferred scope |
| Execution Sandbox | `sandbox/` | E2B | Dockerfile + `e2b.toml`, not invoked by anything yet — `swe-agent` runs unsandboxed in a host tempdir instead |
| Inference Routing | `litellm/` | LiteLLM proxy (self-hosted) | Runnable via docker-compose, one `claude-sonnet` route configured; not used by `swe-agent` (goes direct to Anthropic, see below) |
| Orchestration | `orchestration/` | Temporal (self-hosted) | Worker connects and registers a workflow; workflow body raises `NotImplementedError` |
| Eval/Gating | `eval/` | Braintrust + Langfuse | `eval.config.py` functions all raise `NotImplementedError`; `gate-policy.md` defines the threshold; `swe-agent`'s manifest hardcodes `eval_gate_passed: false` |
| Deployment/Lifecycle | `registry/` | git-backed catalog + CI gate | CI check (`registry-gate.yml`) works; `registry/agents/swe-agent/` is the one real entry (`status: experimental`, `requires_human_supervision: true`) |
| Observability | `observability/` | Langfuse (self-hosted) | Just env template; Langfuse itself runs via docker-compose |

When implementing a layer, wire it per that layer's section in
`agent-factory-architecture.md` §3.x — the doc's rationale, not local
convenience, decides the building block.

## Commands

```
cp .env.example .env      # fill in ANTHROPIC_API_KEY, BRAINTRUST_API_KEY, E2B_API_KEY, etc.
make up                   # docker compose up -d: temporal, temporal-ui, postgres x2, clickhouse, langfuse, litellm
make down                 # docker compose down
make logs                 # docker compose logs -f
make worker                # runs orchestration/worker.py (Temporal worker; requires `make up` first)
make gate                  # runs eval/braintrust/eval.config.py (currently raises — not wired)
uv run pytest              # run the repo-root test suite (tests/), from root pyproject.toml + uv.lock
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
  `registry/agents/` has a `manifest.yaml` and a non-empty `versions/`.
- **Spec triage is a versioned policy, not reviewer judgment** — see
  `spec/triage-policy.md` for the auto-approve / escalate / reject rules an
  agent spec (`spec/schema/agent-spec.schema.json`) must satisfy.
- **Model calls never take a provider key directly** — they route through
  the LiteLLM proxy (`litellm/config.yaml`), keyed by `LITELLM_MASTER_KEY`.
  `harness/template-agent/agent.py` and any new agent should follow the same
  pattern (`LITELLM_BASE_URL` env var), not read `ANTHROPIC_API_KEY` itself.
- **The pipeline's own sequencing is a Temporal workflow**
  (`orchestration/workflows/pipeline_workflow.py`), separate from any
  individual agent's task loop. Don't conflate the two: the workflow
  sequences *spec -> build -> sandbox -> gate -> register -> deploy ->
  monitor*; an agent's own plan/tool-call/observe loop runs inside the Build
  and Sandbox Test steps via the Claude Agent SDK.
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
- **`harness/swe-agent` is a real, runnable agent, not a stub** — it's the
  one entry in `registry/agents/`. It starts at `/speckit-implement`
  (spec/plan/tasks are done upstream, manually), runs unsandboxed in a
  host tempdir, goes direct-to-Anthropic (not LiteLLM-routed), and reuses
  the host's already-authenticated `gh` CLI. Its manifest marks
  `status: experimental` and `requires_human_supervision: true` — treat
  every run as supervised, not autonomous, per its `SKILL.md`'s "Known
  gap" section.
