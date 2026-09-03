# Phase 0 Research: PM-Agent Issue-Shaping and Spec-Review Gate

**Revision note**: This is the second senior-architect review pass
(2026-09-03, same day, later revision). It found the *first* revision's
Unknown 2 fix incomplete — closes git's credential path but not `gh`
CLI's separate one — and Unknown 1's LiteLLM routing incompatible with
Unknown 4's revised trigger (both now fixed below), plus two new
correctness bugs not caught by the first revision: Unknown 7 (spec-path
resolution) and Unknown 8 (an invalid `gh --json` field that would make
`shape_issue()` hard-error on every call). Unknowns 3, 4, 5, 6 are
otherwise unchanged from the first revision — this review confirmed they
hold.

## Unknown 1: How does Issue-Shaping edit the issue while having no capability to run shell commands, use git, or invoke Spec Kit tools (FR-003)? How is the model reached, given Unknown 4 runs it on a target repo's GitHub-hosted runner? **[revised]**

- **Decision**: The model is called with `ClaudeAgentOptions(allowed_tools=[])`
  — no tools bound at all. Code (not the model) fetches the current
  `title`/`body` via `gh issue view <n> --json title,body` before the call,
  passes them as plain prompt text, and after the model returns its rewritten
  text, code (not the model) calls `gh issue edit <n> --title ... --body ...`.
  The zero-tool guarantee is unchanged from the first pass. What's revised:
  the model call goes **direct-to-Anthropic** (`ANTHROPIC_API_KEY`), not
  through the LiteLLM proxy.
- **Rationale (zero tools)**: `swe-agent`'s own guardrail precedent
  (`harness/swe-agent/agent.py`'s `push_and_open_pr`, called from code after
  `query()` returns, never left to the model) is the established pattern in
  this repo for "the model must not be able to do X" — do the mutating step
  in code, not by prompting the model not to. Zero bound tools is a stronger
  version of the same idea and directly satisfies FR-002/FR-003: there is
  nothing for the model to invoke a branch, spec, or pipeline run with.
- **Rationale (direct-to-Anthropic, revised)**: The first revision kept
  LiteLLM routing (`LITELLM_BASE_URL`, `localhost:4000`) on the strength of
  "the repo's default convention." But Unknown 4's revised trigger design
  runs `shape_issue()` on a **target repo's GitHub-hosted runner**, and
  `docs/70-multi-agent-pipeline-design.md` §1.1 already establishes — as the
  entire reason a webhook bridge exists for the Temporal-signal path — that
  a GitHub-hosted runner cannot reach a self-hosted `localhost:4000` proxy
  running on a developer's own machine. LiteLLM routing and Unknown 4's
  runner choice are mutually incompatible; one of them has to change, and
  Unknown 4's runner choice is the one with no alternative (Issue-Shaping's
  whole point is firing on target-repo issues). This is a **different**
  justification from `harness/swe-agent/agent.py`'s direct-to-Anthropic
  deviation (which is about needing Claude Code's own skill discovery for
  `/speckit-implement`) — Issue-Shaping needs no skill discovery at all
  (zero tools); the deviation here is purely about network reachability
  from an execution context this feature doesn't control. Record both
  deviations' distinct justifications so a future reader doesn't conflate
  them or assume fixing one fixes the other.
- **Alternatives considered**:
  - Binding a narrow custom "gh issue edit" MCP tool and nothing else —
    rejected as unnecessary indirection when the model doesn't need
    iterative tool use at all here (one shot: read text in, rewritten text
    out).
  - Keeping LiteLLM routing and having the target-repo runner tunnel or
    proxy to it — rejected as introducing exactly the network-exposure
    problem `docs/70` §1.1 already rejected a simpler version of (exposing a
    local dev service to the internet), for a feature that has no other
    reason to need it.

## Unknown 2: How does Spec-Review get read-only repository inspection (including `/speckit-analyze`, which needs `Bash` to run `.specify/scripts/bash/check-prerequisites.sh`) while structurally being unable to push a commit or otherwise mutate the repo (FR-007)? **[revised again]**

