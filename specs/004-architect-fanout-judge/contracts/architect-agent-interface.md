# Contract: `harness/architect-agent/agent.py` public interface

The interface this feature exposes. Its callers are (a) a human or test
invoking the module directly, and (b) a future
`orchestration/activities.py::architect_stage_activity`, which this feature
does **not** write (see [plan.md](../plan.md), "Out of scope").

Shapes and validation rules referenced below are specified in
[data-model.md](../data-model.md); the reasoning is in
[research.md](../research.md).

Conventions inherited verbatim from `harness/pm-agent/agent.py` and
`harness/swe-agent/agent.py`, not re-argued here:

- `_validate_repo` / `_validate_branch` guard every caller-supplied value
  that reaches `git`/`gh` argv (argument-injection defense).
- `_run(cmd, cwd)` wraps `subprocess.run`, raising `CalledProcessError` on
  non-zero exit; `_scrubbed(error, secret)` redacts a token before the
  error escapes.
- `_model_text(prompt, options)` returns only the model's final text
  result, not a join of every SDK message.
- `load_dotenv` reads this repo's root `.env` without overriding ambient
  values; Braintrust is initialised at module level against
  `BRAINTRUST_PROJECT`.

---

## Module constants

```python
MIN_CANDIDATES = 3            # FR-002's default floor
MAX_CANDIDATES = 6            # == len(ANGLES); bounds N so every candidate
                              # has a distinct *stated* angle (FR-001)
MAX_MALFORMED_RETRIES = 1     # FR-013; owned here
_COMMENT_LIMIT = 60000        # margin under GitHub's 65536-char body cap

CANDIDATE_CONCURRENCY = 3     # in-flight CLI subprocesses; see generate_candidates()
CANDIDATE_TIMEOUT_S = 600     # per model call; timeout => that candidate is invalid
MAX_PLAN_CHARS = 40000        # per-candidate plan_md cap; bounds prompt growth
MAX_TASKS_CHARS = 20000       # per-candidate tasks_md cap

ANGLES = [
    "minimal-diff-first",
    "clean-architecture-first",
    "risk/security-first",
    "test-and-observability-first",
    "data-and-contract-first",
    "operability-and-rollback-first",
]

MODEL = "claude-sonnet-5"    # every role (candidates, gap candidate, scoring,
                              # synthesis, critic) — the only id
                              # litellm/config.yaml guarantees resolves,
                              # since the Agent SDK CLI requests it by
                              # default (plan.md's Constraints)
```

`MAX_PLAN_ATTEMPTS` is deliberately **absent** — it is not this module's to
name (FR-010/FR-013a/FR-013b belong to
`specs/005-pipeline-mode-signals-escalation/`). See data-model.md's budget
table.

---

## `def candidate_count(sc_ids: list[str], n_override: int | None = None) -> int`

FR-002 / SC-005. Pure; no I/O, no model call.

- `n_override is not None` → `max(1, min(n_override, MAX_CANDIDATES))`.
  The `1` floor is the seam `vibe` mode's N=1 collapse will use; this
  feature never passes it.
- otherwise → `min(MAX_CANDIDATES, MIN_CANDIDATES + max(0, (len(sc_ids) - 5) // 3))`

**Guaranteed properties** (these, not the specific arithmetic, are what
SC-005 requires):

1. Monotonic non-decreasing in `len(sc_ids)`.
2. `>= MIN_CANDIDATES` whenever `n_override is None`.
3. `<= MAX_CANDIDATES == len(ANGLES)` always.
4. Not constant across spec sizes — `candidate_count(["SC-001"] * 20) > candidate_count(["SC-001"] * 5)`.

## `def angles_for(n: int) -> list[str]`

Returns `ANGLES[:n]`. Raises `ValueError` if `n > MAX_CANDIDATES` — FR-001
requires each candidate's angle to be distinct and explicitly stated, so
running out of curated angles is an error, never a wrap-around or a
model-invented angle.

---

