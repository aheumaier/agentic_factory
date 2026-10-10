---
name: swe-agent
description: >-
  GitHub-issue-driven SWE agent (Harness/Runtime, agent-factory-architecture.md
  §3.2) that runs GitHub Spec Kit's /speckit-implement against an
  already-planned feature branch and opens a PR.
---

# SWE agent

Design source: `agent-swe-design.md` (full design). Guardrails and
workflow behavior are defined in `prompts/agentic-swe.json` — that file is
this agent's system-prompt-as-data; keep the two in sync if either changes.

## Deviations from the full design, this pass

- **Implement-only.** `/speckit-specify` → `/speckit-plan` → `/speckit-tasks`
  (agent-swe-design.md §5 steps 1-3, mapped to Spec/Intake §3.1) happen
  upstream, manually, before this agent runs — committed to
  `specs/NNN-slug/` on a feature branch that already exists. This agent
  starts at `/speckit-implement` (§5 step 4 onward).
- **Host tempdir, not E2B.** Runs unsandboxed in a host temp directory
  this pass (Execution Sandbox, §3.3, is deferred — see repo's
  `sandbox/`, not yet wired to this agent). Reuses this machine's
  already-authenticated `gh` CLI session rather than a scoped token.
- **Direct-to-Anthropic, not LiteLLM-routed.** `/speckit-implement` only
  exists as a Claude Code skill, so this agent is Claude-Agent-SDK/
  Anthropic-only by construction; LiteLLM routing (§3.4) and
  multi-provider support are both deferred, follow-up work.
- **No CI-wait/retry loop.** agent-swe-design.md §5 steps 8-9 and §8's
  bounded-retry policy are not implemented — this agent pushes and opens
  one PR, then stops. A human (or a separate follow-up pass) handles CI
  failures and re-review.

## Subscription seats and resume (specs/009)

On the Temporal path (`run_swe_agent_activity`), the agent runs on a Claude
Max subscription seat leased from the credential pool. The sandbox receives
the seat's OAuth token as `CLAUDE_CODE_OAUTH_TOKEN`, with no API key, and
`seat_guard.py` makes it the only credential the CLI sees. Calls go direct to
Anthropic, a documented §3.4 deviation.

- **Checkpoints.** The run prompt tells the model to skip tasks already
  marked `[X]` and to mark and commit each task as it finishes, without
  pushing.
- **Seat outcomes.** If the seat runs out (`SeatExhausted`) or its token is
  rejected (`SeatInvalid`) mid-run, `agent.py` pushes every commit on the
  branch and prints a `{"seat_status": …}` JSON line last. It then exits
  **75** (exhausted) or **77** (invalid), and the workflow re-runs Build on
  another seat. It refuses to push `main`/`master`. If that push fails, it
  exits 1, so a seat outcome never hides lost work.
- **Resume.** The successor clones the pushed branch and continues from the
  first open task. If the feature's `tasks.md` is already fully checked, and
  this is not a Gate-feedback retry, it skips straight to opening the PR.
- **Force hook.** `SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS=N` forces exhaustion
  after N commits, as a live-handoff test hook (quickstart V5).

**Usage constraint (binding):** internal, single-operator use only. The seats belong to the operator running this pipeline; neither the pipeline nor its seats are ever offered to third parties (Agent SDK terms). Rotating several subscription seats is a Consumer-Terms grey area the operator accepted knowingly (2026-10-10). This is not a supported product feature; see `specs/009-credential-pool-handoff/spec.md`.

## Known gap

Tool access (`Bash`, `Edit`, `Write`, etc. under `bypassPermissions`) is
broad enough that nothing tool-level stops this agent from pushing or
opening its own PR despite being told not to in its run prompt — the
`push_and_open_pr` step in `agent.py` runs from code, after the agent's
`query()` call returns, specifically so that step is *not* left to the
model. The one structural guarantee is that the checkout never ends on
`main`/`master` (`verify_left_main`). Acceptable for one supervised demo
run on the host; not acceptable for repeated/unattended use without the
sandbox isolation `sandbox/` is meant to eventually provide.

### Seat-pool gaps (specs/009)

- **The GitHub-comment path (`swe-agent-build.yml`) still uses the API key.**
  Seat mode, checkpoint pushes and exit codes 75/77 apply only to the
  Temporal path; without `CLAUDE_CODE_OAUTH_TOKEN` the agent behaves as before.
- **No durable sleep-until-reset.** When every eligible seat is out, the run
  fails with `CredentialPoolExhausted` (earliest reset in its details) instead
  of waiting for the reset.
- **No token-expiry alert.** `token_expires_on` in `pool.yaml` is recorded,
  but nothing warns before a seat's `claude setup-token` token expires. An
  expired token surfaces as `SeatInvalid`, and the operator re-runs
  `reset_seat` after renewing it.
