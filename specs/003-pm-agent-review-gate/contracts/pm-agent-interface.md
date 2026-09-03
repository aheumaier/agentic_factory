# Contract: `harness/pm-agent/agent.py` public interface

**Revision note**: Updated after a **third** senior-architect review pass on
2026-09-03. The first two passes corrected the *rationale* behind FR-002/
FR-003's "no tool is bound" and FR-007's "cannot push or mutate" guarantees
without checking the mechanism against the `claude-agent-sdk` actually
vendored in this repo (`harness/swe-agent/.venv/.../claude_agent_sdk/
{types.py,_internal/transport/subprocess_cli.py}`). Both guarantees were
non-structural as written:
- `allowed_tools=[]` only suppresses permission prompting — it does not
  disable tools. `tools=[]` does (Unknown 1, corrected below).
- `ClaudeAgentOptions.env` only overrides `os.environ` in the subprocess
  launcher; omitting a key from it does not remove an inherited value. The
  credential scrub must happen in the parent process (Unknown 2, corrected
  below).
- The SDK's default `setting_sources=None` loads `.claude/settings.json`
  from the branch under review, including hooks, regardless of which tools
  are bound to the model — a hook committed to an attacker-shaped branch
  would auto-execute in the CLI subprocess. Spec-Review now drops `Bash`
  and `/speckit-analyze` for v1 and sets `setting_sources=[]` explicitly
  (Unknown 2, corrected below), which also reverses Spec-Review's
  direct-to-Anthropic deviation — see Unknown 1.

Also fixed this pass: FR-010/FR-011's idempotency-key conflict (the
`attempt` marker now includes the spec's commit SHA and `attempt` is
defined as strictly increasing); the credential-less clone URL blocking
private target repos (now token-embedded, scrubbed immediately after);
`review_spec()`'s hardcoded `specs/<branch>/spec.md` path gains an optional
override; both function signatures are corrected to `async def`, matching
`quickstart.md`'s `asyncio.run(...)` usage (`query()` is an async
generator).

This is the interface a future orchestration caller (a Temporal activity,
out of scope this pass) or a GH Actions workflow step invokes. It is the
"registry is the portability boundary" contract for this agent, per
`CLAUDE.md` — both functions are plain, importable, independently callable
Python functions, no framework-specific decorator required.

## `async def shape_issue(repo: str, issue_number: int) -> dict`

Issue-Shaping capability (FR-001–FR-003, FR-002a, User Story 1).

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
2. Call the model — **direct-to-Anthropic** (`ANTHROPIC_PLATFORM_API_KEY`), not
   LiteLLM-routed: this capability runs on a target repo's GitHub-hosted
   runner (Unknown 4), which cannot reach the self-hosted LiteLLM proxy on
   `localhost:4000` — a network-reachability deviation from `CLAUDE.md`'s
   "model calls never take a provider key directly" convention, distinct
   from (and not to be conflated with) `harness/swe-agent`'s
   skill-discovery-driven deviation, since nothing here invokes a Spec-Kit
   skill command (`research.md` Unknown 1) — with
   `ClaudeAgentOptions(tools=[], permission_mode="default")` — **no tools
   bound at all** (`tools=[]` disables tool binding entirely; `allowed_tools`
   only controls auto-approval of tools that *are* bound and defaults to
   `[]` already, so it asserts nothing on its own — Unknown 1, corrected).
   `permission_mode` is set explicitly to a value other than
   `"bypassPermissions"` so a future edit that accidentally adds a tool
   doesn't silently inherit auto-approval — the zero-tool guarantee should
   not depend on `permission_mode` at all, but leaving it unset risks
   copy-pasting `harness/swe-agent/agent.py`'s `bypassPermissions` value,
   which is safe only there because that agent's threat model is
   different. The model is prompted to rewrite `title`/`body` with added
   scope clarity and an explicit no-gold-plating note, given the fetched
   text as context. The prompt is a module-level string constant in
   `agent.py` (`SHAPE_ISSUE_PROMPT`), hardcoded exactly like
   `harness/swe-agent/agent.py::IMPLEMENT_PROMPT` — there is no
   `prompts/pm-agent.json` runtime-loaded file.
