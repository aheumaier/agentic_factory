# Phase 0 Research: Architect Fan-Out, Judge, and Completeness-Critic

Input: [spec.md](./spec.md). Every Unknown below was raised while filling
[plan.md](./plan.md)'s Technical Context; each resolves to a Decision,
a Rationale, and the Alternatives rejected.

Two existing implementations are load-bearing precedent throughout and are
cited by path rather than re-argued:

- `harness/pm-agent/agent.py` — the multi-capability-in-one-module pattern,
  the read-only tool binding, the credential-scrub guarantee, the
  idempotent PR-comment marker, and the "mutation is code, never the
  model" rule.
- `harness/swe-agent/agent.py` — the clone/commit/push split and the
  `_REPO_RE`/`_BRANCH_RE` argument-injection guards.

---

## Unknown 1: `pm-agent`'s credential scrub pops and restores `os.environ` around one model call. Does that survive `asyncio.gather` over N concurrent candidates?

**No — it becomes a race, and this is the one thing fan-out breaks about
003's established guarantee.**

`harness/pm-agent/agent.py:307-315` implements FR-007's no-push guarantee
partly by popping `GH_TOKEN`/`GITHUB_TOKEN` off the **parent process's**
`os.environ` before `await _model_text(...)` and restoring them in a
`finally`. That is correct for a single sequential call. Copied per
candidate under `asyncio.gather`, candidate A's `finally` restores the
token into the shared process environment while candidates B and C are
still mid-`query()` — and the SDK's subprocess launcher reads `os.environ`
at spawn time, so a candidate that happens to launch during that window
inherits a live token.

**Decision**: one `_no_git_credentials()` context manager, entered **once**
in `run_architect_stage()`, wrapping the entire stage's model work — the
`gather` over candidates, the scoring call, the synthesis call, the critic
call, and the gap round. Per-call state stays per-call: `setting_sources=[]`,
`GH_CONFIG_DIR` pointed at an empty directory, `GIT_TERMINAL_PROMPT=0`,
and the LiteLLM `ANTHROPIC_BASE_URL`/`ANTHROPIC_API_KEY` overrides all live
in each call's own `ClaudeAgentOptions`, which is not shared state. Only
the process-env mutation is hoisted.

Ordering consequence: the clone happens **before** the scrub is entered
(it needs the token, exactly as `review_spec()` does), and the commit,
push, and `gh pr comment` all happen **after** it exits. `persist_synthesized()`
writing files inside the scrubbed window would be harmless but pointless;
keeping all git/gh mutation outside it keeps the invariant one sentence
long: *no bound tool and no ambient credential exists in the process
environment for the whole duration of every model call in this stage.*

**That invariant is about `os.environ`, and `os.environ` is not the only
place a credential lives.** `git clone https://x-access-token:<token>@...`
writes the token into the checkout's own `.git/config`, where the scrub
window cannot reach it and `git config --local credential.helper ""` does
not remove it — and candidates are bound `Read` with `cwd=checkout`, with
their output posted verbatim to a PR comment. So the clone step must also
`git remote set-url origin` to the token-free URL immediately after cloning,
and the push must carry the credential in argv rather than in the remote.
Stated here because the one-sentence invariant above, taken alone, reads as
a stronger guarantee than the environment scrub actually provides.

**Rationale**: the guarantee 003 documented is a property of the process
environment, and fan-out is the first thing in this repo to run more than
one model call in that environment at once. Fixing it at the scope level
(one window for the stage) rather than per call is both simpler and
strictly stronger.

**Alternatives considered**:
- *Per-candidate pop/restore with a lock or refcount* — rejected: a
  refcounted scrub is exactly the shared-mutable-state bug in a fancier
  costume, and there is no reason any candidate needs the token.
- *Pass an empty token via `ClaudeAgentOptions.env` instead of popping* —
  rejected on the same ground 003 corrected in its third pass: `env=`
  merges on top of `os.environ` in the SDK's subprocess launcher, so it
  overrides a value but cannot remove an inherited one. `env={"GH_TOKEN": ""}`
  leaves `gh` reading an empty-string token, which is not the same as
  absent, and says nothing about `GITHUB_TOKEN`.
