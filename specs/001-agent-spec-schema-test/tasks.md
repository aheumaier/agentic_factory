---

description: "Task list for: Agent spec schema/template regression test"
---

# Tasks: Agent spec schema/template regression test

**Input**: Design documents from `/specs/001-agent-spec-schema-test/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md (no contracts/ — purely internal test, no external interface)

**Tests**: This feature's deliverable *is* a test file — there is no separate "tests for the test." T003 below is both the implementation and the test task.

**Organization**: Single user story (US1) — no Foundational phase needed beyond Setup.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Make `pytest tests/test_agent_spec_schema.py` runnable — repo has no root-level Python project yet.

- [X] T001 Create `pyproject.toml` at repo root declaring `pytest` and `pyyaml` as dependencies (per research.md's "Dependency declaration location" decision) — must not touch `harness/template-agent/pyproject.toml`
- [X] T002 [P] Create `tests/` directory at repo root (if it doesn't already exist)

**Checkpoint**: `uv sync` (or equivalent) succeeds and an empty `pytest` run discovers the `tests/` dir with no errors.

---

## Phase 2: User Story 1 - Catch schema/template drift automatically (Priority: P1) 🎯 MVP

**Goal**: One test file that fails loudly, with an itemized message, whenever `spec/schema/agent-spec.schema.json`'s required keys and `spec/templates/agent-spec.template.md`'s frontmatter drift apart.

**Independent Test**: Run `pytest tests/test_agent_spec_schema.py -v` — passes today; temporarily deleting a required key from the template's frontmatter (then reverting) makes it fail with that key named in the message.

### Implementation for User Story 1

- [X] T003 [US1] Write `tests/test_agent_spec_schema.py` in `tests/test_agent_spec_schema.py`:
  - Load `spec/schema/agent-spec.schema.json` via `json.load`; read its top-level `required` array.
  - Read `spec/templates/agent-spec.template.md`, split on `---` to extract the frontmatter block, parse it with `yaml.safe_load`.
  - Compute `missing = [k for k in schema["required"] if k not in frontmatter]`.
  - `assert not missing, f"Template frontmatter is missing schema-required key(s): {missing}"` (or equivalent itemized message) — satisfies spec FR-003/FR-005.
  - Do **not** call any JSON-Schema validator against the frontmatter's values — satisfies spec FR-004.
- [X] T004 [US1] Run `pytest tests/test_agent_spec_schema.py -v` and confirm it passes against the current schema/template pair (depends on T001, T002, T003)
- [X] T005 [US1] Manually verify the failure path per quickstart.md's "Validating the failure path" section: temporarily remove a required key from the template's frontmatter, rerun, confirm the itemized failure names that key, then revert with `git checkout -- spec/templates/agent-spec.template.md` (depends on T004)

**Checkpoint**: User Story 1 fully functional — this is the entire feature (single-story MVP).

---

## Phase 3: Polish & Cross-Cutting Concerns

- [X] T006 Run quickstart.md's "Run" section verbatim as a final sanity check (depends on T005)

---

## Dependencies & Execution Order

### Phase Dependencies
- **Setup (Phase 1)**: No dependencies — start immediately.
- **User Story 1 (Phase 2)**: Depends on Setup completion.
- **Polish (Phase 3)**: Depends on Phase 2 completion.

### Parallel Opportunities
- T001 and T002 can run in parallel (different files/dirs, no shared state).
- T003 has no parallel counterpart — it's the one deliverable file.

## Implementation Strategy

### MVP First (and only)
1. Complete Phase 1: Setup (T001–T002).
2. Complete Phase 2: User Story 1 (T003–T005) — this **is** the MVP; there is no further story.
3. Complete Phase 3: Polish (T006).
4. Open PR — no further increments planned for this feature.