- **Decision (revised again)**: The first revision (env-scrub `GH_TOKEN`/
  `GITHUB_TOKEN` + `git config --local credential.helper ""`) closes `git
  push` specifically, but a second senior-architect pass found it
  incomplete: on the host-process execution path, `gh` itself — not just
  git — carries an independent, ambient credential. `gh` resolves its
  token in this order: `GH_TOKEN`/`GITHUB_TOKEN` env vars first, then a
  config file at `$GH_CONFIG_DIR` (default `~/.config/gh/hosts.yml`), which
  `gh auth login` writes and which `CLAUDE.md` itself documents swe-agent's
  host-CLI path already relies on ("falling back to the host's ambient `gh`
  credential helper otherwise"). Scrubbing the two env vars does nothing to
  that config file — a `gh api -X PUT repos/<repo>/contents/<path>`,
  `gh pr merge`, or `gh issue edit` call from inside the model's `Bash`
  authenticates straight from `hosts.yml` and never touches git's
  `credential.helper` at all, so it is unaffected by either half of the
  first revision's fix. This closes it at the `gh` config level, not just
  the env-var level: before the model call, also set
  `GH_CONFIG_DIR=<empty temp dir>` in the environment the model's tools
  run in, so `gh` has no config file to read and (with `GH_TOKEN`/
  `GITHUB_TOKEN` already absent) falls through to unauthenticated, which
  fails closed on every mutating `gh` call. The rest of the first
  revision's mechanism (clone with a credential-less URL, disable the
  checkout's git `credential.helper`, restore `GH_TOKEN` only after
  `query()` returns for the one legitimate `gh pr comment` post) is
  unchanged and still necessary — it's the git-level half of the same
  guarantee; `GH_CONFIG_DIR` is the missing gh-level half.
- **Rationale**: The first revision's own stated goal — "a guarantee that
  holds regardless of where this function executes" — was correct in intent
  but the mechanism only accounted for git's credential path, not `gh`'s
  separate one. Both must be closed for FR-007's "MUST NOT be able to push
  any commit or modify the spec itself" to hold against everything the
  model's `Bash` can reach, including a repository-content write via the
  GitHub REST/GraphQL API rather than `git push` — which is still "modifying
  the spec itself" in effect, just via a different transport.
- **Alternatives considered**:
  - Restricting `Bash` via a command allowlist/wrapper — rejected as more
    moving parts than removing the credentials that turn "can run `git`/`gh`"
    into "can mutate."
  - Requiring the future orchestration caller to always run this inside an
    E2B sandbox with no `GH_TOKEN`/`gh` config in the sandbox's env at all —
    remains good defense-in-depth (recorded in Project Structure) but out of
    scope to mandate here, per the spec's own Assumption that orchestration
    sequencing is a dependency, not part of this feature; the credential- and
    config-scrub guarantee above holds with or without it.
  - Keeping the credential-less clone URL as an additional, redundant layer —
    kept: it costs nothing and narrows the window between clone and the
    `credential.helper ""` config write.

## Unknown 3: Where does the `MAX_PM_ATTEMPTS=3` bound and human-decision wait live, given the spec's Assumptions say the orchestration sequencing and gate-signal delivery are dependencies, not part of this feature? **[revised]**