- *Run candidates sequentially to keep 003's pattern verbatim* —
  rejected: FR-001's whole point is `N` concurrent candidates, and the
  §6.1 carve-out (no per-candidate sandbox) exists specifically to make
  that concurrency cheap.

---

## Unknown 2: FR-005's coverage map must key on `SC-NNN` ids. Where do those ids come from — a new regex here, or the Eval-Gate's existing parser?

**The Eval-Gate's parser, extended additively to expose ids.**

`eval/braintrust/eval.config.py::load_success_criteria` already parses
`- **SC-NNN**: ...` bullets out of a Spec Kit `spec.md`'s
`### Measurable Outcomes` section, but returns criterion **text** only —
the id is matched (`SC-\d+`) and discarded. A keyed coverage map needs the
ids.

**Decision**: add `load_success_criteria_ids(spec_path) -> list[tuple[str, str]]`
to `eval/braintrust/eval.config.py`, returning `(id, text)` pairs from a
capturing variant of the same `_SC_BULLET_RE`. `load_success_criteria()`
and `run_eval()` are untouched. `harness/architect-agent/agent.py` loads
that module through the `importlib.util.spec_from_file_location` shim
`orchestration/activities.py:99-112` already uses for the same file (its
name has dots in it, so a plain `import` cannot reach it).

**Load it lazily, inside the function that needs the ids — not at module
scope.** `eval.config.py` does `import braintrust` at module scope, so a
module-scope shim would pull the eval layer's import into every architect
import, including every test collection. `tests/conftest.py` does stub
`braintrust` (lines 52-67), so it would in fact work today — but it makes
`import agent` in the test suite depend on the eval layer's module init for
no benefit, and the ids are needed exactly once per stage run. A
function-local load keeps the dependency where it is actually used.

**And make it injectable, not hard-wired.** `run_architect_stage()` takes an
`sc_loader` parameter whose default is this shim. The correctness argument
below settles *which parser* — one universe, shared with the gate — but not
*who imports whom*, and a harness module importing the eval layer is a layer
inversion that also drags `braintrust` into `harness/architect-agent/`'s
runtime deps for a fifteen-line regex. Injecting moves the coupling to the
composition root, where `orchestration/activities.py:99-112` already loads
that exact module — so the future activity passes the function in and adds
no new coupling at all. The default keeps `python -m` and the quickstart
working standalone.

**Rationale**: the *correctness* argument beats the layering argument
here. If the architect parses its own SC set and the Eval-Gate parses
another, the architect's coverage map can report full coverage over a set
the gate never scores, and nothing detects the divergence — the two
artifacts would be silently keyed on different universes. One parser, one
`SC-NNN` universe, and any future change to the bullet format breaks both
at once instead of desynchronising them.

**Alternatives considered**:
- *Duplicate a small regex in the harness module* — the honest
  alternative, and it has real precedent: `harness/pm-agent/agent.py:103-104`
  deliberately duplicates `_REPO_RE`/`_BRANCH_RE` rather than sharing them.
  Rejected because that duplication is of a *validator* (two copies that
  drift merely become independently strict), whereas this is a duplication
  of a *key set* (two copies that drift produce two incompatible coverage
  maps).
- *A new shared top-level package for the parser* — rejected as
  disproportionate: this repo has no shared-lib directory, and inventing
  one for a single function is a bigger structural change than the feature.
- *Have the model report the criterion text it covered instead of an id* —
  rejected: text matching is fuzzy, which is exactly what SC-006's
  "machine-checkable, not just non-empty" rules out.

---

## Unknown 3: FR-002 requires the candidate count to scale, and SC-005 makes "stays fixed regardless of size" a failure. What is the function, and where do angles for `N > 3` come from?

