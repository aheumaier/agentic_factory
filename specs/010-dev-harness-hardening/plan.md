# Implementation Plan: Dev-Harness Hardening

**Branch**: `010-dev-harness-hardening` | **Date**: 2026-10-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/010-dev-harness-hardening/spec.md`

## Summary

**Replanned 2026-10-10** to fold in research.md R14: User Story 4 (context budget and
continuity), plus a Story 1 fix that adopts a pending snapshot across `/clear`.

Harden this repo's Claude Code harness in four slices.

- **P1: turn-scoped gate.** A `UserPromptSubmit` hook fingerprints every
  Python-relevant file into a per-worktree, per-session snapshot. `Stop` diffs
  against it, so a turn is judged only on what it changed, by any tool, including
  shell edits. The per-edit hook drops to file-local ruff only. All `uv run` calls
  become `--locked`/`--frozen`, so no gate can rewrite a lockfile. A snapshot left
  pending by an earlier session (an interrupted turn, then `/clear`) is **adopted**,
  not replaced. Both turn-start and Stop adopt it, so a `session_id` change mid-turn
  can't orphan the baseline either (research R14 details).
- **P2: policy as deterministic checks.** A single PreToolUse script refuses edits
  under `harness/`, `orchestration/` and `eval/` without a matching spec (AF-SPEC),
  secret reads (AF-SECRET), and red commits (AF-COMMIT). Every refusal carries a
  rule ID and a remediation. Confirmations (registry, AF-REGISTRY; harness
  self-edits, AF-HARNESS / FR-026) are `permissions.ask` rules, because the docs guarantee
  they prompt even in auto mode, which they don't for hook `ask` (research R1).
- **P3: drift test.** An ordinary pytest module checks CLAUDE.md and the reviewer
  prompt against the tree: registry entries, `specs/NNN-slug` paths, code
  identifiers, and an explicit `(pending NNN)` marker for in-flight work. It lands
  after the six known stale facts are fixed.
- **P3: context budget (US4).** Four parts, none of which ever blocks (FR-031):
  - **Cap**: the settings `env` sets `CLAUDE_CODE_AUTO_COMPACT_WINDOW=150000`
    (FR-027).
  - **Warn**: turn-start reads the last assistant `usage` from the tail of the
    transcript and warns operator and agent once per level, at 120k and at 150k
    (FR-028).
  - **Continuity**: a `SessionStart` hook (`compact|clear`) runs
    `session-context.sh`, which injects branch, spec dir, the next 3 tasks, gate
    state and rule IDs (FR-029).
  - **Rules**: a CLAUDE.md "Context budget" section (FR-030).

## Technical Context

**Language/Version**: Bash (hooks; bash 3.2-compatible, because macOS `/bin/bash` is
3.2) plus Python 3.11+ (tests). Root venv is currently CPython 3.12.

**Primary Dependencies**: Claude Code 2.1.285 hooks/permissions, `jq` 1.8,
`uv` 0.10.0, `git`, `ruff` ≥ 0.17, `pytest`. No new Python dependencies.

**Storage**: per-worktree state dir `$(git rev-parse --git-path claude-harness)/`.
It holds the snapshot, the exception-notice marker and the context-level marker
(research R3/R14, data-model.md). Read-only input: the session transcript at the
payload's `transcript_path` (internal format, read best-effort).

**Testing**: root `uv run pytest` (new `tests/test_harness_hooks.py`,
`tests/test_context_drift.py`). `orchestration` suite gains a `temporal` marker
only.

**Target Platform**: operator's macOS host, and the `swe-agent` E2B sandbox image
(Debian, `python:3.11-slim`) when the target repo is this repo.

**Project Type**: developer tooling (hook scripts + config + tests). No runtime
service.

**Performance Goals**: per-edit feedback < 2s (measured 0.43s). Snapshot 0.03s.
Context warn step is constant-cost (`tail -n 200` + one `jq` pass), whatever the
transcript size.
Stop/commit gate ≈ 6s (`tests/` 0.8s + `orchestration/` **5.2s measured**; the
spec's 1.8s assumption is stale, see research R12).

**Constraints**:
- Fail closed: bash entry point, exit 2 when a required tool is missing.
- No lockfile writes (`--locked`).
- No test-only seams in hook code (tests stub `uv` via `PATH`).
- One PreToolUse script, so no parallel-decision merging.
- Never block a prompt or a compaction. turn-start and session-context always exit 0,
  and their stdout is either empty or a single valid JSON object. There's no
  PreCompact hook.

**Scale/Scope**: 45 Python-relevant files today. 4 hook scripts, 1 settings file,
2 test modules, 3 marked test modules, 3 doc fixes (CLAUDE.md, reviewer prompt,
`eval/gate-policy.md`).

No `NEEDS CLARIFICATION` remains. All were resolved in [research.md](./research.md).
Items the docs leave open are marked *[unverified]* there, and the design is correct
either way.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**N/A.** `.specify/memory/constitution.md` is the unfilled Spec Kit template (no
ratified principles). The spec lists ratifying it as a follow-up (Out of Scope). The
binding constraints come from CLAUDE.md instead, and this plan checks against them:

| CLAUDE.md constraint | Status |
|---|---|
| Feature work planned with Spec Kit before code | ✔ this directory; AF-SPEC turns the rule into a check |
| Root `pyproject.toml` is dev/test tooling only | ✔ no new deps; the `temporal` marker goes in `orchestration/pyproject.toml` (that suite's own config) |
| Ruff + both suites stay green; hooks enforce | ✔ strengthened (turn-scoped + commit gate) |
| Registry written by `register_activity` | ✔ AF-REGISTRY confirmation |
| Model calls via LiteLLM | n/a (no model calls) |

**Post-design re-check (after the US4 replan)**: unchanged. US4 adds one hook script
and a settings `env` key. It adds no service, dependency or layer.

## Project Structure

### Documentation (this feature)

```text
specs/010-dev-harness-hardening/
├── spec.md
├── plan.md                       # this file
├── research.md                   # R1–R14 decisions
├── data-model.md                 # turn snapshot (+adopt), policy rule, exception, drift assertion, context budget, continuity context
├── quickstart.md                 # validation scenarios
├── contracts/
│   ├── hook-interface.md         # events, payload fields, outputs, rule messages
│   └── drift-conventions.md      # D-REG / D-SPEC / D-ID grammar + (pending NNN)
├── checklists/requirements.md
└── tasks.md                      # /speckit-tasks (not created here)
```

### Source Code (repository root)

```text
.claude/
├── settings.json                 # + UserPromptSubmit, PreToolUse, SessionStart(compact|clear), permissions.{ask,deny},
│                                 #   env.CLAUDE_CODE_AUTO_COMPACT_WINDOW; edit timeout 60
├── hooks/
│   ├── lib.sh                    # NEW: require_tools, run_check, trim_pytest, run_suites, state_dir, rel_path,
│   │                             #   resolve_snapshot (adopt), feature_spec_dir, CTX_BUDGET/CTX_WARN
│   ├── py-check.sh               # REWRITE: modes turn-start (snapshot/adopt + context warn) | edit (ruff only) | stop (adopt + snapshot diff)
│   ├── policy.sh                 # NEW: PreToolUse — AF-SECRET → AF-SPEC → AF-COMMIT
│   └── session-context.sh        # NEW: SessionStart(compact|clear) — continuity additionalContext
└── agents/py-codereviewer.md     # (pending 009) markers, §2 commands use --locked, harness section

