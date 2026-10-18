# Internal Repository Map: Agentic Factory

Scope: `/Users/aheumaier/Codebox/agentic_factory` (read-only except this file). `.env`, `.env.braintrust`, `docs/Day_1_v3.pdf` not read. Verified against CLAUDE.md, README.md, docs/*, specs/, git log (2026-10-13 snapshot, updated 2026-10-17). All claims cited as `path:line`.

## Two-tier split and definition

### Takeaway
Foundation tier is an 8-layer pipeline producing deployed agent workers. Product tier is a Temporal SDLC pipeline whose output is a merged PR in a target repo. Explicit separation in design docs; known mismatch in code (workflow ends in registry activity, not target-repo merge).

### Cited Findings
- Two tiers explicitly defined: CLAUDE.md:7–21 ("What this repo is"); agent-factory-architecture.md:10–13 (§1.1: "The SDLC pipeline... takes a spec through PM review... its unit of output is a **merged pull request**... The agent factory is this pipeline's foundation, not its product").
- Known mismatch: workflow ends in `register_activity` (factory tier terminus, writing registry manifest), not merged target-repo PR (pipeline tier terminus) — agent-factory-architecture.md:11–12, tracked for spec 005.
- Workflow code: Build→Eval-Gate→Register real; Deploy (`RegistryPromotionWaiterWorkflow`) code-complete but unreachable (no caller, no `pr_merged` signal) — CLAUDE.md:46, docs/00-status.md:19.
- Plan loop signals: `plan_approved`/`plan_rejected` handlers exist (`pipeline_workflow.py:92–100`); `pm_approved`, `security_cleared`, `escalation_*` handlers do not exist — spec 005 gap.
- Bridge parsing: `mode=vibe` rejected as `mode_not_supported` (`webhook_bridge/server.py:178,188`); only `mode=full` accepted.

### Inferences
- Product tier built to narrow plan-review slice only. PM, Quality-Gate, Security-Review, Escalation exist as design text (`docs/70` §2–4), not code.
- Status docs lag code; CLAUDE.md layer table is most current.

### Gaps
- Spec 005 (`pipeline-mode-signals-escalation`) is design-critical but partially implemented; product-tier full implementation blocked on it.

## 8 layers: building blocks and state

### Takeaway
Real: Spec Kit, swe-agent, pm-agent, architect-agent, E2B sandbox, eval gate (v1 coverage), registry. Partial: orchestration (Build→Gate→Register wired, Deploy unreachable), observability (infra only). Stub: template-agent, LiteLLM (configured, bypassed by design).

### Cited Findings
- Spec/Intake: GitHub Spec Kit official, enforced by `swe-agent.verify_spec_exists()` — CLAUDE.md:39, agent-factory-architecture.md:118–134 (§3.1).
- Harness: swe-agent (implement-only, opens PR, ~230 lines, commits via `checkpoint: <task IDs>`), pm-agent (two capabilities: `shape_issue()`, `review_spec()`), architect-agent (`run_architect_stage()` fan-out/judge, N candidates, no E2B sandbox per spec 004 carve-out) — CLAUDE.md:41–43.
- Sandbox: E2B template `swe-agent-sandbox` used by both Temporal (`run_swe_agent_activity`) and GitHub-comment path (`.github/workflows/swe-agent-build.yml`) — CLAUDE.md:44.
- Inference Routing: LiteLLM configured (`config.yaml` has `claude-sonnet`, `claude-sonnet-5`); swe-agent bypasses it (goes direct Anthropic), seat-backed calls also bypass (OAuth token to Anthropic) — CLAUDE.md:45, architecture §3.4 explains the deviation (LiteLLM cannot pool OAuth tokens).
- Eval: `eval.config.py:run_eval()` is v1 binary gate (exit 0 + PR opened + ≥1 `SC-NNN` criterion in spec.md); does NOT score content — docs/00-status.md:20.
- Registry: three agents (swe, pm, architect); manifests all say `status: experimental`, `eval_gate_passed: false` (hand-written, not yet re-registered by automation) — docs/00-status.md:21.
- Observability: env template only; no code feeds Langfuse specifically — docs/00-status.md:22.

## SDLC pipeline: stages and human gates

### Takeaway
Design specifies 6 human gates (PM, Plan, Security, Escalation, plus spec-write and PR-merge outside Temporal). Only Plan gate wired (`plan_approved`/`plan_rejected`); others designed only. Budget exhaustion handling incomplete.

### Cited Findings
- HITL map: four in-workflow signal gates + two outside Temporal — docs/70:113–164 (§1.2).
- Wired: Build→Gate→Register; `plan_approved`/`plan_rejected` handlers exist (orchestration/workflows/pipeline_workflow.py:92–100); `MAX_PLAN_ATTEMPTS=3`, `MAX_BUILD_ATTEMPTS=3` — CLAUDE.md:46–47.
- Not wired: `pm_approved`, `security_cleared`, `escalation_resume`/`escalation_abandon` handlers; escalation pair replaced by bare `ApplicationError` on budget exhaustion — spec 005 item.
- Two swe-agent trigger paths: Temporal (full Build→Gate→Register), GitHub-comment (Build only) — CLAUDE.md:221–227, docs/00-status.md:26–34.
- Deploy code exists but unreachable: `RegistryPromotionWaiterWorkflow` waits on `pr_merged` (never fired) — docs/00-status.md:19.

## Trigger paths

### Takeaway
Two independent paths: `@pm-agent shape` on GitHub issue (terminal, no Temporal), `@pipeline-agent run` on PR via webhook bridge (starts Temporal workflow). Comment path for swe-agent runs Build only (no gate, register, deploy). GitHub App transport; no TLS/auth between local bridge and Temporal.

### Cited Findings
- Entry points: PM issue-shaping (terminal at issue), pipeline run (Temporal) — docs/70:25–28 (§1).
- Bridge (`orchestration/webhook_bridge/`): aiohttp server, reuses swe-agent GitHub App, verifies `X-Hub-Signature-256`, parses `@pipeline-agent run mode=<full|vibe> agent=<name> version=<v>` — docs/70:56–111 (§1.1).
- Grammar enforcement: `mode=vibe` rejected (`mode_not_supported`), only `full` accepted — webhook_bridge/server.py:178,188.
- Deterministic workflow ID: `pipeline/{repo}/{agent_name}/v{version}` — docs/70:563–569 (§6).
- Bridge runs on host with docker-compose, `localhost:7233` connection to Temporal (no auth) — docs/70:58–64.
- `BRIDGE_ALLOWED_REPOS` must stay disposable-repo-only until spec 005 lands (FR-016) — CLAUDE.md:46.
- Reusable-workflow pattern: each trigger calls a reusable workflow (swe-agent-trigger→swe-agent-build, pm-agent-shape-trigger→pm-agent-shape) — CLAUDE.md:228–234.

## Cross-cutting: credentials, tokens, registry, harness rules

### Takeaway
Credential pool (specs 009, 011) leases subscription seats; per-run scoped GitHub App tokens (spec 013) for swe-agent; registry enforced as portability boundary (SKILL.md/MCP); dev-harness hooks (spec 010) gate turns and commits; one fresh context per activity (no cross-stage state).

### Cited Findings
- Credential pool: `CredentialPoolWorkflow` leases seats from `orchestration/credentials/pool.yaml`; Build/architect stage run under `_with_seat` patch, handoff up to `MAX_SEAT_HANDOFFS=4` without charging build/plan budgets — CLAUDE.md:46, specs 009, 011 merged.
- GitHub App token: minted per sandbox run, scoped to target repo only (contents + PRs write, metadata read), no fallback to worker token — CLAUDE.md:41, spec 013 merged.
- Registry enforces SKILL.md/MCP format (not vendor-proprietary) — CLAUDE.md:163–168, `.github/workflows/registry-gate.yml`.
- Dev-harness rules: AF-SPEC (edit under harness/ needs spec dir), AF-SECRET (read .env forbidden), AF-COMMIT (commit needs tests green), AF-REGISTRY (manifest edit prompts approval), AF-HARNESS (hooks edit prompts) — CLAUDE.md:104–110, spec 010 in-flight.
- Cross-activity state: none; only channel is git artifacts, PR comments, Braintrust spans — docs/70:600–651 (§6.1).

## Specs 001–014: inventory and status

### Takeaway
14 specs: 3 implemented (009, 011, 013, 014—but status lines not updated), 1 partial (005 plan-review only), 10 draft. Spec 012 missing from `specs/` (exists in git history as feature branch). Build order for product tier: 004→005→006→007 (004 done, 005 partial, 006–007 draft); foundation features (009, 011, 013, 010, 014) landing in parallel.

### Cited Findings
| Spec | Status (code) | Status (spec.md) | Evidence |
|------|---|---|---|
| 001 agent-spec-schema-test | Draft | Draft | Tests deleted schema; cleanup candidate (docs/00-status.md:15) |
| 002 webhook-trigger-bridge | Real | Draft | Bridge code in `orchestration/webhook_bridge/` (docs/70:56–111) |
| 003 pm-agent-review-gate | Real | Draft | `harness/pm-agent/` exists, no Temporal wiring yet (CLAUDE.md:42) |
| 004 architect-fanout-judge | Real | Draft | `run_architect_stage()` exists, not gated (commit f8464bb) |
| 005 pipeline-mode-signals-escalation | Partial | Draft | Only plan handlers + budgets; no `mode` param, PM/security/escalation gates (CLAUDE.md:210–216) |
| 006–007 quality-gate, automated-security-review | Draft | Draft | Spec.md only; no code (CLAUDE.md:215–216) |
| 008 gate-decision-core | Draft | Draft | Spec only (CLAUDE.md:219) |
| 009 credential-pool-handoff | Real | Implemented | Merged d15b85d; `CredentialPoolWorkflow` + seat handoff (CLAUDE.md:46) |
| 010 dev-harness-hardening | Real | Draft | Merged 7d005ba; hooks in `.claude/hooks/` (CLAUDE.md:85–99) |
| 011 seat-pool-hardening | Real | Implemented | Merged 40a2c40; pool wait, reset tracking, per-task sessions (CLAUDE.md:47) |
| 012 — | Not in specs/ | — | Git history shows feature branch; no `specs/012-*` on main |
| 013 sandbox-app-token | Real | Draft | Merged 98b66fb; scoped per-sandbox token (CLAUDE.md:41) |
| 014 test-workflow-cleanup | Real | Draft | Merged 704ed29; 2-minute workflow limit, end-by-ID (git log) |

## Open questions and known gaps

### Takeaway
Four blocking gaps: spec 005 (no `mode` param, no escalation signals, no PM/security gates—blocks product tier wiring); Deploy unreachable (no `pr_merged` signal sender); escalation-on-budget-exhaustion unimplemented; LiteLLM configured but bypassed by design.

### Cited Findings
- Spec 005 blocks product-tier completion: no `mode` param in workflow, no PM/security/escalation signal handlers, no escalation pair replacing `ApplicationError` — CLAUDE.md:210–216, docs/70:695–729 (§9).
- Deploy unreachable: `RegistryPromotionWaiterWorkflow` exists, code-complete, but nothing starts it or fires `pr_merged` signal — docs/00-status.md:19, docs/60:158–163.
- Escalation signal pair (`escalation_resume`/`escalation_abandon`) unimplemented; today budget exhaustion raises bare `ApplicationError` — docs/70:571–598 (§6).
- LiteLLM convention violation: swe-agent goes direct-to-Anthropic, not through proxy; proxy fully configured but unused — docs/00-status.md:18, docs/60:182–184.
- Repo is single-operator, supervised only; subscription-seat pooling is "internal use only" (specs/009 usage constraint) — CLAUDE.md:41, agent-factory-architecture.md:168.
- Not verified: spec `tasks.md` completion status, test pass/fail, Teams workspace design implementation gap.
