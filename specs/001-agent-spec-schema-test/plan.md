# Implementation Plan: Agent spec schema/template regression test

**Branch**: `001-agent-spec-schema-test` | **Date**: 2026-09-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-agent-spec-schema-test/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Add one regression test, `tests/test_agent_spec_schema.py`, that loads
`spec/schema/agent-spec.schema.json`'s top-level `required` array and
asserts every one of those keys is present in
`spec/templates/agent-spec.template.md`'s YAML frontmatter. No schema or
template changes are expected — this repo has no root-level Python
project yet, so the technical work is mostly minimal `pytest` plumbing
(dependency declaration + one test file), not application logic.

## Technical Context

**Language/Version**: Python 3.11+ (matches `harness/template-agent/pyproject.toml`'s `requires-python`; no repo-root Python version pin exists yet, this test doesn't need one beyond 3.11+).

**Primary Dependencies**: `pytest` (test runner), `PyYAML` (parse the template's frontmatter). Both confirmed **not** currently installed in this environment and no root `pyproject.toml`/`requirements.txt` exists — this feature must add minimal plumbing for both. No `jsonschema` dependency: FR-004 requires structural key-presence checking only, not full schema validation, so a plain `json.load` + `set` comparison against the schema's `required` array is sufficient and avoids adding a library beyond what's needed.

**Storage**: N/A (reads two static repo files).

**Testing**: `pytest`, run via `uv run pytest` (this machine has `uv` installed) or plain `pytest` if a venv is set up — implementer's choice, either must work with a bare `pytest tests/test_agent_spec_schema.py` invocation per spec FR-006.

**Target Platform**: Local dev machine + CI (GitHub Actions, `.github/workflows/`), Linux/macOS.

**Project Type**: Single project — one test file added to a new `tests/` directory at repo root; no CLI/service/library surface is created.

**Performance Goals**: N/A (SC-001 caps runtime at <1s; trivially met — two small local file reads and a key-presence check).

**Constraints**: No network access at test time (FR-006). Must not require full schema validation of the template's intentionally-incomplete placeholder values (FR-004).

**Scale/Scope**: One test file, one new minimal dependency-declaration file (e.g. `pyproject.toml` at repo root or scoped test config) — smallest change that makes `pytest tests/test_agent_spec_schema.py` runnable and green.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is still the unfilled template scaffold
(placeholder principle names/descriptions, no ratified version) — no
project-specific principles are yet defined to gate against. Treated as
**no gates apply**; nothing to check or re-check post-design.

## Project Structure

### Documentation (this feature)

```text
specs/001-agent-spec-schema-test/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

No `contracts/` — this feature exposes no API/CLI/UI surface to document;
it's a single internal test file (see Phase 1 rule: skip contracts for
purely internal build/test tooling).

### Source Code (repository root)

```text
tests/
└── test_agent_spec_schema.py   # the one new file this feature adds

pyproject.toml                  # NEW at repo root (or scoped test-runner
                                 # config) — declares pytest + PyYAML so
                                 # `pytest tests/test_agent_spec_schema.py`
                                 # is runnable; repo currently has no
                                 # root-level Python project (only
                                 # harness/template-agent/pyproject.toml,
                                 # which is a different, unrelated package)
```

**Structure Decision**: Single project, smallest possible footprint — one
test file plus whatever minimal dependency-declaration file makes it
runnable. No `src/` layer is needed since this feature adds a test, not
application code.

## Complexity Tracking

*No constitution gates apply (see Constitution Check above) — nothing to justify here.*