## `async def generate_candidate(checkout: Path, spec_dir: str, angle: str, *, gap: str | None = None, synthesized_plan: dict | None = None) -> dict`

FR-001, FR-003 (fan-out mode) and FR-009 (gap mode). One model call.

**Mode legality** — exactly one of these is valid; anything else raises
`ValueError`:

| `gap` | `synthesized_plan` | Mode |
| --- | --- | --- |
| `None` | `None` | Fan-out (FR-003): prompt has no slot for any plan or other candidate |
| set | set | Gap-targeted (FR-009): prompt carries the gap text and the full synthesized plan |

A partially-populated call is caller error, so a gap candidate cannot
silently degrade into a blind one (research.md Unknown 7).

**Tool binding** — `tools=["Read", "Grep", "Glob"]`, `setting_sources=[]`,
`cwd=str(checkout)`. No `Write`, `Edit`, or `Bash`. This is what makes
FR-011 structural: the candidate's plan cannot reach the filesystem.
`setting_sources=[]` prevents a `.claude/settings.json` hook committed to
the branch under review from executing in the CLI subprocess — a risk
independent of tool binding, since hooks run in the subprocess itself.

**Returns** an Architect Candidate dict (data-model.md). `valid` is derived
from the validity predicate; an unparseable or empty-plan response returns
`{"valid": False, "error": <reason>, "angle": angle, ...}` rather than
raising — FR-013 and the partial-failure edge case both need a per-candidate
verdict, not an exception.

`angle` in the return value is always the caller's, never the model's echo.

## `async def generate_candidates(checkout: Path, spec_dir: str, angles: list[str]) -> list[dict]`

`asyncio.gather` over `generate_candidate()` in fan-out mode, one call per
angle. Returns one dict per angle, in `angles` order, valid and invalid
alike.

**FR-003 is structural**: each `query()` spawns its own CLI subprocess with
its own context. There is no shared conversation for one candidate's output
to reach another through.

**Bounded, not unbounded.** A bare `asyncio.gather` at `N=6` puts six
concurrent Claude CLI subprocesses on the worker host against one self-hosted
LiteLLM proxy, and one hung `query()` hangs the whole stage forever. So:

- `asyncio.Semaphore(CANDIDATE_CONCURRENCY)` caps in-flight calls.
- each call is wrapped in `asyncio.wait_for(..., CANDIDATE_TIMEOUT_S)`; a
  timeout yields `{"valid": False, "error": "timeout", "angle": angle, ...}`,
  reusing the partial-failure path that already exists rather than adding a
  second failure mode.
- `MAX_PLAN_CHARS` / `MAX_TASKS_CHARS` bound each candidate's `plan_md` and
  `tasks_md`; an over-length response is `valid=False`. Without this, prompt
  size is `O(N × plan_length)` with no context-limit guard — scoring carries
  all N plans, synthesis carries them again, and the gap round repeats both
  over `N + 1`. `_COMMENT_LIMIT` bounds the *comment*, not the *prompts*.

**Must be called inside the stage's credential-scrub window** (see
`run_architect_stage()`). Individual candidates must **not** pop/restore
`os.environ` themselves — under `gather`, one candidate's restore would
hand a live `GH_TOKEN` to a sibling still spawning (research.md Unknown 1).
The semaphore does not change this: candidates still overlap.

---

## `async def score_candidates(candidates: list[dict], sc_ids: list[tuple[str, str]]) -> list[dict]`

FR-005. One model call over all **valid** candidates. Returns a list of
Candidate Score dicts (data-model.md).

**Strict, total validation** in Python:

- `coverage` keys must equal `{id for id, _ in sc_ids}` exactly — a
  superset, a subset, or a non-`SC-\d+` key raises.
- `internal_consistency` must be an `int` in `1..5` (FR-005's ordinal-scale
  clarification).
- `candidate_index` must reference a valid candidate.

A validation failure raises — an FR-013a-class error the caller charges to
`MAX_PLAN_ATTEMPTS` per CO-2. It does **not** consume
`MAX_MALFORMED_RETRIES`.