- **Decision (revised)**: `review_spec()` does not enforce an attempt cap or
  raise on exhaustion at all. It takes `attempt` and `feedback` purely as
  content for the writeup (so a human reading the PR thread can tell which
  re-review this is, and so a rejection's feedback gets addressed) and
  returns a plain dict — `{"writeup": str, "attempt": int}` — every time it
  is called, with no notion of a cap built in.
- **Rationale**: `specs/005-pipeline-mode-signals-escalation/spec.md` FR-010
  and FR-011 already assign "track a bounded number of automatic retry
  attempts for each gated stage (**PM review**, plan review, ...)" and
  "signal that a human decision is needed" once a budget is exhausted to the
  *workflow*, explicitly by name. Having `review_spec()` also raise
  `PmAttemptsExhausted` at `attempt > MAX_PM_ATTEMPTS` created two owners of
  the same cap and, on the Temporal path, a further problem: an activity
  raising a bare `RuntimeError` is retryable by default, so an exhausted-cap
  raise would surface as an infra failure and could be silently retried
  rather than escalated, unless every caller remembered to special-case it —
  fragile, and duplicative of what 005 already owns. Returning a plain dict
  also matches this repo's own stated convention for gate outcomes:
  `eval/braintrust/eval.config.py::run_eval` deliberately returns a dict
  rather than raising, with the comment "a failed gate is a normal business
  outcome the caller branches on, not an execution failure" — the same
  reasoning applies to a PM-rejection outcome. `MAX_PM_ATTEMPTS` as a named
  constant is removed from this feature entirely; 005 owns the number.
- **Alternatives considered**:
  - Keeping the cap in `review_spec()` "as a cheap guarantee in case 005's
    wiring is delayed" (the original rationale) — rejected: it's not cheap,
    it's a second source of truth that can silently disagree with 005's
    budget, and the return-vs-raise mismatch is a correctness bug on the
    Temporal path (see above), not just a style preference.
  - Splitting the cap (e.g. `review_spec()` refuses above some hard ceiling
    as a backstop, 005 enforces the real business budget below it) —
    rejected as unnecessary complexity for a gap that has a real, named owner
    once 005 lands; nothing in this spec's Assumptions requires this feature
    to defend against 005 never being implemented.

## Unknown 4: What triggers Issue-Shaping, concretely, given the webhook bridge (`specs/002-webhook-trigger-bridge/`) is a separate feature scoped to the Temporal-signal path? **[revised]**

- **Decision (revised)**: Split into the same two-file shape
  `harness/swe-agent`'s trigger already uses, because Issue-Shaping's whole
  point — like swe-agent's build trigger — is firing on *target-repo* issues,
  not just this factory repo's own:
  - `.github/workflows/pm-agent-shape.yml` (lives in `agentic_factory`,
    reusable): `on: workflow_call: {}`, gated on
    `github.event.issue.pull_request == null`, comment body matching
    `@pm-agent shape`, and the same `author_association` allowlist
    (`OWNER`/`MEMBER`/`COLLABORATOR`) `swe-agent-build.yml` already uses.
    Mints a GitHub App installation token (same `actions/create-github-app-token`
    step swe-agent-build.yml uses) for the `gh issue edit`/`gh issue view`
    calls against the *triggering* (target) repo. Because this runs on a
    target repo's runner with no `harness/pm-agent/` code present, it adds
    one `actions/checkout` step pulling `agentic_factory` itself at a pinned
    ref (`aheumaier/agentic_factory@main`) into a subdirectory, then invokes
    `shape_issue()` via `uv run --project <that-subdirectory>/harness/pm-agent`.
    This is safe to add because Issue-Shaping's model call binds zero tools
    (Unknown 1) — checking out the factory's public source onto the target
    runner carries none of the "attacker-shaped `Bash`" risk Unknown 2 deals
    with for Spec-Review, since there is no `Bash` here at all.
  - `.github/workflows/pm-agent-shape-trigger.yml` (the ~10-line caller each
    opted-in target repo copies, mirroring `swe-agent-trigger.yml`): `on:
    issue_comment: [created]`, `uses:
    aheumaier/agentic_factory/.github/workflows/pm-agent-shape.yml@main`,
    `secrets: inherit`.
- **Rationale**: The original decision (a direct `issue_comment` workflow
  living only in `agentic_factory`) can only ever fire on this factory
  repo's own issues, but Issue-Shaping's stated purpose
  (`docs/70-multi-agent-pipeline-design.md` §1) is shaping issues in
  *target* repos before they become specs there — the reusable-workflow +
  thin-caller split is exactly the mechanism `swe-agent-build.yml` /
  `swe-agent-trigger.yml` already prove works for that, including the
  checkout-the-factory-repo step being unnecessary for *swe-agent* (its code
  is baked into an E2B image instead, since it needs `Bash`/git inside an
  isolated sandbox) but sufficient here precisely because Issue-Shaping needs
  no sandbox and no `Bash` — the checkout is the simplest code-delivery path
  that fits its already-established zero-tool guarantee.
- **Alternatives considered**:
  - Routing Issue-Shaping through the webhook bridge for consistency —
    still rejected as unnecessary coupling to a Temporal-oriented component
    this job never talks to.
  - Baking `harness/pm-agent/` into an E2B image the way swe-agent does —
    rejected as unjustified for a zero-tool, no-`Bash` capability; that
    machinery exists in swe-agent specifically to isolate `Bash`/git access
    Issue-Shaping never has.

## Unknown 5: How does posting the Spec-Review writeup stay safe to retry, given `gh pr comment` is a mutating call with no built-in idempotency? (new)

- **Decision**: The writeup posted via `gh pr comment` includes a hidden
  marker comment, `<!-- pm-agent:review attempt=<N> -->`, as its first line.
  Before posting, `review_spec()` lists the PR's existing comments
  (`gh pr view <pr_url> --json comments`) and checks for that exact marker;
  if found, it returns the existing comment's body unchanged rather than
  posting again.
- **Rationale**: `orchestration/activities.py`'s `_open_factory_pr` already
  establishes the precedent in this repo that a mutating, retryable
  operation must check for its own prior effect before repeating it (there,
  an existing-PR check; the same file's own comment calls out that this is
  the deliberate improvement over `harness/swe-agent/agent.py::push_and_open_pr`'s
  weaker "already exists" string-match on the error). A retried
  `review_spec()` call for the same attempt (e.g. an activity retry after a
  transient failure just after posting) would otherwise double-post the
  writeup into the human's review thread.
- **Alternatives considered**: Relying on the caller (a future Temporal
  activity, out of scope) to dedupe — rejected because the dedup key
  (`attempt` number) is only meaningful inside this function's own domain;
  putting the check here means it holds regardless of what calls it.

## Unknown 6: `_validate_repo`/`_validate_branch` — does one regex cover both `repo` and `branch` inputs? (new, closes a gap the original plan missed)

- **Decision**: Two separate validators, mirroring
  `harness/swe-agent/agent.py` exactly: `_validate_repo` (`^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$`,
  requires the `owner/name` slash) applied only to `repo`, and
  `_validate_branch` (`^[A-Za-z0-9][A-Za-z0-9_./-]*$`, plus a leading-`-`
  rejection) applied only to `branch`. `review_spec(repo, branch, ...)` calls
  both; `shape_issue(repo, issue_number)` has no `branch` parameter and calls
  only `_validate_repo`.
- **Rationale**: A single repo-shaped regex applied to `branch` would reject
  this feature's own branch name (`003-pm-agent-review-gate`, no slash) on
  the very first real `review_spec()` call — branch names and `owner/name`
  repo slugs are not the same shape, which is exactly why
  `harness/swe-agent/agent.py` already keeps `_REPO_RE`/`_BRANCH_RE`
  separate rather than reusing one regex for both.
- **Alternatives considered**: A single permissive regex covering both
  shapes — rejected as weaker (would admit repo-shaped garbage as a "branch")
  for no benefit over just mirroring the two-regex precedent that already
  exists in this codebase.

## Unknown 7: Given `review_spec()`'s precondition is "`specs/*/spec.md` exists on `branch`," which spec does it review when a repo checkout has more than one `specs/*/` directory — as `agentic_factory` itself does (001 through 007)? (new)

- **Decision**: Derive the path directly from `branch`, not a glob:
  `specs/<branch>/spec.md`. This holds under the Spec-Kit convention this
  whole repo already follows — a feature branch's name *is* its spec
  slug (`003-pm-agent-review-gate` ↔ `specs/003-pm-agent-review-gate/`) —
  so `review_spec(repo, branch, ...)` already has everything it needs to
  find the right file without scanning the tree. The existence check
  becomes "does `specs/<branch>/spec.md` exist," raising `RuntimeError` if
  not (same shape of error as before, precise instead of glob-first-match).
- **Rationale**: A second senior-architect review flagged that
  `orchestration/activities.py` (`eval_gate_activity`, lines ~128-135) globs
  `specs/*/spec.md` and unconditionally takes `specs[0]` after `sorted()` —
  on a checkout with multiple spec directories (every checkout of this
  repo, once more than one feature has been specced) that resolves to
  `001-agent-spec-schema-test`, not the branch actually under review. This
  spec's contract described `review_spec()`'s precondition as "the same
  shape... as `harness/swe-agent/agent.py::verify_spec_exists`" — but
  `verify_spec_exists` only checks *existence* (`if not
  glob.glob(...)`), it never picks a file to read; `review_spec()` does
  need to read one specific `spec.md`'s content for its judgment, so
  mirroring the glob pattern without mirroring "existence-only, never
  select" would silently import the same bug. Deriving the path from
  `branch` instead avoids it entirely and needs no tree scan.
  `orchestration/activities.py`'s own bug is real but out of scope for this
  feature to fix (see `data-model.md`'s cross-spec gaps) — noted so it
  isn't mistaken for something this revision already fixed.
- **Alternatives considered**: Globbing but sorting/filtering by branch-name
  prefix match — rejected as solving with a scan what a direct path
  construction already solves exactly, with one fewer failure mode (a
  branch name that happens to be a prefix of another spec slug).

## Unknown 8: `shape_issue()`'s "no linked pull request" precondition check used `gh issue view --json title,body,pullRequest` — is `pullRequest` a real field? (new)

- **Decision**: No — `gh issue view --json` does not expose a `pullRequest`
  field (verified against the `gh` manual's field list for `issue view`).
  Use `closedByPullRequestsReferences` instead:
  `gh issue view <n> --repo <repo> --json title,body,closedByPullRequestsReferences`,
  and treat a non-empty list as "has a linked pull request." This also
  fixes the definition, not just the field name: "linked pull request" in
  this feature's scope means a PR linked via GitHub's closing-reference
  mechanism (the one shown in the issue's "Development" panel) — the only
  linkage `gh` exposes without a separate timeline/GraphQL call, and the
  one a reviewer would actually mean by "already has a linked pull
  request" in the spec's edge case.
- **Rationale**: Calling `gh` with an invalid `--json` field is a hard CLI
  error (unrecognized field), not a soft no-match — the precondition check
  itself would fail on every invocation, not just ones with a real linked
  PR, making `shape_issue()` unusable as written rather than merely
  imprecise. `closedByPullRequestsReferences` is a real, documented field
  and is the narrowest correct match for "linked via a closing reference,"
  which is what GitHub's own UI means by "linked" in this context.
- **Alternatives considered**: Querying the issue's timeline via `gh api
  repos/<repo>/issues/<n>/timeline` for `cross-referenced` events — rejected
  as broader than the spec's edge case needs (it would also catch PRs that
  merely *mention* the issue without closing it) and as an extra API call
  for a distinction the spec doesn't ask for.