**A pure function of the `SC-NNN` count, plus an angle list at least as
long as the maximum `N`.**

The design doc (§2) gestures at `floor(budget.total / per-candidate-cost)`.
This repo has no budget-accounting mechanism at all — no token ledger, no
per-call cost record — so a budget-derived formula would be aspirational
rather than implementable. The spec's own Assumptions leave the exact
function to implementation time and require only that the count is not
hardcoded regardless of spec size.

**Decision**:

```
MIN_CANDIDATES = 3
MAX_CANDIDATES = 6
candidate_count(sc_ids, n_override=None):
    if n_override is not None: return clamp(n_override, 1, MAX_CANDIDATES)
    return min(MAX_CANDIDATES, MIN_CANDIDATES + max(0, (len(sc_ids) - 5) // 3))
```

with a fixed, ordered angle list of `MAX_CANDIDATES` entries, `angles_for(n)`
returning the first `n`:

1. `minimal-diff-first`
2. `clean-architecture-first`
3. `risk/security-first`
4. `test-and-observability-first`
5. `data-and-contract-first`
6. `operability-and-rollback-first`

The first three are the spec's own named defaults, in its order.
`n_override` accepts 1 (below `MIN_CANDIDATES`) — that is the seam `vibe`
mode's N=1 collapse will use; it is not reachable from this feature.

**Rationale**: the testable properties are what matter, and this shape
makes all three trivially assertable without pinning arbitrary numbers as
requirements — the count is monotonic non-decreasing in `len(sc_ids)`,
never below 3 absent an override, never above the angle list's length. The
`MAX_CANDIDATES = 6` ceiling exists because FR-001 requires each candidate
to have a *distinct, explicitly stated* angle: an unbounded `N` would
either reuse angles (breaking FR-001) or require the model to invent them
(making the stated angle unverifiable). Bounding `N` by the length of a
curated list keeps FR-001 structural.

**Alternatives considered**:
- *Scale on a token/cost budget as §2 suggests* — rejected as
  unimplementable today, not as wrong; when a budget ledger exists,
  `n_override` is the parameter it feeds.
- *Let the model choose `N` and its own angles* — rejected: makes FR-001's
  "explicitly stated angle" and SC-005's scaling both unverifiable, and
  puts a cost multiplier under model control.
- *Scale on `spec.md` length or FR count* — rejected: `SC-NNN` count is
  the complexity measure the rest of this pipeline already uses (the
  Eval-Gate scores against it, and FR-007a's coverage check is keyed to
  it), so reusing it keeps one notion of "how big is this spec."

---

## Unknown 4: What makes a candidate "malformed or empty" (FR-013), given the check must be mechanical enough to count zero-valid-candidates reliably?

**A JSON envelope with three required non-empty fields.**

FR-013's retry hinges on a crisp valid/invalid verdict, and the edge case
in the spec requires synthesis to proceed from the *remaining* valid
candidates when only some fail. Free-form markdown gives no such verdict —
"does this prose resemble a plan" is not a decidable check.

**Decision**: each candidate call is prompted to return exactly one JSON
object, `{"angle": str, "plan_md": str, "tasks_md": str, "adrs": [{"title": str, "body": str}]}`.
A candidate is **valid** iff its output parses as JSON *and* `plan_md` and
`tasks_md` are both non-empty after stripping. `adrs` may be empty (a
minimal-diff plan legitimately needs no ADR). `angle` is not trusted from
the model — the caller-assigned angle is authoritative and the returned
value is ignored if it disagrees. An invalid candidate is dropped and
recorded (angle + the parse failure) in the stage result and the PR comment,
never silently discarded.

**Rationale**: a machine-checkable validity predicate is what FR-013's
"zero valid candidates" and the partial-failure edge case both need, and
JSON is what the scoring step consumes anyway (Unknown 5). Not trusting
the model's echoed `angle` keeps FR-001's "distinct, explicitly stated
angle" a property of the caller's fan-out, not of model compliance.

