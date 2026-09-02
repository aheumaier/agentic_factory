# Agent Factory (pilot, self-hosted)

Local scaffold implementing the 8-layer pipeline defined in
[`agent-factory-architecture.md`](./agent-factory-architecture.md), sized per
[`~/.claude/plans/what-woud-be-the-quirky-gray.md`](/Users/aheumaier/.claude/plans/what-woud-be-the-quirky-gray.md)
(pilot, 1-5 agents, self-host OSS everywhere except E2B/Braintrust, which have
no self-host tier and run on their free plans at this volume).

## Layer -> directory

| Layer | Dir | Building block |
|---|---|---|
| Spec/Intake | `.specify/` + `specs/` | GitHub Spec Kit (official; old bespoke `spec/` schema/triage-policy retired) |
| Harness/Runtime | `harness/` | Claude Agent SDK (Python) |
| Execution Sandbox | `sandbox/` | E2B |
| Inference Routing | `litellm/` | LiteLLM proxy (self-hosted) |
| Orchestration | `orchestration/` | Temporal (self-hosted) |
| Eval/Gating | `eval/` | Braintrust + Langfuse |
| Deployment/Lifecycle | `registry/` | git-backed catalog + CI gate |
| Observability | `observability/` | Langfuse (self-hosted) |

## Local infra

```
cp .env.example .env   # fill in ANTHROPIC_API_KEY etc.
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
