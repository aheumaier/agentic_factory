# Research: Agent spec schema/template regression test

## Decision: Dependency declaration location

**Decision**: Add a new, minimal `pyproject.toml` at the repo root declaring
`pytest` and `pyyaml` as dependencies (dev-only), rather than reusing or
modifying `harness/template-agent/pyproject.toml`.

**Rationale**: The repo has no root-level Python project today
(`CLAUDE.md` confirms this explicitly). `harness/template-agent/`'s
`pyproject.toml` is a separate, unrelated agent package (`claude-agent-sdk`,
`openai`) — piggybacking this test's deps onto it would couple an
unrelated package's dependency set to a repo-wide test. A root
`pyproject.toml` is the natural home for repo-wide tests going forward.

**Alternatives considered**:
- Modify `harness/template-agent/pyproject.toml` to add test deps —
  rejected: couples unrelated concerns, and the test needs to run from the
  repo root against `spec/`, not from inside `harness/template-agent/`.
- A bare `requirements-test.txt` with no `pyproject.toml` — works, but a
  `pyproject.toml` is more idiomatic for `pytest`/`uv` discovery and this
  machine already has `uv` installed (`uv run pytest` "just works" against
  a `pyproject.toml`).

## Decision: No `jsonschema` library dependency

**Decision**: Validate only structural key-presence (schema's `required`
array vs. template frontmatter keys) using plain `json.load` +
`PyYAML.safe_load`, no `jsonschema` library.

**Rationale**: Spec FR-004 explicitly excludes full schema validation
(the template's placeholder values like `tools: []` are legitimately
incomplete and would fail full validation). A dependency that would only
ever be used for a check the spec says not to do isn't needed.

**Alternatives considered**:
- `jsonschema` library with a custom draft-07 validator restricted to
  presence checks — rejected as unnecessary complexity/dependency for a
  set-comparison that's a few lines of stdlib code.

## Decision: Frontmatter extraction approach

**Decision**: Extract the YAML frontmatter by splitting
`agent-spec.template.md` on the `---` delimiters (first two occurrences)
and parsing the middle block with `yaml.safe_load`.

**Rationale**: The template file's frontmatter is a standard
`---\n...\n---\n` block (confirmed by reading the file directly) — no
Markdown-frontmatter library is warranted for one file with a fixed,
simple format.

**Alternatives considered**:
- A dedicated frontmatter-parsing library (e.g. `python-frontmatter`) —
  rejected: one more dependency for a two-line split-and-parse.

## Open items

None — no `[NEEDS CLARIFICATION]` markers remain from the spec, and every
Technical Context field in plan.md is resolved.
