# Best practices — completing the scaffold

No diagrams on this page — checklists and conventions, cross-referenced to
the design docs' §-numbering so this stays navigable as the codebase grows.

## 1. Per-layer "definition of done"

Each item below is what should be true before that layer's status in
[`00-status.md`](./00-status.md) can move from stub/partial to real.

**Spec/Intake (§3.1)**
- [ ] `spec/` (schema, template, `triage-policy.md`) needs to exist again
      before any of the below can be built — the directory was deleted
      from the working tree before this documentation pass; restore or
      rewrite it first.
- [ ] A triage engine reads `spec/triage-policy.md`'s auto-approve/escalate/
      reject rules and evaluates them against a submitted spec — today a
      human applies these rules by eye.
- [ ] Escalation actually routes through a touchpoint (Slack/Teams +
      HumanLayer/gotoHuman per §3.1) instead of stopping at "not implemented
      in this scaffold yet."

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
      `harness/swe-agent` — done, but **only for the GitHub-comment
      trigger** (`.github/workflows/swe-agent-build.yml`). The
      Temporal-triggered path still runs in a host tempdir.
- [x] The same argument-injection guards `agent.py`'s `_validate_repo`/
      `_validate_branch` already apply survive the move into a sandboxed
      entrypoint — unchanged code path, same guards.
- [ ] `sandbox/swe-agent/Dockerfile` needs `pip install braintrust` added
      — `agent.py` now imports it unconditionally at module load, but the
      image only installs `claude-agent-sdk`; a GH-triggered run will
      `ImportError` until this is fixed and the image rebuilt.
- [ ] Wire the Temporal-triggered path into the same E2B sandbox (or
      retire that path) so "sandboxed" isn't conditional on which trigger
      fired.

**Inference Routing (§3.4)**
- [ ] `swe-agent` (and any future harness) calls the LiteLLM proxy
      (`LITELLM_BASE_URL`) instead of the Anthropic API directly — closing
      the one documented convention violation in this repo. This is a
      genuinely small change (the Claude Agent SDK already supports a
      custom base URL); it's flagged as "partial" rather than "stub"
      specifically because the proxy side is already done.

**Orchestration (§3.5)**
- [ ] Add activities for Sandbox Test, Eval/Gate, and Deploy to
      `orchestration/activities.py`, and wire them into
      `pipeline_workflow.py` in the order `agent-factory-architecture.md`
      §2 specifies, including the Eval/Gate-fail-routes-to-Build loop.
- [ ] Decide and document a real retry policy per step (today's
      `maximum_attempts=1` on Build is a placeholder, not a considered
      choice).

**Eval/Gating (§3.6)**
- [x] Braintrust tracing is live — `harness/swe-agent/agent.py` and
      `harness/template-agent/agent.py` both call
      `braintrust.init_logger()` + `auto_instrument()` at import time
      (added by the Braintrust setup wizard). This is tracing, not
      gating — nothing downstream reads these traces yet.
- [ ] Reconcile the project name: tracing goes to `"My Project"` (wizard
      default); `eval.config.py`'s `PROJECT` constant is
      `"agent-factory-pilot"`. Pick one and update the other, or the two
      halves of this layer will keep looking at different data.
- [ ] Implement `load_success_criteria` (parse `success_criteria` from a
      spec) and `run_eval` (score a sandbox trace, raise on regression) in
      `eval/braintrust/eval.config.py` — until both exist,
      `eval_gate_passed` in any manifest is a hardcoded default, never a
      scored result (see [`00-status.md`](./00-status.md)).
- [ ] Wire Braintrust traces to Langfuse per `gate-policy.md`'s "on fail"
      section, so a rejected candidate carries an actionable trace back to
      Build, not a bare fail signal.

**Deployment/Lifecycle (§3.7)**
- [ ] Automate registry entry creation/update on a passing Eval/Gate,
      rather than hand-writing `manifest.yaml`/`versions/vN.yaml`.
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

- **`eval_gate_passed: false` reads as a quality signal but isn't one.**
  Nothing in this repo can currently produce `true` for that field. Any
  dashboard, report, or downstream automation that treats this field as
  meaningful should not be built until `eval/braintrust/eval.config.py` is
  implemented.
- **`swe-agent` runs unsandboxed, with `bypassPermissions` and full `Bash`
  access, in a host tempdir — but only via the Temporal trigger.** The
  GitHub-comment trigger now runs it inside an E2B sandbox instead. Both
  paths are still documented as supervised, not autonomous, per
  `SKILL.md` and the registry manifest's `requires_human_supervision:
  true`.
- **The E2B sandbox image is missing a dependency it now needs.**
  `sandbox/swe-agent/Dockerfile` installs `claude-agent-sdk` but not
  `braintrust`, which `agent.py` now imports unconditionally — a
  GitHub-comment-triggered run will fail at import time until the image
  is rebuilt with that dependency added.
- **Braintrust tracing and the Braintrust eval gate point at two
  different projects.** `agent.py`'s `init_logger(project="My Project")`
  vs. `eval.config.py`'s `PROJECT = "agent-factory-pilot"` — nobody has
  reconciled these, so today's traces aren't even in the project the gate
  script would look at once it's implemented.
- **`spec/` no longer exists.** Schema, template, and `triage-policy.md`
  were deleted from the working tree before this documentation pass, for
  reasons outside this pass's scope; `tests/test_agent_spec_schema.py`
  fails unconditionally as a result and hasn't been fixed or removed.
- **LiteLLM is fully configured and unused.** Low-effort, high-value fix
  (see Inference Routing checklist above) — the proxy side of this
  integration is already done; only the harness-side call needs to change.
- **No CI-wait/retry/re-entry path exists for `swe-agent`.** Every run is a
  single one-shot attempt. A failing CI check on an agent-authored PR
  currently has no mechanism to route back into the agent at all.
