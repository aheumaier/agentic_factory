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

## Subscription seats and resume (specs/009, hardened in specs/011)

On the Temporal path (`run_swe_agent_activity`), the agent runs on a Claude
Max subscription seat leased from the credential pool. The sandbox receives
the seat's OAuth token as `CLAUDE_CODE_OAUTH_TOKEN`, with no API key, and
`seat_guard.py` makes it the only credential the CLI sees. Calls go direct to
Anthropic, a documented §3.4 deviation.

- **Checkpoints (specs/011).** The run prompt tells the model to skip tasks
  already marked `[X]` and to mark each task `[X]` as soon as it finishes it.
  The harness, not the model, then saves the checkpoint: after every streamed
  message, when the feature's set of done task IDs has grown and the tree is
  dirty, `agent.py` commits it as `checkpoint: T001 …`. If the model already
  committed, nothing more is committed. Edits left after the last tick are
  committed as `checkpoint: end of run` on a normal finish. Commits are
  local; the push happens later. Without a configured git identity, the
  commit uses `swe-agent <swe-agent@users.noreply.github.com>`.
- **Seat outcomes.** If the seat runs out (`SeatExhausted`) or its token is
  rejected (`SeatInvalid`) mid-run, `agent.py` pushes every commit on the
  branch and prints a `{"seat_status": …}` JSON line last. It then exits
  **75** (exhausted) or **77** (invalid), and the workflow re-runs Build on
  another seat. It refuses to push `main`/`master`. If that push fails, it
  exits 1, so a seat outcome never hides lost work.
- **Resume.** The successor clones the pushed branch and continues from the
  first open task. If the feature's `tasks.md` is already fully checked, and
  this is not a Gate-feedback retry, it skips straight to opening the PR. A
  successor seat (`SEAT_HANDOFF_INDEX` > 0, set by the workflow) with every
  task done skips the "made no new commit" check, because its predecessor may
  already have pushed this attempt's work (e.g. a Gate-feedback fix).
- **Usage reading.** Every `seat_status` line also carries
  `utilization_resets_at`, the reset time of the usage window the reading
  came from. The pool stops counting the reading after that time.
- **Force hook.** `SEAT_GUARD_FORCE_EXHAUST_AFTER_COMMITS=N` forces exhaustion
  after N commits, harness checkpoints included, as a live-handoff test hook
  (quickstart V5). The worker forwards it when the seat matches
  `SEAT_GUARD_FORCE_EXHAUST_SEAT`, or when the handoff index matches
  `SEAT_GUARD_FORCE_EXHAUST_HANDOFF`. Seat selection cannot route around the
  handoff index.

**Usage constraint (binding):** internal, single-operator use only. The seats belong to the operator running this pipeline; neither the pipeline nor its seats are ever offered to third parties (Agent SDK terms). Rotating several subscription seats is a Consumer-Terms grey area the operator accepted knowingly (2026-10-10). This is not a supported product feature; see `specs/009-credential-pool-handoff/spec.md` and `specs/011-seat-pool-hardening/spec.md`.

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

### Seat-pool gaps (specs/009, 011)

- **The GitHub-comment path (`swe-agent-build.yml`) still uses the API key.**
  Seat mode, checkpoint pushes and exit codes 75/77 apply only to the
  Temporal path; without `CLAUDE_CODE_OAUTH_TOKEN` the agent behaves as before.
- **Waiting for a reset is bounded (specs/011).** When every eligible seat is
  out, the workflow waits durably for the earliest reset, but only if that
  reset is at most 6 h away, and at most twice per stage. A later reset, or a
  pool with only invalid seats, still fails with `CredentialPoolExhausted`.
- **Token expiry is a log line only (specs/011).** The worker logs a warning
  at startup for any seat within 14 days of `token_expires_on`, and the
  pool's `seats()` table shows `expires_in_days`. Nothing posts to a PR or to
  Teams. An expired token surfaces as `SeatInvalid`; after renewing it, the
  operator runs `reset_seat`.
- **Tick granularity is the model's.** If the model marks several tasks
  `[X]` in one edit, they land in one checkpoint, so a handoff can still
  redo at most the tasks in that batch.
