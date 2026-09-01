# Layer status — designed vs. actual

Reference table for the whole `docs/` set. "Designed" summarizes the
building-block choice from `agent-factory-architecture.md` §3.x; "Actual"
and "Evidence" are file-cited, not taken from `CLAUDE.md`'s table on faith —
every row below was re-verified against the source file during this
documentation pass.

| Layer | Dir | Designed (§3.x) | Actual | Status | Evidence |
|---|---|---|---|---|---|
| Spec/Intake | `spec/` | Composio/Nango transport + Slack/Teams + HumanLayer/gotoHuman touchpoint + bespoke schema/triage (§3.1) | JSON Schema (`schema/agent-spec.schema.json`) and `triage-policy.md` fully written; triage policy's own text says escalation routing "not implemented in this scaffold yet" | 🟡 partial | Schema + policy exist as documents; only runtime check is `tests/test_agent_spec_schema.py` (template/schema key drift, not full validation) |
| Harness/Runtime | `harness/` | Claude Agent SDK (§3.2) | `template-agent/agent.py`: stub, literal `# TODO: bind tools...`. `swe-agent/agent.py`: real, ~190 lines, implement-only | 🟢 real (swe-agent) / ⚪ stub (template-agent) | `agent.py` files read directly; `swe-agent`'s `run()` orchestrates 7 helper functions end to end |
| Execution Sandbox | `sandbox/` | E2B (§3.3) | `Dockerfile` builds `harness/template-agent`, not `swe-agent`; `e2b.toml` configured; nothing invokes either | ⚪ stub | `sandbox/Dockerfile` COPYs `template-agent/*`; `swe-agent` clones into a host tempdir instead (`agent.py:run`) |
| Inference Routing | `litellm/` | LiteLLM self-hosted proxy, all model calls routed through it (§3.4) | `config.yaml` defines one working `claude-sonnet` route; `swe-agent` calls the Claude Agent SDK's `query()` directly against Anthropic, bypassing the proxy entirely | 🟡 partial — **and a convention violation** | `litellm/config.yaml` is complete and runnable; `swe-agent/agent.py` has no `LITELLM_BASE_URL` reference anywhere, contradicting `CLAUDE.md`'s stated "model calls never take a provider key directly" rule |
| Orchestration | `orchestration/` | Temporal sequences both the pipeline and each agent's task loop (§3.5) | `worker.py` registers `AgentPipelineWorkflow` + `run_swe_agent_activity`; `pipeline_workflow.py`'s `run()` wires **only** the Build step, `maximum_attempts=1` | 🟡 partial | `pipeline_workflow.py` read directly — no Sandbox Test/Eval-Gate/Deploy activity exists to register |
| Eval/Gating | `eval/` | Braintrust (gate) + Langfuse (trace store) (§3.6) | `gate-policy.md` fully written (promotion threshold, fail-routes-to-Build, ongoing prod scoring); `braintrust/eval.config.py`'s two functions both `raise NotImplementedError` | ⚪ stub | `eval.config.py` read directly — `load_success_criteria` and `run_eval` are both unconditional raises; `make gate` will always fail |
| Deployment/Lifecycle | `registry/` | Git-backed catalog + CI gate (§3.7) | `registry-gate.yml` real and functional (every `registry/agents/*/` must have `manifest.yaml` + non-empty `versions/`); one live entry, `swe-agent` | 🟡 partial | `manifest.yaml`: `status: experimental`, **`eval_gate_passed: false`**, `requires_human_supervision: true` — a hardcoded default, not a scored result, since nothing upstream in `eval/` can currently produce `true` |
| Observability | `observability/` | Langfuse (§3.8) | Just `langfuse.env.example`; Langfuse service itself runs via root `docker-compose.yml` (postgres + clickhouse + langfuse) | 🟡 partial | Infra is fully up and configured (same shape as the LiteLLM row above); no trace-emission code anywhere in `harness/swe-agent` or `orchestration/` feeds it |

## Cross-cutting facts worth carrying into every diagram

- **The one real path through the system** is: a human manually completes
  Spec Intake (writes `specs/NNN-slug/` via Spec Kit) → assigns/triggers
  `swe-agent` → `swe-agent` clones, implements, commits, pushes, opens a PR
  → a human reviews and merges outside the factory's control. Sandbox,
  Eval/Gate, Registry-auto-registration, Deploy, and Observability are not
  in that path today.
- **`eval_gate_passed: false` is not evidence of a failing eval** — it is
  the only value the field could ever hold right now, since `run_eval`
  raises unconditionally. Any documentation or dashboard that reads this
  field as a quality signal would be wrong.
- **The LiteLLM bypass is a documented-by-omission deviation**, not a
  stub — the proxy is fully configured and runnable; `swe-agent` simply
  doesn't call it.