tests/
├── test_harness_hooks.py         # NEW: Story 1, 2 and 4 scenarios via subprocess, stub uv on PATH, fixture transcripts
└── test_context_drift.py         # NEW: Story 3 (D-REG, D-SPEC, D-ID)

orchestration/
├── pyproject.toml                # + [tool.pytest.ini_options] markers = ["temporal: …"]
├── tests/test_pipeline_workflow.py                  # + pytestmark = pytest.mark.temporal
└── webhook_bridge/tests/{test_integration,test_e2e_pipeline_gate}.py   # + pytestmark

CLAUDE.md                         # FR-011, FR-023(a–d), FR-024 harness section + rule catalogue, FR-030 "Context budget" section
eval/gate-policy.md               # FR-023(e): describe the v1 SC-NNN binary coverage gate
sandbox/swe-agent/Dockerfile      # FR-025: jq + uv 0.10.0 (already in working tree)
```

**Structure Decision**: no new top-level directories. Hook logic stays in
`.claude/hooks/` as bash, with shared code factored into `lib.sh`. Tests go in the
existing root `tests/` suite, so the Stop gate itself runs them.

## Implementation Order (constraints for `/speckit-tasks`)

The existing T001–T039 phase order and its rationale stay as they are. `tasks.md`'s
"Phase order is deliberate" section still applies. US4 slots in as marked.

1. **Foundations first**: `lib.sh`, the `temporal` marker, and the test fixture
   (tmp git repo + stub `uv`). `lib.sh` also gets `resolve_snapshot`,
   `feature_spec_dir` and `CTX_BUDGET`/`CTX_WARN` here, so later phases only call
   them.
2. **P1 (US1)**: rewrite `py-check.sh` (turn-start/edit/stop) and its tests, and wire
   UserPromptSubmit and the new edit timeout in settings.json. **Snapshot adoption
   is US1 work**: turn-start and stop both go through `resolve_snapshot`, with tests
   for adopt-after-`session_id`-change, prune-before-adopt (>7 days discarded) and
   multiple-pending (oldest adopted, rest deleted) (SC-010).
3. **P3 doc fixes before the drift test (US3)**: FR-023(a)–(f) in CLAUDE.md, the
   reviewer prompt and gate-policy.md, *then* `test_context_drift.py`, so the suite
   never goes red mid-feature.
4. **P2 (US2)**: `policy.sh` and its tests.
5. **US4 scripts**: add the turn-start context warn to `py-check.sh` and create
   `session-context.sh`, each with tests (fixture transcripts with synthetic
   `usage`; feature-branch and off-branch cases). Do this **before** the T036 review
   pass, so that pass covers `session-context.sh` and the warn code while
   `.claude/hooks/**` can still be edited without prompts.
6. **Last settings change**: in one edit, wire PreToolUse, `permissions.ask`/`deny`
   (research R2), **`SessionStart` (`compact|clear`) → `session-context.sh`**, and
   **`env.CLAUDE_CODE_AUTO_COMPACT_WINDOW = "150000"`**. Add settings tests for the
   SessionStart wiring and for env == `CTX_BUDGET`. This step activates AF-HARNESS.
   Any `.claude/` edit after it prompts the operator, so CLAUDE.md's FR-024 harness
   section and FR-030 "Context budget" section are written in the same step or after
   it (CLAUDE.md is not AF-HARNESS-gated).
7. Commit the existing Dockerfile change (FR-025) with the feature.
8. `py-codereviewer` on all `.py` and `.sh` changes before committing (CLAUDE.md).
9. **Live checks for US4** (operator-pending, in T045):
   - whether compaction fires near 150k with the project `env` setting. If it
     doesn't, switch FR-027 to the documented launch-flag fallback;
   - that the warn notice renders;
   - `/clear` continuity and adoption.

## Risks

| Risk | Mitigation |
|---|---|
| `systemMessage` rendering (FR-009 "still red", FR-018 notice) is undocumented | Already relied on by today's Stop hook; quickstart §2.3/§3.7 verify it live |
| `permissions.ask` under `bypassPermissions` (sandbox) has no human to answer | `swe-agent` never edits registry or `.claude/`; recorded as a known limit (R1) |
| Stop may not fire on Esc, leaving a stale pending snapshot | Fails toward checking more; adopted by the next session (incl. after `/clear`), pruned if > 7 days (R3, R14) |
| `CLAUDE_CODE_AUTO_COMPACT_WINDOW` may not be honoured from the project `env` block | Live check (quickstart §6.1). Fallback: CLAUDE.md documents `claude --autocompact 150k` as the launch convention (FR-027) |
| Transcript JSONL is an internal format, so the warn parse may break on upgrade | Fail-silent by contract (FR-028). The cap (FR-027) doesn't depend on it, and a test pins today's shape |
| `session_id` may change across compaction *[unverified]* | `stop` also runs `resolve_snapshot`, so the baseline is adopted, not lost (R14) |
| SessionStart `additionalContext` after `/clear` *[unverified rendering]* | Live check (quickstart §6.3). The output is pure context, so a miss costs only a re-read |
| Bash 3.2 on macOS (no `mapfile`, assoc arrays) | Constraint stated above; tests run under `/bin/bash` |
| Hook `onFailure` field (if the operator upgrades past 2.1.295) | Not used; fail-closed comes from exit 2 |

## Complexity Tracking

No constitution violations to justify (constitution not ratified; see Constitution
Check).
