# Tasks: Architect Fan-Out, Judge, and Completeness-Critic

**Input**: Design documents from `/specs/004-architect-fanout-judge/`

**Prerequisites**: plan.md, spec.md, research.md (11 Unknowns), data-model.md, contracts/architect-agent-interface.md, quickstart.md

**Tests**: Included — `plan.md`'s Testing section names `tests/test_architect_agent.py` explicitly, and `quickstart.md`'s offline tier is the *primary* validation surface for this feature rather than a supplement. That is not a stylistic choice: most of this feature's requirements (FR-003's candidate isolation, FR-011's never-on-disk guarantee, FR-005's strict score validation, FR-007b's critic independence) are **structural** — they are properties of tool bindings, prompt contents, and process state that a live run cannot demonstrate and only an assertion on a mocked call can. Skipping tests here would leave the feature's central guarantees unverified.

**Organization**: Tasks are grouped by user story — US1 = fan-out (P1), US2 = synthesis (P1), US3 = completeness-critic (P2) — per `spec.md`'s priorities.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (independent additions, no dependency on an incomplete task)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Every task names the exact file it touches

## Path Conventions

Single project, following the existing `harness/<agent>/` + `registry/agents/<agent>/` pattern per `plan.md`'s Structure Decision:

- `harness/architect-agent/agent.py`, `SKILL.md`, `pyproject.toml`
- `registry/agents/architect-agent/manifest.yaml`, `versions/v1.yaml`, `SKILL.md`
- `eval/braintrust/eval.config.py` (one additive function)
- `tests/conftest.py` (one additive loader), `tests/test_architect_agent.py`

**Note on `[P]` within `agent.py`**: most implementation tasks touch the same file. `[P]` is marked only where the additions are genuinely independent functions with no shared edit region — the same convention `specs/003-pm-agent-review-gate/tasks.md` used (its T006-T008 are three `[P]` tasks in one file).

---

## Phase 1: Setup

**Purpose**: Package and registry scaffolding — no behavior yet

- [X] T001 Create `harness/architect-agent/pyproject.toml` declaring runtime deps `claude-agent-sdk`, `braintrust>=0.36.0`, `python-dotenv>=1.0.0` — a copy of `harness/pm-agent/pyproject.toml` with the name changed (`braintrust` is required here for a second reason beyond spans: `eval/braintrust/eval.config.py` imports it, and T013 loads that module)
- [X] T002 [P] Create `registry/agents/architect-agent/manifest.yaml` mirroring `registry/agents/pm-agent/manifest.yaml` (`status: experimental`, `eval_gate_passed: false`, `requires_human_supervision: true` — this feature ships no Temporal wiring, per `plan.md`'s "Out of scope"), with `design_docs` pointing at `specs/004-architect-fanout-judge/spec.md` and `harness/architect-agent/SKILL.md`
- [X] T003 [P] Create `registry/agents/architect-agent/versions/v1.yaml` mirroring `registry/agents/swe-agent/versions/v1.yaml`'s field set, with `harness_entrypoint: harness/architect-agent/agent.py`, `orchestration_entrypoint: none (no Temporal activity in this feature — specs/005)`, `model_runtime: Claude Agent SDK via LiteLLM proxy`, `tools_allowed: [Read, Grep, Glob]`, `model: claude-sonnet-5` (one pinned id for every role — candidates, gap candidate, scoring, synthesis, critic — per `contracts/architect-agent-interface.md`'s `MODEL` constant and `plan.md`'s Constraints; it is the only id `litellm/config.yaml`'s two routes guarantee resolves, since the Agent SDK CLI requests it by default), and a `sandbox:` value stating **no E2B sandbox** per `docs/70-multi-agent-pipeline-design.md` §6.1's carve-out — `.github/workflows/registry-gate.yml` requires a non-empty `versions/`, so this file is gate-blocking, not optional
- [X] T004 [P] Run `cd harness/architect-agent && uv sync` to confirm the declared deps resolve
- [X] T005 [P] Update root `CLAUDE.md`'s layer table (new `harness/architect-agent/` Harness/Runtime row + a third `registry/agents/` entry) and `docs/00-status.md` to record this feature, its LiteLLM routing (`research.md` Unknown 9), and its §6.1 no-sandbox carve-out

**Checkpoint**: Scaffolding exists; no code yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The test-import path, the shared helpers, and the two guarantees that are process-wide rather than per-story

**⚠️ CRITICAL**: All three user stories depend on every task in this phase. T006 in particular blocks *every* test task in the file — without it, `tests/test_architect_agent.py` cannot import the module at all.