3. Parse the model's response into new `title`/`body` (code, not model).
4. **Preserve the original content** (FR-002a): before overwriting, post
   the original `title`/`body` as a `gh issue comment` (e.g. prefixed
   "Original issue content, preserved before PM-agent shaping:"). This is a
   model-authored, irreversible-by-`gh` overwrite on a **target** repo with
   no other human checkpoint in this job's path — the comment is the only
   recovery mechanism.
5. Call `gh issue edit <issue_number> --repo <repo> --title ... --body ...`
   (code, not model).

**Returns**: `{"number": int, "title": str, "body": str}` — the edited
issue's new state, as confirmed by the `gh issue edit` call.

**Postconditions**: No branch, spec file under `specs/`, or Temporal
workflow is created or referenced (FR-002) — guaranteed structurally by
step 2's `tools=[]`, not by a runtime check. The original issue content
remains readable in the issue's comment history (FR-002a) — guaranteed by
step 4 running unconditionally before step 5's overwrite.

## `async def review_spec(repo: str, branch: str, pr_url: str, attempt: int, feedback: str | None = None, spec_dir: str | None = None) -> dict`

Spec-Review capability (FR-004–FR-011, User Story 2). No longer enforces or
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
  function's. `attempt` MUST be strictly increasing per distinct review
  request against a given `(repo, branch, pr_url)` — it is the sole
  idempotency key (FR-011). A caller MUST NOT reuse an `attempt` number
  with different `feedback`; doing so is caller error, not something this
  function detects or resolves (FR-010/FR-011 are only in tension if a
  caller violates this).
- `spec_dir` (new, optional): the directory under the checkout containing
  `spec.md`, e.g. `specs/003-pm-agent-review-gate`. Defaults to
  `specs/<branch>` when omitted — the Spec-Kit convention this repo follows
  where a feature branch's name is its spec slug (`research.md` Unknown 7).
  Callers on a branch that doesn't follow that convention (e.g. a spec
  committed to `main`, as this repo's own `specs/002`, `004`–`007`
  currently are) MUST pass `spec_dir` explicitly. `<spec_dir>/spec.md` is
  checked for existence — never a glob over `specs/*/spec.md` (a checkout
  of this repo alone has seven `specs/*/` directories; a first-sorted-match
  glob would silently review the wrong one). Else raises `RuntimeError`.
- A target-repo PR at `pr_url` is assumed to already exist by the time this
  is called — **this feature does not create or verify it**; see
  `data-model.md`'s "`pr_url`" section and the added Assumption in
  `spec.md`.