**Candidate order is randomised** in the prompt (the returned list stays in
candidate-index order). LLM-judge position/anchoring bias is well documented,
and FR-007a's coverage half is a closed-form per-candidate determination that
needs no cross-candidate comparison at all. Randomising the presentation
order is the cheap mitigation; scoring each candidate in its own call is the
thorough one, and is the natural upgrade if bias shows up in practice.

## `def pick_winner(scores: list[dict]) -> int`

FR-005a. **Pure Python, no model call.** Returns the winning candidate index
under this total ordering, applied in sequence until one discriminates:

1. Highest count of `coverage` entries that are `True`.
2. Highest `internal_consistency`.
3. Lowest `candidate_index` (deterministic tie-break; total by construction,
   since indices are unique).

The winner is **computed, not model-chosen**. A `synthesize()` call that
ignored the scores entirely would otherwise be indistinguishable from one
that used them, which drains FR-005a's stated purpose — "an evaluation error
is not silently baked into the artifact as fact" — of any enforcement. This
also gives ties a defined answer (nothing else in this feature does), makes
the PR comment's "why this winner" line a reproducible computation rather
than a model claim, and makes the property assertable in a test.

## `async def synthesize(candidates: list[dict], scores: list[dict], winner_index: int, feedback: str | None = None) -> dict`

FR-004, FR-005a. One model call, separate from `score_candidates()`.
Returns exactly one Synthesis Result dict, or raises — there is no
list-valued path, which is how SC-002's "never zero and never more than
one" is enforced rather than requested.

**Receives** the valid candidates' `plan_md`/`tasks_md`/`adrs` plus the
validated `scores` structure. Does **not** receive the scoring call's
reasoning in any aggregate form beyond the per-candidate `notes` field the
structure itself carries — FR-005a's separation exists so an evaluation
error is inspectable rather than baked into the artifact as fact.

