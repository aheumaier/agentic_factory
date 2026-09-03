# Contract: `harness/pm-agent/agent.py` public interface

**Revision note**: Updated after two senior-architect review passes on
2026-09-03 — see `research.md` for the Unknowns this responds to. First
pass: `review_spec()` returns a dict instead of a string and no longer
raises `PmAttemptsExhausted`; `_validate_repo`/`_validate_branch` are two
distinct guards; the credential-scoping guarantee behind FR-007 is described
precisely; posting is idempotent per attempt. Second pass (this update):
`shape_issue()`'s linked-PR check uses a valid `gh --json` field and goes
direct-to-Anthropic instead of via LiteLLM (Unknowns 8, 1); `review_spec()`
resolves its spec path from `branch` directly, not a glob (Unknown 7); its
credential scrub also covers `gh` CLI's own config-file fallback, not just
git's (Unknown 2).

This is the interface a future orchestration caller (a Temporal activity,
out of scope this pass) or a GH Actions workflow step invokes. It is the
"registry is the portability boundary" contract for this agent, per
`CLAUDE.md` — both functions are plain, importable, independently callable
Python functions, no framework-specific decorator required.

## `shape_issue(repo: str, issue_number: int) -> dict`

Issue-Shaping capability (FR-001–FR-003, User Story 1).

**Preconditions**:
- `repo` passes `_validate_repo` (`^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$`, same
  shape guard as `harness/swe-agent/agent.py::_validate_repo`), else raises
  `ValueError`.
- The issue identified by `issue_number` has no linked pull request — checked
  via `gh issue view <issue_number> --repo <repo> --json
  title,body,closedByPullRequestsReferences` before any model call (`pullRequest`
  is not a valid field — `research.md` Unknown 8); if
  `closedByPullRequestsReferences` is non-empty, raises `RuntimeError` and
  performs no edit (Edge Case in spec.md).

