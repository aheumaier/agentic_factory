# Agent Factory (pilot, self-hosted)

This repo builds a **software-engineering pipeline**: a Temporal-orchestrated,
multi-agent SDLC process (PM review → architect → build → quality/security
gates → register) that takes a spec and ships a **merged pull request** in a
target repo — driven entirely through a GitHub App, not a bespoke UI or a
direct Temporal call. The "Agent Factory" 8-layer pipeline below is that
process's **foundation**, not its product: it's how the individual agent
workers the pipeline calls at each stage (`swe-agent`, `pm-agent`, and the
planned `architect-agent`) get built, tested, and versioned in the first
place — see [`agent-factory-architecture.md`](./docs/agent-factory-architecture.md)
§1.1 for the full two-tier framing and
[`docs/70-multi-agent-pipeline-design.md`](./docs/70-multi-agent-pipeline-design.md)
for the pipeline itself.

Local scaffold implementing the 8-layer foundation pipeline defined in
[`agent-factory-architecture.md`](./docs/agent-factory-architecture.md), sized per
[`~/.claude/plans/what-woud-be-the-quirky-gray.md`](/Users/aheumaier/.claude/plans/what-woud-be-the-quirky-gray.md)
(pilot, 1-5 agents, self-host OSS everywhere except E2B/Braintrust, which have
no self-host tier and run on their free plans at this volume).

## Layer -> directory

| Layer                | Dir                    | Building block                                                               |
| -------------------- | ---------------------- | ---------------------------------------------------------------------------- |
| Spec/Intake          | `.specify/` + `specs/` | GitHub Spec Kit (official; old bespoke `spec/` schema/triage-policy retired) |
| Harness/Runtime      | `harness/`             | Claude Agent SDK (Python)                                                    |
| Execution Sandbox    | `sandbox/`             | E2B                                                                          |
| Inference Routing    | `litellm/`             | LiteLLM proxy (self-hosted)                                                  |
| Orchestration        | `orchestration/`       | Temporal (self-hosted); `webhook_bridge/` relays GitHub PR comments to `AgentPipelineWorkflow` (specs/002-webhook-trigger-bridge) — real-repo use still blocked on specs/005-pipeline-mode-signals-escalation (Draft, no code) |
| Eval/Gating          | `eval/`                | Braintrust + Langfuse                                                        |
| Deployment/Lifecycle | `registry/`            | git-backed catalog + CI gate                                                 |
| Observability        | `observability/`       | Langfuse (self-hosted)                                                       |

## Local infra

```
cp .env.example .env   # fill in ANTHROPIC_PLATFORM_API_KEY etc.
docker compose up -d   # temporal, postgres, langfuse, clickhouse, litellm
```

## Pipeline (matches §2 of the architecture doc)

```
Spec Kit specs/NNN-slug/ (accepted) -> harness/ (build) -> sandbox/ (test) -> eval/ (gate)
  -> registry/ (register + version) -> deploy -> observability/ (monitor)
  -> registry/ (retire or new version)
```

One path is wired end-to-end for real: a Temporal workflow
(`orchestration/workflows/pipeline_workflow.py`) runs the `swe-agent`
build inside an E2B sandbox, gates it through a v1 Braintrust coverage
check, retries up to 3 times on failure, and opens a registry PR on pass.
Deploy (flipping a registry entry to `active`) is implemented but never
triggered — nothing signals it yet. Everything else remains the skeleton
each layer's integration work lands in; see TODOs in each subdirectory
and [`docs/`](./docs/) (start at [`docs/00-status.md`](./docs/00-status.md))
for the full, file-cited designed-vs-actual breakdown.

Four more pipeline stages exist only as Draft Spec Kit specs (spec.md,
no code): `specs/004-architect-fanout-judge`, `specs/005-pipeline-mode-signals-escalation`,
`specs/006-quality-gate`, `specs/007-automated-security-review` — in that
build order, each depending on the ones before it and on the webhook
bridge above for delivery. See `docs/00-status.md`'s "Planned work"
section for the per-spec breakdown.

Once those land, the pipeline's real terminus is a **merged target-repo
PR** — not a registry entry. Today's `AgentPipelineWorkflow` still ends
every run in `register_activity`, which writes
`registry/agents/<agent_name>/manifest.yaml`; that's the foundation
tier's own terminus (versioning an agent worker), grafted onto a run
whose actual output is a shipped feature in someone else's repo. Known
mismatch, not yet fixed in code — see `agent-factory-architecture.md`
§1.1.