**Alternatives considered**:
- *Markdown with required `##` section headers* — rejected: heading
  matching is brittle, and a heading with empty content passes it.
- *Accept anything non-empty* — rejected: makes FR-013 unreachable in
  practice, since a one-line apology from the model would count as a valid
  candidate and synthesis would then have to make a plan out of it.
- *Retry an individual malformed candidate* — rejected as out of spec:
  FR-013 defines the retry unit as the whole set (all candidates
  malformed), and the edge case explicitly says synthesis proceeds from the
  remaining valid ones. Per-candidate retry would be a third budget nobody
  asked for.

---

## Unknown 5: FR-005a says scoring and synthesis must be distinguishable steps so an evaluation error is not "silently baked into the generated artifact as if it were fact." What does that mean concretely?

**Two `query()` calls, with a validated data structure — not prose — as the
only thing crossing between them.**

FR-005a permits "separate model calls, or clearly separated phases within
one call." One call with two phases would still let the model's own
scoring narrative condition its synthesis in ways nothing can inspect, and
would leave no artifact to validate.

**Decision**: `score_candidates()` runs one call over all valid candidates
and returns a validated list of per-candidate score records
(`{candidate_index, angle, coverage: {SC-NNN: bool}, internal_consistency: 1..5, notes: str}`).
Validation is strict and happens in Python: every `coverage` key must be a
member of the `SC-NNN` id set from Unknown 2, every id in that set must be
present, and `internal_consistency` must be an integer in `1..5` (FR-005's
ordinal-scale clarification). Candidate order in the *prompt* is randomised
against position/anchoring bias; the returned list stays in candidate-index
order.

`pick_winner(scores)` then computes the winner **in Python** — coverage-true
count, then `internal_consistency`, then lowest index — and `synthesize()`
receives the candidate `plan_md`/`tasks_md`/`adrs`, that structure, and the
computed `winner_index` as a given, and **not** the scoring call's `notes`
prose in any aggregate form beyond the per-candidate field the structure
itself carries. Computing rather than asking is what gives FR-005a
enforcement: a synthesis call that ignored the scores entirely would
otherwise be indistinguishable from one that used them, and nothing else in
this feature defines a tie-break.

A validation failure here is a scoring-step error and propagates to the
caller under FR-013a (if deterministic) or FR-013b (if transient) — it does
**not** consume `MAX_MALFORMED_RETRIES`, which FR-013 scopes strictly to
"every candidate malformed."

**Rationale**: "not silently baked in as fact" is only achievable if there
is a separately inspectable artifact between the two steps, and only
enforceable if that artifact is validated against a key set the model does
not control. The strict key check is what turns SC-006's coverage map from
a claim into a check.

**Alternatives considered**:
- *One call, two prompt phases* — permitted by FR-005a's letter, rejected
  on its stated purpose: no inspectable intermediate artifact, so nothing
  to validate and nothing to log.
- *Lenient validation (accept a partial coverage map, default missing ids
  to `false`)* — rejected: a model that omits half the criteria would then
  look like a model that found them uncovered, which corrupts both the
  gap-detection path (FR-007a) and SC-006's map.

---

## Unknown 6: FR-007b requires the critic to run "as an independent pass — not appended to the synthesis judge's own context." What is actually withheld from it?

**The judge's rationale. Not the angle names.**

The critic must answer two questions: is every `SC-NNN` addressed by the
synthesized plan (FR-007a), and does an *untried* architectural angle
appear to have been missed (FR-007b). The second question is unanswerable
without knowing which angles were tried, so the angle list cannot be
withheld. What must be withheld is the reasoning that produced the
synthesis, since inheriting it is precisely the blind-spot sharing FR-007b
names.

**Decision**: the critic's prompt contains the synthesized `plan_md`/
`tasks_md`/`adrs`, the full `(SC-NNN, text)` list, and the *names* of the
angles tried. It does not contain the judge's rationale, the per-candidate
score records, or any candidate's plan text. It returns
`{"gap_found": bool, "uncovered": [SC-NNN...], "missed_angle": str|null, "note": str}`,
with `uncovered` validated against the same id set. `gap_found` is derived
in Python as `bool(uncovered) or missed_angle is not None`, not taken from
the model's own boolean, so the flag cannot disagree with its own evidence.

