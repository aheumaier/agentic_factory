# Phase 1 Data Model: Architect Fan-Out, Judge, and Completeness-Critic

Entities from [spec.md](./spec.md)'s Key Entities, plus the two structures
its Functional Requirements imply but do not name (the coverage map's key
set and the combined comment). Nothing here is a database schema — this
feature persists only git content and PR comments (see
[plan.md](./plan.md), "Storage").

Validation rules stated below are enforced in Python in
`harness/architect-agent/agent.py`, not by prompt instruction. That
distinction is the whole point: see [research.md](./research.md) Unknowns
4, 5, and 6.

---

## `SC-NNN` id set — the key universe

Not a spec entity, but every other structure here is keyed on it, so it
comes first.

| Field | Type | Source |
| --- | --- | --- |
| `id` | `str`, matches `SC-\d+` | `spec.md`'s `### Measurable Outcomes` bullets |
| `text` | `str`, whitespace-collapsed | same bullet, wrapped lines joined |

Produced by `load_success_criteria_ids(spec_path)`, added to
`eval/braintrust/eval.config.py` and loaded through the `importlib` path
shim `orchestration/activities.py:99-112` already uses for that file
(research.md Unknown 2).

**Validation**: a `spec.md` with no `### Measurable Outcomes` section
raises `ValueError` (inherited from `load_success_criteria`'s existing
behavior). An empty criteria list is a stage precondition failure, not a
gap finding — FR-007a's per-outcome determination is vacuous without one,
and so is SC-006's map.

**Invariant**: this is the *only* `SC-NNN` universe in the stage. The
scoring step's coverage keys, the critic's `uncovered` list, and the
Eval-Gate's own criteria all derive from this one parser.

---

## Architect Candidate

One independently produced plan/task/ADR set from one stated angle, with no
knowledge of other candidates (FR-001, FR-003).

| Field | Type | Notes |
| --- | --- | --- |
| `index` | `int` | Position in the fan-out; the stable handle scores and the comment refer to |
| `angle` | `str` | **Caller-assigned**, from `angles_for(n)`. The model's echoed value is ignored (research.md Unknown 4) |
| `plan_md` | `str`, non-empty | Candidate's `plan.md` content |
| `tasks_md` | `str`, non-empty | Candidate's `tasks.md` content |
| `adrs` | `list[{title: str, body: str}]` | May be empty — a minimal-diff plan legitimately needs none |
| `valid` | `bool` | Derived, not model-reported |
| `error` | `str \| None` | Parse/validity failure reason when `valid` is `False` |

