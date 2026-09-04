# Implementation Plan: Architect Fan-Out, Judge, and Completeness-Critic

**Branch**: `004-architect-fanout-judge` | **Date**: 2026-09-04 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-architect-fanout-judge/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

One new registry entry, `registry/agents/architect-agent/`, backing a
single stage entrypoint plus five independently callable capability
functions in `harness/architect-agent/agent.py`. The stage runs
fan-out → score → synthesize → completeness-critic → persist → post,
all inside one process, with every model call a plain Claude Agent SDK
`query()` and **no E2B sandbox anywhere** (`docs/70-multi-agent-pipeline-design.md`
§6.1's carve-out: candidates, judge, and critic only ever produce and
consume markdown, so there is nothing to execute).

The structural guarantees the spec asks for are enforced in Python, not
by prompt instruction — the same "the mutation is code, never left to
the model" pattern `harness/pm-agent/agent.py` established:

1. **Fan-out (FR-001–FR-003)** — `N` candidates run as `N` separate
   `query()` calls awaited together via `asyncio.gather`. Each `query()`
   spawns its own CLI subprocess with its own context, so "no visibility
   into any other candidate's output" (FR-003) holds because there is no
   shared conversation to leak through, not because a prompt says so.
   Candidates get `tools=["Read","Grep","Glob"]` against a shallow clone
   of the branch — enough to read `spec.md` and the surrounding code a
   minimal-diff angle needs, and deliberately no `Write`/`Edit`/`Bash`,
   which is what makes FR-011 structural: **a candidate's plan never
   reaches the filesystem at all**, so "only the synthesized plan is
   committed" is not a promise about commit contents.
2. **Scoring, then synthesis, as two calls (FR-005/FR-005a)** — the
   scoring call returns a JSON envelope (per-`SC-NNN` coverage tag +
   1-5 ordinal internal-consistency rating), validated in Python against
   the `SC-NNN` id set parsed out of `spec.md`. The synthesis call
   receives that validated structure, not the scoring call's prose. A
   model-invented criterion id, a missing one, or an out-of-range rating
   is a hard parse error, which is what makes SC-006's coverage map
   machine-checkable rather than merely non-empty.
3. **Completeness-critic as an independent pass (FR-007a/FR-007b)** —
   a third fresh `query()` whose prompt contains the synthesized plan,
   the `SC-NNN` list, and the *angle names* tried, but **not** the judge's
   rationale, so it does not inherit the synthesis step's reasoning.
   Its FR-007a half is closed-form (per-criterion addressed yes/no,
   keyed to the same id set); its FR-007b half is reported as "no
   additional angle identified," never as proof none exists.
4. **Budgets split by owner** — `MAX_MALFORMED_RETRIES` (FR-013,
   default 1) is owned *inside* this module, because "every candidate in
   the set came back malformed" is only observable here. `MAX_PLAN_ATTEMPTS`
   (FR-010) is **not** owned here: a synthesis- or critic-step error
   (FR-013a), or a human rejection, propagates to the caller, which
   charges its own budget. This follows 003's precedent exactly — its
   `contracts/pm-agent-interface.md` lists `PmAttemptsExhausted` as
   *removed*, because an agent that names the workflow's budget becomes a
   second, conflicting owner of it. No `PlanAttemptsExhausted` analogue
   is introduced; exhausting `MAX_MALFORMED_RETRIES` raises a plain
   `RuntimeError`.
5. **One combined PR comment per attempt (FR-014)** — synthesized plan
   first, judge rationale and completeness note next, candidates last and
   collapsed behind `<details>`, with a leading delta line on attempt ≥ 2.
   Size-budgeted against GitHub's 65536-char comment cap (see
   `data-model.md`), and idempotent per `attempt` via a hidden marker
   comment, mirroring `pm-agent`'s `<!-- pm-agent:review attempt=N spec=<sha> -->`.

Goes **through LiteLLM** (`LITELLM_BASE_URL`), matching this repo's
default convention and `pm-agent`'s `review_spec()` — this stage runs on
the Temporal worker host, which can reach the self-hosted proxy, unlike
`pm-agent`'s `shape_issue()` on a target-repo runner.

### Deviation from `docs/70-multi-agent-pipeline-design.md` §2

