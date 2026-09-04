# Multi-agent SDLC pipeline — the product narrative

This document — not the 8-layer foundation pipeline in
`agent-factory-architecture.md` — describes a Temporal-orchestrated software-engineering pipeline whose output is a
merged pull request in a target repo. The
foundation-tier agent factory builds and ships the agent workers
(`swe-agent`, `pm-agent`, `architect-agent`) this pipeline calls at each
stage below.

`orchestration/workflows/pipeline_workflow.py`'s `AgentPipelineWorkflow`
today sequences Build (§3.2) → Eval-Gate (§3.6) → Register (§3.7) only,
with no `mode` parameter and no `@workflow.signal` handlers. This document
specifies the full multi-stage pipeline that extends it — PM review,
architecture/plan review, build, cleanup, automated code review, security
review, human approval gates, register, deploy. Every new stage below is a
sibling of Build inside the same pipeline-level sequencing (Orchestration
layer, §3.5), not a reopening of `agent-swe-design.md` §10's
single-agent-per-task scope.

## 1. Entry points

Two independent starting points exist, with a mandatory manual break
between them — the second never fires automatically from the first.

| Entry point                | Trigger                                                                                                                                                                                                       | Scope                                                                                                                                | Temporal entry?                             |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------- |
| **PM-agent Issue-Shaping** | `@pm-agent shape` comment on a raw, unshaped GitHub **issue** (no PR, no branch, no spec)                                                                                                                     | Rewrites/clarifies the issue in place (`gh issue edit`) — adds scope clarity, an explicit value-judgment note, no-gold-plating flags | **No.** Terminal at the issue.              |
| **Pipeline run**           | `@pipeline-agent run mode=<full\|vibe> agent=<name> version=<v>` comment on the target-repo PR (mirrors `swe-agent-build.yml`'s `@swe-agent build` comment trigger and its author-association gate; see §1.1) | Everything from §2 onward below                                                                                                      | Yes — this is the workflow this doc extends |

A developer's only interfaces to this repo are GitHub (issue/PR comments,
the GitHub Web UI) or the `gh` CLI — never a direct Temporal SDK call.
`orchestration/worker.py` only registers `AgentPipelineWorkflow`;
`orchestration/webhook_bridge/` (§1.1, built) is the webhook receiver that
turns a GitHub comment into the internal `AgentPipelineWorkflow.run(...)`/
`.signal(...)` call.

Between these two entry points, a human decides when a shaped issue becomes
`specs/NNN-slug/spec.md` — today, manually, via `/speckit-specify` →
`/speckit-plan` → `/speckit-tasks`, per `CLAUDE.md`'s Spec Kit flow.
PM-agent's Issue-Shaping job does not call `/speckit-specify`, does not
create a branch, and never touches the pipeline.

Issue-Shaping mirrors `swe-agent-build.yml`'s authorization gate
(`github.event.comment.author_association` in `["OWNER", "MEMBER",
"COLLABORATOR"]`, per `.github/workflows/swe-agent-build.yml`), keyed off
an **issue** comment with no linked PR (`github.event.issue.pull_request ==
null`) instead of a PR comment. Its tool access is deliberately narrow: `gh
issue` only — no `Bash`, no git, no Spec Kit tools — so it structurally
cannot create a branch or a spec even if instructed to.

### 1.1 Trigger bridge

A GitHub event reaches Temporal through `orchestration/webhook_bridge/` — a
persistent webhook server, not a CI-hook. `docker-compose.yml`'s `temporal`
service listens on `7233:7233` with no TLS and no auth, reachable only from
the machine running `make up` (today, a developer's laptop).
GitHub-hosted Actions runners can't reach that, so a CI-hook would need
either a self-hosted runner on the same machine/network or exposing
Temporal's unauthenticated control plane publicly — both real infra
changes, and worse than running one new local server. The webhook server
needs no such exposure: it runs on the same host as `make up`, connects to
Temporal exactly as `orchestration/worker.py` does, and only needs its own
HTTP endpoint reachable from GitHub — the normal shape of a GitHub App
webhook. It also handles both the initial `run` command and every later
signal (`pm_approved`, `plan_rejected`, `security_cleared`, etc.) as the
same kind of event.

Built as `orchestration/webhook_bridge/` (`server.py`, `auth.py`,
`grammar.py`, `temporal_client.py`, `github_app.py`, `dedup.py`,
`audit.py`, plus a test suite):

- **Transport** — reuses the existing `swe-agent` GitHub App
  (`SWE_AGENT_APP_ID`/`SWE_AGENT_APP_PRIVATE_KEY`) rather than registering a
  second one: its webhook URL is subscribed to `issue_comment` (created)
  deliveries. `GH_WEBHOOK_SECRET` verifies each delivery's
  `X-Hub-Signature-256` HMAC before anything else runs.
- **Authorization** — enforces in code the same allowlist
  `swe-agent-build.yml`'s `if:` enforces (`author_association` in
  `["OWNER", "MEMBER", "COLLABORATOR"]`) — there's no GH Actions `if:` to
  lean on off Actions.