**Behavior**:
1. Fetch current `title`/`body` via `gh issue view` (code, not model).
2. Call the model — **direct-to-Anthropic** (`ANTHROPIC_API_KEY`), not
   LiteLLM-routed: this capability runs on a target repo's GitHub-hosted
   runner (Unknown 4), which cannot reach the self-hosted LiteLLM proxy on
   `localhost:4000` — a network-reachability deviation from `CLAUDE.md`'s
   "model calls never take a provider key directly" convention, distinct
   from (and not to be conflated with) `harness/swe-agent`'s
   skill-discovery-driven deviation, since nothing here invokes a Spec-Kit
   skill command (`research.md` Unknown 1) — with
   `ClaudeAgentOptions(allowed_tools=[])` — no tools — prompting it to
   rewrite `title`/`body` with added scope clarity and an explicit
   no-gold-plating note, given the fetched text as context. The prompt is a
   module-level string constant in `agent.py` (`SHAPE_ISSUE_PROMPT`),
   hardcoded exactly like `harness/swe-agent/agent.py::IMPLEMENT_PROMPT` —
   there is no `prompts/pm-agent.json` runtime-loaded file (the original
   plan's premise that `prompts/agentic-swe.json` has a loadable
   multi-entry structure was checked against that file directly and is
   false; `harness/swe-agent/agent.py` doesn't load it either).
3. Parse the model's response into new `title`/`body` (code, not model).
4. Call `gh issue edit <issue_number> --repo <repo> --title ... --body ...`
   (code, not model).

**Returns**: `{"number": int, "title": str, "body": str}` — the edited
issue's new state, as confirmed by the `gh issue edit` call.

**Postconditions**: No branch, spec file under `specs/`, or Temporal
workflow is created or referenced (FR-002) — guaranteed structurally by
step 2's empty tool set, not by a runtime check.

## `review_spec(repo: str, branch: str, pr_url: str, attempt: int, feedback: str | None = None) -> dict`

Spec-Review capability (FR-004–FR-010, User Story 2). No longer enforces or
raises on an attempt cap — see Unknown 3.

**Preconditions**:
- `repo` passes `_validate_repo`; `branch` passes `_validate_branch`
  (`^[A-Za-z0-9][A-Za-z0-9_./-]*$`, plus rejecting a leading `-`) — two
  distinct guards, mirroring `harness/swe-agent/agent.py`'s own
  `_REPO_RE`/`_BRANCH_RE` split (`research.md` Unknown 6). Either failing
  raises `ValueError`.
- `attempt >= 1`, else raises `ValueError`. No upper bound is enforced here
  (see Unknown 3) — a caller exceeding its own budget is a
  `specs/005-pipeline-mode-signals-escalation/` concern, not this
  function's.
- `specs/<branch>/spec.md` exists on `branch` — checked by path derived
  directly from `branch`, **not** a glob over `specs/*/spec.md` (a checkout
  of this repo alone has seven `specs/*/` directories; a first-sorted-match
  glob would silently review the wrong one — `research.md` Unknown 7). Else
  raises `RuntimeError`.
- A target-repo PR at `pr_url` is assumed to already exist by the time this
  is called — **this feature does not create or verify it**; see
  `data-model.md`'s "`pr_url` — an unresolved cross-spec precondition" and
  the added Assumption in `spec.md`.

**Behavior**:
1. Clone `branch` shallowly (`git clone --depth 1 --branch <branch>`,
   matching `orchestration/activities.py::eval_gate_activity`'s convention)
   from the plain, credential-less `https://github.com/<repo>.git` URL, into
   a temp directory. Immediately run `git config --local
   credential.helper ""` in that checkout.
2. Capture `GH_TOKEN` from the process environment into a local variable,
   then build the environment for the model's tool-use loop as a copy of the
   process environment with `GH_TOKEN`/`GITHUB_TOKEN` removed,
   `GIT_TERMINAL_PROMPT=0` set, and `GH_CONFIG_DIR` pointed at a freshly
   created empty temp directory — so `gh` has no `hosts.yml` to fall back to
   either (env-var removal alone stops `git push` but not a `gh api`/`gh pr
   merge` call authenticating from `gh`'s own config file, a separate
   credential path — `research.md` Unknown 2). Call the model — direct-to-Anthropic, **not**
   LiteLLM-routed (a documented deviation from the usual convention, on the
   same grounds `harness/swe-agent/agent.py` already documents: this
   capability may invoke `/speckit-analyze`, a Spec-Kit skill command that
   needs Claude Code's own runtime skill discovery) — with `Read`/`Grep`/
   `Glob`/`Bash` bound (no `Write`/`Edit`), using that scrubbed environment,
   prompting a value-judgment review of `spec.md` — right thing to build,
   right scope, explicit no-gold-plating flag (FR-005) — optionally running
   `/speckit-analyze` for structural consistency, and, if `feedback` is
   given, explicitly addressing it (FR-010). The prompt is a module-level
   string constant, `SPEC_REVIEW_PROMPT` (+ a `FEEDBACK_PROMPT_SUFFIX`
   mirroring `harness/swe-agent/agent.py`'s pattern exactly), not a runtime-
   loaded JSON file.
3. Restore the captured `GH_TOKEN` in the environment used for this step's
   own `gh` calls (`GH_TOKEN` takes precedence over `GH_CONFIG_DIR`'s absent
   config file, so restoring just the env var is sufficient here — code
   only, never exposed to the model).
   Build the writeup body with a leading idempotency marker, `<!--
   pm-agent:review attempt=<attempt> -->` (`research.md` Unknown 5). Check
   `gh pr view <pr_url> --json comments` for that exact marker; if already
   present, return that existing comment's body instead of posting again.
   Otherwise post via `gh pr comment <pr_url> --body ...` — this is the only
   mutating GitHub call this capability makes, and it uses the restored
   token, never the model's own `Bash`.

**Returns**: `{"writeup": str, "attempt": int}` — a plain dict, mirroring
`eval/braintrust/eval.config.py::run_eval`'s "business outcome, not
exception" convention for gate results.

**Postconditions**: No commit is pushed, and no repository content is
mutated via the GitHub API either. This is guaranteed by removing the
push-capable credential from the model's own execution environment (both
`GH_TOKEN`/`GITHUB_TOKEN` and, via `GH_CONFIG_DIR`, `gh`'s own config-file
fallback) and disabling the checkout's git credential helper
(`research.md` Unknown 2) — a guarantee that holds regardless of whether
this function runs on a host process or inside an E2B sandbox, since it
does not depend on either. (A
future orchestration caller running this inside a sandbox, the way
`orchestration/activities.py::run_swe_agent_activity` already does for
Build, remains good defense-in-depth against attacker-shaped `Bash` content
more broadly, but is that caller's decision, not a requirement enforced
here.)

## `_validate_repo(repo: str) -> None` / `_validate_branch(branch: str) -> None`

Shared guards (`research.md` Unknown 6), mirroring
`harness/swe-agent/agent.py`'s `_REPO_RE`/`_BRANCH_RE` exactly. Both raise
`ValueError` on a malformed input. `shape_issue()` calls only
`_validate_repo` (it has no `branch` parameter); `review_spec()` calls both.

## `PmAttemptsExhausted` — removed

Removed in this revision (`research.md` Unknown 3, `data-model.md`).
Callers needing to escalate on exhausted retry budgets do so via
`specs/005-pipeline-mode-signals-escalation/`'s workflow-level tracking, not
by catching an exception from this module.