The design doc's Architect step 2 has the judge consume *each candidate's
own `/speckit-analyze` consistency result*. This plan does not: the spec's
FR-005 replaced that with a model-produced ordinal 1-5 internal-consistency
rating, and it is followed. The reason is concrete rather than
preferential — `/speckit-analyze` is a Spec Kit skill that needs `Bash`,
and `Bash` is exactly the tool 003 dropped from `review_spec()` in order
to keep the stage LiteLLM-routed and free of the branch-under-review's
own hooks. Binding `Bash` to N concurrent candidates to recover a
consistency number would reintroduce that whole surface N times over.
Recorded here rather than left silent, since `CLAUDE.md` makes the design
doc's rationale, not local convenience, the decider.

### Deviation from `docs/70-multi-agent-pipeline-design.md` §2 / §6.1 — activity granularity

The design doc specifies the N candidates as "plain concurrent activities,"
one judge/synthesis activity and one completeness-critic activity, under a
general rule that *every* stage in §2's roster is a single Temporal activity.
This plan instead collapses all `N + 3` model calls into **one in-process
function**, `run_architect_stage()`, intended to sit behind one activity.

The reason is a hard constraint, not convenience: passing N full `plan.md`
blobs between activities routes them through Temporal's workflow history,
which has payload and history-size limits that N candidate plans will
exceed. Keeping the fan-out in-process keeps the plans in memory and puts
only the synthesized result on the history.

The costs are real and are handled at the caller, not hidden — the
**Consumer obligations** and **Intended activity boundary** sections of
`contracts/architect-agent-interface.md` specify the timeout (≥20 min at
N=6), the heartbeat expectation, the retry policy, and the workflow-
versioning question that follows from inserting a stage ahead of Build.
The one cost that is *accepted* rather than mitigated: there is no durable
checkpoint inside the stage, so a critic-step failure discards the whole
fan-out's spend and re-runs it. Splitting the stage to fix that trades a
bounded cost problem for an unbounded payload one.

### This stage is not automatically gated

Stated plainly here so it is not inferred from silence.
`eval/braintrust/eval.config.py::run_eval` is a Build-stage gate — it passes
on sandbox `exit_code == 0`, an opened PR, and ≥1 parsed `SC-NNN`. The
architect stage produces none of those facts, so **nothing gates it**. Two
things compound that: SC-006's coverage map scores the *candidates*, not the
shipped synthesized plan (fresh model-written text that no score covers);
and the completeness-critic never blocks — a gap routes to one extra round
whose result is never re-checked. The critic is **advisory with one retry**.
Plan-to-spec coverage stays unenforced until `specs/006-quality-gate`'s
traceability check lands, and the human reviewing the PR comment is the
only gate this feature ships.

### N is 3 for every spec currently in this repo

`candidate_count`'s formula,
`min(6, 3 + max(0, (len(sc_ids) - 5) // 3))`, returns 3 for ≤5 criteria and
4 at 8. Every spec in this repo has 5-7 success criteria — 004 itself has 7 —
so **N=3 in practice, always**. SC-005's "scales with complexity rather than
staying fixed" is therefore satisfied *structurally* (the function is
monotonic and non-constant over its domain) but is not observable on any
real input here, and T020 asserts it with a synthetic 20-criterion list. If
observable scaling is wanted, move the breakpoints down (e.g. 6 and 9);
otherwise this paragraph is the honest reading of what SC-005 buys today.

## Technical Context

**Language/Version**: Python 3.11 (matches `harness/swe-agent`, `harness/pm-agent`)

**Primary Dependencies**: `claude-agent-sdk`, `braintrust`, `python-dotenv`
(same three as `harness/pm-agent/pyproject.toml`); GitHub CLI (`gh`) and
`git`, invoked via `subprocess` from code, never bound as model tools

**Storage**: N/A — the synthesized plan is written into the branch's
`specs/NNN-slug/` directory as git content; scores, rationale, and the
completeness note live in the PR comment and Braintrust spans. Nothing
else is persisted, and candidate plans are never written to disk (FR-011)

**Testing**: `uv run pytest` from repo root, new `tests/test_architect_agent.py`;
`subprocess`/`gh`/`git` and `query()` all mocked — no real GitHub or model
network access in tests

**Target Platform**: Temporal worker host process. No sandbox lifecycle
(§6.1 carve-out) — unlike `harness/swe-agent`, which its callers run
inside E2B

**Project Type**: Single agent harness + registry entry, following the
existing `harness/<agent>/` + `registry/agents/<agent>/` pattern