- **Grammar** (`grammar.py`, mirrors the `@swe-agent build` comment-command
  shape):
  - `@pipeline-agent run mode=<full|vibe> agent=<agent_name>
    version=<version>` (all three tokens required, exactly once each), not
    yet running for this PR → `client.start_workflow("AgentPipelineWorkflow",
    args=[repo, branch, agent_name, version], id=f"pipeline/{repo}/{agent_name}/v{version}")`
    (§6's deterministic ID). `mode` is parsed and validated but not yet
    forwarded to the workflow, since the workflow itself has no `mode`
    param until §6's change lands; only `mode=full` is accepted today —
    `mode=vibe` is rejected as `mode_not_supported`.
  - `pm_approved` / `pm_rejected: <feedback>` / `plan_approved` /
    `plan_rejected: <feedback>` / `security_cleared` /
    `security_rejected: <feedback>`, already running →
    `client.get_workflow_handle(same id).signal(...)`. The workflow has no
    matching `@workflow.signal` handler yet, so the bridge logs this
    outcome as `signal_issued_no_handler`.
- **Network** — runs on the same host as `make up` and connects to
  Temporal via `Client.connect("localhost:7233")`, same as
  `orchestration/worker.py`; Temporal's own exposure is unchanged.
- **Local-dev reachability** — `smee-client` (npm package, GitHub's own
  recommended relay for local App dev) relays deliveries from a
  `smee.io/<channel>` proxy to the bridge's local port. The channel URL
  lives in one `WEBHOOK_PROXY_URL` env var, read by both `smee-client`
  (`npx smee-client --url "$WEBHOOK_PROXY_URL" --target
  http://localhost:<port>/webhook`) and the bridge itself. `make bridge`
  runs the relay and the server together as sibling processes.

### 1.2 HITL checkpoint map — where a human actually has to act

This diagram collapses §3's full state diagram and §5's sequence diagram
down to one question: where does a human have to act. Four checkpoint
*kinds* exist: three in-workflow signal gates (PM, Plan, Security), one
cross-cutting escalation gate that fires only on budget exhaustion, and two
actions a human takes outside Temporal entirely (writing the spec, merging
the final PR).

```mermaid
flowchart TB
    classDef human fill:#8250df,stroke:#6639ba,color:#fff,stroke-width:2px
    classDef auto fill:#1a7f37,stroke:#116329,color:#fff
    classDef gate fill:#9a6700,stroke:#7d5700,color:#fff,stroke-width:2px
    classDef terminal fill:#57606a,stroke:#424a53,color:#fff

    Issue(["GitHub issue"]):::terminal
    Spec(["human writes spec.md\n(/speckit-specify → plan → tasks)"]):::human
    PMReview["PM-agent\nSpec-Review"]:::auto
    PMGate{{"pm_approved /\npm_rejected"}}:::gate
    Arch["Architect fan-out\n+ judge + critic"]:::auto
    PlanGate{{"plan_approved /\nplan_rejected"}}:::gate
    Build["Build + Simplify +\nEval-Gate + Quality-Gate +\nAutomated-Review loop"]:::auto
    SecReview["Security-Review"]:::auto
    SecGate{{"security_cleared /\nsecurity_rejected"}}:::gate
    Register["Register\n(factory-repo PR)"]:::auto
    Merge(["human merges\ntarget-repo PR"]):::human
    Deploy["Deploy\n(RegistryPromotionWaiter)"]:::auto
    Escalate{{"escalation_resume /\nescalation_abandon"}}:::gate
    End(["workflow terminated"]):::terminal

    Issue --> Spec --> PMReview --> PMGate
    PMGate -- rejected --> PMReview
    PMGate -- approved --> Arch
    PMGate -. budget exhausted .-> Escalate

    Arch --> PlanGate
    PlanGate -- rejected --> Arch
    PlanGate -- approved --> Build
    PlanGate -. budget exhausted .-> Escalate

    Build -- gate/review failure --> Build
    Build --> SecReview --> SecGate
    SecGate -- rejected --> Build
    SecGate -- cleared --> Register
    SecGate -. budget exhausted .-> Escalate

    Escalate -. "resume → back to\nexhausted stage" .-> Build
    Escalate -. abandon .-> End

    Register --> Merge --> Deploy
```

Purple rounded = human action outside Temporal (writing the spec, merging
the PR); orange hexagon = in-workflow human signal gate; green rectangle =
fully automated activity/loop; gray rounded = terminal state. This omits
`vibe`-mode branches and the `EnsureTargetPR` setup step, and collapses
Build's internal Eval-Gate/Quality-Gate/Automated-Review retry loop into
one box — see §3/§4 for the full version.

## 2. Stage roster

**Existing, unchanged:**

| Stage         | Activity                          | Notes                                                                                                                                            |
| ------------- | --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Build         | `run_swe_agent_activity`          | Collapses Build + Sandbox Test (§3.2+§3.3), runs in the E2B `swe-agent-sandbox` template                                                         |
| Eval-Gate     | `eval_gate_activity`              | v1 binary coverage gate (`eval/braintrust/eval.config.py::run_eval`): checks *presence* of `SC-NNN` criteria in the diff, not semantic pass/fail |
| Register      | `register_activity`               | Opens a factory-repo PR writing `manifest.yaml`/`versions/vN.yaml`                                                                               |
| Deploy waiter | `RegistryPromotionWaiterWorkflow` | Separate long-lived workflow, waits on `pr_merged` — unreachable today; nothing starts or signals it yet                                         |

**New:**

| Stage                       | Wraps                                                                                                                                              | Blocking?                                                                                                                                                               |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ensure_target_pr_activity` | New — mirrors `activities.py::_open_factory_pr`'s idempotent existing-PR check, against the **target** repo instead of the factory repo            | N/A — setup step                                                                                                                                                        |
| PM Spec-Review              | New `pm-agent` (Spec-Review job)                                                                                                                   | Blocking human gate (`full`); auto-proceeds (`vibe`)                                                                                                                    |
| Architect                   | New `architect-agent`, N concurrent candidates (default 3, scales with spec complexity/budget — see §2's Architect subsection) + 1 judge/synthesis | Blocking human gate (`full`); auto-proceeds once `/speckit-analyze` passes or budget exhausted (`vibe`)                                                                 |
| Completeness-Critic         | New activity, single critic pass over judge's synthesized plan                                                                                     | Non-blocking gate-of-its-own; can trigger one bounded extra candidate (`full` only) — skipped entirely in `vibe`                                                        |
| Simplify                    | `code-simplifier:code-simplifier` (Anthropic plugin agent — not the `pr-review-toolkit:code-simplifier` variant)                                   | Never blocking; skipped entirely in `vibe`                                                                                                                              |
| Quality-Gate                | New activity, extends `load_success_criteria`'s parsing pattern                                                                                    | Blocking in `full`; skipped entirely in `vibe`                                                                                                                          |
| Automated-Review            | `pr-review-toolkit:review-pr`'s 5-subagent bundle                                                                                                  | `code-reviewer` + `silent-failure-hunter` blocking in `full` (all advisory in `vibe`); `comment-analyzer` + `pr-test-analyzer` + `type-design-analyzer` always advisory |
| Security-Review             | `security-review` skill                                                                                                                            | Always blocking, in both modes — a safety control, not a speed/quality tradeoff                                                                                         |
| Escalation                  | New signal pair (`escalation_resume`/`escalation_abandon`), cross-cutting — not its own activity                                                   | Fires only when PM/Plan/shared-Build-loop budget is exhausted; see §6                                                                                                   |

**Not recommended as new stages:**

- **Standalone QA/test-writer** — redundant with `swe-agent`'s own test-first
  mandate (`agent-swe-design.md` §5 steps 3–4) and with the advisory
  `pr-test-analyzer`.
- **Standalone docs/changelog updater** — redundant with `versions/vN.yaml`
  (§3.7) plus extending `register_activity`'s existing PR body.

### PM-agent — two decoupled jobs

Documented as one stage, two subsections, because they run at different
times, on different artifacts, with different tool access:

- **Issue-Shaping** — see §1. Terminal at the issue. Tool access: `gh issue`
  only.
- **Spec-Review + PM-Approval-Gate** — runs once `spec.md` already exists on
  the branch (created by a human, whether or not that human started from a
  PM-agent-shaped issue). Produces a value-judgment writeup — "is this the
  right thing, built right," explicit no-gold-plating check — posted to the
  target-repo PR thread. Gated by `pm_approved`/`pm_rejected`. Tool access
  includes read-only `/speckit-analyze`-style inspection but **no git-push** —
  mirrors `swe-agent`'s own "push only after verification steps run in code,
  not left to the model" guardrail (`registry/agents/swe-agent/SKILL.md`,
  "Known gap").

New registry entry `registry/agents/pm-agent/` (own `manifest.yaml`/
`SKILL.md`, same pattern as `registry/agents/swe-agent/`), own harness.

### Architect-agent — judge-panel, not single-answer

Architecture is not a single-answer problem, so this stage fans out instead
of producing one plan directly:

1. **N candidate architects run concurrently** — plain concurrent activities
   inside the same workflow execution (Temporal activities already run
   concurrently when awaited together; no child workflow needed), each
   producing an independent `plan.md`/`tasks.md`/ADR set for the same
   `spec.md`, prompted from a distinct angle. `N` defaults to 3
   (minimal-diff-first, clean-architecture-first, risk/security-first) and
   scales up for specs with more `SC-NNN` criteria or a larger token budget
   (mirroring the `budget.total`-scaled fan-out pattern used elsewhere for
   agent fleets — e.g. `Math.floor(budget.total / per-candidate-cost)`);
   `vibe` mode collapses it to 1 (§4). Because a candidate's only output is
   text/markdown (`plan.md`/`tasks.md`/ADRs), never executed code, each
   candidate runs as a plain Claude Agent SDK call — no E2B sandbox
   provisioned per candidate (§6.1's carve-out).
2. **1 judge/synthesis activity** scores all N against `spec.md`'s `SC-NNN`
   criteria, each candidate's own `/speckit-analyze` consistency result, and
   the same no-gold-plating principle PM-agent applies — then produces a
   single synthesized `plan.md`/`tasks.md`, picking a winner and grafting
   strong ideas from runners-up. Also a plain agent call, no sandbox.
3. **1 completeness-critic activity** runs next, before the human gate: a
   single fresh-context agent (again no sandbox — it only reads text) that
   checks whether every `SC-NNN` criterion is actually addressed by the
   synthesized plan, whether an architectural angle none of the N
   candidates tried exists, and whether an edge case the spec implies but
   no candidate touched exists. This is the check that the panel's coverage
   was actually adequate, not just diverse-looking.
   - **No gap found** — critic posts a short "coverage checked, none found"
     note to the PR thread and the synthesized plan proceeds straight to the
     human `plan_approved`/`plan_rejected` gate, unchanged.
   - **Gap found** — critic's finding (a specific missing angle or
     uncovered `SC-NNN`) is fed back as the prompt for exactly one
     additional targeted candidate (re-entering step 1 with `N=1`, angle =
     the critic's finding), then judge/synthesis re-runs to fold it in
     before reaching the human gate. This extra round counts against the
     same `MAX_PLAN_ATTEMPTS=3` budget as an ordinary `plan_rejected` loop,
     so at most one such gap-driven round can happen before the attempts
     are exhausted by human-reject loops alone.
   - Skipped entirely in `vibe` (§4) — `vibe` already runs a single architect
     with no panel to check the coverage of.
4. The bounded autonomous-repair loop (`MAX_PLAN_ATTEMPTS=3`, re-invoking
   `/speckit-plan` on the synthesized result) and the single human
   `plan_approved`/`plan_rejected` gate apply to this one synthesized plan,
   not to each candidate — Build still consumes exactly one `tasks.md`,
   unchanged.
5. Candidate plans + judge rationale + the critic's note are posted to the
   target-repo PR thread (so the human gate can challenge the automated
   pick) and logged as Braintrust spans; only the synthesized plan is
   committed to `specs/NNN-slug/` — candidates are not committed.

A reject at the human gate re-enters the bounded re-plan loop once more (can
request a specific candidate's approach instead of the judge's pick), then
escalates if still rejected.

### Quality-Gate

New activity, positioned right after Eval-Gate, in the same "objective
measurable threshold" family — extends the `SC-NNN` parsing pattern
`eval.config.py::load_success_criteria` already implements rather than
inventing a parallel mechanism. Enforces three concrete, blocking attributes:

1. **Traceability** — every `SC-NNN` bullet parsed from `spec.md`'s
   `### Measurable Outcomes` must be referenced at least once in the diff
   (test name, docstring, or commit message).
2. **Documentation** — every new/changed public function/class has a
   docstring; any diff touching `orchestration/`, `harness/`, or introducing a
   new stage/layer must also touch a corresponding `docs/*.md` file — checked
   structurally (diff-touches-docs-when-diff-touches-orchestration), not
   semantically judged.
3. **Test coverage** — >=80% combined line coverage across unit + integration
   + e2e, read from whatever coverage tool the target repo already reports.

Quality-Gate implements `eval/gate-policy.md`'s stated target ("all
`success_criteria` score >= pass"); today's Eval-Gate (`eval.config.py`)
only checks presence of criteria, not semantic pass/fail. On failure: route
back to Build with the specific failing attribute as feedback, sharing
`MAX_BUILD_ATTEMPTS`.

## 3. Diagram (a) — stage transition graph

```mermaid
stateDiagram-v2
    [*] --> IssueShaping
    IssueShaping --> [*] : issue rewritten (gh issue edit)\n[out-of-band, terminal — no Temporal entry]
    note right of IssueShaping
        "@pm-agent shape" on a raw issue.
        No spec, branch, or Temporal entry.
    end note

    [*] --> EnsureTargetPR : human writes spec.md\n[mandatory manual break — not automated]

    EnsureTargetPR --> PMSpecReview : draft PR opened (idempotent)
    PMSpecReview --> PMGate : value-judgment writeup posted to PR
    PMGate --> PMSpecReview : pm_rejected + feedback\n[MAX_PM_ATTEMPTS=3]
    PMGate --> ArchitectFanOut : pm_approved
    PMGate --> Escalate : attempts exhausted
    PMGate --> ArchitectFanOut : [vibe: auto-proceed, no gate]

    ArchitectFanOut --> ArchitectJudge : N candidates ready\n(default 3: minimal-diff / clean-arch / risk-first;\nscales with spec complexity/budget)
    ArchitectJudge --> CompletenessCritic : synthesized plan.md/tasks.md\n[full only]
    ArchitectJudge --> PlanGate : synthesized plan.md/tasks.md\n[vibe: critic skipped]
    CompletenessCritic --> ArchitectFanOut : gap found\n[+1 targeted candidate, N=1,\nshared MAX_PLAN_ATTEMPTS=3 budget]
    CompletenessCritic --> PlanGate : no gap found
    PlanGate --> ArchitectFanOut : plan_rejected\n[MAX_PLAN_ATTEMPTS=3]
    PlanGate --> Build : plan_approved
    PlanGate --> Escalate : attempts exhausted
    PlanGate --> Build : [vibe: single architect, auto-proceed once /speckit-analyze passes or budget exhausted]

    Build --> Simplify : [full only]
    Build --> EvalGate : [vibe: Simplify skipped entirely]
    Simplify --> EvalGate

    EvalGate --> Build : failed + reason\n[shared MAX_BUILD_ATTEMPTS=3 — never mode-conditional]
    EvalGate --> QualityGate : passed [full only]
    EvalGate --> AutomatedReview : passed [vibe: Quality-Gate skipped entirely]

    QualityGate --> Build : failed (traceability/docs/coverage) + reason\n[shared budget]
    QualityGate --> AutomatedReview : passed

    AutomatedReview --> Build : code-reviewer/silent-failure-hunter finding\n[shared budget — full: blocking, vibe: advisory-only]
    AutomatedReview --> SecurityReview : blocking findings clear\n(comment/test/type findings: always advisory, never block)

    SecurityReview --> SecurityGate : findings posted to PR
    SecurityGate --> Build : security_rejected + feedback\n[hard stop, no auto-retry-around — never mode-conditional]
    SecurityGate --> Register : security_cleared

    Build --> Escalate : MAX_BUILD_ATTEMPTS exhausted\n(at Eval/Quality/Automated/Security)

    Register --> DeployWaiter : registry PR opened
    DeployWaiter --> [*] : pr_merged signal\n[unreachable today — nothing starts/signals this workflow]
    Escalate --> PMSpecReview : escalation_resume\n[+1 attempt, if PM budget exhausted]
    Escalate --> ArchitectFanOut : escalation_resume\n[+1 attempt, if Plan budget exhausted]
    Escalate --> Build : escalation_resume\n[+1 attempt, if shared Build-loop budget exhausted]
    Escalate --> [*] : escalation_abandon(reason)

    classDef real fill:#1a7f37,stroke:#1a7f37,color:#fff
    classDef partial fill:#9a6700,stroke:#9a6700,color:#fff,stroke-dasharray: 4 3
    classDef stub fill:#6e7781,stroke:#6e7781,color:#fff,stroke-dasharray: 2 2
    class IssueShaping,EnsureTargetPR,PMSpecReview,PMGate,PlanGate,Simplify,QualityGate,AutomatedReview,SecurityReview,SecurityGate,Escalate stub
    class Build,EvalGate,Register real
    class DeployWaiter,ArchitectFanOut,ArchitectJudge,CompletenessCritic partial
```

Coloring follows `docs/README.md`'s status legend: green = real, orange
dashed = partial, gray dashed = stub. `Build`/`EvalGate`/`Register` are
real; `DeployWaiter` is partial (code-complete, unreachable);
`ArchitectFanOut`/`ArchitectJudge`/`CompletenessCritic` are partial too —
`harness/architect-agent/agent.py::run_architect_stage()` (spec
`004-architect-fanout-judge`) implements fan-out, scoring, synthesis, and
the one-round completeness-critic as a directly callable function, but it
is not registered as a Temporal activity and nothing in
`orchestration/workflows/pipeline_workflow.py` calls it — same
code-complete/unreachable shape as `DeployWaiter`. `PlanGate` stays stub:
no `@workflow.signal` handler for `plan_approved`/`plan_rejected` exists
yet (`005-pipeline-mode-signals-escalation`'s job). Every other node is a
design-only stage.

## 4. Per-stage contract table

**Eval-Gate and Security-Review are never mode-conditional.**

| Stage               | `full`                                                                            | `vibe`                                                                                                                                          |
| ------------------- | --------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| PM Spec-Review      | blocking human gate                                                               | runs, posts writeup, auto-proceeds                                                                                                              |
| Architect           | N-candidate panel (default 3, scales with complexity/budget) + judge + human gate | single architect (N=1), auto-proceeds once `/speckit-analyze` passes or budget exhausted                                                        |
| Completeness-Critic | runs after judge, before human gate; can trigger 1 bounded extra candidate        | skipped entirely — no panel to check coverage of                                                                                                |
| Build               | unchanged                                                                         | unchanged                                                                                                                                       |
| Simplify            | runs                                                                              | skipped                                                                                                                                         |
| Eval-Gate           | blocking (absolute floor)                                                         | blocking (absolute floor)                                                                                                                       |
| Quality-Gate        | blocking                                                                          | skipped entirely                                                                                                                                |
| Automated-Review    | 2 blocking / 3 advisory                                                           | all advisory, nothing blocks                                                                                                                    |
| Security-Review     | blocking human gate                                                               | unchanged — still blocking                                                                                                                      |
| Escalation          | fires on PM/Plan/Build-loop budget exhaustion                                     | not mode-conditional — fires identically, since the Build-loop budget is shared and Eval-Gate/Security-Review are always blocking in both modes |
| Register            | unchanged                                                                         | unchanged                                                                                                                                       |

Full contract per stage:

| Stage                       | Input                                                                      | Output                                                                                                                      | Pass condition                                                                    | On failure                                                                                                                                                                                                                                                                                                                                                             |
| --------------------------- | -------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ensure_target_pr_activity` | `repo`, `branch` (requires `spec.md` already on branch)                    | Target-repo PR url (idempotent — reuses existing open PR)                                                                   | PR exists or is opened                                                            | N/A (setup step, no failure branch)                                                                                                                                                                                                                                                                                                                                    |
| PM Spec-Review              | `spec.md`, target PR                                                       | Value-judgment writeup on PR + `pm_approved`/`pm_rejected` signal                                                           | Human signals `pm_approved`                                                       | `pm_rejected` + feedback loops PM-agent, `MAX_PM_ATTEMPTS=3`, then escalate                                                                                                                                                                                                                                                                                            |
| Architect (fan-out + judge) | `spec.md`                                                                  | Synthesized `plan.md`/`tasks.md` + ADRs; candidates+rationale on PR                                                         | `/speckit-analyze` clean on synthesized plan + human `plan_approved`              | `plan_rejected` re-enters fan-out, `MAX_PLAN_ATTEMPTS=3`, then escalate                                                                                                                                                                                                                                                                                                |
| Completeness-Critic         | Synthesized `plan.md`, `spec.md`, N candidates                             | `{gap_found, detail}` + PR note                                                                                             | No uncovered `SC-NNN` criterion or untried angle                                  | `gap_found` triggers 1 targeted candidate (N=1) + re-synthesis, shared `MAX_PLAN_ATTEMPTS=3` — not a separate budget                                                                                                                                                                                                                                                   |
| Build                       | `repo`, `branch`, `feedback`                                               | PR url, pushed commits                                                                                                      | sandbox exit 0                                                                    | `_NO_AUTO_RETRY` (Temporal); loop is the workflow's own retry                                                                                                                                                                                                                                                                                                          |
| Simplify                    | Build's branch                                                             | Optional extra commit (via `code-simplifier:code-simplifier`, its own activity/sandbox — not a step inside Build's sandbox) | N/A — always "succeeds" from the pipeline's view                                  | Execution failure logged and swallowed, never fails pipeline                                                                                                                                                                                                                                                                                                           |
| Eval-Gate                   | `spec.md`, sandbox trace                                                   | `{passed, criteria, reason}`                                                                                                | exit 0 + PR exists + ≥1 `SC-NNN` found                                            | loops to Build w/ `reason` as feedback, shared budget                                                                                                                                                                                                                                                                                                                  |
| Quality-Gate                | diff, `spec.md`, coverage report                                           | `{passed, reason}` per §2's 3 checks                                                                                        | traceability + docs + ≥80% coverage all pass                                      | loops to Build w/ failing attribute, shared budget                                                                                                                                                                                                                                                                                                                     |
| Automated-Review            | Build's PR diff                                                            | 5 subagents' findings                                                                                                       | `code-reviewer` + `silent-failure-hunter` clean (`full`); always "pass" in `vibe` | blocking findings loop to Build, shared budget; advisory findings posted, never block                                                                                                                                                                                                                                                                                  |
| Security-Review             | Build's PR diff                                                            | Findings + `security_cleared`/`security_rejected`                                                                           | human signals `security_cleared`                                                  | `security_rejected` + feedback loops to Build, shared budget — hard stop, no auto-retry-around                                                                                                                                                                                                                                                                         |
| Escalation                  | Exhausted stage name, attempts used, accumulated failure/rejection reasons | PR comment summarizing the exhaustion + `escalation_resume`/`escalation_abandon` signal                                     | human signals `escalation_resume`                                                 | `escalation_resume` re-enters the exhausted stage's loop with exactly one additional attempt (not a numeric grant), reusing the last `*_rejected` feedback already given — repeatable, uncapped in v1, each resume logged (Braintrust span + PR comment); `escalation_abandon(reason)` terminates the workflow after posting a final PR comment, `Register` never runs |
| Register                    | gate result, `agent_name`, `version`                                       | Factory-repo PR url                                                                                                         | — (always runs once reached)                                                      | N/A — `_NO_AUTO_RETRY`, existing-PR idempotency                                                                                                                                                                                                                                                                                                                        |
| Deploy waiter               | `pr_merged` signal                                                         | `manifest.yaml.status: active`                                                                                              | signal received                                                                   | N/A — nothing starts/signals this today                                                                                                                                                                                                                                                                                                                                |

Two details remain open (§9): the exact severity schema of the 5 bundled
review subagents, and Security-Review's exact severity threshold.

`eval/gate-policy.md`'s second promotion clause — "no
`guardrails.requires_human_approval` item is untouched without sign-off" —
is the existing precedent for treating Security-Review (and, at Register,
an explicit human-approval field on the spec itself) as hard human-sign-off
gates rather than agent-judged thresholds.

## 5. Diagram (b) — workflow / activity / agent / signal sequence

```mermaid
sequenceDiagram
    actor Human
    participant GH as GitHub (PR comment)
    participant Bridge as webhook_bridge (§1.1)
    participant PR as Target-repo PR
    participant WF as AgentPipelineWorkflow
    participant PM as PM-agent (Spec-Review)
    participant ARCH as Architect candidates (xN, concurrent)
    participant JUDGE as Judge/Synthesis
    participant CRITIC as Completeness-Critic
    participant BUILD as swe-agent (Build)
    participant GATE as Eval-Gate + Quality-Gate
    participant REV as Automated-Review (5-subagent bundle)
    participant SEC as Security-Review

    Human->>GH: comment "@pipeline-agent run mode=full agent=widget-export version=v3"
    GH->>Bridge: webhook delivery (issue_comment)
    Bridge->>WF: start_workflow(id=pipeline/{repo}/{agent_name}/v{version})
    WF->>PR: ensure_target_pr_activity (idempotent draft PR)
    WF->>PM: run Spec-Review
    PM->>PR: post value-judgment writeup
    WF->>WF: wait_condition(pm_approved | pm_rejected)
    Human->>GH: comment "pm_rejected: <feedback>"
    GH->>Bridge: webhook delivery
    Bridge->>WF: signal pm_rejected(feedback)
    WF->>PM: re-run with feedback [MAX_PM_ATTEMPTS=3]
    Human->>GH: comment "pm_approved"
    GH->>Bridge: webhook delivery
    Bridge->>WF: signal pm_approved

    par N concurrent candidates (default 3, scales w/ complexity/budget)
        WF->>ARCH: candidate A — minimal-diff-first
    and
        WF->>ARCH: candidate B — clean-architecture-first
    and
        WF->>ARCH: candidate C — risk/security-first
    end
    ARCH->>JUDGE: Nx plan.md/tasks.md + /speckit-analyze results
    JUDGE->>PR: post candidates + rationale (human can challenge)
    JUDGE-->>WF: synthesized plan.md/tasks.md
    WF->>CRITIC: run completeness check [full only]
    CRITIC->>PR: post coverage note
    alt gap found
        CRITIC-->>WF: gap_found(detail)
        WF->>ARCH: 1 targeted candidate (N=1) on the gap\n[shared MAX_PLAN_ATTEMPTS budget]
        ARCH->>JUDGE: re-synthesize with new candidate folded in
        JUDGE-->>WF: updated synthesized plan.md/tasks.md
    else no gap
        CRITIC-->>WF: no gap
    end
    WF->>WF: wait_condition(plan_approved | plan_rejected)
    Human->>GH: comment "plan_rejected: <feedback>"
    GH->>Bridge: webhook delivery
    Bridge->>WF: signal plan_rejected
    WF->>ARCH: re-run fan-out [MAX_PLAN_ATTEMPTS=3]
    Human->>GH: comment "plan_approved"
    GH->>Bridge: webhook delivery
    Bridge->>WF: signal plan_approved

    loop Build loop (MAX_BUILD_ATTEMPTS=3, shared across Eval/Quality/Automated/Security)
        WF->>BUILD: run_swe_agent_activity(feedback)
        BUILD->>PR: push commits
        WF->>BUILD: Simplify activity [full only]
        WF->>GATE: eval_gate_activity, then quality_gate_activity [full only]
        GATE-->>WF: pass/fail + reason
        WF->>REV: automated_review_activity
        REV->>PR: post findings (blocking + advisory)
        REV-->>WF: blocking findings, if any
    end

    alt shared build-loop budget exhausted (MAX_BUILD_ATTEMPTS)
        WF->>PR: post summary (stage, attempts used, accumulated reasons)
        WF->>WF: wait_condition(escalation_resume | escalation_abandon)
        Human->>GH: comment "resume"
        GH->>Bridge: webhook delivery
        Bridge->>WF: signal escalation_resume
        WF->>BUILD: re-enter Build loop [+1 attempt]
    end

    WF->>SEC: security_review_activity
    SEC->>PR: post findings
    WF->>WF: wait_condition(security_cleared | security_rejected)
    Human->>GH: comment "security_rejected: <feedback>"
    GH->>Bridge: webhook delivery
    Bridge->>WF: signal security_rejected(feedback)
    WF->>BUILD: re-enter Build loop [shared budget — hard stop if exhausted]
    Human->>GH: comment "security_cleared"
    GH->>Bridge: webhook delivery
    Bridge->>WF: signal security_cleared

    WF->>WF: register_activity(repo, agent_name, version, eval_result)
    WF-->>Human: return registry PR url
```

## 6. Orchestration shape

**Mode switch.** `AgentPipelineWorkflow.run(repo, branch, agent_name, version,
mode="full")` gains a `mode: Literal["full", "vibe"]` parameter — `"full"`
runs every stage above; `"vibe"` relaxes engineering rigor for speed, never
safety, per §4's matrix. Eval-Gate and Security-Review are never
mode-conditional.

**Signals stay inline on `AgentPipelineWorkflow` itself.** The three human
gates — `pm_approved`/`pm_rejected`, `plan_approved`/`plan_rejected`,
`security_cleared`/`security_rejected` — are modeled as bare signals using
`workflow.wait_condition`, the same pattern `RegistryPromotionWaiterWorkflow`
already uses for `pr_merged`, inlined rather than split into a sibling
workflow. These gates are same-SLA-class as ordinary PR review
(hours–days), unlike Deploy's independent, weeks-scale lifecycle (per
`pipeline_workflow.py`'s own module docstring and
`registry_promotion_waiter.py`'s docstring), so they don't warrant a
separate workflow the way Deploy does. This keeps Register single-caller
and avoids inventing new correlation machinery.

A human never calls `workflow.signal()` directly. Each gate's PR comment
(e.g. `pm_approved`, `plan_rejected: <feedback>`) is the human-facing
interface; `orchestration/webhook_bridge/` parses the comment and issues the
Temporal signal server-side. `AgentPipelineWorkflow` has none of these three
gates' `@workflow.signal` handlers yet, so a signal the bridge issues today
has nothing to land on — the bridge logs this outcome as
`signal_issued_no_handler`.

**Architect's N-candidate fan-out is plain concurrency, not a child
workflow.** Awaiting N `workflow.execute_activity` calls together inside the
same workflow execution is a normal Temporal pattern (`asyncio.gather`
equivalent). The parent/child split stays reserved for genuinely independent
SLA/lifecycle stages, which is why Deploy (and only Deploy) is a separate
workflow.

**Deterministic workflow ID.**
`orchestration/webhook_bridge/temporal_client.py::workflow_id()` implements
`f"pipeline/{repo}/{agent_name}/v{version}"` for `AgentPipelineWorkflow`,
scoped by `repo` since two different target repos could otherwise pick the
same `agent_name`/`version` — mirrors the `registry-promotion-{agent_name}-v{version}`
convention already on the waiter workflow. The bridge needs no correlation
lookup beyond parsing the comment's own `agent=`/`version=` tokens.

**Budget-exhaustion escalation.** On exhausting `MAX_PM_ATTEMPTS`/
`MAX_PLAN_ATTEMPTS`/shared `MAX_BUILD_ATTEMPTS` at any budgeted loop, the
workflow today raises a silent `ApplicationError`. This design replaces
that with a generic escalation signal pair, mirroring the three gate pairs'
pattern (bare `@workflow.signal` + `workflow.wait_condition`, comment-driven
via the webhook bridge):

- **`escalation_resume`** (no payload) / **`escalation_abandon(reason:
  str)`** — one pair, reused across all three exhaustion points (PM, Plan,
  shared Build-loop budgets), since Escalate is a single cross-cutting
  state in §3's diagram, not per-stage.
- On exhaustion, the workflow posts a PR comment naming the exhausted
  stage, attempts used, and the accumulated failure/rejection reasons.
- **Grammar addition** (`orchestration/webhook_bridge/grammar.py`): exact
  match `resume`; regex `^abandon:\s*(.+)$` (reason required, consistent
  with `pm_rejected`/`plan_rejected`/`security_rejected` all requiring
  feedback text). New `_SIGNAL_NAMES` entries: `("escalation", "resume")
  -> "escalation_resume"`, `("escalation", "abandon") ->
  "escalation_abandon"`.
- **`escalation_resume` semantics**: re-enters the exhausted stage's loop
  with exactly one additional attempt — not a numeric grant, keeping the
  same small-bounded-loop philosophy as `MAX_*_ATTEMPTS` rather than
  inventing a new knob. Reuses whatever feedback was already given via the
  last ordinary `*_rejected` comment. Repeatable, uncapped in v1, logged
  each time (Braintrust span + PR comment).
- **`escalation_abandon(reason)` semantics**: terminates the workflow
  after posting a final PR comment with the reason — `Register` is never
  reached on this path.

## 6.1 Execution model: one activity, one fresh context (sandboxed unless code-free)

Every stage in §2's roster — existing and new — is a single Temporal
activity, and every activity invocation gets its own fresh, memoryless
Claude Agent SDK context, with no memory of any other stage's, or even its
own previous attempt's, conversation. Most of these run inside a fresh E2B
sandbox; the Architect fan-out is the one exception (below), because
sandboxing is about giving an agent a filesystem + shell to execute code,
not an inherent property of "one activity." `run_swe_agent_activity`
(`orchestration/activities.py:70-90`) calls `AsyncSandbox.create()` at the
start of the activity and `sandbox.kill()` in a `finally` at the end, once
per call. Every new stage below (PM, Simplify, Quality-Gate,
Automated-Review, Security-Review) follows the identical pattern: create a
sandbox, run one agent invocation to completion, kill the sandbox.

**Carve-out: the Architect fan-out (candidates, judge/synthesis,
completeness-critic) provisions no E2B sandboxes at all.** Every other
stage's sandbox exists to give the agent a filesystem + shell to actually
execute code (Build compiles/runs tests, Simplify edits files in place,
Automated/Security-Review may run linters). Architect's candidates, Judge,
and the Completeness-Critic never execute anything — their entire output is
`plan.md`/`tasks.md`/ADR prose plus a critic note, read from and written to
the branch as plain git content. Each of these is therefore a plain Claude
Agent SDK call with no sandbox lifecycle, which is materially cheaper per
candidate and is what makes scaling `N` up for a complex spec (§2) an
acceptable cost tradeoff rather than an N-times multiplier on sandbox
provisioning overhead too.

Concretely:

- The N concurrent Architect candidates (§2, §5) are N separate agent
  contexts run in parallel, not N branches of one conversation — each
  candidate agent never sees the other candidates' output, only the
  judge/synthesis activity (itself a separate context) and, after that, the
  completeness-critic (another separate context) do.
- A Build-loop retry (`MAX_BUILD_ATTEMPTS=3`) is a new sandbox per
  attempt — the retried agent has no memory of its own prior attempt
  except what the workflow explicitly re-injects as the `feedback` string
  (Eval-Gate's `reason`, Quality-Gate's failing attribute, a review
  finding, security feedback). The agent re-derives context from that
  feedback string plus whatever is already committed to the branch/PR, not
  from conversation history.
- Nothing in-process ever crosses a stage boundary. The only things that
  cross are the artifacts already listed in §8's table — git commits, PR
  comments, Braintrust spans. This is what makes the target-repo PR thread
  the actual hand-off mechanism between agents: it's not incidental
  logging, it's the sole channel through which one stage's output becomes
  the next stage's (or the next attempt's) input.

## 7. Diagram (c) — artifact flow and storage at rest

```mermaid
flowchart LR
    issue["GitHub issue"]:::stub
    spec["spec.md / plan.md / tasks.md\n(specs/NNN-slug/, target-repo git)"]:::real
    adr["ADR docs\n(specs/NNN-slug/adr/000N-*.md, target-repo git)"]:::stub
    branch["implementation branch + commits\n(target-repo git)"]:::real
    pr["target-repo PR + comment thread"]:::stub
    span["Braintrust spans\n(per-stage, eval.config.py logger pattern)"]:::real
    manifest["registry manifest.yaml / versions/vN.yaml\n(factory-repo git)"]:::real

    issue -->|"gh issue edit\n(Issue-Shaping, terminal)"| issue
    issue -.->|"explicit human decision\n(mandatory manual break, not automated)"| spec
    spec -->|"read by PM / Architect / Build"| pr
    spec --> adr
    adr -->|"posted for human review"| pr
    spec --> branch
    branch -->|"Simplify + Build commits"| pr
    pr -->|"PM writeup, Architect rationale,\ncompleteness-critic note,\nAutomated/Security findings"| span
    pr -->|"Eval-Gate pass"| manifest

    classDef real fill:#1a7f37,stroke:#1a7f37,color:#fff
    classDef partial fill:#9a6700,stroke:#9a6700,color:#fff,stroke-dasharray: 4 3
    classDef stub fill:#6e7781,stroke:#6e7781,color:#fff,stroke-dasharray: 2 2
```

## 8. Artifact & persistence model

| Artifact                                        | Store                                                                                                                     | Notes                                                                                                                                                                                                                  |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `spec.md`/`plan.md`/`tasks.md`                  | Target-repo git, `specs/NNN-slug/`                                                                                        | Unchanged from today's Spec Kit flow                                                                                                                                                                                   |
| Implementation branch + commits                 | Target-repo git                                                                                                           | Simplify adds an optional extra commit                                                                                                                                                                                 |
| **Target-repo PR + comment thread**             | Target repo, GitHub                                                                                                       | New home for PM's value-judgment writeup, Architect's candidates + judge rationale, Automated-Review/Security-Review findings — all human-readable, mirrors `swe-agent-build.yml`'s existing `gh pr comment` precedent |
| ADR docs                                        | Target-repo git, `specs/NNN-slug/adr/000N-*.md`                                                                           | Committed — no new store, reuses git-branch-as-artifact-store                                                                                                                                                          |
| Review findings                                 | PR comment + a Braintrust span (reusing `eval.config.py`'s existing `init_logger`/`start_span` pattern), tagged per stage | For audit/traceability                                                                                                                                                                                                 |
| Eval-Gate result / registry manifest / versions | Unchanged (factory-repo git, per §3.7)                                                                                    | —                                                                                                                                                                                                                      |

Temporal workflow/activity state is orchestration state only — nothing here
relies on Temporal to persist an artifact past workflow completion; every
artifact above lives in git or a comment thread, not in Temporal history.

## 9. Open questions

- **Review-subagent severity schema.** The exact severity levels
  `pr-review-toolkit:code-reviewer` / `silent-failure-hunter` /
  `comment-analyzer` / `pr-test-analyzer` / `type-design-analyzer` actually
  emit need verification against their real prompts before implementation —
  this doc assumes a blocking/advisory split (§4) but not a specific
  severity taxonomy.
- **Security-Review's exact severity threshold.** What specific finding
  severity triggers `security_rejected` vs. an advisory note is left
  unspecified here — `gate-policy.md`'s "no `guardrails.requires_human_approval`
  item untouched without sign-off" clause is the closest existing precedent,
  but a concrete threshold still needs to be set.
- **Budget-exhaustion escalation — resume cap policy.** Whether repeated
  `escalation_resume` calls should ever be capped is open; v1 leaves it
  uncapped.
- **Capped human-reject-replan rounds.** PM (`MAX_PM_ATTEMPTS=3`) and
  Architect (`MAX_PLAN_ATTEMPTS=3`) both bound the autonomous retry loop, but
  neither bounds how many times a human can reject before some other
  escalation kicks in beyond "escalate" — worth deciding explicitly before
  implementation to avoid an unbounded human-reject cycle.
- **Completeness-critic's gap-detection threshold.** What counts as a real
  gap (an `SC-NNN` criterion genuinely unaddressed, an architectural angle
  none of the N candidates tried) vs. noise (a stylistic difference, a
  criterion addressed implicitly rather than explicitly) is left to the
  critic's judgment here, with no concrete rubric. Too loose a threshold
  turns every Architect run into an extra round; too strict makes the
  critic decorative. Needs a concrete rubric (e.g. "flag only if an
  `SC-NNN` bullet has zero mention across all N candidates' plans") before
  implementation.
- **Architect's default N and its scaling function.** §2 sets N=3 by
  default, scaling with spec complexity/budget, but doesn't pin the exact
  function (e.g. `SC-NNN` count thresholds, a `budget.total`-derived
  formula, or a human-set flag per pipeline run) — needs a concrete rule
  before implementation so N isn't picked ad hoc per run.

## 10. Worked example — fictional repo walkthrough

Everything above is specified abstractly (state diagram, contract tables).
This section makes it concrete: a single narrated run on a fictional repo,
`octo/widget-service`, feature "add CSV export to the `/reports` endpoint",
in `full` mode. Every step names the actor, the concrete action, and the
artifact produced — including the failures and corrections at each gate.
Per §6.1, every agent step below runs in its own fresh sandbox with no
memory of any other step; the PR thread and the branch are the only things
carrying state forward.

1. **Human** opens issue `octo/widget-service#142`, "CSV export for
   reports." **Human** comments `@pm-agent shape`. **PM-agent**
   (Issue-Shaping job, §1) runs `gh issue edit 142` — adds scope clarity
   ("CSV only, no other formats implied") and a no-gold-plating note.
   Terminal at the issue, per §1.
2. **Human** manually runs `/speckit-specify` → `/speckit-plan` →
   `/speckit-tasks` (the mandatory manual break from §1) and pushes
   `specs/003-csv-export/spec.md` to branch `003-csv-export`. Spec's
   `### Measurable Outcomes` lists `SC-001` (export endpoint returns
   `text/csv`) and `SC-002` (row count matches the underlying query).
3. **Human** starts the pipeline the only way they actually can: commenting
   `@pipeline-agent run mode=full agent=widget-export version=v3` on the
   branch's GitHub PR. The `webhook_bridge` GitHub App server (§1.1) catches
   this delivery and calls `client.start_workflow("AgentPipelineWorkflow",
   args=["octo/widget-service", "003-csv-export", "widget-export", "v3"],
   ...)` server-side — `mode` is validated (`full` is accepted) but not yet
   forwarded, since the workflow itself has no `mode` param until §6's
   change lands. Workflow ID: `pipeline/octo/widget-service/widget-export/v3`
   (§6). **`ensure_target_pr_activity`** opens draft PR `#57` on
   `octo/widget-service`.
4. **PM-agent** (Spec-Review job) runs, posts a value-judgment writeup to
   PR `#57`: flags that the spec's prose still mentions "CSV/XLSX export"
   in one sentence even though only `SC-001`/`SC-002` (CSV) are measurable
   — a no-gold-plating catch. **Human** signals `pm_rejected("drop XLSX
   mention, CSV only")` — via a PR comment, through the §1.1 bridge, same
   as every other signal in this walkthrough from here on. PM-agent re-runs
   (attempt 2/`MAX_PM_ATTEMPTS=3`) against the updated `spec.md`, posts a
   clean writeup. **Human** signals `pm_approved`.
5. **Architect fan-out**: N=3 candidates run concurrently (spec is small,
   default N applies), each a plain agent call with no sandbox (§6.1's
   carve-out) — minimal-diff-first, clean-architecture-first,
   risk/security-first — each producing its own `plan.md`/`tasks.md`/ADRs
   for the CSV-only spec. **Judge/synthesis** activity scores all 3,
   synthesizes a `plan.md` based on the minimal-diff candidate, posts all
   3 plus rationale to PR `#57`. **Completeness-critic** runs next, checks
   the synthesized plan against `SC-001`/`SC-002` and the 3 candidates —
   finds no gap, posts "coverage checked, none found" to PR `#57`, proceeds
   straight to the human gate. **Human** reviews, prefers the risk-first
   candidate's streamed-response approach (avoids buffering the whole CSV
   in memory) over the judge's pick, signals `plan_rejected("use candidate
   C's streaming approach for the CSV writer")`. Architect fan-out re-runs
   (attempt 2/`MAX_PLAN_ATTEMPTS=3`), judge grafts the streaming approach
   into the synthesized plan as instructed, completeness-critic re-checks
   (still no gap), commits `specs/003-csv-export/plan.md` + `tasks.md` +
   ADR `0001-streaming-csv-writer.md`. **Human** signals `plan_approved`.
6. **Build** (attempt 1/`MAX_BUILD_ATTEMPTS=3`) runs `run_swe_agent_activity`
   against `tasks.md`, pushes commits implementing the streaming CSV
   writer, updates PR `#57`. **Simplify** runs (own activity/sandbox —
   `code-simplifier:code-simplifier`), adds one small commit tightening a
   generator expression. **Eval-Gate** runs: sandbox exit 0, PR exists, but
   only `SC-001` is found referenced in the diff — no test name/docstring/
   commit message matches `SC-002`. Loops to Build with
   `reason="SC-002 (row count) has no test coverage"` as feedback.
7. **Build** (attempt 2) adds `test_csv_export_sc002_row_count_matches_query`,
   pushes. **Eval-Gate** passes (both `SC-001`/`SC-002` referenced).
   **Quality-Gate** passes (traceability/docs/coverage all clear).
   **Automated-Review** runs the 5-subagent bundle: `silent-failure-hunter`
   finds a blocking issue — the streaming writer's `except Exception:
   pass` swallows a broken-pipe error instead of logging it — posted to
   PR `#57` as blocking. Loops to Build (attempt 3/3, the last one under
   the shared budget) with that finding as feedback.
