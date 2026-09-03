# Tasks: PM-Agent Issue-Shaping and Spec-Review Gate

**Input**: Design documents from `/specs/003-pm-agent-review-gate/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/pm-agent-interface.md, quickstart.md — all revised 2026-09-03 (third senior-architect pass). This tasks.md regenerates the prior version, which was written against the second-pass design and asserted invariants (`allowed_tools=[]`, `options.env`-only credential scrub) that don't hold against the vendored SDK — see `research.md`'s revision notes.

**Tests**: Included — `plan.md`'s Testing section names `tests/test_pm_agent.py` and its mocking convention explicitly, so tests are part of this feature's own design, not optional filler.

**Organization**: Tasks are grouped by user story (US1 = Issue-Shaping, US2 = Spec-Review — both Priority P1 per `spec.md`) to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2)
- Every task with a file path names the exact file

## Path Conventions

Single project, following `harness/<agent>/` + `registry/agents/<agent>/` — the existing pattern `harness/swe-agent/` established, per `plan.md`'s Structure Decision:

- `harness/pm-agent/agent.py`, `SKILL.md`, `pyproject.toml`
- `registry/agents/pm-agent/manifest.yaml`, `versions/v1.yaml`, `SKILL.md`
- `.github/workflows/pm-agent-shape.yml`, `pm-agent-shape-trigger.yml`
- `tests/test_pm_agent.py`

---

## Phase 1: Setup

**Purpose**: Registry entry and package scaffolding — no behavior yet

- [X] T001 Create `harness/pm-agent/pyproject.toml` declaring runtime deps `claude-agent-sdk`, `braintrust`, mirroring `harness/swe-agent/pyproject.toml`
- [X] T002 [P] Create `registry/agents/pm-agent/manifest.yaml` and `registry/agents/pm-agent/versions/v1.yaml`, hand-written mirroring `registry/agents/swe-agent/manifest.yaml` (`status: experimental`, `requires_human_supervision: true` — this feature has no automated Register/Deploy wiring, per `plan.md`'s Structure Decision). FR-012's "distinguishing the two jobs' distinct triggers and tool access" is satisfied by `SKILL.md` prose (T018/T019), not a manifest field — the manifest schema has none to extend (`plan.md`'s Structure Decision)
- [X] T003 [P] Run `cd harness/pm-agent && uv sync` to confirm the declared deps resolve
- [X] T004 [P] Update root `CLAUDE.md`'s layer table and `docs/00-status.md` to record the new `harness/pm-agent/` + `registry/agents/pm-agent/` entry and its two capabilities' distinct LiteLLM-routing deviations (Issue-Shaping direct-to-Anthropic for network reachability; Spec-Review LiteLLM-routed per `research.md` Unknown 9)

**Checkpoint**: Package scaffolding exists; no code yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared code both user stories call — MUST complete before either story's implementation tasks

**⚠️ CRITICAL**: US1 and US2 both depend on every task in this phase.

- [X] T005 Create `harness/pm-agent/agent.py` with module docstring, imports (`os`, `re`, `subprocess`, `tempfile`, `json`, `braintrust`, `claude_agent_sdk`), and Braintrust setup (`BRAINTRUST_PROJECT` env var, `braintrust.init_logger(project=BRAINTRUST_PROJECT)`, `braintrust.auto_instrument()`) — mirrors `harness/swe-agent/agent.py` lines 15-20, same project so a run's trace lands beside `eval/braintrust/eval.config.py`'s score
- [X] T006 [P] Implement `_validate_repo(repo: str) -> None` and `_validate_branch(branch: str) -> None` in `harness/pm-agent/agent.py` as two distinct regex guards (`^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$` for repo, `^[A-Za-z0-9][A-Za-z0-9_./-]*$` plus leading-`-` rejection for branch), mirroring `harness/swe-agent/agent.py::_REPO_RE`/`_BRANCH_RE` exactly (`research.md` Unknown 6 — one shared regex would reject this feature's own branch name)
- [X] T007 [P] Implement `_run(cmd: list[str], cwd: Path | None = None) -> str` in `harness/pm-agent/agent.py`, mirroring `harness/swe-agent/agent.py::_run` exactly (subprocess wrapper raising `CalledProcessError` on non-zero exit, returning stripped stdout)
- [X] T008 [P] Implement `_scrubbed(error: subprocess.CalledProcessError, secret: str) -> subprocess.CalledProcessError` in `harness/pm-agent/agent.py`, mirroring `harness/swe-agent/agent.py::_scrubbed` exactly, for redacting a captured `GH_TOKEN` from any subprocess error before it could reach a log or PR comment

**Checkpoint**: Foundation ready — US1 and US2 implementation can now proceed (in parallel, if staffed).

---

## Phase 3: User Story 1 - Shape a raw issue before it becomes a spec (Priority: P1) 🎯

**Goal**: `shape_issue(repo, issue_number)` rewrites a raw issue's title/body with scope clarity and a no-gold-plating note, with zero bound tools, preserves the original content, and has zero side effects outside the issue itself.

**Independent Test**: Per `quickstart.md`'s "Validate User Story 1" — file a vague-scope issue with no linked PR, call `shape_issue()`, confirm the issue is edited, the original content is still readable as a comment, and nothing else in the repo changed; repeat against an issue with a linked PR and confirm `RuntimeError`, no edit.

### Tests for User Story 1

- [X] T009 [P] [US1] Unit test in `tests/test_pm_agent.py::test_shape_issue_rejects_linked_pr` — mocked `gh issue view` returns a non-empty `closedByPullRequestsReferences`, assert `RuntimeError` raised and no `gh issue edit` call made (`research.md` Unknown 8 — not the invalid `pullRequest` field the pre-revision tasks used)
- [X] T010 [P] [US1] Unit test in `tests/test_pm_agent.py::test_shape_issue_zero_tools` — assert the `ClaudeAgentOptions` passed to the model call has `tools=[]` (not merely `allowed_tools=[]`, which asserts nothing beyond the SDK's own default — `research.md` Unknown 1, corrected: this is the structural guarantee behind FR-002/FR-003) and that `permission_mode` is not `"bypassPermissions"`
- [X] T011 [P] [US1] Unit test in `tests/test_pm_agent.py::test_shape_issue_direct_to_anthropic` — assert the model call carries no LiteLLM base-URL override (`research.md` Unknown 1 — target-repo runner can't reach the proxy)
- [X] T012 [P] [US1] Unit test in `tests/test_pm_agent.py::test_shape_issue_edits_issue` — given a mocked model response, assert `gh issue edit <n> --title ... --body ...` is called with the model's rewritten text and the function returns `{"number", "title", "body"}`
- [X] T013 [P] [US1] Unit test in `tests/test_pm_agent.py::test_shape_issue_preserves_original` — given a mocked model response, assert a `gh issue comment <n> --body ...` call containing the *original* (pre-shaping) title/body is made, and that it happens before the `gh issue edit` call (FR-002a — no other human checkpoint exists on this path)

### Implementation for User Story 1

- [X] T014 [US1] Add `SHAPE_ISSUE_PROMPT` module-level string constant to `harness/pm-agent/agent.py`, hardcoded like `harness/swe-agent/agent.py::IMPLEMENT_PROMPT` — no `prompts/pm-agent.json` (depends on T005)
- [X] T015 [US1] Implement `shape_issue(repo: str, issue_number: int) -> dict` precondition steps in `harness/pm-agent/agent.py`: call `_validate_repo(repo)`; fetch `gh issue view <issue_number> --repo <repo> --json title,body,closedByPullRequestsReferences` via `_run`; raise `RuntimeError` if `closedByPullRequestsReferences` is non-empty (`research.md` Unknown 8) (depends on T006, T007)
- [X] T016 [US1] In `shape_issue()`, call the model via `query()` with `ClaudeAgentOptions(tools=[], permission_mode=<not "bypassPermissions">)`, direct-to-Anthropic (`ANTHROPIC_PLATFORM_API_KEY`, no LiteLLM base URL), passing the fetched `title`/`body` as plain prompt text with `SHAPE_ISSUE_PROMPT`; parse the model's response into new `title`/`body` in code (depends on T014, T015)
- [X] T017 [US1] In `shape_issue()`, call `gh issue comment <issue_number> --repo <repo> --body ...` with the *original* fetched `title`/`body` (FR-002a — must run before the edit below, since it is the only recovery path for a model-authored overwrite with no other human checkpoint), then call `gh issue edit <issue_number> --repo <repo> --title ... --body ...` via `_run`; return `{"number": issue_number, "title": ..., "body": ...}` (depends on T016)

### Trigger for User Story 1

- [X] T018 [US1] Create `.github/workflows/pm-agent-shape.yml` (reusable, `on: workflow_call: {}`) in `agentic_factory`: `github.event.issue.pull_request == null` gate, `@pm-agent shape` comment-body match, `author_association` allowlist (`OWNER`/`MEMBER`/`COLLABORATOR`) mirroring `swe-agent-build.yml`, an explicit `permissions: {issues: write}` block, an `astral-sh/setup-uv` step before `uv run` (`ubuntu-latest` has no `uv` preinstalled), mints a GitHub App installation token via `actions/create-github-app-token`, adds an `actions/checkout` step pulling `agentic_factory@main` into a subdirectory, invokes `shape_issue()` via `uv run --project <subdirectory>/harness/pm-agent` — issue title/body passed via `env:` and referenced as `"$VAR"`, never interpolated into `run:` via `${{ }}` (mirroring `swe-agent-build.yml`'s own convention — title/body are this feature's most attacker-shapeable input), plus a failure-comment-back step mirroring `swe-agent-build.yml:100-119` (`research.md` Unknown 4; `plan.md`'s Project Structure notes `@main` here is a moving-target reference, not a pinned one, matching `swe-agent-trigger.yml`'s existing convention)
- [X] T019 [P] [US1] Create `.github/workflows/pm-agent-shape-trigger.yml`, the ~10-line per-repo caller (`on: issue_comment: [created]`, `uses: aheumaier/agentic_factory/.github/workflows/pm-agent-shape.yml@main`, `secrets: inherit`), mirroring `swe-agent-trigger.yml`

### Documentation for User Story 1

- [X] T020 [P] [US1] Write `harness/pm-agent/SKILL.md` documenting `shape_issue()`'s design, its zero-tool structural guarantee (`tools=[]`, not `allowed_tools=[]`), its original-content-preservation step (FR-002a), and its direct-to-Anthropic deviation (network-reachability justification, distinct from `harness/swe-agent`'s skill-discovery justification — `research.md` Unknown 1), mirroring `harness/swe-agent/SKILL.md`'s structure
- [X] T021 [P] [US1] Write `registry/agents/pm-agent/SKILL.md` as the registry-side copy required by `CLAUDE.md`'s portability boundary, distinguishing both capabilities' triggers and tool access (FR-012 — no manifest field for this; see T002)

**Checkpoint**: User Story 1 is independently functional and testable — `quickstart.md`'s Validate User Story 1 steps should all pass.

---

## Phase 4: User Story 2 - Review a spec for value and scope before build starts (Priority: P1)

**Goal**: `review_spec(repo, branch, pr_url, attempt, feedback=None, spec_dir=None)` posts a value-judgment writeup to the target-repo PR, is structurally unable to push a commit or mutate the repo via any other API or via a hook from the reviewed branch, and is idempotent per `attempt`.

**Independent Test**: Per `quickstart.md`'s "Validate User Story 2" — with `spec.md` on a branch and a PR open, call `review_spec()` and confirm a writeup comment appears, its body/attempt/feedback are all human-legible; confirm no push occurs and `GH_TOKEN`/`gh` auth are both absent from the model's environment for the duration of the model call; re-call with feedback and confirm a fresh, feedback-addressing writeup; re-call with the same `attempt` and confirm no duplicate comment; call with `attempt=99` and confirm no exception.

### Tests for User Story 2

- [X] T022 [P] [US2] Unit test in `tests/test_pm_agent.py::test_review_spec_env_scrubbed` — assert `os.environ` has `GH_TOKEN`/`GITHUB_TOKEN` popped for the duration of the model call and restored afterward (patch/mock `os.environ`, not the `env=` dict passed to `ClaudeAgentOptions` — `ClaudeAgentOptions.env` only overrides `os.environ` in the SDK's subprocess launcher, it cannot remove an inherited value; `research.md` Unknown 2, corrected), and that the `ClaudeAgentOptions.env` override has `GH_CONFIG_DIR` pointed at an empty directory and `GIT_TERMINAL_PROMPT=0`
- [X] T023 [P] [US2] Unit test in `tests/test_pm_agent.py::test_review_spec_no_bash_no_hooks` — assert `ClaudeAgentOptions.tools == ["Read", "Grep", "Glob"]` (no `Bash`) and `setting_sources == []` (`research.md` Unknown 2, corrected — closes the hook-injection path a branch under review could otherwise exploit regardless of tool binding)
- [X] T024 [P] [US2] Unit test in `tests/test_pm_agent.py::test_review_spec_litellm_routed` — assert the model call for `review_spec()` uses the LiteLLM base URL (`LITELLM_BASE_URL`), not direct-to-Anthropic (`research.md` Unknown 9 — the direct-to-Anthropic deviation no longer applies once `/speckit-analyze`/`Bash` are dropped)
- [X] T025 [P] [US2] Unit test in `tests/test_pm_agent.py::test_review_spec_credential_helper_disabled` — assert `git config --local credential.helper ""` runs against the checkout immediately after clone
- [X] T026 [P] [US2] Unit test in `tests/test_pm_agent.py::test_review_spec_no_attempt_cap` — call with `attempt=99`, assert no exception raised and a plain dict is returned (`research.md` Unknown 3 — no `MAX_PM_ATTEMPTS`, no `PmAttemptsExhausted`, that ownership is `specs/005-pipeline-mode-signals-escalation/`'s)
- [X] T027 [P] [US2] Unit test in `tests/test_pm_agent.py::test_review_spec_idempotent_post` — mock `gh pr view --json comments` to already contain a comment whose marker's `attempt=2` portion matches, assert no `gh pr comment` call is made, the existing body is returned unchanged, and the check happens *before* any model call is made (`research.md` Unknown 5 — a retry should not burn a model call it will discard)
- [X] T028 [P] [US2] Unit test in `tests/test_pm_agent.py::test_review_spec_marker_includes_spec_sha` — assert the posted comment's first line matches `<!-- pm-agent:review attempt=<N> spec=<sha> -->`, where `<sha>` is the checkout's short commit SHA (`research.md` Unknown 5, extended)
- [X] T029 [P] [US2] Unit test in `tests/test_pm_agent.py::test_review_spec_writeup_includes_attempt_and_feedback` — call with `feedback="<text>"`, assert both the `attempt` number and the literal feedback text appear in the writeup body passed to `gh pr comment` (FR-008 — previously untested beyond a manual quickstart step)
- [X] T030 [P] [US2] Unit test in `tests/test_pm_agent.py::test_review_spec_spec_path_default_and_override` — with no `spec_dir` given, assert the spec read is `specs/<branch>/spec.md`; with `spec_dir="specs/other-slug"` given, assert that path is used instead, never a glob over `specs/*/spec.md` (`research.md` Unknown 7, extended)
- [X] T031 [P] [US2] Unit test in `tests/test_pm_agent.py::test_review_spec_missing_spec_raises` — checkout has no `<spec_dir>/spec.md`, assert `RuntimeError`

### Implementation for User Story 2

- [X] T032 [US2] Add `SPEC_REVIEW_PROMPT` and `FEEDBACK_PROMPT_SUFFIX` module-level string constants to `harness/pm-agent/agent.py`, mirroring `harness/swe-agent/agent.py::IMPLEMENT_PROMPT`/`FEEDBACK_PROMPT_SUFFIX`'s pattern exactly — no runtime-loaded JSON file (depends on T005)
- [X] T033 [US2] Implement `review_spec(repo: str, branch: str, pr_url: str, attempt: int, feedback: str | None = None, spec_dir: str | None = None) -> dict` signature and guard clauses in `harness/pm-agent/agent.py`: `_validate_repo(repo)`, `_validate_branch(branch)`, `attempt >= 1` else `ValueError` — no upper bound; default `spec_dir` to `f"specs/{branch}"` when omitted (depends on T006)
- [X] T034 [US2] Implement the clone step in `review_spec()`: capture `GH_TOKEN` from the process environment into a local variable; `git clone --depth 1 --branch <branch>` via `_run` from `https://x-access-token:<token>@github.com/<repo>.git` — a token-embedded URL so private target repos can be cloned; this runs before the credential scrub in T036, so it does not weaken FR-007 — into a temp directory; immediately run `git config --local credential.helper ""` in that checkout (depends on T007, T033)
- [X] T035 [US2] Implement the spec-existence check in `review_spec()`: verify `<spec_dir>/spec.md` exists in the checkout (never a glob — `research.md` Unknown 7); raise `RuntimeError` if absent (depends on T034)
- [X] T036 [US2] Implement the credential scrub in `review_spec()` **in the parent process**: `os.environ.pop("GH_TOKEN", None)` and `os.environ.pop("GITHUB_TOKEN", None)` before the model call, restored in a `finally` block after it returns (`ClaudeAgentOptions.env` cannot remove an inherited variable — it only overrides `os.environ` in the SDK's subprocess launcher; `research.md` Unknown 2, corrected); build the `ClaudeAgentOptions.env` override dict with `GH_CONFIG_DIR` pointed at a freshly created empty temp directory and `GIT_TERMINAL_PROMPT=0` (depends on T035)
- [X] T037 [US2] Implement the idempotency-marker check in `review_spec()`, **before** calling the model (so a retry for an already-posted `attempt` doesn't burn a model call it will discard — `research.md` Unknown 5): compute the checkout's short commit SHA (`git rev-parse --short HEAD` via `_run`); restore the captured `GH_TOKEN` for this check's own `gh` call; check `gh pr view <pr_url> --json comments` for a comment whose first line matches `<!-- pm-agent:review attempt=<attempt> spec=... -->`; if found, return that comment's body as `{"writeup": ..., "attempt": attempt}` immediately, skipping the remaining steps (depends on T036)
- [X] T038 [US2] Call the model in `review_spec()` via `query()` with `ClaudeAgentOptions(cwd=checkout, tools=["Read", "Grep", "Glob"], setting_sources=[], env=<GH_CONFIG_DIR/GIT_TERMINAL_PROMPT override>)`, **LiteLLM-routed** (`LITELLM_BASE_URL`, not direct-to-Anthropic — `research.md` Unknown 9), prompting `SPEC_REVIEW_PROMPT` (+ `FEEDBACK_PROMPT_SUFFIX.format(feedback=feedback)` if `feedback` is given) using the scrubbed `os.environ` from T036; this runs only if T037 found no existing marker (depends on T032, T037). **Known limitation**: FR-005's content requirements (rightness-of-scope, explicit gold-plating flag) are enforced only by this prompt text — no test asserts the model's actual writeup satisfies them, since LLM output content isn't deterministically unit-testable; T029 checks only that `attempt`/`feedback` appear, not the scope/gold-plating judgment itself
- [X] T039 [US2] Implement the post step in `review_spec()`: restore the captured `GH_TOKEN` (T036's `finally`) for this step's own `gh` calls; build the writeup body with a leading `<!-- pm-agent:review attempt=<attempt> spec=<sha> -->` marker (using the SHA computed in T037); post via `gh pr comment <pr_url> --body ...` (depends on T038)
- [X] T040 [US2] Return `{"writeup": str, "attempt": int}` from `review_spec()` (depends on T037 or T039, whichever path was taken)
- [X] T041 [US2] Wrap the clone step's `subprocess.CalledProcessError` with `_scrubbed()` before it can propagate, redacting any credential that could otherwise leak into a log or PR comment (depends on T008, T034)

**Checkpoint**: User Story 2 is independently functional and testable — `quickstart.md`'s Validate User Story 2 steps should all pass.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T042 [P] Run `quickstart.md`'s Validate User Story 1 and Validate User Story 2 steps end-to-end against a scratch repo
- [X] T043 [P] Run `uv run pytest` from repo root — confirm every `tests/test_pm_agent.py` test passes with no real GitHub network access
- [X] T044 Add a "Known gaps" section to `harness/pm-agent/SKILL.md` documenting the unresolved cross-spec gaps recorded in `data-model.md`: the `pr_url` precondition (no producer of a target-repo PR exists yet), the cross-stage spec-version gap (the idempotency marker now records a spec SHA for human legibility, but nothing yet carries it into a structured field the Eval-Gate stage could compare against), and the spec-path glob bug in `orchestration/activities.py::eval_gate_activity` — not fixed by this feature, but noted as a **blocking dependency for this feature's own gate score being reachable at all**, not just an adjacent nuisance (`data-model.md`) — mirrors `harness/swe-agent/SKILL.md`'s own "Known gap" section pattern
- [X] T045 [P] Re-run `checklists/requirements.md` against the final `spec.md` text and annotate or clear any items that no longer hold given FR-009/SC-005's implementation-referencing wording

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS both user stories
- **User Story 1 (Phase 3)**: Depends on Foundational only — no dependency on US2
- **User Story 2 (Phase 4)**: Depends on Foundational only — no dependency on US1
- **Polish (Phase 5)**: Depends on both user stories being complete

### Within Each User Story

- Tests before implementation (write first, confirm they fail)
- Guard clauses / preconditions before the model call
- Idempotency-marker check before the model call (US2 — T037 before T038), not after
- Model call before the mutating `gh`/`git` step
- Story complete and independently testable before Polish

### Parallel Opportunities

- T002, T003, T004 (Setup) can run in parallel with T001 once T001's file exists
- T006, T007, T008 (Foundational) can all run in parallel — different functions, no shared state
- Once Foundational (Phase 2) completes, **all of Phase 3 (US1) and Phase 4 (US2) can proceed in parallel** — `shape_issue()` and `review_spec()` share no code path beyond the Phase 2 helpers
- All test tasks within a story (T009-T013; T022-T031) can run in parallel — independent mocks, same file but non-overlapping test functions
- T018/T019 (US1 trigger) can run in parallel with T014-T017 (US1 core logic) — different files

---

## Parallel Example: User Story 1

```bash
# Launch all US1 tests together:
Task: "Unit test test_shape_issue_rejects_linked_pr in tests/test_pm_agent.py"
Task: "Unit test test_shape_issue_zero_tools in tests/test_pm_agent.py"
Task: "Unit test test_shape_issue_direct_to_anthropic in tests/test_pm_agent.py"
Task: "Unit test test_shape_issue_edits_issue in tests/test_pm_agent.py"
Task: "Unit test test_shape_issue_preserves_original in tests/test_pm_agent.py"

# Launch US1's trigger workflow and documentation together (independent of core logic):
Task: "Create .github/workflows/pm-agent-shape-trigger.yml"
Task: "Write harness/pm-agent/SKILL.md"
Task: "Write registry/agents/pm-agent/SKILL.md"
```

---

## Implementation Strategy

### De-risk First (recommended)

Both user stories are Priority P1 in `spec.md`, but they carry very different risk: US1 binds zero tools (a purely structural guarantee); US2 binds `Read`/`Grep`/`Glob` against a shallow clone and carries the credential-scrub and hook-isolation guarantees this feature's three senior-architect review passes spent the most effort on (`research.md` Unknowns 2, 3, 5, 7, 9). Shipping US1 first, independently, is the lower-risk slice:

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (blocks both stories)
3. Complete Phase 3: User Story 1 (Issue-Shaping)
4. **STOP and VALIDATE**: run `quickstart.md`'s User Story 1 steps independently
5. Complete Phase 4: User Story 2 (Spec-Review) — the higher-risk slice, now validated in isolation
6. **STOP and VALIDATE**: run `quickstart.md`'s User Story 2 steps, including the credential-scrub and no-hooks verification (T022, T023, T025)
7. Complete Phase 5: Polish

### Parallel Team Strategy

With two developers, Phase 3 (US1) and Phase 4 (US2) can proceed genuinely in parallel once Phase 2 (Foundational) is done — they share no code path beyond the three Phase 2 helpers.

---

## Notes

- [P] tasks = different files or non-overlapping functions, no dependencies
- [Story] label maps task to US1 or US2 for traceability
- Out of scope for these tasks, per `plan.md`/`spec.md` Assumptions: wiring `review_spec()` as a Temporal activity, delivering `pm_approved`/`pm_rejected` decisions via the webhook bridge (`specs/002-webhook-trigger-bridge/`), attempt-budget tracking and escalation (`specs/005-pipeline-mode-signals-escalation/`), and ensuring a target-repo PR exists before the PM stage runs (`data-model.md`'s `pr_url` gap)
- Commit after each task or logical group