**Performance Goals**: N/A for latency. One relevant shape: fan-out cost is
`N` × one candidate call, and the §6.1 carve-out is what makes scaling `N`
affordable — there is no per-candidate sandbox provisioning to multiply

**Constraints**:
- No E2B sandbox for any of the three roles (§6.1 carve-out)
- Candidates: `tools=["Read","Grep","Glob"]`, `setting_sources=[]`,
  no `Write`/`Edit`/`Bash` — FR-011 is structural, not prompt-enforced
- Judge (scoring), synthesis, and critic: separate `query()` calls with
  fresh contexts; the critic never sees the judge's rationale (FR-007b)
- **Model**: every role (fan-out candidates, gap candidate, scoring,
  synthesis, critic) uses the same pinned id, `claude-sonnet-5` — no
  `ClaudeAgentOptions.model` override anywhere, mirroring `pm-agent`'s
  `_model_text()`. This is not an arbitrary "one model for everything"
  choice: it is the *only* id `litellm/config.yaml` guarantees resolves,
  since the Agent SDK CLI requests `claude-sonnet-5` by default and that
  is the route name the config comment calls out as load-bearing for
  exactly this reason. A per-role model split is not precluded by this
  plan, but nothing in this feature's budget or research justifies one,
  and inventing a second pinned id here would make the registry entry's
  reproducibility claim (T003) false on any proxy config that only
  carries the two routes this repo's does today.
- **One process-wide credential scrub wraps the entire stage's model
  calls**, not one per call. `pm-agent`'s per-call
  `os.environ.pop(...)`/restore-in-`finally` is correct for a sequential
  caller but is a race under `asyncio.gather` — candidate A's `finally`
  would restore `GH_TOKEN` while candidate B is still mid-`query()`.
  See `research.md` Unknown 1
- `SC-NNN` ids come from the *same* parser the Eval-Gate uses
  (`eval/braintrust/eval.config.py`), loaded via the `importlib`
  path shim `orchestration/activities.py:99-112` already establishes, so
  the architect cannot "cover" a criterion set the gate doesn't see
  (`research.md` Unknown 2)
- Candidate count is a pure, testable function of the `SC-NNN` count with
  an explicit angle list of matching length — never a bare `3`
  (FR-002/SC-005; `research.md` Unknown 3)
- Combined comment is size-budgeted below GitHub's 65536-char body cap,
  degrading to per-candidate truncation with an explicit notice rather
  than failing the post (`data-model.md`, "Combined stage comment")
- Idempotent per `attempt`, which MUST be strictly increasing per distinct
  stage invocation — same contract as `review_spec()`
- `MAX_PLAN_ATTEMPTS` is neither enforced nor tracked here (FR-010/FR-013a
  belong to `specs/005-pipeline-mode-signals-escalation/`)

**Scale/Scope**: One registry entry, one stage entrypoint + five capability
functions, no new external services, no new orchestration activity

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is still the unfilled placeholder
template (no principles ratified for this repo) — there are no gates to
check against. No violations to justify. Re-checked after Phase 1: unchanged.

## Project Structure

### Documentation (this feature)

