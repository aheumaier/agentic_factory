---

description: "Task list template for feature implementation"
---

# Tasks: PM-Agent Issue-Shaping and Spec-Review Gate

**Input**: Design documents from `/specs/003-pm-agent-review-gate/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/pm-agent-interface.md, quickstart.md — all revised 2026-09-03 (second senior-architect pass). This tasks.md regenerates the prior version, which was written against the pre-revision design and no longer matches `plan.md`/`contracts/pm-agent-interface.md`.

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

- [ ] T001 Create `harness/pm-agent/pyproject.toml` declaring runtime deps `claude-agent-sdk`, `braintrust`, mirroring `harness/swe-agent/pyproject.toml`
- [ ] T002 [P] Create `registry/agents/pm-agent/manifest.yaml` and `registry/agents/pm-agent/versions/v1.yaml`, hand-written mirroring `registry/agents/swe-agent/manifest.yaml` (`status: experimental`, `requires_human_supervision: true` — this feature has no automated Register/Deploy wiring, per `plan.md`'s Structure Decision)
- [ ] T003 [P] Run `cd harness/pm-agent && uv sync` to confirm the declared deps resolve

**Checkpoint**: Package scaffolding exists; no code yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared code both user stories call — MUST complete before either story's implementation tasks

**⚠️ CRITICAL**: US1 and US2 both depend on every task in this phase.

- [ ] T004 Create `harness/pm-agent/agent.py` with module docstring, imports (`os`, `re`, `subprocess`, `tempfile`, `json`, `braintrust`, `claude_agent_sdk`), and Braintrust setup (`BRAINTRUST_PROJECT` env var, `braintrust.init_logger(project=BRAINTRUST_PROJECT)`, `braintrust.auto_instrument()`) — mirrors `harness/swe-agent/agent.py` lines 15-20, same project so a run's trace lands beside `eval/braintrust/eval.config.py`'s score
- [ ] T005 [P] Implement `_validate_repo(repo: str) -> None` and `_validate_branch(branch: str) -> None` in `harness/pm-agent/agent.py` as two distinct regex guards (`^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$` for repo, `^[A-Za-z0-9][A-Za-z0-9_./-]*$` plus leading-`-` rejection for branch), mirroring `harness/swe-agent/agent.py::_REPO_RE`/`_BRANCH_RE` exactly (`research.md` Unknown 6 — one shared regex would reject this feature's own branch name)
- [ ] T006 [P] Implement `_run(cmd: list[str], cwd: Path | None = None) -> str` in `harness/pm-agent/agent.py`, mirroring `harness/swe-agent/agent.py::_run` exactly (subprocess wrapper raising `CalledProcessError` on non-zero exit, returning stripped stdout)
- [ ] T007 [P] Implement `_scrubbed(error: subprocess.CalledProcessError, secret: str) -> subprocess.CalledProcessError` in `harness/pm-agent/agent.py`, mirroring `harness/swe-agent/agent.py::_scrubbed` exactly, for redacting a captured `GH_TOKEN` from any subprocess error before it could reach a log or PR comment

**Checkpoint**: Foundation ready — US1 and US2 implementation can now proceed (in parallel, if staffed).

---

## Phase 3: User Story 1 - Shape a raw issue before it becomes a spec (Priority: P1) 🎯

**Goal**: `shape_issue(repo, issue_number)` rewrites a raw issue's title/body with scope clarity and a no-gold-plating note, with zero bound tools, and zero side effects outside the issue itself.

**Independent Test**: Per `quickstart.md`'s "Validate User Story 1" — file a vague-scope issue with no linked PR, call `shape_issue()`, confirm the issue is edited and nothing else in the repo changed; repeat against an issue with a linked PR and confirm `RuntimeError`, no edit.

### Tests for User Story 1

- [ ] T008 [P] [US1] Unit test in `tests/test_pm_agent.py::test_shape_issue_rejects_linked_pr` — mocked `gh issue view` returns a non-empty `closedByPullRequestsReferences`, assert `RuntimeError` raised and no `gh issue edit` call made (`research.md` Unknown 8 — not the invalid `pullRequest` field the pre-revision tasks used)
- [ ] T009 [P] [US1] Unit test in `tests/test_pm_agent.py::test_shape_issue_zero_tools` — assert the `ClaudeAgentOptions` passed to the model call has `allowed_tools=[]` (`research.md` Unknown 1 — the structural guarantee behind FR-002/FR-003)
- [ ] T010 [P] [US1] Unit test in `tests/test_pm_agent.py::test_shape_issue_direct_to_anthropic` — assert the model call carries no LiteLLM base-URL override (`research.md` Unknown 1, revised — target-repo runner can't reach the proxy)
- [ ] T011 [P] [US1] Unit test in `tests/test_pm_agent.py::test_shape_issue_edits_issue` — given a mocked model response, assert `gh issue edit <n> --title ... --body ...` is called with the model's rewritten text and the function returns `{"number", "title", "body"}`

### Implementation for User Story 1

- [ ] T012 [US1] Add `SHAPE_ISSUE_PROMPT` module-level string constant to `harness/pm-agent/agent.py`, hardcoded like `harness/swe-agent/agent.py::IMPLEMENT_PROMPT` — no `prompts/pm-agent.json` (depends on T004)
- [ ] T013 [US1] Implement `shape_issue(repo: str, issue_number: int) -> dict` precondition steps in `harness/pm-agent/agent.py`: call `_validate_repo(repo)`; fetch `gh issue view <issue_number> --repo <repo> --json title,body,closedByPullRequestsReferences` via `_run`; raise `RuntimeError` if `closedByPullRequestsReferences` is non-empty (depends on T005, T006, T013's own field choice per `research.md` Unknown 8)
- [ ] T014 [US1] In `shape_issue()`, call the model via `query()` with `ClaudeAgentOptions(allowed_tools=[])`, direct-to-Anthropic (`ANTHROPIC_API_KEY`, no LiteLLM base URL), passing the fetched `title`/`body` as plain prompt text with `SHAPE_ISSUE_PROMPT`; parse the model's response into new `title`/`body` in code (depends on T012, T013)
- [ ] T015 [US1] In `shape_issue()`, call `gh issue edit <issue_number> --repo <repo> --title ... --body ...` via `_run`; return `{"number": issue_number, "title": ..., "body": ...}` (depends on T014)

### Trigger for User Story 1

- [ ] T016 [US1] Create `.github/workflows/pm-agent-shape.yml` (reusable, `on: workflow_call: {}`) in `agentic_factory`: `github.event.issue.pull_request == null` gate, `@pm-agent shape` comment-body match, `author_association` allowlist (`OWNER`/`MEMBER`/`COLLABORATOR`) mirroring `swe-agent-build.yml`, mints a GitHub App installation token via `actions/create-github-app-token`, adds an `actions/checkout` step pulling `agentic_factory@main` into a subdirectory, invokes `shape_issue()` via `uv run --project <subdirectory>/harness/pm-agent` (`research.md` Unknown 4, revised)
- [ ] T017 [P] [US1] Create `.github/workflows/pm-agent-shape-trigger.yml`, the ~10-line per-repo caller (`on: issue_comment: [created]`, `uses: aheumaier/agentic_factory/.github/workflows/pm-agent-shape.yml@main`, `secrets: inherit`), mirroring `swe-agent-trigger.yml`

### Documentation for User Story 1

- [ ] T018 [P] [US1] Write `harness/pm-agent/SKILL.md` documenting `shape_issue()`'s design, its zero-tool structural guarantee, and its direct-to-Anthropic deviation (network-reachability justification, distinct from `harness/swe-agent`'s skill-discovery justification — `research.md` Unknown 1), mirroring `harness/swe-agent/SKILL.md`'s structure
- [ ] T019 [P] [US1] Write `registry/agents/pm-agent/SKILL.md` as the registry-side copy required by `CLAUDE.md`'s portability boundary (the pre-revision plan omitted this copy — `plan.md`'s Project Structure)

**Checkpoint**: User Story 1 is independently functional and testable — `quickstart.md`'s Validate User Story 1 steps should all pass.

---

## Phase 4: User Story 2 - Review a spec for value and scope before build starts (Priority: P1)

**Goal**: `review_spec(repo, branch, pr_url, attempt, feedback=None)` posts a value-judgment writeup to the target-repo PR, is structurally unable to push a commit or mutate the repo via any other API, and is idempotent per attempt.

**Independent Test**: Per `quickstart.md`'s "Validate User Story 2" — with `spec.md` on a branch and a PR open, call `review_spec()` and confirm a writeup comment appears; confirm no push occurs and `GH_TOKEN`/`gh` auth are both absent from the model's environment; re-call with feedback and confirm a fresh, feedback-addressing writeup; re-call with the same `attempt` and confirm no duplicate comment; call with `attempt=99` and confirm no exception.

### Tests for User Story 2

- [ ] T020 [P] [US2] Unit test in `tests/test_pm_agent.py::test_review_spec_env_scrubbed` — assert the environment built for the model's tool-use loop has no `GH_TOKEN`/`GITHUB_TOKEN` and `GH_CONFIG_DIR` pointed at an empty directory (`research.md` Unknown 2, revised again — env-var removal alone doesn't stop a `gh api`/`gh pr merge` call authenticating from `gh`'s own config file)
- [ ] T021 [P] [US2] Unit test in `tests/test_pm_agent.py::test_review_spec_credential_helper_disabled` — assert `git config --local credential.helper ""` runs against the checkout immediately after clone
- [ ] T022 [P] [US2] Unit test in `tests/test_pm_agent.py::test_review_spec_no_attempt_cap` — call with `attempt=99`, assert no exception raised and a plain dict is returned (`research.md` Unknown 3 — no `MAX_PM_ATTEMPTS`, no `PmAttemptsExhausted`, that ownership is `specs/005-pipeline-mode-signals-escalation/`'s)
- [ ] T023 [P] [US2] Unit test in `tests/test_pm_agent.py::test_review_spec_idempotent_post` — mock `gh pr view --json comments` to already contain the `<!-- pm-agent:review attempt=2 -->` marker, assert no `gh pr comment` call is made and the existing body is returned unchanged (`research.md` Unknown 5)
- [ ] T024 [P] [US2] Unit test in `tests/test_pm_agent.py::test_review_spec_spec_path_from_branch` — assert the spec read is `specs/<branch>/spec.md`, derived from the `branch` argument, never a glob over `specs/*/spec.md` (`research.md` Unknown 7)
- [ ] T025 [P] [US2] Unit test in `tests/test_pm_agent.py::test_review_spec_missing_spec_raises` — checkout has no `specs/<branch>/spec.md`, assert `RuntimeError`

### Implementation for User Story 2

- [ ] T026 [US2] Add `SPEC_REVIEW_PROMPT` and `FEEDBACK_PROMPT_SUFFIX` module-level string constants to `harness/pm-agent/agent.py`, mirroring `harness/swe-agent/agent.py::IMPLEMENT_PROMPT`/`FEEDBACK_PROMPT_SUFFIX`'s pattern exactly — no runtime-loaded JSON file (depends on T004)
- [ ] T027 [US2] Implement `review_spec(repo: str, branch: str, pr_url: str, attempt: int, feedback: str | None = None) -> dict` signature and guard clauses in `harness/pm-agent/agent.py`: `_validate_repo(repo)`, `_validate_branch(branch)`, `attempt >= 1` else `ValueError` — no upper bound (depends on T005)
- [ ] T028 [US2] Implement the clone step in `review_spec()`: `git clone --depth 1 --branch <branch>` from the credential-less `https://github.com/<repo>.git` URL into a temp directory via `_run`; immediately run `git config --local credential.helper ""` in that checkout (depends on T006, T027)
- [ ] T029 [US2] Implement the spec-existence check in `review_spec()`: verify `specs/<branch>/spec.md` exists in the checkout (path derived from `branch`, not a glob — `research.md` Unknown 7); raise `RuntimeError` if absent (depends on T028)
- [ ] T030 [US2] Implement the credential scrub in `review_spec()`: capture `GH_TOKEN` from the process environment into a local variable; build the model tool-use environment as a copy of the process environment with `GH_TOKEN`/`GITHUB_TOKEN` removed, `GIT_TERMINAL_PROMPT=0` set, and `GH_CONFIG_DIR` pointed at a freshly created empty temp directory (`research.md` Unknown 2, revised again) (depends on T029)
- [ ] T031 [US2] Call the model in `review_spec()` via `query()` with `ClaudeAgentOptions(cwd=checkout, allowed_tools=["Read", "Grep", "Glob", "Bash"], env=<scrubbed env>)`, direct-to-Anthropic, prompting `SPEC_REVIEW_PROMPT` (+ `FEEDBACK_PROMPT_SUFFIX.format(feedback=feedback)` if `feedback` is given) (depends on T026, T030)
- [ ] T032 [US2] Implement the idempotent-post step in `review_spec()`: restore the captured `GH_TOKEN` for this step's own `gh` calls; build the writeup body with a leading `<!-- pm-agent:review attempt=<attempt> -->` marker; check `gh pr view <pr_url> --json comments` via `_run` for that exact marker; if present, use the existing comment's body; otherwise post via `gh pr comment <pr_url> --body ...` (depends on T031)
- [ ] T033 [US2] Return `{"writeup": str, "attempt": int}` from `review_spec()` (depends on T032)
- [ ] T034 [US2] Wrap the clone step's `subprocess.CalledProcessError` with `_scrubbed()` before it can propagate, redacting any credential that could otherwise leak into a log or PR comment (depends on T007, T028)

**Checkpoint**: User Story 2 is independently functional and testable — `quickstart.md`'s Validate User Story 2 steps should all pass.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [ ] T035 [P] Run `quickstart.md`'s Validate User Story 1 and Validate User Story 2 steps end-to-end against a scratch repo
- [ ] T036 [P] Run `uv run pytest` from repo root — confirm every `tests/test_pm_agent.py` test passes with no real GitHub network access
- [ ] T037 Add a "Known gaps" section to `harness/pm-agent/SKILL.md` documenting the unresolved cross-spec gaps recorded in `data-model.md`: the `pr_url` precondition (no producer of a target-repo PR exists yet), the cross-stage spec-version gap (no SHA pin between PM approval and Eval-Gate), and the spec-path glob bug found in `orchestration/activities.py::eval_gate_activity` (not fixed by this feature) — mirrors `harness/swe-agent/SKILL.md`'s own "Known gap" section pattern

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
- Model call before the mutating `gh`/`git` step
- Story complete and independently testable before Polish

### Parallel Opportunities

- T002, T003 (Setup) can run in parallel with T001 once T001's file exists
- T005, T006, T007 (Foundational) can all run in parallel — different functions, no shared state
- Once Foundational (Phase 2) completes, **all of Phase 3 (US1) and Phase 4 (US2) can proceed in parallel** — `shape_issue()` and `review_spec()` share no code path beyond the Phase 2 helpers
- All test tasks within a story (T008-T011; T020-T025) can run in parallel — independent mocks, same file but non-overlapping test functions
- T016/T017 (US1 trigger) can run in parallel with T012-T015 (US1 core logic) — different files

---

## Parallel Example: User Story 1

```bash
# Launch all US1 tests together:
Task: "Unit test test_shape_issue_rejects_linked_pr in tests/test_pm_agent.py"
Task: "Unit test test_shape_issue_zero_tools in tests/test_pm_agent.py"
Task: "Unit test test_shape_issue_direct_to_anthropic in tests/test_pm_agent.py"
Task: "Unit test test_shape_issue_edits_issue in tests/test_pm_agent.py"

# Launch US1's trigger workflow and documentation together (independent of core logic):
Task: "Create .github/workflows/pm-agent-shape-trigger.yml"
Task: "Write harness/pm-agent/SKILL.md"
Task: "Write registry/agents/pm-agent/SKILL.md"
```

---

## Implementation Strategy

### De-risk First (recommended)

Both user stories are Priority P1 in `spec.md`, but they carry very different risk: US1 binds zero tools (a purely structural guarantee); US2 binds `Bash` against a shallow clone and carries the credential-scrub guarantee this feature's two senior-architect review passes spent the most effort on (`research.md` Unknowns 2, 3, 5, 7). Shipping US1 first, independently, is the lower-risk slice:

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (blocks both stories)
3. Complete Phase 3: User Story 1 (Issue-Shaping)
4. **STOP and VALIDATE**: run `quickstart.md`'s User Story 1 steps independently
5. Complete Phase 4: User Story 2 (Spec-Review) — the higher-risk slice, now validated in isolation
6. **STOP and VALIDATE**: run `quickstart.md`'s User Story 2 steps, including the credential-scrub verification (T020, T021)
7. Complete Phase 5: Polish

### Parallel Team Strategy

With two developers, Phase 3 (US1) and Phase 4 (US2) can proceed genuinely in parallel once Phase 2 (Foundational) is done — they share no code path beyond the three Phase 2 helpers.

---

## Notes

- [P] tasks = different files or non-overlapping functions, no dependencies
- [Story] label maps task to US1 or US2 for traceability
- Out of scope for these tasks, per `plan.md`/`spec.md` Assumptions: wiring `review_spec()` as a Temporal activity, delivering `pm_approved`/`pm_rejected` decisions via the webhook bridge (`specs/002-webhook-trigger-bridge/`), attempt-budget tracking and escalation (`specs/005-pipeline-mode-signals-escalation/`), and ensuring a target-repo PR exists before the PM stage runs (`data-model.md`'s `pr_url` gap)
- Commit after each task or logical group
