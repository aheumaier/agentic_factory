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

Portable copy of `harness/swe-agent/SKILL.md` — the registry entry per
`registry/README.md`'s documented layout. Keep the two in sync.

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