```text
specs/004-architect-fanout-judge/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
harness/architect-agent/
├── agent.py             # run_architect_stage() + candidate_count(),
│                        # angles_for(), generate_candidates(),
│                        # score_candidates(), synthesize(),
│                        # check_completeness(), persist_synthesized(),
│                        # push_synthesized(), post_stage_comment();
│                        # CANDIDATE_PROMPT/SCORING_PROMPT/
│                        # SYNTHESIS_PROMPT/CRITIC_PROMPT as module-level
│                        # constants (mirrors pm-agent's
│                        # SHAPE_ISSUE_PROMPT/SPEC_REVIEW_PROMPT — no
│                        # runtime-loaded prompts/architect-agent.json)
├── SKILL.md             # design source, the §2 /speckit-analyze
│                        # deviation, and known gaps
└── pyproject.toml       # own runtime deps: claude-agent-sdk, braintrust,
                         # python-dotenv (copy of pm-agent's)

registry/agents/architect-agent/
├── manifest.yaml        # mirrors registry/agents/pm-agent/manifest.yaml
├── versions/
│   └── v1.yaml          # mirrors registry/agents/swe-agent/versions/v1.yaml;
│                        # note "no sandbox (§6.1 carve-out)" in `sandbox:`
└── SKILL.md             # registry-side copy — CLAUDE.md's portability
                         # boundary requires this live under
                         # registry/agents/<name>/, and
                         # .github/workflows/registry-gate.yml enforces
                         # manifest.yaml + non-empty versions/

eval/braintrust/eval.config.py
└── + load_success_criteria_ids()  # additive: returns [(id, text)];
                                   # existing load_success_criteria() and
                                   # run_eval() unchanged (research.md
                                   # Unknown 2). Loaded lazily, inside the
                                   # function that needs the ids, so the
                                   # eval layer's `import braintrust` isn't
                                   # pulled into every architect import

tests/
├── conftest.py           # + _load_agent(name, path): loads each harness
│                         # agent by explicit path under a distinct module
│                         # name. Required, not cosmetic — conftest.py:16-18
│                         # currently puts harness/pm-agent/ on sys.path so
│                         # tests `import agent`, and a second
│                         # harness/<agent>/agent.py collides on that name
│                         # (research.md Unknown 11). The existing stub
│                         # block and test_pm_agent.py are left untouched
└── test_architect_agent.py  # candidate_count/angles_for property tests,
                             # concurrent-scrub test, malformed-candidate
                             # and all-malformed-retry paths, coverage-map
                             # validation rejects invented/missing ids,
                             # critic prompt excludes judge rationale,
                             # gap round runs exactly once, comment
                             # assembly + idempotent re-post
```

**Structure Decision**: Follows the existing `harness/<agent>/` +
`registry/agents/<agent>/` single-project pattern established by
`harness/swe-agent/` and `harness/pm-agent/` — no new top-level project
boundary. Two files are touched outside those two trees, both additively:
`eval/braintrust/eval.config.py` (Unknown 2) and `tests/conftest.py`
(Unknown 11).

Out of scope, per the spec's own Assumptions:

- **The Temporal wiring.** No `architect_stage_activity` in
  `orchestration/activities.py`, no new step in
  `orchestration/workflows/pipeline_workflow.py`. This feature ends at
  directly callable, testable functions — the same place 003 ended.
- **The `plan_approved`/`plan_rejected` gate.** Signal delivery is
  `specs/002-webhook-trigger-bridge/` (parsing) plus
  `specs/005-pipeline-mode-signals-escalation/` (the `@workflow.signal`
  handlers, which do not exist yet).
- **`MAX_PLAN_ATTEMPTS` and escalation** — `specs/005-...` (FR-010/FR-013a).
- **`vibe` mode's N=1 collapse and critic skip** (§4 of the design doc) —
  needs the `mode` param that `specs/005-...` introduces. `candidate_count()`
  accepts an `n_override`, which is the seam a future `vibe` caller uses;
  this feature does not add the mode itself.
- **A `pr_url` producer.** Like `review_spec()`, this stage takes `pr_url`
  as an argument and assumes a target-repo PR already exists. Nothing in
  this repo creates one yet — an inherited gap, documented in 003's
  `data-model.md` and unchanged here.

### SC-007, and what was deliberately moved out of it

SC-007 as originally written — "every plan-attempt's human approve/reject
decision is recorded as a plain fact against the PR" — was **not satisfiable
by this feature at all**, since capturing the decision requires the gate
`specs/005-pipeline-mode-signals-escalation/` owns. A success criterion a
feature cannot meet by construction is a spec defect rather than a
documentation footnote, and it also distorts `candidate_count`, whose input
is the SC count. So SC-007 was **narrowed** to the half this feature does
land: every stage comment carries a machine-parseable
`<!-- architect-agent:stage attempt=N spec=<sha> -->` marker sufficient to
correlate a later approve/reject decision to the exact attempt and spec
revision it answered. That is scoreable today.

The decision-capture half now belongs to 005 and is not a criterion of this
feature. Stated here rather than silently claimed, following 003's
convention for the same situation.

Separately inherited, not fixed here: `orchestration/activities.py::eval_gate_activity`'s
`sorted(glob("specs/*/spec.md"))[0]` resolves to `001-agent-spec-schema-test`
on any checkout of this repo, so this feature's own gate score is no more
reachable than 003's was. Same pre-existing bug, same non-fix, called out
for the same reason.

## Complexity Tracking

*No Constitution Check violations — this section is not applicable.*