**Behavior**:
1. Capture `GH_TOKEN` from the process environment into a local variable.
   Clone `branch` shallowly (`git clone --depth 1 --branch <branch>`,
   matching `orchestration/activities.py::eval_gate_activity`'s convention)
   from `https://x-access-token:<token>@github.com/<repo>.git` — a
   token-embedded URL, needed so private target repos can be cloned at all
   — into a temp directory. Immediately run `git config --local
   credential.helper ""` in that checkout. The clone happens *before* the
   credential scrub in step 2, so embedding the token here does not weaken
   FR-007: nothing has bound any tool to the model yet.
2. Scrub credentials **in the parent process**, not via `ClaudeAgentOptions.env`
   (`options.env` only overrides `os.environ` in the SDK's subprocess
   launcher — it does not remove an inherited key, so omitting `GH_TOKEN`/
   `GITHUB_TOKEN` from it leaves the parent process's own value fully
   intact in the CLI subprocess; `research.md` Unknown 2, corrected):
   `os.environ.pop("GH_TOKEN", None)` and `os.environ.pop("GITHUB_TOKEN",
   None)` before calling `query()`, restoring both in a `finally` block
   after the model call returns (step 4) and before this step's own `gh`
   calls. `GH_CONFIG_DIR` (pointed at a freshly created empty temp
   directory, so `gh` has no `hosts.yml` to fall back to) and
   `GIT_TERMINAL_PROMPT=0` remain `ClaudeAgentOptions.env` overrides — those
   work as designed, since the SDK's merge-on-top-of-`os.environ` semantics
   are exactly what an *override* needs.
3. Call the model — **LiteLLM-routed** (`LITELLM_BASE_URL`), matching this
   repo's default convention (`CLAUDE.md`'s "model calls never take a
   provider key directly"). This capability runs as a Temporal activity on
   the orchestration worker host, which — unlike Issue-Shaping's
   target-repo GitHub-hosted runner — can reach the self-hosted proxy on
   `localhost:4000`; the prior direct-to-Anthropic deviation was justified
   by needing `/speckit-analyze`'s skill discovery, which this revision
   drops (see next paragraph), so no deviation is needed here (`research.md`
   Unknown 1, reversed; Unknown 9, new).
4. With `ClaudeAgentOptions(cwd=checkout, tools=["Read", "Grep", "Glob"],
   setting_sources=[], permission_mode="default")`: **no `Bash`, and no
   `/speckit-analyze`** (dropped this revision — the prior design's `Bash` +
   default `setting_sources=None` combination meant a hook committed to
   `.claude/settings.json` on the branch under review would auto-execute in
   the CLI subprocess regardless of the model's own tool access, and
   `skills=[...]` cannot avoid this since the SDK forces project
   setting-sources on whenever `skills` is set — `research.md` Unknown 2,
   corrected). Spec-Review only needs to read files for its judgment, not
   execute anything, so dropping `Bash` closes this off entirely rather
   than mitigating it. `setting_sources=[]` is set explicitly regardless,
   as defense in depth against a future edit re-adding `Bash` without
   revisiting this reasoning. Prompt a value-judgment review of `spec.md` —
   right thing to build, right scope, explicit no-gold-plating flag
   (FR-005) — and, if `feedback` is given, explicitly addressing it
   (FR-010), using the scrubbed environment from step 2. The prompt is a
   module-level string constant, `SPEC_REVIEW_PROMPT` (+ a
   `FEEDBACK_PROMPT_SUFFIX` mirroring `harness/swe-agent/agent.py`'s
   pattern exactly), not a runtime-loaded JSON file.
5. Restore the captured `GH_TOKEN` (step 2's `finally`) for this step's own
   `gh` calls (`GH_TOKEN` takes precedence over `GH_CONFIG_DIR`'s absent
   config file, so restoring just the env var is sufficient here — code
   only, never exposed to the model). Read the checkout's current
   `spec.md` content and compute its short commit SHA (`git rev-parse
   --short HEAD` in the checkout) **before** the model call in step 4 would
   also work, but computing it here alongside the marker keeps the
   SHA-capture and marker-construction logic in one place. Build the
   idempotency marker as `<!-- pm-agent:review attempt=<attempt>
   spec=<sha> -->` (`research.md` Unknown 5, extended — the spec SHA
   additionally records which version of `spec.md` this writeup judged,
   partially addressing the cross-stage SHA-pin gap in `data-model.md`).
   Check `gh pr view <pr_url> --json comments` for that exact marker; if
   already present, return that existing comment's body instead of
   posting again. Otherwise post via `gh pr comment <pr_url> --body ...` —
   this is the only mutating GitHub call this capability makes, and it
   uses the restored token, never the model's own tools (which have none
   with GitHub-mutation capability regardless, per step 4).

**Returns**: `{"writeup": str, "attempt": int}` — a plain dict, mirroring
`eval/braintrust/eval.config.py::run_eval`'s "business outcome, not
exception" convention for gate results.

**Postconditions**: No commit is pushed, and no repository content is
mutated via the GitHub API either. This is guaranteed by (a) binding no
tool with GitHub-mutation or shell-execution capability to the model at all
(`tools=["Read","Grep","Glob"]`, step 4), (b) `setting_sources=[]`
preventing any hook on the branch under review from executing in the CLI
subprocess regardless of (a), and (c) removing the push-capable credential
from the *parent* process's environment for the duration of the model call
(step 2) so even a future re-introduction of `Bash` would not have an
ambient credential to use. This guarantee holds regardless of whether this
function runs on a host process or inside an E2B sandbox, since it does not
depend on either. (A future orchestration caller running this inside a
sandbox, the way `orchestration/activities.py::run_swe_agent_activity`
already does for Build, remains good defense-in-depth more broadly, but is
that caller's decision, not a requirement enforced here.)

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
