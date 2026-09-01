# Quickstart: Agent spec schema/template regression test

## Prerequisites
- Python 3.11+
- `uv` (already installed on the reference dev machine) or a plain `venv`
  + `pip`

## Setup
```bash
cd agentic_factory
uv sync           # or: python3 -m venv .venv && .venv/bin/pip install -e .
```

## Run
```bash
uv run pytest tests/test_agent_spec_schema.py -v
# or, without uv:
.venv/bin/pytest tests/test_agent_spec_schema.py -v
```

## Expected outcome
- Exits 0; one test passes, confirming every key in
  `spec/schema/agent-spec.schema.json`'s `required` array is present in
  `spec/templates/agent-spec.template.md`'s frontmatter (see
  [data-model.md](./data-model.md)).

## Validating the failure path (manual, not part of CI)
```bash
# Temporarily remove a required key (e.g. "owner:") from the template's
# frontmatter, rerun the test, observe an itemized failure naming "owner",
# then revert the temporary edit (git checkout -- spec/templates/agent-spec.template.md).
```