Per FR-007b, a `missed_angle` of `null` is recorded and reported as
"no additional angle identified" — never as "no additional angle exists."
The note text in the PR comment says exactly that.

**Rationale**: independence here is about which *reasoning* crosses the
boundary, not about starving the critic of the facts its question needs.
Deriving `gap_found` from the evidence fields rather than trusting a
separate boolean removes a whole class of self-inconsistent output.

**Alternatives considered**:
- *Withhold the angle list too* — rejected: makes FR-007b's question
  literally unanswerable, and would invite the critic to "discover" angles
  that were in fact tried.
- *Give the critic the candidates' full plans* — rejected: it re-imports
  the panel's framing, which is the blind spot FR-007b exists to reduce,
  and it is the largest prompt cost in the stage for no gain on either
  question.
- *Trust the model's `gap_found` boolean* — rejected: a `gap_found: true`
  with an empty `uncovered` and null `missed_angle` would trigger a gap
  round with no gap to target.

---

## Unknown 7: FR-009's gap-triggered candidate sees "the gap description plus the full synthesized plan." How does one function serve both that and FR-003's blind original candidates?

**Same function, two optional parameters, and a hard assertion that the
two modes never overlap.**

The original `N` candidates must have no visibility into each other or into
any synthesized plan (FR-003); the gap candidate must see the synthesized
plan and the gap text (FR-009). These are opposite input contracts on the
same capability.

