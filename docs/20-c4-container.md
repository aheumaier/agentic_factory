# C4 Level 2 — Containers

Two diagrams, deliberately not one: collapsing "designed" and "as built"
into a single diagram at this granularity would either omit the LiteLLM
bypass or bury it in a footnote, and that bypass is one of the most
important facts in this repo right now.

## Diagram A — as designed (`agent-factory-architecture.md` §3.1–§3.8)

All 8 layers, full intended data flow. This diagram shows *intent*, not
status — every container is drawn solid, on purpose.

```mermaid
flowchart LR
    subgraph factory["Agent Factory"]
        direction LR
        spec["<<Container>>\nSpec/Intake\n(spec/)"]
        harness["<<Container>>\nHarness/Runtime\n(harness/)"]
        sandbox["<<Container>>\nExecution Sandbox\n(sandbox/, E2B)"]
        litellm["<<Container>>\nInference Routing\n(litellm/, LiteLLM proxy)"]
        orch["<<Container>>\nOrchestration\n(orchestration/, Temporal)"]
        evalgate["<<Container>>\nEval/Gating\n(eval/, Braintrust)"]
        registry["<<Container>>\nDeployment/Lifecycle\n(registry/, git + CI gate)"]
        obs["<<Container>>\nObservability\n(observability/, Langfuse)"]
    end
    anthropic["<<System>>\nAnthropic API"]

    spec --> harness
    harness --> sandbox
    sandbox --> evalgate
    evalgate -->|"pass"| registry
    evalgate -.->|"fail: back to Build"| harness
    registry --> obs
    orch --- spec
    orch --- harness
    orch --- sandbox
    orch --- evalgate
    orch --- registry
    harness --> litellm
    sandbox --> litellm
    litellm --> anthropic
    obs -.->|"scores feed back"| evalgate
```

## Diagram B — as built (status-colored)

Same 8 containers; color and edge shape now reflect what actually runs.
**The LiteLLM edge is deliberately drawn twice** — the designed path
(dashed, through the proxy) and the actual path (solid, direct to
Anthropic) — because this single deviation contradicts a convention
`CLAUDE.md` states explicitly ("model calls never take a provider key
directly").

```mermaid
flowchart LR
    subgraph factory["Agent Factory — as built"]
        direction LR
        spec["Spec/Intake"]:::partial
        harnessT["Harness: template-agent"]:::stub
        harnessS["Harness: swe-agent"]:::real
        sandbox["Execution Sandbox"]:::stub
        litellm["Inference Routing\n(LiteLLM proxy)"]:::partial
        orch["Orchestration\n(Build step only)"]:::partial
        evalgate["Eval/Gating"]:::stub
        registry["Deployment/Lifecycle\n(CI gate real,\nno auto-registration)"]:::partial
        obs["Observability"]:::partial
    end
    anthropic["<<System>>\nAnthropic API"]
    github["<<System>>\nGitHub"]

    spec -.->|"manual today"| harnessS
    orch -->|"run_swe_agent_activity"| harnessS
    harnessS -.->|"designed path\n(not used)"| litellm
    litellm -.->|"designed path\n(not used)"| anthropic
    harnessS -->|"actual: direct SDK call"| anthropic
    harnessS -->|"clone/push/PR"| github
    harnessS -.->|"never invoked"| sandbox
    harnessS -.->|"never invoked"| evalgate
    evalgate -.->|"stub: no scoring code"| registry
    registry -.->|"no traces emitted"| obs
    harnessT -.->|"builds into\nsandbox/Dockerfile,\nnever run"| sandbox

    classDef real fill:#1a7f37,stroke:#1a7f37,color:#fff
    classDef partial fill:#9a6700,stroke:#9a6700,color:#fff,stroke-dasharray: 4 3
    classDef stub fill:#6e7781,stroke:#6e7781,color:#fff,stroke-dasharray: 2 2
```

**Reading this diagram:** the only solid, unconditional edges in the "as
built" view are `orch → harnessS`, `harnessS → anthropic` (direct), and
`harnessS → github`. Everything else is either manual, unused, or
one-directional-and-incomplete. See [`00-status.md`](./00-status.md) for
the file-level evidence behind each status color.