`feedback`, when present, is the prior attempt's human rejection text
(spec.md's rejection edge case). It is content for this call only; this
function neither counts nor bounds attempts.

`winner_index` is an **input**, computed by `pick_winner()` and passed to the
model as a given — the synthesis call does grafting and prose, not selection.
It is echoed unchanged into the returned dict; the model's own echo of it, if
any, is discarded the way `generate_candidate()` discards the model's echo of
`angle`.

Every `grafted_from` entry must reference a valid candidate index; a dangling
reference raises (FR-013a class).

## `async def check_completeness(synthesized: dict, sc_ids: list[tuple[str, str]], angles_tried: list[str]) -> dict`

FR-007a, FR-007b. One model call with a fresh context. Returns a
Completeness Note dict (data-model.md).

**Withheld from the prompt** (FR-007b's independence requirement): the
judge's rationale, the score records, and every candidate's plan text.
**Supplied**: the synthesized plan, the full `(id, text)` criteria list,
and `angles_tried` — the last is required, since "was an angle missed" is
unanswerable without knowing which were tried.

`uncovered` is validated against the id set. `gap_found` is **derived in
Python** as `bool(uncovered) or missed_angle is not None`, never taken from
the model's own boolean.

`missed_angle is None` renders in `note` as *"no additional angle was
identified"* — FR-007b forbids reporting it as confidence that none exists.

---

## `def persist_synthesized(checkout: Path, spec_dir: str, synthesized: dict) -> str`

FR-011. Pure `subprocess`/filesystem code — no model call.

Writes `<spec_dir>/plan.md`, `<spec_dir>/tasks.md`, and one
`<spec_dir>/ADR-NNN-<slug>.md` per ADR into the clone, then makes one
commit. Returns the new commit SHA.

**The commit MUST carry an explicit committer identity**, passed as
`git -c user.email=<...> -c user.name=<...> commit ...`, mirroring
`orchestration/activities.py`'s `_GIT_IDENTITY` constant. `harness/swe-agent`
gets away without one only because *the model* commits via `Bash` in a
sandbox that has git configured; here the commit is code-side, on a Temporal
worker host that may have no global git config — where `git commit` fails
with `Please tell me who you are`, **after** all `N + 3` model calls have
been paid for. This passes in tests regardless (temp repos inherit the
developer's config), so it must be asserted on the argv, not inferred from a
green test.

**Overwrites unconditionally.** An existing `<spec_dir>/plan.md` or
`tasks.md` on the branch is replaced by the synthesized one — that is the
intent (this stage *is* the plan producer for a pipeline run), but it means
pointing the stage at a branch whose plan was written by hand or by
`/speckit-plan` destroys it. The prior content stays recoverable through
git history, since this is a commit on a branch, not an in-place edit of
untracked content.

Writes **only** the synthesized artifacts. Candidate plans were never on
disk to begin with (see `generate_candidate()`'s tool binding), so FR-011
holds without any discipline about commit contents.

## `def push_synthesized(checkout: Path, branch: str, token: str | None = None) -> None`

Pushes `branch` from the clone. Because step 3 stripped the credential from
`origin`, this pushes to an explicitly-constructed
`https://x-access-token:<token>@github.com/<repo>.git` argv URL when `token`
is set, rather than relying on the remote — the credentialed URL never goes
back into `.git/config`. `CalledProcessError` output is `_scrubbed(...)`
against the token, as everywhere else. With `token=None` it falls back to
`git push origin <branch>` and the host's ambient credential helper.

Separate from
`persist_synthesized()`, mirroring `harness/swe-agent/agent.py`'s own
commit/push split, so a caller can take the artifact without the network
effect. Called by `run_architect_stage()` when its `push=True` default
stands.

## `def post_stage_comment(repo: str, pr_url: str, attempt: int, *, synthesized: dict, scores: list[dict], candidates: list[dict], completeness: dict, delta: str | None) -> str`

FR-006, FR-014. One `gh pr comment`. Returns the posted body.

Assembles the body in data-model.md's fixed section order, honours the
`_COMMENT_LIMIT` size budget (truncating `<details>` blocks with an
explicit notice, never silently, and never dropping the synthesized plan),
and prefixes the hidden marker
`<!-- architect-agent:stage attempt=<N> spec=<sha> -->`.

`delta` is `None` on attempt 1 and a one-line summary of what changed
thereafter (FR-014's delta-line requirement). It is an argument, so
`run_architect_stage()` owns the derivation. **The rule, so FR-014 is
implemented rather than merely typed:**

```
attempt == 1                      -> None
feedback is not None              -> "Revised after: <first line of feedback, truncated>"
gap_round_ran                     -> "Re-synthesized after gap round: <completeness.note, truncated>"
otherwise (attempt >= 2)          -> "Re-ran attempt <N> against spec <sha>."
```

`delta` MUST be non-`None` whenever `attempt >= 2`; the final branch exists
so that guarantee holds with no prior feedback and no gap.

## `def _existing_stage_comment(repo: str, pr_url: str, attempt: int) -> str | None`

Returns the body of an existing comment whose body starts with
`<!-- architect-agent:stage attempt=<N> `, else `None`. Mirrors
`harness/pm-agent/agent.py::_existing_review_comment`.

---

## `async def run_architect_stage(repo: str, branch: str, pr_url: str, attempt: int, feedback: str | None = None, spec_dir: str | None = None, n_candidates: int | None = None, push: bool = True, sc_loader: Callable[[Path], list[tuple[str, str]]] | None = None) -> dict`

The stage entrypoint. Sequences everything above.

**Arguments**

| Name | Notes |
| --- | --- |
| `repo` | `owner/name`; `_validate_repo` |
| `branch` | `_validate_branch` |
| `pr_url` | Assumed to exist — nothing in this repo creates one yet (data-model.md, "`pr_url`") |
| `attempt` | `>= 1`, MUST be strictly increasing per distinct invocation; **sole** idempotency key — `_existing_stage_comment` matches on the `attempt=<N> ` prefix only, so re-running a reused `attempt` against a *changed* `spec.md` silently returns the stale body. The marker records the spec sha for the reader, but does not participate in the match. Reusing an attempt number is caller error. |
| `feedback` | Prior attempt's human rejection text; content only, never counted here |
| `spec_dir` | Defaults to `specs/<branch>`; caller-overridable, never a glob over `specs/*/` |
| `n_candidates` | `n_override` for `candidate_count()`; the future `vibe` seam |
| `push` | `False` skips `push_synthesized()` only |
| `sc_loader` | `Callable[[Path], list[tuple[str, str]]]`; defaults to the `eval.config` path-shim (step 4) |

**Sequence**

1. Validate inputs. `attempt < 1` → `ValueError`.
2. `_existing_stage_comment(...)` — **before any model work**. On a hit,
   return the **degraded idempotent shape** below immediately; a
   re-invocation that skipped only the post would still have burned
   `N + 3` model calls.

   ```python
   {"attempt": int, "comment_body": str, "idempotent_hit": True}
   ```

   This is a **terminal, degraded shape, not the full result dict**. The
   twelve keys of the normal return (`plan_md`, `scores`, `commit_sha`,
   `gap_round_ran`, …) are not reconstructible from a posted comment body,
   so pretending to return them would hand a caller a `KeyError` on the
   *success* path of a Temporal retry. Every caller MUST branch on
   `result.get("idempotent_hit")` before touching any other key. The full
   shape's `idempotent_hit` is absent — a caller may treat absent and
   `False` as equivalent.

   This is the one behavioural difference from
   `harness/pm-agent/agent.py::review_spec()`, whose own return is only
   `{"writeup", "attempt"}` and therefore *is* reconstructible from the
   comment.
3. Shallow-clone `branch` into a `TemporaryDirectory` using a token-embedded
   URL (so private target repos clone), then **immediately**
   `git remote set-url origin https://github.com/<repo>.git` and disable the
   checkout's credential helper. Resolve `<spec_dir>/spec.md`; a missing file
   raises with the "pass `spec_dir` explicitly" guidance `review_spec()` uses.

   **The `set-url` is not optional and is not the same thing as the
   credential-helper reset.** `git clone https://x-access-token:<token>@...`
   writes the token into the checkout's `.git/config` as
   `[remote "origin"] url = ...`; `git config --local credential.helper ""`
   does nothing about it. Candidates are bound `Read` with `cwd=checkout`
   (see `generate_candidate()`), and their `plan_md` is posted verbatim into
   a target-repo PR comment (FR-014) — so without the rewrite, a candidate
   that reads `.git/config` publishes a GitHub App installation token.
   Note the mechanism: `Grep`/`Glob` do not reach it (ripgrep skips `.git/`),
   `Read` on the explicit path does. This is also orthogonal to
   `_no_git_credentials()`, which scrubs `os.environ` in the parent process
   and never touches the checkout.

   The credentialed URL is re-attached only in step 10, for the push, after
   every model call has finished.
4. `sc_loader(spec_path)` → the `(id, text)` criteria list. No criteria →
   precondition failure (data-model.md), not a gap finding.

   `sc_loader` is an **injected parameter** defaulting to the path-shim that
   loads `eval/braintrust/eval.config.py::load_success_criteria_ids`. The
   correctness argument for a single `SC-NNN` universe shared with the
   Eval-Gate is right; making the *harness* import from the *eval* layer to
   get it is a layer inversion, and it drags `braintrust` into
   `harness/architect-agent/`'s runtime deps for a fifteen-line regex.
   Injecting it moves the coupling to the composition root — where
   `orchestration/activities.py` **already** loads that exact module by path,
   so the future activity passes the function in and adds no new coupling at
   all. The default keeps `python -m` and the quickstart working standalone.
5. **Enter the credential-scrub window** (`GH_TOKEN`/`GITHUB_TOKEN` popped
   from the parent process's `os.environ`, restored in a `finally`). Every
   model call in steps 6-9 happens inside it; the clone above and the git/gh
   mutations in steps 10-11 happen outside it.

   **The `try`/`finally` covers steps 6-9 only** — not the whole function.
   A `finally` wrapping the function body would leave steps 10-11 running
   with the token still popped on the success path, so
   `persist_synthesized`'s commit, the push, and `gh pr comment` would all
   fail against a private repo. The window is a scope, and getting that
   scope wrong is the same bug class the per-candidate scrub had
   (research.md Unknown 1). Steps 2 and 3 also need the token and are
   deliberately before it.
6. `candidate_count()` → `angles_for()` → `generate_candidates()`.
   If **zero** candidates are valid: retry step 6 up to
   `MAX_MALFORMED_RETRIES` times (FR-013). On exhaustion, raise
   `RuntimeError` — explicitly *not* falling through to the caller's plan
   budget, which FR-013 forbids.
7. `score_candidates()` → `pick_winner()` → `synthesize()`.
8. `check_completeness()`.
9. If `gap_found` and not `gap_round_ran`: one `generate_candidate()` in gap
   mode, then `score_candidates()` + `pick_winner()` + `synthesize()` again
   over the extended set; set `gap_round_ran = True`, which per **CO-1** the
   caller charges as one plan attempt. The critic is **not** re-run — FR-009
   specifies exactly one targeted candidate plus a re-synthesis, and Story
   3's scenario 3 sends further checking to the next attempt against
   `MAX_PLAN_ATTEMPTS`.
10. Exit the scrub window. `persist_synthesized()`, then
    `push_synthesized(checkout, branch, token)` if `push` — the token goes
    into that call's argv, never back into `.git/config` (step 3).
11. `post_stage_comment()`, with `delta` derived per that function's rule.

**Returns**

```python
{
    "attempt": int,
    "plan_md": str, "tasks_md": str, "adrs": list,
    "winner_index": int, "grafted_from": list[int], "rationale": str,
    "scores": list[dict],            # SC-006's machine-checkable map
    "completeness": dict,            # gap_found / uncovered / missed_angle / note
    "gap_round_ran": bool,           # SC-003: at most one, structurally
    "invalid_candidates": list[dict],# angle + error, reported not hidden
    "malformed_retries_used": int,
    "commit_sha": str,
    "comment_body": str,
}
```

…on the normal path. On an idempotent hit (step 2) the return is instead the
three-key degraded shape documented there, distinguished by
`idempotent_hit: True`.

**Raises**

| Condition | Exception | Budget the caller charges |
| --- | --- | --- |
| Bad `repo`/`branch`/`attempt`, illegal gap-mode args, `n > MAX_CANDIDATES` | `ValueError` | Caller error — neither budget |
| Missing `<spec_dir>/spec.md`, no `### Measurable Outcomes`, empty criteria | `RuntimeError` / `ValueError` | Precondition failure — neither budget |
| Zero valid candidates after `MAX_MALFORMED_RETRIES` | `RuntimeError` | Stage failed; FR-013 forbids falling through to `MAX_PLAN_ATTEMPTS` |
| Scoring/synthesis/critic call error or validation failure | propagates | `MAX_PLAN_ATTEMPTS` (FR-013a) in the caller if deterministic (CO-2); activity-level transient retry if not (CO-2a) |
| `git`/`gh` failure | `CalledProcessError`, token-scrubbed | Caller's choice |

### Consumer obligations

This module deliberately does not name `MAX_PLAN_ATTEMPTS`, so several of
this feature's own requirements are only satisfiable **in the caller** — the
future `orchestration/activities.py::architect_stage_activity` and the
`specs/005-pipeline-mode-signals-escalation/` workflow changes. Without the
five rules below, FR-010, FR-013, FR-013a and FR-013b are requirements that no
artifact in 004 or 005 implements. They are listed here, in 004's contract,
because 004 is where the obligation originates.

| # | Trigger | The caller MUST |
| --- | --- | --- |
| CO-1 | `gap_round_ran is True` in the returned dict | Charge **one** `MAX_PLAN_ATTEMPTS` attempt. FR-010 requires the gap-driven round to cost an attempt; because the round runs *inside* one `run_architect_stage()` call, this module cannot charge it and the caller must. Without CO-1 the round is free and FR-010 is violated silently. |
| CO-2 | A propagated scoring/synthesis/critic error (the FR-013a row above) that is a **deterministic validation failure** | Charge one `MAX_PLAN_ATTEMPTS` attempt. |
| CO-2a | The same, but a **transient** failure (API 429/5xx, timeout, connection reset) | Retry the activity under Temporal's `_TRANSIENT_RETRY` instead of charging a plan attempt. `spec.md`'s rationale for splitting `MAX_MALFORMED_RETRIES` off — "an API or parsing hiccup shouldn't consume the same budget a human needs for legitimate plan iteration" — applies with more force here, because under the collapsed activity boundary (below) charging a plan attempt re-runs the entire `N + 3`-call fan-out. |
| CO-3 | `RuntimeError` from `MAX_MALFORMED_RETRIES` exhaustion | **Not** charge a plan attempt, and escalate to a human (005's FR-011 path). FR-013 forbids the fall-through; but note that because this is not a budget exhaustion, 005's escalation does *not* fire on its own — the caller must map this exception onto the escalation path explicitly, or the run dies silently. |
| CO-4 | Any return | Branch on `idempotent_hit` (step 2) before reading any other key. |

`specs/005-pipeline-mode-signals-escalation/spec.md` currently describes
only a per-stage attempt budget and says nothing about CO-1, CO-2a or CO-3;
carrying these three into that spec is 005's tracked follow-up.

### Intended activity boundary

`plan.md` runs all `N + 3` model calls inside **one** in-process function,
where `docs/70-multi-agent-pipeline-design.md` §2/§6.1 specify one Temporal
activity per stage with the N candidates as plain concurrent activities.
That deviation and its rationale (N full `plan.md` blobs through workflow
history hit Temporal's payload/history limits) are recorded in `plan.md`.
Its consequences are the caller's to handle:

- **One** activity — `architect_stage_activity` — wrapping
  `run_architect_stage()`.
- `start_to_close_timeout` must cover `N + 3` model calls plus a possible
  gap round: **≥ 20 minutes at N=6**, not the minutes-scale default the
  Build activity uses.
- The activity should **heartbeat** between stage steps. There is no durable
  checkpoint inside the stage, so a critic-step failure discards the whole
  fan-out's spend; a heartbeat at least distinguishes a slow stage from a
  hung one.
- Retry policy: `_TRANSIENT_RETRY` (`pipeline_workflow.py`) is safe **only**
  because step 2 makes the stage idempotent per `attempt`, and only once the
  H2 degraded shape is honoured per CO-4. Before that, `_NO_AUTO_RETRY`.
- **Workflow versioning**: inserting this stage ahead of Build changes
  `AgentPipelineWorkflow`'s activity sequence, so in-flight executions
  replaying against new code hit non-determinism. 004 ships no workflow
  change, so the mechanism choice — `workflow.patched(...)` versus a new
  workflow name on a new task queue — lands in 005. Naming it here so 005
  does not rediscover it.

**No budget-encoding exception type is introduced.** 003's
`contracts/pm-agent-interface.md` lists its own `PmAttemptsExhausted` as
*removed* — an agent that names the workflow's budget becomes a second,
conflicting owner of it. `MAX_MALFORMED_RETRIES` is bounded here because
its trigger condition is only observable here; `MAX_PLAN_ATTEMPTS` is not,
and errors that belong to it propagate as plain exceptions.

---

## `python -m` / `__main__` entrypoint

Mirrors `harness/pm-agent/agent.py`'s dispatch shape:

```
uv run python agent.py architect-stage <repo> <branch> <pr_url> <attempt> [feedback]
```

`asyncio.run(...)` the coroutine, print the result dict, `logger.flush()`.
Intended for manual/quickstart use, not as the production trigger — that is
the future Temporal activity's job.
