# Best practices — completing the scaffold

No diagrams on this page — checklists and conventions, cross-referenced to
the design docs' §-numbering so this stays navigable as the codebase grows.

## 1. Per-layer "definition of done"

Each item below is what should be true before that layer's status in
[`00-status.md`](./00-status.md) can move from stub/partial to real.

**Spec/Intake (§3.1 — superseded)**
- [x] Fulfilled by GitHub Spec Kit (`.specify/` + `specs/NNN-slug/`), the
      official and only supported intake flow, enforced at runtime by
      `swe-agent`'s `verify_spec_exists()`. The original §3.1 design
      (bespoke `spec/` schema + `triage-policy.md`, Composio/Nango
      transport, Slack/Teams + HumanLayer/gotoHuman escalation) is
      retired — do not rebuild it.
- [ ] Only remaining action item: delete `tests/test_agent_spec_schema.py`,
      which still tests the deleted `spec/` schema and fails
      unconditionally.

**Harness/Runtime (§3.2)**
- [ ] `template-agent/agent.py` gets real tool bindings and a real system
      prompt, or is removed if `swe-agent` remains the only harness needed
      for now — a stub with no consumer is a maintenance cost with no
      benefit.
- [ ] `swe-agent` gains the CI-wait/retry loop and reviewer-re-entry path
      from `agent-swe-design.md` §5/§8 (see [`40-sequence-swe-agent-runtime.md`](./40-sequence-swe-agent-runtime.md)
      for exactly what's missing).

**Execution Sandbox (§3.3)**
- [x] `swe-agent`'s clone/implement/verify/commit sequence runs inside the
      E2B container defined by `sandbox/swe-agent/e2b.toml`, built from
      `harness/swe-agent` — done for **both** trigger paths now: the
      GitHub-comment trigger (`.github/workflows/swe-agent-build.yml`, via
      `@e2b/cli`) and the Temporal trigger (`run_swe_agent_activity`, via
      the `e2b` Python SDK's `AsyncSandbox`). No host-tempdir path remains.
- [x] The same argument-injection guards `agent.py`'s `_validate_repo`/
      `_validate_branch` already apply survive the move into a sandboxed
      entrypoint — unchanged code path, same guards. `orchestration/activities.py`
      additionally re-validates `repo`/`branch` itself before they reach a
      `shlex.join`-built sandbox command.
- [x] `sandbox/swe-agent/Dockerfile` now `pip install`s `braintrust>=0.36.0`
      alongside `claude-agent-sdk` — the earlier `ImportError` gap is
      fixed.
- [ ] Reconcile the two independent invocation mechanisms — the Temporal
      path (`orchestration/activities.py`, Python `e2b` SDK) and the
      GitHub-comment path (`swe-agent-build.yml`, `@e2b/cli` shelled out
      from bash) — into one, or document why both need to exist
      long-term. Today a change to sandbox lifecycle handling (timeouts,
      env vars passed in) has to be made in two places.

**Inference Routing (§3.4)**
- [ ] `swe-agent` (and any future harness) calls the LiteLLM proxy
      (`LITELLM_BASE_URL`) instead of the Anthropic API directly — closing
      the one documented convention violation in this repo. This is a
      genuinely small change (the Claude Agent SDK already supports a
      custom base URL); it's flagged as "partial" rather than "stub"
      specifically because the proxy side is already done.

**Orchestration (§3.5)**
- [x] Sandbox Test is collapsed into the Build activity (`run_swe_agent_activity`);
      Eval/Gate (`eval_gate_activity`) and Register (`register_activity`)
      are real activities wired into `pipeline_workflow.py`'s
      `AgentPipelineWorkflow`, in the order §2 specifies, including the
      Eval/Gate-fail-routes-to-Build loop (`MAX_BUILD_ATTEMPTS=3`, gate
      `reason` fed back as `feedback`).
- [x] A real, considered retry policy exists per step: `_NO_AUTO_RETRY`
      (`maximum_attempts=1`) on the two side-effecting activities
      (Build, Register — pushing a branch/opening a PR isn't idempotent
      enough for Temporal's own retries), `_TRANSIENT_RETRY` (backoff,
      up to 4 attempts) on the read-only Eval-Gate activity.
- [ ] **Deploy is unreachable.** `promote_agent_activity` and
      `RegistryPromotionWaiterWorkflow` are written and registered on the
      worker, but nothing ever calls `client.start_workflow(RegistryPromotionWaiterWorkflow, ...)`
      or `handle.signal("pr_merged")` — no GH Actions step watches the
      registry PR's merge event and fires the signal. Add that step (e.g.
      a `pull_request` `closed`+`merged==true` workflow filtered to
      `registry/promote-*` branches) before Deploy can be called "wired."
- [ ] Reconcile the GitHub-comment trigger path
      (`.github/workflows/swe-agent-build.yml`) with this workflow — today
      it's a fully separate Build-only path with no Gate/Register/Deploy,
      so a build triggered by a PR comment never reaches the registry at
      all.

**Eval/Gating (§3.6)**
- [x] Braintrust tracing is live — `harness/swe-agent/agent.py` and
      `harness/template-agent/agent.py` both call
      `braintrust.init_logger()` + `auto_instrument()` at import time
      (added by the Braintrust setup wizard).
- [x] Project name reconciled: both `agent.py` files and
      `eval.config.py` now read the same `BRAINTRUST_PROJECT` env var
      (default `"agent-factory-pilot"`) instead of the wizard's `"My
      Project"` literal.
- [x] `load_success_criteria` and `run_eval` are implemented in
      `eval/braintrust/eval.config.py` as a **v1 binary coverage gate** —
      parses `SC-NNN` bullets from `spec.md`, passes iff the sandbox
      exited 0, a PR exists, and at least one criterion was found.
- [ ] This is coverage, not semantic scoring — no per-criterion LLM judge
      or labeled dataset exists yet, so `run_eval` can't tell whether a
      criterion's *content* was actually satisfied. That's the real next
      step for this layer, not project reconciliation (done) or
      `NotImplementedError` removal (done).
- [ ] Wire Braintrust traces to Langfuse per `gate-policy.md`'s "on fail"
      section, so a rejected candidate carries an actionable trace back to
      Build, not just the plain-text `reason` string currently passed as
      `feedback`.

**Deployment/Lifecycle (§3.7)**
- [x] Registry entry creation/update on a passing Eval/Gate is automated:
      `register_activity` opens a PR against this repo writing
      `manifest.yaml`/`versions/vN.yaml` from the real gate result,
      instead of a human hand-writing them.
- [ ] Wire the actual Deploy trigger — `promote_agent_activity` and
      `RegistryPromotionWaiterWorkflow` exist but nothing starts the
      workflow or signals `pr_merged` on registry-PR merge (see
      Orchestration checklist above). Until that exists, `status: active`
      never happens automatically.
- [ ] Add a rollback/retire path — `registry-gate.yml` only checks shape on
      PR, it doesn't manage the lifecycle after merge.

**Observability (§3.8)**
- [ ] Emit traces from `swe-agent`'s tool calls and model calls to Langfuse
      specifically — the infra (`docker-compose.yml`'s
      langfuse/postgres/clickhouse services) is already running with
      nothing feeding it. The new Braintrust tracing (see Eval/Gating
      above) is a separate service and doesn't satisfy this item.

## 2. Cross-cutting conventions already established — replicate these

- **§-number cross-referencing.** Every file in `harness/swe-agent/`,
  `orchestration/`, `registry/agents/swe-agent/` cites the specific
  `agent-factory-architecture.md` §3.x or `agent-swe-design.md` §N section
  it implements, in a code comment or doc header. New layer work should do
  the same — it's how a scaffold this thin stays navigable without a
  separate index.
- **Spec Kit gates all feature work.** `/speckit-specify → /speckit-plan →
  /speckit-tasks` must produce a `specs/NNN-slug/` directory *before* any
  implementation branch exists (see `specs/001-agent-spec-schema-test/` for
  the one complete example, all tasks checked off). `swe-agent` itself
  enforces this at runtime via `verify_spec_exists()` — don't hand-write a
  feature's code without a matching `specs/NNN-slug/` behind it.
- **`registry-gate.yml`'s pattern is the template for future gates.** It's
  a small, focused CI check enforcing one directory-shape invariant
  ("every `registry/agents/*/` has a manifest and a version"). The same
  shape — a CI job asserting a structural invariant on PRs touching a given
  path — is the right model for a future `eval-gate.yml` (e.g., "every
  spec with `guardrails.requires_human_approval` non-empty has a
  corresponding sign-off record") or `sandbox-gate.yml`.

## 3. Open gaps / risks (carried forward from `00-status.md`, stated plainly)

- **Deploy is code-complete but structurally unreachable.**
  `promote_agent_activity` and `RegistryPromotionWaiterWorkflow` exist and
  are registered on the worker, but nothing in this repo ever starts that
  workflow or fires its `pr_merged` signal — there's no GH Actions step
  watching the registry PR's merge event. `manifest.yaml.status` can never
  flip to `active` through automation today, only by hand.
- **`eval_gate_passed` can now be `true`, but only proves coverage, not
  correctness.** `run_eval` is a real, implemented v1 gate — it checks the
  sandbox exited 0, a PR exists, and `spec.md` had success criteria — but
  it doesn't score any criterion's content. Treat a `true` here as "the
  agent ran and produced something with criteria to check," not "the
  criteria were met."
- **The two `swe-agent` trigger paths still don't share a pipeline.** The
  Temporal path (Build→Gate→Register) and the GitHub-comment path
  (Build-only, via `swe-agent-build.yml`) both run inside E2B now, but a
  PR-comment-triggered build never reaches Eval-Gate, Register, or Deploy
  — those only exist on the Temporal path. Both are still documented as
  supervised, not autonomous, per `SKILL.md` and the registry manifest's
  `requires_human_supervision: true`.
- **`spec/` is retired, not a gap.** GitHub Spec Kit is the official
  Spec/Intake flow; the old bespoke `spec/` (schema, template,
  `triage-policy.md`) is a deliberate cleanup candidate, not something to
  restore. `tests/test_agent_spec_schema.py` still tests the deleted
  schema and fails unconditionally — delete it, don't fix it.
- **LiteLLM is fully configured and unused.** Low-effort, high-value fix
  (see Inference Routing checklist above) — the proxy side of this
  integration is already done; only the harness-side call needs to change.
- **The Build→Gate retry loop re-enters on the factory's own coverage
  check, not on the target repo's CI or a human review comment.** A
  failing CI check on an agent-authored PR, or a reviewer's
  requested-changes comment, still has no mechanism to route back into
  the agent at all — only a failed Eval-Gate does.
