# Feature Specification: Agent spec schema/template regression test

**Feature Branch**: `001-agent-spec-schema-test`

**Created**: 2026-09-01

**Status**: Draft

**Input**: User description: "Add pytest test validating agent-spec schema against template frontmatter. `spec/schema/agent-spec.schema.json` (JSON Schema, draft-07) defines the required shape of an agent spec. `spec/templates/agent-spec.template.md` is the human-facing template authors copy to write a new spec — its YAML frontmatter (`name`, `owner`, `tools`, `success_criteria`) is meant to be a valid starting point against that schema, but nothing currently checks that the two stay in sync as either evolves. Add `tests/test_agent_spec_schema.py` that loads the schema, extracts the template's frontmatter, and asserts structural/key-presence alignment (not full semantic validity, since placeholders like `tools: []` are legitimately empty), failing with a clear itemized message naming exactly which required key(s) are missing. Out of scope: full schema validation of a real filled-in spec; changing the schema/template unless a genuine mismatch is found. Issue: https://github.com/aheumaier/agentic_factory/issues/1"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Catch schema/template drift automatically (Priority: P1)

A maintainer changes `spec/schema/agent-spec.schema.json` (e.g. adds a new
required top-level key) or edits `spec/templates/agent-spec.template.md`'s
frontmatter, without realizing the other file now needs a matching update.
Today nothing catches this — the drift is silent until a real agent spec
authored from the template fails validation downstream. A regression test
makes this an immediate, itemized local/CI failure instead.

**Why this priority**: This is the only story in this feature — it *is*
the deliverable. Without it, there is no automated check at all.

**Independent Test**: Run `pytest tests/test_agent_spec_schema.py` — it
passes today (template and schema currently agree on required keys) and
can be independently proven to fail-with-a-clear-message by temporarily
removing a required key from the template's frontmatter in a throwaway
edit, observing the itemized failure, then reverting.

**Acceptance Scenarios**:

1. **Given** the schema's required top-level keys and the template's
   current frontmatter, **When** the test runs, **Then** it passes because
   every schema-required key that the template is expected to carry as a
   placeholder is present in the frontmatter.
2. **Given** a required key is removed from the template's frontmatter
   (drift introduced), **When** the test runs, **Then** it fails with a
   message that itemizes exactly which required key(s) are missing —
   not a generic "invalid" or raw jsonschema traceback.
3. **Given** the template's frontmatter as-is (placeholder values like
   `tools: []`, `success_criteria: []`), **When** the test runs,
   **Then** it does not attempt full schema validation of those
   placeholder values (which would legitimately fail on emptiness) — only
   structural/key-presence alignment.

### Edge Cases

- What happens when the template's frontmatter is missing or fails to
  parse as YAML? The test must fail with a clear message pointing at the
  parse failure, not an unrelated assertion error.
- What happens when the schema itself is missing a `required` array or it
  is empty? The test should still run meaningfully (e.g., report "no
  required keys declared") rather than silently passing on a vacuous
  check.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A new test module `tests/test_agent_spec_schema.py` MUST
  load `spec/schema/agent-spec.schema.json` as JSON.
- **FR-002**: The test MUST extract the YAML frontmatter block (the
  `---`-delimited header) from `spec/templates/agent-spec.template.md`.
- **FR-003**: The test MUST assert that every key listed in the schema's
  top-level `required` array is present as a key in the template's
  frontmatter.
- **FR-004**: The test MUST NOT assert full JSON-Schema validity of the
  template's frontmatter values (placeholders such as `tools: []` are
  expected to be structurally present but semantically incomplete).
- **FR-005**: On failure, the test MUST report the specific missing
  key(s) by name, not a generic pass/fail or raw library exception.
- **FR-006**: The test MUST be runnable via a standard `pytest` invocation
  with no network access and no fixtures beyond the two files above.

### Key Entities

- **Agent spec schema**: `spec/schema/agent-spec.schema.json` — JSON
  Schema (draft-07) declaring required top-level keys for a valid agent
  spec (`name`, `owner`, `goal`, `tools`, `guardrails`,
  `success_criteria`).
- **Agent spec template**: `spec/templates/agent-spec.template.md` — the
  Markdown template with YAML frontmatter that authors copy to start a new
  spec; frontmatter today declares `name`, `owner`, `tools`,
  `success_criteria` as placeholders.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Running `pytest tests/test_agent_spec_schema.py` locally or
  in CI completes in under 1 second and exits 0 against the current
  schema/template pair.
- **SC-002**: Deliberately removing any one schema-required key from the
  template's frontmatter causes the test to fail, and the failure message
  names that exact key.
- **SC-003**: No changes to `spec/schema/agent-spec.schema.json` or
  `spec/templates/agent-spec.template.md` are made unless the test
  reveals a genuine, pre-existing mismatch between them.

## Assumptions

- The schema's top-level `required` array is the authoritative list of
  keys the template's frontmatter is expected to carry (as placeholders,
  not filled-in values).
- `tools` and `success_criteria` in the template frontmatter being empty
  arrays (`[]`) is intentional placeholder state, not a defect this test
  should flag.
- No test framework beyond `pytest` and a YAML parser (e.g. `PyYAML`,
  likely already resolvable in this environment) is required; if `PyYAML`
  is not already a dependency anywhere in the repo, adding it is
  in-scope and must be flagged in the implementing PR's description per
  this repo's own guardrail (`prompts/agentic-swe.json`: "never silently"
  add a dependency).
- This repo currently has no root-level Python project/test runner
  configured (per `CLAUDE.md`) — the implementing change may need to add
  minimal `pytest` plumbing (e.g. a `pyproject.toml` or `pytest.ini` at the
  repo root, or scoped to `tests/`) as part of making this test runnable;
  that plumbing is in-scope as long as it's the minimum needed to run this
  one test file.