8. **Build** (attempt 3) replaces the bare `except` with a logged,
   re-raised error. **Automated-Review** re-runs, clean this time —
   `code-reviewer`/`silent-failure-hunter` both pass; the always-advisory
   3 (`comment-analyzer`/`pr-test-analyzer`/`type-design-analyzer`) post
   minor advisory notes that never block.
9. **Security-Review** runs (always blocking, never mode-conditional, per
   §4/§6), finds the CSV filename in the `Content-Disposition` response
   header is built from unsanitized user input — potential header
   injection — posts the finding to PR `#57`. **Human** signals
   `security_rejected("sanitize filename before setting the header")`. Per
   §4/§6 this is a hard stop with no auto-retry-around, so it re-enters the
   Build loop directly rather than looping within Security-Review itself.
   This walkthrough assumes a fresh Build budget at this stage. Build fixes
   the filename sanitization; **Security-Review** re-runs, clean. **Human**
   signals `security_cleared`.
10. **`register_activity`** opens a PR on the factory repo writing
    `registry/agents/widget-export/manifest.yaml` and `versions/v3.yaml`
    from the real Eval-Gate result. **Human** merges target-repo PR `#57`
    (out of band, on GitHub, not a Temporal signal). `RegistryPromotionWaiterWorkflow`'s
    `pr_merged` signal would fire here — nothing today wires a GH Actions
    step to send that signal, so in an actual run `manifest.yaml.status`
    stays `experimental` until that wiring exists.
