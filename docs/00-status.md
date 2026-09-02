# Layer status — designed vs. actual

Reference table for the whole `docs/` set. "Designed" summarizes the
building-block choice from `agent-factory-architecture.md` §3.x; "Actual"
and "Evidence" are file-cited, not taken from `CLAUDE.md`'s table on faith —
every row below was re-verified against the source file during this
documentation pass.

| Layer | Dir | Designed (§3.x) | Actual | Status | Evidence |
|---|---|---|---|---|---|
| Spec/Intake | `spec/` | Composio/Nango transport + Slack/Teams + HumanLayer/gotoHuman touchpoint + bespoke schema/triage (§3.1) | **Directory no longer exists.** Schema, template, and `triage-policy.md` were all deleted from the working tree before this documentation pass | ⚪ empty | `spec/` is absent from this checkout; `tests/test_agent_spec_schema.py` now fails unconditionally with `FileNotFoundError` as a result |
| Harness/Runtime | `harness/` | Claude Agent SDK (§3.2) | `template-agent/agent.py`: still a stub (`# TODO: bind tools...`), now also calls `braintrust.init_logger()`/`auto_instrument()` at import time. `swe-agent/agent.py`: real, ~230 lines, implement-only; `clone_and_checkout()` now authenticates via a `GH_TOKEN` env var (GitHub App installation token) when set, falling back to the host's ambient `gh` credential helper otherwise; same Braintrust tracing calls added | 🟢 real (swe-agent) / ⚪ stub (template-agent) | `agent.py` files read directly; token-scrub helper `_scrubbed()` rebuilds a clean `CalledProcessError` so a failed authenticated clone can't leak the token via `args`/`cmd`/`output`/`stderr` |
| Execution Sandbox | `sandbox/` | E2B (§3.3) | `sandbox/swe-agent/Dockerfile` + `e2b.toml` built and proven end-to-end (commit `e505938`). Now actually invoked, but only from one of two trigger paths: `.github/workflows/swe-agent-build.yml` creates/execs/kills an E2B sandbox running `agent.py` for a GitHub PR-comment trigger. The Temporal-triggered path still runs `agent.py` in a host tempdir, bypassing the sandbox entirely | 🟡 partial — real for the GH-comment trigger, stub for the Temporal trigger | `sandbox/swe-agent/Dockerfile` `pip install`s `claude-agent-sdk` but not `braintrust`, even though `agent.py` now imports it unconditionally — **a GH-triggered sandbox run will `ImportError` until the image is rebuilt with that dependency added** |
| Inference Routing | `litellm/` | LiteLLM self-hosted proxy, all model calls routed through it (§3.4) | `config.yaml` defines one working `claude-sonnet` route; `swe-agent` calls the Claude Agent SDK's `query()` directly against Anthropic, bypassing the proxy entirely | 🟡 partial — **and a convention violation** | `litellm/config.yaml` is complete and runnable; `swe-agent/agent.py` has no `LITELLM_BASE_URL` reference anywhere, contradicting `CLAUDE.md`'s stated "model calls never take a provider key directly" rule |
| Orchestration | `orchestration/` | Temporal sequences both the pipeline and each agent's task loop (§3.5) | `worker.py` registers `AgentPipelineWorkflow` + `run_swe_agent_activity`; `pipeline_workflow.py`'s `run()` wires **only** the Build step, `maximum_attempts=1`. This path and the newer GitHub-comment trigger (`.github/workflows/swe-agent-build.yml`) are two independent, unreconciled ways to invoke `agent.py` — only the latter runs inside the E2B sandbox | 🟡 partial | `pipeline_workflow.py` read directly — no Sandbox Test/Eval-Gate/Deploy activity exists to register |
| Eval/Gating | `eval/` | Braintrust (gate) + Langfuse (trace store) (§3.6) | `gate-policy.md` fully written (promotion threshold, fail-routes-to-Build, ongoing prod scoring); `braintrust/eval.config.py`'s two functions still both `raise NotImplementedError` — the promotion gate itself remains unimplemented. Separately, both `agent.py` files now call `braintrust.init_logger(project="My Project")` + `braintrust.auto_instrument()` (added by the Braintrust setup wizard) — this is live tracing, not gating | 🟡 partial — tracing real, gate still stub | `eval.config.py` read directly: still unconditional raises, so `make gate` will always fail. **Project-name mismatch:** the wizard's `init_logger` calls use the literal `"My Project"`; `eval.config.py`'s `PROJECT` constant is `"agent-factory-pilot"` — two different Braintrust projects, never reconciled |
| Deployment/Lifecycle | `registry/` | Git-backed catalog + CI gate (§3.7) | `registry-gate.yml` real and functional (every `registry/agents/*/` must have `manifest.yaml` + non-empty `versions/`); one live entry, `swe-agent` | 🟡 partial | `manifest.yaml`: `status: experimental`, **`eval_gate_passed: false`**, `requires_human_supervision: true` — a hardcoded default, not a scored result, since nothing upstream in `eval/` can currently produce `true` |
| Observability | `observability/` | Langfuse (§3.8) | Just `langfuse.env.example`; Langfuse service itself runs via root `docker-compose.yml` (postgres + clickhouse + langfuse) | 🟡 partial | Infra is fully up and configured (same shape as the LiteLLM row above); no trace-emission code anywhere in `harness/swe-agent` or `orchestration/` feeds *Langfuse* specifically — the new Braintrust tracing (Eval/Gating row above) is a separate service and does not feed this layer |

## Cross-cutting facts worth carrying into every diagram

- **There are now two independent trigger paths for `swe-agent`, with
  different guarantees.** A human manually completes Spec Intake (writes
  `specs/NNN-slug/` via Spec Kit; note this is Spec *Kit*, unrelated to the
  now-deleted `spec/` directory), then either (a) a Temporal activity runs
  `agent.py` unsandboxed in a host tempdir using the ambient `gh` session,
  or (b) a collaborator comments `@swe-agent build` on a PR, which runs
  `agent.py` inside an E2B sandbox authenticated via a scoped GitHub App
  token (`.github/workflows/swe-agent-build.yml`). Either way, the agent
  clones, implements, commits, pushes, opens a PR, and a human reviews and
  merges outside the factory's control. Eval/Gate scoring, Registry
  auto-registration, Deploy, and Langfuse Observability are not in either
  path today.
- **`eval_gate_passed: false` is not evidence of a failing eval** — it is
  the only value the field could ever hold right now, since `run_eval`
  raises unconditionally. Any documentation or dashboard that reads this
  field as a quality signal would be wrong.
- **Braintrust tracing is now live, but is not the same thing as the
  Eval/Gate.** `agent.py`'s `braintrust.auto_instrument()` call and
  `eval/braintrust/eval.config.py`'s gate logic are separate, currently
  disconnected pieces — traces flow to a Braintrust project literally
  named `"My Project"` (the setup wizard's default, never renamed); the
  gate script (still all `NotImplementedError`) targets a different
  project, `"agent-factory-pilot"`, and would need to actually run to
  score anything either way.
- **The LiteLLM bypass is a documented-by-omission deviation**, not a
  stub — the proxy is fully configured and runnable; `swe-agent` simply
  doesn't call it.
- **`spec/` no longer exists in this checkout.** Its removal (schema,
  template, and `triage-policy.md` all deleted) predates this
  documentation pass and wasn't part of any change described here;
  `tests/test_agent_spec_schema.py` fails unconditionally as a result and
  hasn't been removed or fixed.