**Validity predicate** (FR-013's mechanical verdict): output parses as one
JSON object **and** `plan_md` and `tasks_md` are both non-empty after
stripping. Anything else is invalid.

**Lifecycle**: created by `generate_candidate()`, consumed by
`score_candidates()` and `synthesize()`, and **never written to disk**.
That last clause is what makes FR-011 structural rather than a promise
about commit contents — no model call in this stage has `Write`, `Edit`,
or `Bash` bound.

**Invalid candidates are reported, not silently dropped**: the stage result
and the combined PR comment both list each invalid candidate's angle and
`error`. Synthesis proceeds from the remaining valid ones (spec.md's edge
case), unless there are zero — which is FR-013's retry path.

### Gap-targeted candidate — same entity, opposite input contract

FR-009's extra candidate is the same shape, produced by the same function
with `gap` and `synthesized_plan` both supplied. Exactly one of "both set"
and "both `None`" is legal; a partially-populated call raises `ValueError`
so a gap candidate cannot silently degrade into a blind one (research.md
Unknown 7). Its `angle` is the critic's gap description, not an entry from
`angles_for()`.

---

## Candidate Score

The structured, per-candidate output of the FR-005 scoring step — the thing
FR-005a requires synthesis to consume *instead of* the scoring step's prose.

| Field | Type | Validation |
| --- | --- | --- |
| `candidate_index` | `int` | Must reference a valid candidate |
| `angle` | `str` | Copied from the candidate, not the model |
| `coverage` | `dict[str, bool]` | Keys MUST equal the `SC-NNN` id set exactly — no invented id, no missing id |
| `internal_consistency` | `int` | MUST be `1..5` (FR-005's ordinal-scale clarification) |
| `notes` | `str` | Free-form; the only prose field, carried per-candidate |

**Validation is strict and total.** A superset, a subset, a non-`SC-\d+`
key, or an out-of-range or non-integer rating is a hard parse error. That
error is a **synthesis/critic-class failure under FR-013a** — deterministic,
so it propagates to the caller to charge `MAX_PLAN_ATTEMPTS` (a *transient*
failure of the same call goes to FR-013b's orchestration-level retry
instead, and charges nothing). It does **not** consume
`MAX_MALFORMED_RETRIES`, which FR-013 scopes strictly to "every candidate
malformed."

Lenient handling was considered and rejected: defaulting missing ids to
`false` makes a model that *omitted* half the criteria indistinguishable
from one that found them *uncovered*, corrupting both FR-007a's gap path
and SC-006's map (research.md Unknown 5).

---

## Synthesis Result

The single chosen plan/task/ADR set plus its rationale (FR-004, FR-006).

| Field | Type | Notes |
| --- | --- | --- |
| `plan_md` | `str`, non-empty | Persisted to `<spec_dir>/plan.md` |
| `tasks_md` | `str`, non-empty | Persisted to `<spec_dir>/tasks.md` |
| `adrs` | `list[{title, body}]` | Persisted as `<spec_dir>/ADR-NNN-<slug>.md` |
| `winner_index` | `int` | Which candidate most influenced the result |
| `grafted_from` | `list[int]` | Candidate indices whose ideas were pulled in |
| `rationale` | `str` | Human-facing reasoning; posted, never committed |

**Cardinality is enforced, not requested**: exactly one Synthesis Result
per candidate set (FR-004, SC-002 "never zero and never more than one").
The function returns one object or raises — there is no list-valued path.

`winner_index` is **computed in Python** by `pick_winner()` from the
validated scores — coverage-true count, then `internal_consistency`, then
lowest index — and passed *into* the synthesis call as a given. It is not
model-chosen. A synthesis that ignored the scores entirely would otherwise
be indistinguishable from one that used them, and ties would have no defined
answer. Every `grafted_from` entry must reference a *valid* candidate index;
a reference to an invalid or nonexistent one is a deterministic
synthesis-step error (FR-013a).

**Convergent candidates** (spec.md edge case): two candidates arriving at
effectively the same approach is not an error. A winner is still picked,
and the rationale may note the convergence.

---

## Completeness Note

The coverage check's output (FR-007a, FR-007b, FR-008, FR-009).

| Field | Type | Notes |
| --- | --- | --- |
| `uncovered` | `list[str]` | `SC-NNN` ids the synthesized plan does not address; validated against the id set |
| `missed_angle` | `str \| None` | An architectural angle none of the candidates tried |
| `note` | `str` | The short human-facing text posted to the PR |
| `gap_found` | `bool` | **Derived in Python** as `bool(uncovered) or missed_angle is not None` |

`gap_found` is deliberately not taken from the model's own boolean, so the
flag cannot disagree with its own evidence — a `gap_found: true` with
nothing to target would otherwise trigger a gap round with no gap
(research.md Unknown 6).

**Asymmetry between the two halves is preserved in the output text**, per
FR-007b: `uncovered` is a closed-form determination over a known id set,
but `missed_angle is None` is rendered as *"no additional angle was
identified"* — never as confidence that none exists.

**Input asymmetry**: the critic receives the synthesized plan, the full
`(id, text)` criteria list, and the *angle names* tried. It does not
receive the judge's rationale, the score records, or any candidate's plan
text (research.md Unknown 6).

---

## Combined stage comment

FR-014's single per-attempt PR comment. Not named in Key Entities, but it
has a format contract and a hard size limit, so it is specified here rather
than discovered at runtime.

**Body order** (progressive disclosure — the synthesized plan is the
primary reading surface):

1. Hidden marker: `<!-- architect-agent:stage attempt=<N> spec=<sha> -->`
2. **Delta line — attempt ≥ 2 only.** One line naming what changed since
   the prior attempt: the rejection feedback, or the gap addressed. FR-014
   forbids re-presenting everything as if it were the first attempt.
3. Synthesized `plan.md` and `tasks.md`, inline.
4. Judge rationale, winner, and what was grafted from whom.
5. The SC-006 coverage map, as a table (criterion × candidate).
6. Completeness note.
7. Invalid candidates, if any: angle + failure reason, one line each.
8. `<details>` per candidate, collapsed, containing its `plan_md`/`tasks_md`.

**Size budget.** A GitHub issue/PR comment body caps at **65536
characters**, and `N` full candidate plans inline can exceed that — FR-014's
"collapsed **or linked**" is the escape hatch, so the threshold is defined
up front:

- Sections 1–4, 6 and 7 are always included in full; they are bounded by one
  plan's size, not `N`. **Section 5 is not** — the coverage map is a
  criterion × candidate table, so it grows with `N` and is subject to the
  same budget as the `<details>` blocks.
- The remaining budget up to `_COMMENT_LIMIT = 60000` chars (a margin under
  the hard cap) is divided evenly across the `N` `<details>` blocks.
- A candidate whose content exceeds its share is truncated at that share
  with an explicit `…[truncated — full candidate text in the Braintrust
  span for this attempt]` notice. Truncation is never silent. **This notice
  obliges the implementation to actually log each candidate's `plan_md` to
  that span** — a pointer to an artifact nothing produces is worse than no
  pointer. Module-level `init_logger`/`auto_instrument` does not do it; the
  candidate text must be logged explicitly.
- If sections 1–7 alone exceed `_COMMENT_LIMIT`, the `<details>` blocks are
  omitted entirely with one line saying so.
- If they *still* exceed it, sections 3's plan/tasks bodies are truncated
  inline with a pointer to `<spec_dir>/plan.md` at the commit made in step
  10. This is the one case where the plan text is trimmed, and it costs the
  reader nothing: by then the full plan is committed on the branch. Without
  this branch, `gh pr comment` fails hard after all `N + 3` calls are paid
  for, which is strictly worse than a pointer. The synthesized plan is never
  *dropped*; it may be *linked*.

**Idempotency.** `attempt` is the sole key and MUST be strictly increasing
per distinct stage invocation — same contract as
`harness/pm-agent/agent.py::review_spec`. The existing-comment check runs
**before any model work**, not merely before the post: a re-invocation that
skipped only the post would still have burned `N + 3` model calls
(research.md Unknown 10). The marker carries `spec=<sha>` for the reader but
the match is on the `attempt=<N> ` prefix alone, so reusing an attempt number
against a changed spec returns the stale body — caller error, stated here so
it is not discovered at runtime.

On a hit the stage returns a **degraded three-key shape** —
`{"attempt", "comment_body", "idempotent_hit": True}` — not the full result
dict. The twelve keys below (`plan_md`, `scores`, `commit_sha`,
`gap_round_ran`, …) are not reconstructible from a comment body, so returning
that shape would hand a caller a `KeyError` on the *success* path of a
Temporal retry. Callers branch on `idempotent_hit`. `review_spec()` needs no
such split only because its own return is `{"writeup", "attempt"}`, which a
comment body *does* reconstruct.

---

## Retry and budget state — deliberately not an entity here

| Budget | Default | Owner |
| --- | --- | --- |
| `MAX_MALFORMED_RETRIES` | 1 | **This module.** Zero valid candidates is only observable here (FR-013) |
| `MAX_PLAN_ATTEMPTS` | 3 | **Not here.** `specs/005-pipeline-mode-signals-escalation/` (FR-010, FR-013a) — including the rules on *when not to charge it*: the transient carve-out (FR-013b) and the malformed-exhaustion escalation, both listed as Consumer obligations in `contracts/architect-agent-interface.md` |

`run_architect_stage()` tracks two pieces of in-attempt state and nothing
more:

- the malformed-retry counter, bounded by `MAX_MALFORMED_RETRIES`;
  exhausting it raises a plain `RuntimeError` rather than falling through
  to the plan budget (FR-013's explicit requirement).
- `gap_round_ran: bool`, which makes SC-003's "never an unbounded chain"
  a property of one boolean — a second gap round within one attempt is
  unreachable.

No `PlanAttemptsExhausted`-style exception is introduced. 003's
`contracts/pm-agent-interface.md` lists its own `PmAttemptsExhausted` as
*removed*, on the grounds that an agent naming the workflow's budget
becomes a second, conflicting owner of it; that precedent applies
unchanged.

---

## `pr_url` — an inherited, unresolved precondition

This stage takes `pr_url` as an argument and assumes a target-repo PR
already exists to post FR-014's comment to. **Nothing in this repo creates
one yet** — the same gap 003's `data-model.md` documented for
`review_spec()`. Not fixed here; it belongs to whichever feature adds the
ensure-target-PR step (`docs/70-multi-agent-pipeline-design.md` §3's
`EnsureTargetPR` state).

## Spec-path resolution — the same adjacent bug 003 flagged

`orchestration/activities.py::eval_gate_activity` resolves its spec as
`sorted(glob("specs/*/spec.md"))[0]`, which on any checkout of this repo
returns `001-agent-spec-schema-test`. This stage does not use that code
path (it takes `spec_dir`, defaulting to `specs/<branch>`, exactly as
`review_spec()` does), so it is not affected at runtime — but the bug still
means this feature's own Eval-Gate score is unreachable, as 003's was.
Unfixed, and called out for the same reason.