**Decision**: `generate_candidate(..., gap=None, synthesized_plan=None)`.
Both `None` is fan-out mode (FR-003) and the prompt template used contains
no slot for a plan. Both non-`None` is gap mode (FR-009). Exactly one of
those two states is legal — passing one without the other raises
`ValueError`, so a partially-populated gap call cannot silently degrade
into a blind candidate that happens to mention a gap. Fan-out mode is
invoked only from the `gather`; gap mode is invoked exactly once per stage
attempt, immediately before the re-synthesis, and `run_architect_stage()`
tracks a `gap_round_ran` flag so a second gap round within the same
attempt is impossible (SC-003's "never an unbounded chain").

After the re-synthesis, the critic is **not** re-run within the same
attempt. FR-009 requires "exactly one additional targeted candidate
followed by a re-synthesis"; Story 3's scenario 3 sends any further
checking to the next attempt against `MAX_PLAN_ATTEMPTS`, which this module
does not own.

**Rationale**: one function with a legality assertion keeps the two
contracts visibly adjacent in the code that must honor both, rather than
duplicating a prompt-building path that would drift. The `gap_round_ran`
flag makes SC-003 a structural property of one boolean rather than an
emergent one.

**Alternatives considered**:
- *Two separate public functions* — a fine alternative; rejected only
  because the shared body (clone path, tool binding, JSON envelope,
  validity predicate) is nearly the whole function, and the divergence is
  one prompt template plus two fields.
- *Re-run the critic after the re-synthesis* — rejected: it is one
  re-read of FR-009 away from an unbounded critic↔candidate loop, which
  SC-003 forbids and which `MAX_PLAN_ATTEMPTS` (not owned here) is the
  designated bound for.

---

## Unknown 8: FR-011 says only the synthesized plan is persisted to the spec directory. Does this stage also commit and push it?

**It writes and commits from code; pushing is a separate, caller-optional
step.**

FR-011's "MUST be persisted to the spec's directory" is a requirement on
the system, and FR-014 already has this stage mutating the target repo's PR
thread, so the stage is not read-only in the way `review_spec()` was.

**Decision**: mirror `harness/swe-agent/agent.py`'s split.
`persist_synthesized(checkout, spec_dir, synthesized)` writes `plan.md`,
`tasks.md`, and `ADR-NNN-<slug>.md` files into `<spec_dir>/` in the clone
and makes one commit, returning the new SHA — with an explicit
`-c user.email=... -c user.name=...` identity, mirroring
`orchestration/activities.py`'s `_GIT_IDENTITY`, since unlike swe-agent's
model-made `Bash` commit this one runs code-side on a worker host that may
have no global git config. `push_synthesized(checkout, branch, token)` is a
separate function, called by `run_architect_stage()` only when its
`push=True` default is left in place; it builds the credentialed URL in argv
because the clone step strips the token from `.git/config`. All of it is `subprocess` code — no
model call, and no `Write`/`Bash` tool is bound to any model call in this
stage, which is what makes FR-011 structural: **a candidate's plan is
never written to disk at all**, so "only the synthesized plan is committed"
requires no discipline about commit contents.

`persist_synthesized()` runs *after* the credential scrub window closes
(Unknown 1), as does the push.

**Rationale**: `swe-agent` already separates commit from push for the same
reason — a caller may want the artifact without the network effect (tests
do; a dry-run caller might). Making FR-011 a consequence of tool binding
rather than of correct commit hygiene is the same move `pm-agent`'s
`tools=[]` made for FR-003 there.

**Alternatives considered**:
- *Return the plan text and let the caller persist* — rejected: FR-011
  puts the persistence obligation on the system, and this stage is the only
  component in scope.
- *Let the synthesis model write the files with a bound `Write` tool* —
  rejected: it hands the model the ability to write anything anywhere in
  the checkout, which is exactly the FR-011 guarantee, and it contradicts
  the §6.1 carve-out's premise that these roles never touch a filesystem
  they can execute in.
- *One function doing write+commit+push* — rejected per above.

---

## Unknown 9: Which model route — LiteLLM proxy or direct-to-Anthropic?

**LiteLLM, matching the repo default.**

`CLAUDE.md` makes LiteLLM routing the convention and direct-to-Anthropic
the documented exception. This repo has exactly two precedents:
`shape_issue()` goes direct because it runs on a *target repo's*
GitHub-hosted runner, which cannot reach a self-hosted proxy on
`localhost:4000`; `review_spec()` goes through LiteLLM because it runs on
the Temporal worker host, which can.

**Decision**: LiteLLM for all four call types (candidate, scoring,
synthesis, critic), via `env={"ANTHROPIC_BASE_URL": LITELLM_BASE_URL,
"ANTHROPIC_API_KEY": LITELLM_API_KEY}` on each `ClaudeAgentOptions`,
exactly as `harness/pm-agent/agent.py:302-303` does.

**Rationale**: this stage's only trigger is a pipeline run on the worker
host — it has no target-repo-runner path, since nothing about fan-out
needs to execute on the target repo's infrastructure. Neither of the two
documented reasons for deviating (network reachability, Claude Code skill
discovery for `/speckit-*`) applies: the `/speckit-analyze` dependency that
would have needed skill discovery is dropped per plan.md's §2 deviation.

**Alternatives considered**:
- *Direct-to-Anthropic for consistency with `harness/swe-agent`* —
  rejected: `swe-agent`'s deviation is justified by *its* reasons
  (documented in its `SKILL.md`), and inheriting a deviation by proximity
  is how a documented exception becomes an undocumented default.
- *LiteLLM for the judge, direct for candidates* — rejected: no reason
  distinguishes them, and a split route doubles the credential surface for
  nothing.

---

## Unknown 10: `attempt` and idempotency — can this stage safely be re-invoked?

**Yes for the comment; the commit is idempotent by content, and the model
calls are not idempotent at all.**

FR-014 posts one combined comment per plan-attempt via `gh pr comment`, a
mutating call with no built-in idempotency — the same problem 003 solved
for `review_spec()`.

**Decision**: same solution, extended. A hidden marker
`<!-- architect-agent:stage attempt=<N> spec=<sha> -->` leads the combined
comment body, where `sha` is the short SHA of the branch's `spec.md` at
clone time. `run_architect_stage()` checks for an existing comment starting
with `<!-- architect-agent:stage attempt=<N> ` **before doing any model
work** and, if found, returns the degraded shape
`{"attempt", "comment_body", "idempotent_hit": True}` — **not** the full
result dict. That divergence from `review_spec()` is forced: `review_spec()`
returns `{"writeup", "attempt"}`, which a comment body does reconstruct,
whereas this stage's twelve keys (`plan_md`, `scores`, `commit_sha`,
`gap_round_ran`, …) do not exist anywhere in a posted comment. Returning the
full shape's key set would hand a caller a `KeyError` on the *success* path
of a Temporal retry, so callers branch on `idempotent_hit` instead.

