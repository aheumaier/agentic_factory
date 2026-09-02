# C4 Level 1 — System Context

Who and what talks to the Agent Factory from outside its boundary. This
level is nearly identical between "designed" and "actual" — the boundary
itself hasn't shifted, only which internal edges are live has (see
[`20-c4-container.md`](./20-c4-container.md) for that split). Dashed edges
below mark integrations that are configured/built but never actually
called.

```mermaid
flowchart TB
    author["<<Person>>\nSpec Author /\nPlatform Engineer"]:::person
    reviewer["<<Person>>\nHuman Reviewer"]:::person

    subgraph factory["Agent Factory"]
        direction TB
        core["<<System>>\n8-layer pipeline\n(spec -> build -> sandbox -> gate\n-> register -> deploy -> monitor)"]:::real
    end

    github["<<System>>\nGitHub\n(issues, code host, Actions CI)"]:::ext
    anthropic["<<System>>\nAnthropic API\n(model inference)"]:::ext
    e2b["<<System>>\nE2B\n(sandboxed execution)"]:::ext
    braintrust["<<System>>\nBraintrust\n(eval scoring)"]:::ext
    targetrepo["<<System>>\nTarget repositories\n(the codebases being built/fixed)"]:::ext

    author -->|"assigns issue / raises spec"| github
    author -->|"comments\n@swe-agent build\non a PR"| github
    github -->|"actual: PR-comment trigger\n(reusable GH Actions workflow)"| core
    github -.->|"designed: issue assigned,\nfailing CI, or webhook"| core
    core -->|"clone, branch, commit,\npush, open PR"| targetrepo
    core -->|"model inference\n(direct today — see container view)"| anthropic
    core -->|"actual: sandbox test,\nGH-comment path only"| e2b
    core -->|"actual: trace emit\n(braintrust.auto_instrument)"| braintrust
    core -.->|"designed: eval gate\n(scoring code still\nNotImplementedError)"| braintrust
    reviewer -->|"reviews, approves, merges\n(outside factory's control)"| targetrepo
    github -->|"review/CI status"| reviewer

    classDef person fill:#083a5e,stroke:#083a5e,color:#fff
    classDef ext fill:#3d3d3d,stroke:#3d3d3d,color:#fff
    classDef real fill:#1a7f37,stroke:#1a7f37,color:#fff
```

**Reading this diagram:**
- Solid edges are live today. `core --> e2b` is real but conditional — it
  only fires for the GitHub-comment trigger path, not the Temporal one
  (see `00-status.md`). `core --> braintrust` (trace emit) is unconditional
  today, since it's an import-time call in `agent.py`; the dashed
  `core -.-> braintrust` (eval gate) edge is the still-unimplemented
  scoring path — same external system, two different integrations, only
  one of which is real.
- `targetrepo` (the codebase the factory builds/fixes) is drawn as external to the factory itself — it's the factory's actual work product, not part of it.
- The Human Reviewer is a first-class actor, not an edge case: per `agent-swe-design.md` §5/§6, the workflow's terminal state is always "awaiting human," never "merged" — the factory has no path that reaches `targetrepo`'s default branch without this actor.
