# Quickstart: Architect Fan-Out, Judge, and Completeness-Critic

Runnable validation for [spec.md](./spec.md)'s three user stories against
the interface in [contracts/architect-agent-interface.md](./contracts/architect-agent-interface.md).

Two tiers, and the split matters: **most of this feature's guarantees are
structural and are validated by the offline suite**, not by a live run. A
live run demonstrates the stage end-to-end but proves less — a passing
live run cannot show that a candidate *could not* have seen a sibling's
output, only that it apparently didn't.

## Prerequisites

**Offline tier (Stories 1-3's structural guarantees, no network):**

```bash
uv run pytest tests/test_architect_agent.py     # from repo root
```

Nothing else. `query()`, `git`, and `gh` are all mocked — no model calls,
no GitHub access. `tests/conftest.py` stubs `claude_agent_sdk`, `dotenv`,
and `braintrust`, so the root venv (`pytest`/`pyyaml` only) needs none of
the harness's runtime deps. Note that this feature must **extend**
`conftest.py` before its tests can exist at all: today it puts
`harness/pm-agent/` on `sys.path` and tests `import agent`, which a second
`harness/<agent>/agent.py` collides with ([research.md](./research.md)
Unknown 11).

**Live tier (end-to-end demonstration):**

```bash
cp .env.example .env      # then fill in the values below
make up                   # LiteLLM proxy on :4000 (+ Temporal, Langfuse)
```

- `LITELLM_MASTER_KEY`, `LITELLM_BASE_URL` — this stage is LiteLLM-routed
  ([research.md](./research.md) Unknown 9), so `make up` must be running.
- `ANTHROPIC_PLATFORM_API_KEY` — read by the LiteLLM proxy, not by this
  module.
- `BRAINTRUST_API_KEY` — full candidate text lands in the attempt's span,
  which is where a truncated `<details>` block points.
- `GH_TOKEN` — a GitHub App installation token with `contents: write`
  (the stage commits and pushes the synthesized plan) and
  `pull_requests: write` (FR-014's comment).
- A **disposable** target repo with a branch carrying `specs/<branch>/spec.md`
  (with a populated `### Measurable Outcomes` section) and an **open PR**
  for that branch. Nothing in this repo creates that PR yet
  ([data-model.md](./data-model.md), "`pr_url`") — open it by hand.

Use a disposable repo. The stage commits, pushes, and comments — and
`persist_synthesized()` **overwrites `<spec_dir>/plan.md` and
`<spec_dir>/tasks.md`** on that branch with the synthesized versions. If
the branch already has a hand-written or `/speckit-plan`-generated plan
there, it is replaced (recoverable from git history, since it lands as a
commit). Do not point the live tier at a branch whose plan you want to
keep.

---

## Validate User Story 1 — multiple independent candidates

Spec's Independent Test: multiple candidates, each from a distinct stated
angle, none influenced by another's output.

**Offline — the parts that are actually provable:**

- `candidate_count()` satisfies its four guaranteed properties
  (monotonic non-decreasing in `len(sc_ids)`, `>= 3` absent an override,
  `<= len(ANGLES)`, and not constant across spec sizes — the last is
  SC-005's requirement).
- `angles_for(n)` returns `n` distinct angles and raises above
  `MAX_CANDIDATES`, so FR-001's "explicitly stated angle" can never fall
  back to a reused or model-invented one.
- `generate_candidates()` issues one `query()` per angle with no candidate's
  output in any other's prompt — assert against the recorded prompts of a
  mocked `query()`. **This, not a live run, is what validates FR-003**:
  each `query()` is its own CLI subprocess, so there is no shared
  conversation to leak through.
- `generate_candidate()` binds `tools=["Read","Grep","Glob"]` and
  `setting_sources=[]`, and never `Write`/`Edit`/`Bash` — the binding that
  makes FR-011 structural.
- **The concurrency-specific one** (research.md Unknown 1): with
  `GH_TOKEN` set in the parent environment, a fake `query()` that records
  `os.environ.get("GH_TOKEN")` at call time must record `None` for **every**
  candidate. A per-candidate scrub passes a sequential test and fails this
  one; that is the point of the test.

**Live:**

```bash
cd harness/architect-agent
uv run python agent.py architect-stage <owner>/<repo> <branch> <pr_url> 1
```

Expected: the printed result's `scores` has one entry per angle, and the
PR comment's collapsed `<details>` blocks show visibly different approaches
under distinct angle headings.

To exercise scaling (SC-005), point it at a branch whose `spec.md` has
~12+ `SC-NNN` criteria and confirm more than 3 candidates appear.

---

## Validate User Story 2 — one synthesized plan, rationale visible

Spec's Independent Test: exactly one synthesized plan + tasks, referencing
the most influential candidate, rationale visible to a human.

**Offline:**

- `synthesize()` returns exactly one result or raises — there is no
  list-valued path, which is how SC-002 is enforced (never zero, never
  more than one).
- `score_candidates()` **rejects** a coverage map with an invented
  `SC-NNN` key, with a missing one, and with an `internal_consistency`
  outside `1..5`. These three rejections are what make SC-006's map
  machine-checkable rather than merely non-empty.
- `synthesize()`'s prompt contains the validated score structure and not
  the scoring call's aggregate prose (FR-005a) — assert on the recorded
  prompt.
- One malformed candidate among several: synthesis still produces a result
  from the remaining valid ones, and the invalid one appears in
  `invalid_candidates` with its angle and reason (reported, not silently
  dropped).
- **All** candidates malformed: exactly `MAX_MALFORMED_RETRIES` (1) extra
  fan-out happens, then `RuntimeError` — and specifically *not* a fall-
  through to the caller's plan budget (FR-013).
- A scoring/synthesis call error propagates as-is, consuming no
  malformed-retry budget. Which budget it *does* consume is the caller's
  decision, not this module's: a deterministic failure charges a plan
  attempt (FR-013a), a transient one is retried at the orchestration layer
  and charges nothing (FR-013b).
- `post_stage_comment()` places the synthesized plan before the collapsed
  candidates, truncates oversized `<details>` blocks with a visible notice
  rather than silently, and never drops the synthesized plan to fit
  (FR-014's progressive disclosure + the 65536-char cap).
- Re-invoking `run_architect_stage()` with the same `attempt` **issues zero
  `query()` calls** — the marker check runs before any model work — and
  returns the degraded three-key shape
  `{"attempt", "comment_body", "idempotent_hit": True}`, not the full result
  dict, whose twelve keys a comment body cannot reconstruct.

**Live:** confirm `<spec_dir>/plan.md` and `tasks.md` exist on the pushed
branch, that **no candidate plan was committed** (`git show --stat` on the
new commit — FR-011), and that the PR carries exactly one new comment
containing the plan, the rationale, the coverage-map table, and the
collapsed candidates.

Then re-run the identical command. Expected: no second comment, no new
commit, and the previous body returned.

---

## Validate User Story 3 — coverage gaps the panel missed

Spec's Independent Test: a plan omitting a measurable outcome → gap
identified + exactly one targeted attempt; a plan with no gaps → short
note, no extra attempt.

**Offline:**

- `check_completeness()`'s prompt contains the synthesized plan, the
  `(id, text)` criteria list, and the angle names — and **not** the judge's
  rationale, the score records, or any candidate's plan text (FR-007b's
  independence; assert on the recorded prompt).
- `gap_found` is derived, not trusted: a mocked critic returning
  `gap_found: true` with empty `uncovered` and null `missed_angle` yields
  `gap_found == False`, so no gap round fires with nothing to target.
- `uncovered` containing an id outside the spec's set raises.
- Gap path: one extra `generate_candidate()` in **gap mode** (both `gap`
  and `synthesized_plan` set — FR-009), then one re-synthesis, and
  `gap_round_ran == True`. The critic is **not** re-run, and a second gap
  round within the same attempt is unreachable (SC-003).
- Mode legality: `generate_candidate(gap=..., synthesized_plan=None)`
  raises `ValueError`, so a gap candidate cannot degrade into a blind one.
- No-gap path: `gap_round_ran == False`, exactly `N` candidate calls total,
  and the note text reads *"no additional angle was identified"* — never
  "none exists" (FR-007b).

**Live:** remove one `SC-NNN` bullet's subject matter from the target
branch's `spec.md` in a way the plan will plainly not address, re-run with
`attempt=2`, and confirm the comment leads with a delta line and its
completeness section names the specific gap.

---

## What this quickstart does not cover

Out of scope for this feature, so there is nothing here to run:

- **The Temporal wiring.** No `architect_stage_activity` and no
  `pipeline_workflow.py` step exists — the live tier above invokes the
  module directly, which is the only trigger this feature ships.
- **The `plan_approved`/`plan_rejected` gate.** Signal delivery is
  `specs/002-webhook-trigger-bridge/` plus
  `specs/005-pipeline-mode-signals-escalation/`. `feedback` can be passed
  by hand to simulate a rejection; the gate itself cannot be exercised.
- **`MAX_PLAN_ATTEMPTS`.** Not enforced here by design — increment
  `attempt` manually to simulate the loop.
- **`vibe` mode** (N=1, critic skipped). `n_candidates=1` exercises the
  seam, but the mode itself arrives with 005.
- **Capturing the human approve/reject decision.** SC-007 was narrowed to
  the per-attempt correlation marker, which this feature does land and which
  *is* scoreable here; recording the decision against that marker needs 005's
  gate and is 005's criterion, not this one's — see [plan.md](./plan.md),
  "SC-007, and what was deliberately moved out of it".
- **The Eval-Gate score.** `eval_gate_activity`'s
  `sorted(glob("specs/*/spec.md"))[0]` resolves to `001-...` on any
  checkout of this repo, so this feature's gate score is unreachable for
  the same inherited reason 003's was.
