# Data Model: Agent spec schema/template regression test

No persistent or runtime data model — this feature reads two static
repository files at test time. Documented here as the two "entities" the
test reasons about, per spec's Key Entities section.

## Entities

### Agent spec schema (`spec/schema/agent-spec.schema.json`)
- **Represents**: JSON Schema (draft-07) declaring the required shape of
  any agent spec.
- **Field the test reads**: top-level `required` array (list of key
  names, e.g. `["name", "owner", "goal", "tools", "guardrails", "success_criteria"]`).
- **Validation rule this test enforces**: every name in this array must
  also appear as a key in the template's frontmatter (see below) — this
  is the one relationship this test checks.

### Agent spec template frontmatter (`spec/templates/agent-spec.template.md`)
- **Represents**: the YAML frontmatter block (delimited by `---`) at the
  top of the human-facing spec template.
- **Fields today**: `name`, `owner`, `tools` (`[]`), `success_criteria`
  (`[]`) — placeholders, not filled-in values.
- **Validation rule this test enforces**: must contain, as keys, every
  entry from the schema's `required` array (values are not checked —
  only key presence, per spec FR-004).

## State transitions

None — both inputs are static files read once per test run; there is no
mutation or multi-step state machine.