- [X] T006 Extend `tests/conftest.py` with `_load_agent(name, path)` using `importlib.util.spec_from_file_location`, and load `harness/architect-agent/agent.py` as module name `architect_agent`. **Required, not cosmetic**: `tests/conftest.py:16-18` currently inserts `harness/pm-agent/` onto `sys.path` so tests do `import agent`, and a second `harness/<agent>/agent.py` collides on that module name (`research.md` Unknown 11). Leave the existing stub block (`claude_agent_sdk`/`dotenv`/`braintrust`) and `tests/test_pm_agent.py`'s `import agent` untouched — refactoring 003's tests onto the same loader is deliberately deferred
- [X] T007 Create `harness/architect-agent/agent.py` with module docstring, imports (`asyncio`, `importlib.util`, `json`, `os`, `re`, `subprocess`, `tempfile`, `pathlib.Path`, `braintrust`, `claude_agent_sdk`, `dotenv`), `load_dotenv` of the repo-root `.env`, Braintrust setup (`BRAINTRUST_PROJECT`, `init_logger`, `auto_instrument`), and the `LITELLM_BASE_URL`/`LITELLM_API_KEY` constants — mirrors `harness/pm-agent/agent.py:1-33` (depends on T001)
- [X] T008 [P] Add module constants `MIN_CANDIDATES = 3`, `MAX_CANDIDATES = 6`, `MAX_MALFORMED_RETRIES = 1`, `_COMMENT_LIMIT = 60000`, `CANDIDATE_CONCURRENCY = 3`, `CANDIDATE_TIMEOUT_S = 600`, `MAX_PLAN_CHARS = 40000`, `MAX_TASKS_CHARS = 20000`, and the six-entry `ANGLES` list to `harness/architect-agent/agent.py` per `contracts/architect-agent-interface.md`'s "Module constants". Do **not** add a `MAX_PLAN_ATTEMPTS` constant — FR-010/FR-013a are `specs/005-pipeline-mode-signals-escalation/`'s to own, and 003 removed its own `PmAttemptsExhausted` for exactly this reason (depends on T007)
- [X] T009 [P] Implement `_validate_repo` and `_validate_branch` in `harness/architect-agent/agent.py` as two distinct regex guards, mirroring `harness/pm-agent/agent.py:103-114` exactly (depends on T007)
- [X] T010 [P] Implement `_run(cmd, cwd=None)` and `_scrubbed(error, secret)` in `harness/architect-agent/agent.py`, mirroring `harness/pm-agent/agent.py:117-144` exactly (depends on T007)
- [X] T011 [P] Implement `_model_text(prompt, options)` in `harness/architect-agent/agent.py`, mirroring `harness/pm-agent/agent.py:147-163` — returns only the final `result`, not a join of every SDK message (depends on T007)
- [X] T012 [P] Add `load_success_criteria_ids(spec_path) -> list[tuple[str, str]]` to `eval/braintrust/eval.config.py` using a capturing variant of the existing `_SC_BULLET_RE` (`SC-\d+` currently matched and discarded). Leave `load_success_criteria()` and `run_eval()` byte-for-byte unchanged — this is additive so the architect and the Eval-Gate share one `SC-NNN` universe (`research.md` Unknown 2)
- [X] T013 Implement `_load_sc_ids(spec_path)` in `harness/architect-agent/agent.py`: an `importlib.util.spec_from_file_location` load of `eval/braintrust/eval.config.py` (its filename has dots, so plain `import` can't reach it), mirroring `orchestration/activities.py:99-112`, then a call to `load_success_criteria_ids`. **Load lazily, inside this function — not at module scope**: `eval.config.py` does `import braintrust` at module scope, and a module-scope shim would drag the eval layer's import into every architect import and test collection (`research.md` Unknown 2). **`_load_sc_ids` is the *default* for `run_architect_stage`'s injectable `sc_loader` parameter, not a hard call** — the single-`SC-NNN`-universe argument is right, but making the harness import from the eval layer to get it is a layer inversion that also drags `braintrust` into the harness's runtime deps for a fifteen-line regex. Injecting moves the coupling to the composition root, where `orchestration/activities.py` already loads that exact module by path; the default keeps `python -m` and the quickstart standalone (depends on T007, T012)
- [X] T014 Implement the `_no_git_credentials()` context manager in `harness/architect-agent/agent.py`: pops `GH_TOKEN`/`GITHUB_TOKEN` from the parent process's `os.environ` on enter, restores both in a `finally` on exit. **One window per stage, entered once** — not per model call: `harness/pm-agent/agent.py:307-315`'s per-call pop/restore becomes a race under `asyncio.gather`, where one candidate's restore hands a live token to a sibling still spawning (`research.md` Unknown 1). Use `contextlib.contextmanager`; note that `ClaudeAgentOptions.env` cannot substitute here — it merges *on top of* `os.environ` in the SDK's subprocess launcher, so it can override a value but not remove an inherited one (depends on T007)
- [X] T015 [P] Unit test `tests/test_architect_agent.py::test_no_git_credentials_pops_and_restores` — with both `GH_TOKEN` and `GITHUB_TOKEN` set, assert both are absent inside the `with` block and restored to their original values after, including on the exception path (depends on T006, T014)
- [X] T016 [P] Unit test `tests/test_architect_agent.py::test_load_sc_ids_returns_id_text_pairs` — write a temp `spec.md` with three `- **SC-NNN**: ...` bullets under `### Measurable Outcomes` (one wrapping across lines), assert `_load_sc_ids` returns `[("SC-001", ...), ("SC-002", ...), ("SC-003", ...)]` with whitespace collapsed; assert a spec with no `### Measurable Outcomes` section raises `ValueError` (depends on T006, T013)
- [X] T017 Implement `_clone_spec_branch(repo, branch, spec_dir, work_root)` in `harness/architect-agent/agent.py`: shallow-clone via a token-embedded `https://x-access-token:<token>@github.com/<repo>.git` URL (so private target repos clone), `_scrubbed` any `CalledProcessError`, then **immediately `git remote set-url origin https://github.com/<repo>.git`**, disable the checkout's `credential.helper`, and resolve `<spec_dir>/spec.md` — raising with `review_spec()`'s "pass `spec_dir` explicitly" guidance when it is missing. Mirrors `harness/pm-agent/agent.py:267-286` **except** for the `set-url`, which pm-agent lacks. That line is security-critical, not tidiness — it is what FR-015 requires: `git clone` writes the token into the checkout's `.git/config` as the `origin` URL, `credential.helper ""` does nothing about it, candidates are bound `Read` with `cwd=checkout`, and their `plan_md` is posted verbatim to a PR comment (FR-014) — so without it a candidate that reads `.git/config` publishes a GitHub App installation token. This runs **before** the `_no_git_credentials()` window, since it needs the token (depends on T009, T010)
- [X] T017a [P] [FR-015] Unit test `tests/test_architect_agent.py::test_clone_leaves_no_token_in_checkout` — run `_clone_spec_branch` against a local fixture repo with a sentinel token value, then walk **every** file in the checkout (`.git/` included, and explicitly not via `Grep`/ripgrep, which skips `.git/`) asserting the sentinel appears in none of them. Also assert `git remote get-url origin` returns the token-free URL. This is the only test that catches FR-015's exfiltration path (depends on T006, T017)
- [X] T018 [P] Implement `_parse_json_envelope(text)` in `harness/architect-agent/agent.py`: extract and `json.loads` the single JSON object from a model response, raising a descriptive error on failure. Shared by the candidate, scoring, synthesis, and critic calls — all four exchange JSON, not prose (`research.md` Unknowns 4, 5, 6) (depends on T007)
- [X] T019 [P] Unit test `tests/test_architect_agent.py::test_clone_spec_branch_scrubs_token_on_failure` — mocked `_run` raising `CalledProcessError` whose `cmd` contains the token; assert the re-raised error's `cmd`, `output`, `stderr`, and `args` all have it replaced with `***` (depends on T006, T017)

**Checkpoint**: Foundation ready. All three stories can now proceed, in parallel if staffed.

---

## Phase 3: User Story 1 - Explore multiple architectural angles instead of committing to one (Priority: P1) 🎯 MVP

**Goal**: `candidate_count()` / `angles_for()` / `generate_candidates()` produce N independent candidate plans for one spec, each from a distinct stated angle, none with visibility into another's output, and N scaling with spec complexity.

**Independent Test**: Per `quickstart.md`'s "Validate User Story 1" — assert on a mocked `query()`'s recorded prompts that no candidate's prompt contains another candidate's output, that each carries a distinct angle, and that the count scales with the `SC-NNN` count. The concurrency-scrub test (T024) is the one that a per-call credential scrub would fail while a sequential test passed.

### Tests for User Story 1

- [X] T020 [P] [US1] Unit test `tests/test_architect_agent.py::test_candidate_count_properties` — assert all four guaranteed properties from `contracts/architect-agent-interface.md`: monotonic non-decreasing in `len(sc_ids)`, `>= MIN_CANDIDATES` when `n_override is None`, `<= MAX_CANDIDATES` always, and not constant across spec sizes (`candidate_count(["SC-001"] * 20) > candidate_count(["SC-001"] * 5)` — this last one is SC-005's actual requirement, not the arithmetic) (depends on T006, T028)
- [X] T021 [P] [US1] Unit test `tests/test_architect_agent.py::test_candidate_count_override` — `n_override=1` returns 1 (the `vibe`-mode seam, below `MIN_CANDIDATES`), `n_override=99` clamps to `MAX_CANDIDATES` (depends on T006, T028)
- [X] T022 [P] [US1] Unit test `tests/test_architect_agent.py::test_angles_for` — returns `n` distinct angles in `ANGLES` order, and raises `ValueError` for `n > MAX_CANDIDATES` so FR-001's "explicitly stated angle" can never fall back to a reused or model-invented one (depends on T006, T028)
- [X] T023 [P] [US1] Unit test `tests/test_architect_agent.py::test_generate_candidates_isolation` — fake `query()` recording every prompt and returning a distinctly-identifiable envelope per call; assert one call per angle, each prompt containing its own angle and **no other candidate's returned text**, and no `synthesized_plan` content in any prompt. This is FR-003's verification: isolation holds because each `query()` is its own CLI subprocess, and this test asserts nothing leaks through the prompts either (depends on T006, T028)
- [X] T024 [P] [US1] Unit test `tests/test_architect_agent.py::test_generate_candidates_scrubs_credentials_for_every_call` — set `GH_TOKEN` in the parent env, enter `_no_git_credentials()`, then run `generate_candidates()` with a fake `query()` that records `os.environ.get("GH_TOKEN")` at call time; assert **every** recorded value is `None`. A per-candidate scrub passes a sequential test and fails this one — that asymmetry is the point (`research.md` Unknown 1) (depends on T006, T014, T028)
- [X] T025 [P] [US1] Unit test `tests/test_architect_agent.py::test_generate_candidate_tool_binding` — assert the `ClaudeAgentOptions` for a candidate call has `tools == ["Read","Grep","Glob"]`, `setting_sources == []`, `cwd` set to the checkout, and no `Write`/`Edit`/`Bash` anywhere. This is FR-011's structural half: a candidate plan cannot reach the filesystem. Also assert `env` carries the LiteLLM `ANTHROPIC_BASE_URL`/`ANTHROPIC_API_KEY` overrides (`research.md` Unknown 9) (depends on T006, T027)
- [X] T026 [P] [US1] Unit test `tests/test_architect_agent.py::test_generate_candidate_validity_and_mode_legality` — (a) unparseable output, and output with empty `plan_md` or empty `tasks_md`, each return `{"valid": False, "error": ...}` rather than raising; (b) a valid envelope whose `angle` disagrees with the caller's keeps the **caller's** angle; (c) `gap` set with `synthesized_plan=None` (and the reverse) raises `ValueError`, so a gap candidate cannot silently degrade into a blind one (`research.md` Unknowns 4, 7) (depends on T006, T027)

### Implementation for User Story 1

- [X] T027 [US1] Add `CANDIDATE_PROMPT` and `GAP_CANDIDATE_PROMPT` module-level constants to `harness/architect-agent/agent.py` (hardcoded, like `harness/pm-agent/agent.py`'s prompt constants — no runtime-loaded `prompts/architect-agent.json`), then implement `generate_candidate(checkout, spec_dir, angle, *, gap=None, synthesized_plan=None)`: mode-legality check (both-`None` = fan-out, both-set = gap, anything else `ValueError`), one `query()` with the tool binding from T025, `_parse_json_envelope`, the validity predicate (parses **and** non-empty `plan_md` **and** non-empty `tasks_md`), and a return dict carrying the caller's `angle`. The fan-out prompt template must have **no slot** for any plan or other candidate (depends on T008, T011, T018)
- [X] T028 [US1] Implement `candidate_count(sc_ids, n_override=None)`, `angles_for(n)`, and `generate_candidates(checkout, spec_dir, angles)` in `harness/architect-agent/agent.py` — the last as an `asyncio.gather` over `generate_candidate()` in fan-out mode, returning one dict per angle in `angles` order, valid and invalid alike. **Bounded, not bare**: an `asyncio.Semaphore(CANDIDATE_CONCURRENCY)` caps in-flight CLI subprocesses (at `N=6` an unbounded gather puts six of them on the worker host against one self-hosted LiteLLM proxy), and each call is wrapped in `asyncio.wait_for(..., CANDIDATE_TIMEOUT_S)` so one hung `query()` cannot hang the stage forever — a timeout yields `{"valid": False, "error": "timeout", ...}`, reusing the partial-failure path rather than adding a second failure mode. `generate_candidates()` must **not** manipulate `os.environ` itself; it documents that it must be called inside the stage's single `_no_git_credentials()` window, which the semaphore does not change since candidates still overlap (depends on T008, T027)
- [X] T028a [P] [US1] Unit test `tests/test_architect_agent.py::test_generate_candidates_bounds` — (a) with a fake `query()` that records concurrent entries, assert the peak never exceeds `CANDIDATE_CONCURRENCY`; (b) a `query()` that never returns yields a `valid=False` `"timeout"` candidate rather than hanging, and the surviving candidates still come back; (c) a candidate whose `plan_md` exceeds `MAX_PLAN_CHARS` is `valid=False` — without (c), prompt size is `O(N × plan_length)` with no context-limit guard, since scoring carries all N plans and synthesis carries them again (depends on T006, T028)

**Checkpoint**: US1 independently functional — `quickstart.md`'s Validate User Story 1 offline assertions all pass.

---

## Phase 4: User Story 2 - Synthesize one actionable plan from the candidates (Priority: P1)

**Goal**: Scoring produces a validated, machine-checkable per-`SC-NNN` coverage map plus a 1-5 ordinal consistency rating; a separate synthesis step consumes that structure to produce exactly one plan/tasks/ADR set; the synthesized plan is committed and posted with candidates collapsed.

**Independent Test**: Per `quickstart.md`'s "Validate User Story 2" — exactly one result or a raise (never a list), three distinct score-validation rejections, one malformed candidate tolerated while all-malformed retries once then raises, comment section order and truncation honored, and a same-`attempt` re-invocation issuing zero `query()` calls.

### Tests for User Story 2

- [X] T029 [P] [US2] Unit test `tests/test_architect_agent.py::test_score_candidates_rejects_bad_coverage` — three separate rejections: an invented `SC-NNN` key, a missing one (subset), and a non-`SC-\d+` key. These three are what make SC-006's map machine-checkable rather than merely non-empty (depends on T006, T038)
- [X] T030 [P] [US2] Unit test `tests/test_architect_agent.py::test_score_candidates_rejects_bad_consistency_rating` — `0`, `6`, `"high"`, and `3.5` each raise; `1` through `5` pass (FR-005's ordinal-scale clarification) (depends on T006, T038)
- [X] T031 [P] [US2] Unit test `tests/test_architect_agent.py::test_synthesize_receives_scores_not_prose` — assert the synthesis prompt contains the validated score structure (coverage keys, consistency ratings) and does **not** contain the scoring call's aggregate reasoning; assert scoring and synthesis are two distinct `query()` calls (FR-005a's separation, so an evaluation error stays inspectable instead of being baked into the artifact as fact) (depends on T006, T038, T039)
- [X] T032 [P] [US2] Unit test `tests/test_architect_agent.py::test_synthesize_cardinality_and_references` — returns exactly one result object or raises, with no list-valued path (SC-002's "never zero and never more than one"); a `winner_index` or `grafted_from` entry referencing an invalid or nonexistent candidate raises (depends on T006, T039)
- [X] T033 [P] [US2] Unit test `tests/test_architect_agent.py::test_partial_and_total_malformed_candidates` — (a) one malformed candidate among three: synthesis still runs over the remaining two, and the invalid one appears in `invalid_candidates` with its angle and reason (reported, never silently dropped); (b) **all** candidates malformed: exactly `MAX_MALFORMED_RETRIES` (1) extra fan-out happens, then `RuntimeError` — and specifically not a fall-through to the caller's plan budget, which FR-013 forbids; (c) a scoring- or synthesis-call error propagates as-is with `malformed_retries_used == 0`, since FR-013a routes those to `MAX_PLAN_ATTEMPTS` in the caller (depends on T006, T042)
- [X] T034 [P] [US2] [SC-004] Unit test `tests/test_architect_agent.py::test_post_stage_comment_format_and_budget` — assert (a) marker first, then delta line only when `delta` is not `None`, then synthesized plan, then rationale, coverage table, completeness note, invalid candidates, and collapsed `<details>` last (FR-014's progressive disclosure); (b) an oversized candidate is truncated at its share with the visible `…[truncated …]` notice pointing at its Braintrust span, never silently — this notice-with-pointer is what makes SC-004's narrowed form ("in full or via an explicit pointer") true rather than violated; (c) with sections 1-7 alone over `_COMMENT_LIMIT`, the `<details>` blocks are dropped with a one-line note and the synthesized plan survives; (d) the assembled body never exceeds `_COMMENT_LIMIT` (depends on T006, T041)
- [X] T035 [P] [US2] Unit test `tests/test_architect_agent.py::test_persist_synthesized_writes_only_synthesized` — assert `plan.md`, `tasks.md`, and one `ADR-NNN-<slug>.md` per ADR are written under `<spec_dir>/`, that **no candidate plan is written anywhere** in the checkout, that one commit is made, and that an existing `plan.md`/`tasks.md` is overwritten (the documented intent — `contracts/architect-agent-interface.md`'s "Overwrites unconditionally"). **Additionally assert on the commit argv that `-c user.email=` and `-c user.name=` are present** — a temp repo inherits the developer's global git config, so this test passes either way unless the identity is asserted directly rather than inferred from a green commit (depends on T006, T040)
- [X] T036 [P] [US2] Unit test `tests/test_architect_agent.py::test_run_architect_stage_idempotent_per_attempt` — with `_existing_stage_comment` returning a body for the given `attempt`, assert (a) **zero `query()` calls are issued** — the check must run before any model work, not merely before the post, or a re-invocation would still burn `N + 3` model calls (`research.md` Unknown 10); and (b) the return is exactly the degraded three-key shape `{"attempt", "comment_body", "idempotent_hit": True}` and **not** the twelve-key result dict. (b) is the half that matters to a caller: none of `plan_md`/`scores`/`commit_sha` is reconstructible from a comment body, so a contract that promised them would `KeyError` on the *success* path of a Temporal retry. Also assert the normal path's return has no `idempotent_hit` key or a falsy one (depends on T006, T042)
- [X] T037 [P] [US2] Unit test `tests/test_architect_agent.py::test_run_architect_stage_scrub_window_scope` — assert the token is absent during every model call **and present again** for `persist_synthesized`, the push, and `gh pr comment`. A `try`/`finally` wrapping the whole function instead of steps 6-9 would leave the commit/push/comment running token-less against a private repo — the same scope bug as T024's, one step further out (depends on T006, T042)

### Implementation for User Story 2

- [X] T038 [US2] Add `SCORING_PROMPT` to `harness/architect-agent/agent.py` and implement `score_candidates(candidates, sc_ids)`: one `query()` over the valid candidates, `_parse_json_envelope`, then **strict, total** Python validation — `coverage` keys must equal the `SC-NNN` id set exactly (no superset, no subset, no non-`SC-\d+` key) and `internal_consistency` must be an `int` in `1..5`. Reject leniency deliberately: defaulting a missing id to `false` makes a model that *omitted* half the criteria indistinguishable from one that found them *uncovered* (`research.md` Unknown 5). **Randomise candidate order in the prompt** (the returned list stays in candidate-index order) — a single comparative call imports position/anchoring bias, and FR-007a's coverage half is a per-candidate determination needing no comparison at all (depends on T013, T018)
- [X] T038a [US2] Implement `pick_winner(scores) -> int` in `harness/architect-agent/agent.py` — **pure Python, no model call**: highest count of `True` coverage entries, then highest `internal_consistency`, then lowest `candidate_index`. This is what gives FR-005a teeth. With a model-chosen winner, a synthesis call that ignored the scores entirely is indistinguishable from one that used them, and ties have no defined answer; computing it makes the PR comment's "why this winner" a reproducible computation and makes the property assertable (depends on T008)
- [X] T038b [P] [US2] Unit test `tests/test_architect_agent.py::test_pick_winner_ordering_is_total` — coverage count dominates consistency; consistency breaks a coverage tie; lowest index breaks a full tie; and the function is deterministic across repeated calls on shuffled input. Assert `synthesize()` receives this computed value rather than deriving its own (depends on T006, T038a)
- [X] T039 [US2] Add `SYNTHESIS_PROMPT` and implement `synthesize(candidates, scores, winner_index, feedback=None)` in `harness/architect-agent/agent.py`: one `query()` distinct from T038's, receiving the valid candidates' `plan_md`/`tasks_md`/`adrs`, the validated `scores` structure, and the `pick_winner()`-computed `winner_index` **as a given** — the model does grafting and prose, not selection — and **not** the scoring call's aggregate prose; returns exactly one Synthesis Result (`plan_md`, `tasks_md`, `adrs`, `winner_index`, `grafted_from`, `rationale`) or raises. Echo the passed `winner_index` into the result, discarding the model's own echo of it the way `generate_candidate` discards the model's echo of `angle`. Validate that every `grafted_from` entry references a valid candidate. `feedback` is prompt content only — this function neither counts nor bounds attempts (depends on T038, T038a)
- [X] T040 [US2] Implement `persist_synthesized(checkout, spec_dir, synthesized) -> str` and `push_synthesized(checkout, branch, token=None) -> None` as two separate functions in `harness/architect-agent/agent.py`, mirroring `harness/swe-agent/agent.py`'s own commit/push split so a caller can take the artifact without the network effect. Pure `subprocess`/filesystem code — no model call, and no `Write`/`Bash` tool is bound anywhere in this stage, which is what makes FR-011 structural (`research.md` Unknown 8). Two things swe-agent does not need and this does: (a) the commit MUST pass `-c user.email=... -c user.name=...`, mirroring `orchestration/activities.py`'s `_GIT_IDENTITY` — swe-agent's commit is made by the *model* via `Bash` in a configured sandbox, this one is code-side on a Temporal worker that may have no global git config, where `git commit` dies with `Please tell me who you are` **after** all `N + 3` model calls are paid for; (b) `push_synthesized` builds the credentialed `https://x-access-token:<token>@github.com/<repo>.git` URL in argv rather than reading it from `origin`, because T017 stripped it from `.git/config` (depends on T010)
- [X] T041 [US2] Implement `_existing_stage_comment(repo, pr_url, attempt)` and `post_stage_comment(...)` in `harness/architect-agent/agent.py`: the marker `<!-- architect-agent:stage attempt=<N> spec=<sha> -->` (mirroring `harness/pm-agent/agent.py:230-237`'s convention), the fixed section order from `data-model.md`, and the `_COMMENT_LIMIT` size budget — remaining budget split evenly across the `<details>` blocks, oversized ones truncated with a visible notice pointing at the attempt's Braintrust span, and the synthesized plan never *dropped* (it may, in the last-resort branch where sections 1-7 alone still exceed the limit, be truncated inline with a pointer to `<spec_dir>/plan.md` at the step-10 commit — by then the full text is on the branch, and the alternative is `gh pr comment` failing hard after all `N + 3` calls are paid for). Note that section 5's coverage table is criterion × candidate and therefore **is** `N`-bounded, so it shares the budget rather than being always-in-full. **The truncation notice obliges an explicit `braintrust` log of each candidate's `plan_md` for the attempt** — module-level `init_logger`/`auto_instrument` does not capture it, and a notice pointing at an artifact nothing produces is worse than no notice (depends on T008, T010)
- [X] T042 [US2] Implement `run_architect_stage(repo, branch, pr_url, attempt, feedback=None, spec_dir=None, n_candidates=None, push=True, sc_loader=None)` in `harness/architect-agent/agent.py` per `contracts/architect-agent-interface.md`'s 11-step sequence, **minus step 9's gap round** (added in US3): validate inputs (`attempt < 1` → `ValueError`); `_existing_stage_comment` early-return before any model work, returning the degraded `{"attempt", "comment_body", "idempotent_hit": True}` shape; `_clone_spec_branch`; `sc_loader(spec_path)` defaulting to `_load_sc_ids` (empty criteria = precondition failure, not a gap finding); enter `_no_git_credentials()` wrapping **only** the model calls; fan-out with the `MAX_MALFORMED_RETRIES` loop (exhaustion → plain `RuntimeError`, no fall-through); score; `pick_winner`; synthesize; exit the window; `persist_synthesized`; `push_synthesized(checkout, branch, token)` if `push`; `post_stage_comment` with `delta` derived per the rule below. Return the documented result dict with `gap_round_ran=False` for now.

  **`delta` derivation** (FR-014's delta line is otherwise an argument nothing ever fills): `attempt == 1` → `None`; `feedback` set → `"Revised after: <first line of feedback, truncated>"`; `gap_round_ran` → `"Re-synthesized after gap round: <completeness.note, truncated>"`; otherwise (`attempt >= 2`) → `"Re-ran attempt <N> against spec <sha>."`. The last branch exists so the "non-`None` whenever `attempt >= 2`" guarantee holds with no feedback and no gap (depends on T014, T017, T028, T038a, T039, T040, T041)
- [X] T042a [P] [US2] Unit test `tests/test_architect_agent.py::test_delta_line_derivation` — assert `None` on attempt 1, and a non-`None` delta on attempt 2 in each of the three branches (feedback present, gap round ran, neither) (depends on T006, T042)

**Checkpoint**: US1 + US2 both work. The stage runs end-to-end without the coverage check — `quickstart.md`'s Validate User Story 2 offline assertions all pass.

---

## Phase 5: User Story 3 - Catch coverage gaps the candidate panel missed (Priority: P2)

**Goal**: An independent completeness pass determines per-`SC-NNN` coverage and looks for an untried angle; no gap yields a short note and an unchanged plan; a gap yields exactly one targeted candidate plus one re-synthesis.

**Independent Test**: Per `quickstart.md`'s "Validate User Story 3" — the critic prompt excludes the judge's rationale, `gap_found` is derived rather than trusted, the gap path fires exactly one gap-mode candidate and one re-synthesis with the critic *not* re-run, and the no-gap path produces the "no additional angle was identified" wording.

### Tests for User Story 3

- [X] T043 [P] [US3] Unit test `tests/test_architect_agent.py::test_check_completeness_prompt_independence` — assert the critic prompt contains the synthesized plan, the full `(id, text)` criteria list, and the angle **names**, and does **not** contain the judge's rationale, the score records, or any candidate's plan text (FR-007b's independence). Also assert the angle names *are* present — withholding them would make "was an angle missed" literally unanswerable (`research.md` Unknown 6) (depends on T006, T048)
- [X] T044 [P] [US3] Unit test `tests/test_architect_agent.py::test_gap_found_is_derived_not_trusted` — a mocked critic returning `gap_found: true` with empty `uncovered` and null `missed_angle` yields `gap_found == False` (no gap round fires with nothing to target); a critic returning `gap_found: false` while listing an `uncovered` id yields `gap_found == True`. Also assert an `uncovered` id outside the spec's set raises (depends on T006, T048)
- [X] T045 [P] [US3] Unit test `tests/test_architect_agent.py::test_no_gap_path` — `gap_round_ran == False`, exactly `N` candidate `query()` calls total, the plan is posted unchanged, and the note text reads "no additional angle was identified" rather than asserting none exists (FR-007b, FR-008) (depends on T006, T049)
- [X] T046 [P] [US3] Unit test `tests/test_architect_agent.py::test_gap_path_runs_exactly_one_extra_round` — assert exactly one additional `generate_candidate()` in **gap mode** (both `gap` and `synthesized_plan` set, per FR-009), exactly one re-`score_candidates` + re-`synthesize`, `gap_round_ran == True`, and that `check_completeness` is **not** re-run within the same attempt. Then assert a second gap round is unreachable even if the mocked critic would report another gap — SC-003's "never an unbounded chain" is a property of the `gap_round_ran` flag, not an emergent one (depends on T006, T049)
- [X] T047 [P] [US3] Unit test `tests/test_architect_agent.py::test_gap_candidate_sees_synthesized_plan` — assert the gap-mode prompt contains both the gap description and the **full** synthesized plan, unlike the fan-out prompts asserted in T023 (the 2026-09-03 clarification: the gap candidate's output must slot into the existing plan rather than being a disconnected alternative) (depends on T006, T027, T049)

### Implementation for User Story 3

- [X] T048 [US3] Add `CRITIC_PROMPT` and implement `check_completeness(synthesized, sc_ids, angles_tried)` in `harness/architect-agent/agent.py`: one `query()` with a fresh context whose prompt carries the synthesized plan, the `(id, text)` criteria list, and `angles_tried` — and none of the judge's rationale, the scores, or any candidate's plan text. Validate `uncovered` against the id set; derive `gap_found` in Python as `bool(uncovered) or missed_angle is not None`; render `missed_angle is None` in `note` as "no additional angle was identified" (depends on T013, T018)
- [X] T049 [US3] Add step 9 to `run_architect_stage()` in `harness/architect-agent/agent.py`: call `check_completeness()` after synthesis; if `gap_found` and not `gap_round_ran`, run one `generate_candidate()` in gap mode (gap description + full synthesized plan), then `score_candidates()` + `synthesize()` again over the extended set, and set `gap_round_ran = True`. Do **not** re-run the critic — FR-009 specifies exactly one targeted candidate plus a re-synthesis, and Story 3's scenario 3 sends any further checking to the next attempt against the `MAX_PLAN_ATTEMPTS` this module does not own. Include the completeness note in the posted comment and `gap_round_ran` in the result dict (depends on T042, T048)

**Checkpoint**: All three stories independently functional. The full stage sequence from `contracts/architect-agent-interface.md` is implemented.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T050 Add the `__main__` dispatch block to `harness/architect-agent/agent.py` (`architect-stage <repo> <branch> <pr_url> <attempt> [feedback]` → `asyncio.run`, print result, `logger.flush()`), mirroring `harness/pm-agent/agent.py:325-343`. Manual/quickstart use only — the production trigger is the future Temporal activity `specs/005-...` brings (depends on T049)
- [X] T051 [P] Write `harness/architect-agent/SKILL.md` mirroring `harness/pm-agent/SKILL.md`'s structure: the three roles and their distinct tool access, the §6.1 no-sandbox carve-out, the LiteLLM routing (`research.md` Unknown 9), the **documented deviation from `docs/70-multi-agent-pipeline-design.md` §2** (a model-produced ordinal 1-5 consistency rating instead of each candidate's `/speckit-analyze` result — `/speckit-analyze` needs `Bash`, exactly what 003 dropped to stay LiteLLM-routed and hook-free, and binding it to N candidates reintroduces that surface N times), and a "Known gaps" section covering no Temporal wiring, no gate, `MAX_PLAN_ATTEMPTS` not owned here, no `vibe` mode, and the `pr_url` producer that does not exist
- [X] T052 [P] Write `registry/agents/architect-agent/SKILL.md` as the registry-side copy `CLAUDE.md`'s portability boundary requires under `registry/agents/<name>/`. Make one of the two files authoritative and the other a generated copy or a pointer to it — a hand-copy bakes in drift, and `.github/workflows/registry-gate.yml` checks only for a `manifest.yaml` and a non-empty `versions/`, never SKILL content or parity between the copies (`pm-agent` already carries two independently-editable copies)
- [X] T053a [P] Record in `harness/architect-agent/SKILL.md`, `registry/agents/architect-agent/manifest.yaml`, and `plan.md` that **this stage is not automatically gated**, plainly rather than by omission: `eval/braintrust/eval.config.py::run_eval` passes on sandbox `exit_code == 0` + a `pr_url` + ≥1 parsed `SC-NNN`, all Build-stage facts the architect stage produces none of. Compounding it, SC-006's coverage map scores the **candidates**, not the shipped synthesized plan (which is fresh model-written text no score covers), and the critic never blocks — FR-008/FR-009 route a gap to one extra round whose result is never re-checked. So the critic is **advisory with one retry, not a gate**, and plan-to-spec coverage stays unenforced until `specs/006-quality-gate`'s traceability check lands. Consider also having `synthesize()` emit a coverage map over its **own** output, so the comment's table describes the artifact the human is approving (depends on T051)
- [X] T053 [P] Record in `harness/architect-agent/SKILL.md` and `docs/00-status.md` that SC-007 covers **only** the per-attempt correlation marker this feature lands — scoreable today — and that the approve/reject *decision capture* it enables needs `specs/005-pipeline-mode-signals-escalation/`'s gate and is therefore 005's to deliver. (SC-007 was narrowed to the correlation half precisely so this feature has no success criterion it cannot satisfy by construction; do not restate the old, wider claim.) Also record that this feature's own Eval-Gate score stays unreachable while `orchestration/activities.py::eval_gate_activity` resolves its spec via `sorted(glob("specs/*/spec.md"))[0]` (→ `001-agent-spec-schema-test` on any checkout of this repo) — the same inherited bug 003 flagged and did not fix (depends on T051)
- [X] T054 Run `uv run pytest` from repo root — the full suite, not just the new file. `tests/test_agent_spec_schema.py` fails unconditionally (it tests the deleted `spec/` schema, per `CLAUDE.md`); confirm `tests/test_pm_agent.py` still passes, which is the real check that T006's `conftest.py` change did not break 003's `import agent` path (depends on T049)
- [ ] T055 Run `quickstart.md`'s live tier against a **disposable** target repo with an open PR: confirm one comment with the plan, rationale, coverage table, and collapsed candidates; confirm `<spec_dir>/plan.md` + `tasks.md` are on the pushed branch and `git show --stat` shows **no** candidate plan committed (FR-011); then re-run the identical command and confirm no second comment and no new commit (depends on T050). **Not run in this pass** — no disposable target repo with an open PR and live GH_TOKEN/LiteLLM access was available in this environment; the full offline tier (T054, `uv run pytest tests/`) passed instead.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on T001; **blocks all three stories**. T006 additionally blocks every test task in the feature
- **US1 (Phase 3)**, **US2 (Phase 4)**, **US3 (Phase 5)**: all depend on Phase 2
- **Polish (Phase 6)**: depends on the stories you intend to ship

### Cross-Story Dependencies — read this before parallelizing

The three stories are independently *testable* but not fully independently *implementable*, because they compose one pipeline:

- **US2's T042** (`run_architect_stage`) calls US1's `generate_candidates` — the stage entrypoint cannot be finished before US1's fan-out exists.
- **US3's T049** extends T042 rather than adding a parallel path.
- US1 alone is genuinely standalone: `candidate_count`/`angles_for`/`generate_candidates` need nothing from US2 or US3.

So: US1 → US2 → US3 sequentially for the entrypoint, while each story's own capability functions and every test task can proceed in parallel.

### Within Each Story

Prompts and helpers before the functions that use them; capability functions before `run_architect_stage` wires them.

**On test ordering**: the `depends on T0NN` markers on test tasks name the implementation whose *interface* the test is written against, not a requirement that the implementation be finished first. Write each test before its named implementation and watch it fail; the dependency arrow exists so the test is not written against an interface that has not been agreed yet. (An earlier draft of this file stated a strict tests-first rule while every test task declared a dependency on the code it tests — those two cannot both hold, and this is the reading that survives.)

### Parallel Opportunities

- Phase 1: T002-T005 all `[P]`
- Phase 2: T008-T012 and T015/T016/T017a/T018/T019 all `[P]` (T006, T007, T013, T014, T017 are serial gates)
- Every test task in Phases 3-5 is `[P]` against the others — they are separate test functions in one file with no shared fixtures beyond `conftest.py`
- Phase 6: T051-T053a all `[P]`

---

## Parallel Example: User Story 1

```bash
# All US1 tests together (each a separate test function, all mocked):
Task: "test_candidate_count_properties in tests/test_architect_agent.py"
Task: "test_angles_for in tests/test_architect_agent.py"
Task: "test_generate_candidates_isolation in tests/test_architect_agent.py"
Task: "test_generate_candidates_scrubs_credentials_for_every_call in tests/test_architect_agent.py"
Task: "test_generate_candidate_tool_binding in tests/test_architect_agent.py"

# Then the two implementation tasks, in order (T027 before T028):
Task: "generate_candidate() + prompt constants in harness/architect-agent/agent.py"
Task: "candidate_count/angles_for/generate_candidates in harness/architect-agent/agent.py"
```

---

## Implementation Strategy

### MVP First (US1 only)

1. Phase 1 Setup → Phase 2 Foundational (T006 first — nothing testable without it)
2. Phase 3 US1
3. **STOP and VALIDATE**: `quickstart.md`'s Validate User Story 1 offline assertions

At this point there is a working, tested candidate panel and no synthesis — deliberately not shippable as a pipeline stage, since Build consumes exactly one `tasks.md`. US1 alone is an MVP for *verifying the fan-out design*, not for running the stage.

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. + US1 → fan-out verified in isolation
3. + US2 → **the first genuinely usable stage**: fan-out → score → synthesize → commit → post, minus the coverage check. This is the natural stopping point if scope needs cutting; `spec.md` marks US3 P2 for exactly this reason
4. + US3 → the coverage check the panel's adequacy claim rests on
5. Polish

### Deliberately Not In Any Phase

Per `plan.md`'s "Out of scope" — no `architect_stage_activity`, no `pipeline_workflow.py` step, no `plan_approved`/`plan_rejected` gate, no `MAX_PLAN_ATTEMPTS` enforcement, no `vibe` mode, no `pr_url` producer. If a task appears to need one of these, it is out of scope, not underspecified.

**Two of this feature's own requirements deliberately have no task here**, because they are budget rules and this module does not name `MAX_PLAN_ATTEMPTS`: **FR-010** (the gap round costs one plan attempt) and **FR-013a/FR-013b's charging halves** (a deterministic stage error costs one attempt, a transient one must not). All three are stated as CO-1, CO-2, and CO-2a in `contracts/architect-agent-interface.md`'s Consumer obligations and land as `specs/005-pipeline-mode-signals-escalation/`'s FR-014, per `spec.md`'s "Consumer obligations" subsection. A traceability pass over this file will flag them as uncovered; that is the intended reading, not a gap.

---

## Notes

- `[P]` = independent addition, no shared edit region with another incomplete task
- Every test task asserts a **structural** property (a tool binding, a prompt's contents, process env state, a validation rejection) rather than a model's output quality — that is what this feature's requirements actually are
- Commit after each task or logical group
- The three highest-value tests in the file are T017a (no token anywhere in the checkout), T024 (concurrent credential scrub) and T037 (scrub-window scope). All three fail under the obvious implementation and pass under the correct one; drop T024 or T037 and `research.md` Unknown 1's whole finding goes unverified, drop T017a and the credential-exfiltration path it guards is unverified — and that one ends in a token posted to a public PR comment