`attempt` MUST be strictly increasing per distinct stage invocation and is
the sole idempotency key — the `spec=<sha>` in the marker is for the reader
and does not participate in the match, so a caller reusing an `attempt`
against changed `feedback` *or a changed spec* is caller error, the same
contract `review_spec()` states.

The early check placement matters more here than in 003: a re-invocation
that skipped only the *post* would still have burned `N + 3` model calls.

**Rationale**: reusing 003's exact marker convention keeps one parseable
comment grammar across pipeline stages, which is also what makes SC-007's
correlation half work (see plan.md, "Known partial: SC-007").

**Alternatives considered**:
- *Edit the existing comment instead of skipping* — rejected for v1: it
  makes the PR thread lose the per-attempt history FR-014's delta line
  assumes, and 003 chose skip-on-marker for the same reason.
- *Include the model output hash in the key* — rejected: it makes every
  retry a fresh post, which is the duplication the marker exists to
  prevent.

---

## Unknown 11: `tests/conftest.py` puts `harness/pm-agent/` on `sys.path` so tests can `import agent`. What happens when a second `harness/<agent>/agent.py` exists?

**They collide on the module name `agent`, and `tests/test_pm_agent.py`
breaks — so the shim has to change before this feature's tests can exist.**

`tests/conftest.py:16-18` inserts `harness/pm-agent/` at `sys.path[0]`
and stubs `claude_agent_sdk`/`dotenv`/`braintrust` so `import agent`
resolves to the PM agent with none of its runtime deps installed in the
root venv. `harness/architect-agent/agent.py` is a second file with the
same basename: whichever directory lands earlier on `sys.path` wins, and
the other agent's tests silently import the wrong module. This is latent
today only because `pm-agent` is the sole harness agent with tests.

**Decision**: keep the existing stub block as-is, and load each harness
agent by explicit path under a distinct module name rather than by
`sys.path` search:

```python
def _load_agent(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

_load_agent("architect_agent", REPO_ROOT / "harness" / "architect-agent" / "agent.py")
```

`tests/test_architect_agent.py` then does `import architect_agent`. The
existing `harness/pm-agent/` `sys.path` insert and `import agent` in
`tests/test_pm_agent.py` are left untouched — this feature adds a
non-colliding path for its own module rather than refactoring 003's
working tests, which is a separate cleanup.

**Rationale**: the stubs are the reusable part of `conftest.py` and stay
shared; the `sys.path` insert is the part that does not generalise past one
agent. Naming modules explicitly also means a future third harness agent
adds one line instead of hitting the same collision.

**Alternatives considered**:
- *Rename this feature's module to `architect_agent.py`* — rejected: it
  breaks the `harness/<agent>/agent.py` convention every existing agent
  (including `template-agent`) follows, and `registry/agents/swe-agent/versions/v1.yaml`'s
  `harness_entrypoint` field assumes it.
- *Refactor `test_pm_agent.py` onto the same explicit loader* — the right
  end state, deliberately deferred: it edits 003's tests for no behavior
  change, and the additive path above is enough for this feature.
- *Per-test-file `sys.path` manipulation* — rejected: import caching makes
  ordering-dependent, so it would work until the two test files run in the
  wrong order.
