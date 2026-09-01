# Agent Factory (pilot, self-hosted)

Local scaffold implementing the 8-layer pipeline defined in
[`agent-factory-architecture.md`](./agent-factory-architecture.md), sized per
[`~/.claude/plans/what-woud-be-the-quirky-gray.md`](/Users/aheumaier/.claude/plans/what-woud-be-the-quirky-gray.md)
(pilot, 1-5 agents, self-host OSS everywhere except E2B/Braintrust, which have
no self-host tier and run on their free plans at this volume).

## Layer -> directory

| Layer | Dir | Building block |
|---|---|---|
| Spec/Intake | `spec/` | bespoke schema + triage policy |
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
spec/ (accepted) -> harness/ (build) -> sandbox/ (test) -> eval/ (gate)
  -> registry/ (register + version) -> deploy -> observability/ (monitor)
  -> registry/ (retire or new version)
```

Nothing here is wired end-to-end yet — this is the skeleton each layer's
integration work lands in. See TODOs in each subdirectory.
