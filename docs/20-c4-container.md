# C4 Level 2 — Containers

**Scope note:** "the 8 layers" below are the foundation tier
(`agent-factory-architecture.md` §1.1) — containers for building/shipping
agent workers, not the SDLC pipeline that runs them
(`docs/70-multi-agent-pipeline-design.md`), which has no container diagram
here yet.

Two diagrams, deliberately not one: collapsing "designed" and "as built"
into a single diagram at this granularity would either omit the LiteLLM
bypass or bury it in a footnote, and that bypass is one of the most
important facts in this repo right now.

## Diagram A — as designed (`agent-factory-architecture.md` §3.1–§3.8)

All 8 layers, full intended data flow. This diagram shows *intent*, not
status — every container is drawn solid, on purpose. The Spec/Intake box
reflects the *current* design (Spec Kit) — the original bespoke
schema/triage-policy design this box once meant is retired; see
`00-status.md`.

```mermaid
flowchart LR
    subgraph factory["Agent Factory"]
        direction LR
        spec["<<Container>>\nSpec/Intake\n(Spec Kit: .specify/ + specs/)"]
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
        spec["Spec/Intake\n(Spec Kit, official)"]:::real
        harnessT["Harness: template-agent"]:::stub
        harnessS["Harness: swe-agent"]:::real
        ghTrigger["GH Actions:\nswe-agent-build.yml\n(reusable workflow,\nBuild-only, no Gate)"]:::partial
        sandbox["Execution Sandbox\n(E2B)"]:::real
        litellm["Inference Routing\n(LiteLLM proxy)"]:::partial
        orch["Orchestration\n(Build->Gate loop,\nRegister; Deploy\ncode exists, unreachable)"]:::partial
        evalgate["Eval/Gating\n(v1 coverage gate,\nreal; tracing real)"]:::real
        registry["Deployment/Lifecycle\n(Register: real, automated;\nDeploy: unreachable)"]:::partial
        obs["Observability"]:::partial
    end
    anthropic["<<System>>\nAnthropic API"]
    github["<<System>>\nGitHub"]
    braintrust["<<System>>\nBraintrust"]

    spec -->|"human-authored via\n/speckit-specify -> plan -> tasks,\nverify_spec_exists() enforces it"| harnessS
    orch -->|"run_swe_agent_activity"| sandbox
    sandbox -->|"runs agent.py"| harnessS
    github -->|"PR comment\n@swe-agent build"| ghTrigger
    ghTrigger -->|"App token,\ncreate/exec/kill\n(separate from orch)"| sandbox
    harnessS -.->|"designed path\n(not used)"| litellm
    litellm -.->|"designed path\n(not used)"| anthropic
    harnessS -->|"actual: direct SDK call"| anthropic
    harnessS -->|"clone/push/PR"| github
    harnessS -->|"trace emit:\ninit_logger +\nauto_instrument"| evalgate
    orch -->|"eval_gate_activity\n(reads spec.md,\nreads sandbox result)"| evalgate
    evalgate --> braintrust
    evalgate -->|"pass: register_activity\nopens factory-repo PR"| registry
    evalgate -.->|"fail: loop back to Build\n(max 3 attempts)"| orch
    registry -.->|"promote_agent_activity exists;\nnothing starts/signals\nRegistryPromotionWaiterWorkflow"| orch
    registry -.->|"no traces emitted"| obs
    harnessT -.->|"trace emit only;\nno tool bindings"| evalgate

    classDef real fill:#1a7f37,stroke:#1a7f37,color:#fff
    classDef partial fill:#9a6700,stroke:#9a6700,color:#fff,stroke-dasharray: 4 3
    classDef stub fill:#6e7781,stroke:#6e7781,color:#fff,stroke-dasharray: 2 2
    classDef empty fill:#3d3d3d,stroke:#3d3d3d,color:#fff,stroke-dasharray: 1 4
```

**Reading this diagram:** `orch → sandbox → harnessS` is the Temporal
path — Build now always runs inside E2B, never a host tempdir. The
GitHub-comment path (`github → ghTrigger → sandbox → harnessS`) is solid
but *independent* — it drives the same E2B template via its own `@e2b/cli`
calls, not through `orch`, and stops at Build with no Gate/Register/Deploy
of its own. `evalgate` is real for the Temporal path only (coverage gate,
same `BRAINTRUST_PROJECT` as tracing now — the earlier project-name split
is fixed) and feeds `registry`'s Register step, which really does open a
PR on pass. The `registry -.-> orch` edge marks the one genuine dead end:
`promote_agent_activity` and `RegistryPromotionWaiterWorkflow` are written
but nothing ever starts or signals the latter, so Deploy never executes.
See [`00-status.md`](./00-status.md) for the file-level evidence behind
each status color.
