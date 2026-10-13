# Contract: Context-Drift Conventions (010)

> Amended by `specs/012-dev-harness-followups/contracts/drift-conventions.md` (extractor rules as shipped, D-ID corpus, Stop coverage).

How facts in the always-loaded context files must be written so that
`tests/test_context_drift.py` can check them, and what the test does with each.
The authors of `CLAUDE.md` and `.claude/agents/py-codereviewer.md` are bound by
this contract.

## Files in scope

| File | Families checked |
|---|---|
| `CLAUDE.md` | D-REG, D-SPEC |
| `.claude/agents/py-codereviewer.md` | D-SPEC, D-ID |

`eval/gate-policy.md` is corrected once (FR-023(e)) but is not drift-checked.

## D-REG: registry entries (CLAUDE.md)

1. **Path refs**: every `registry/agents/<name>` (where `<name>` matches
   `[a-z0-9][a-z0-9-]*`; placeholders like `<name>`/`<agent_name>` and globs are
   skipped) must be a directory.
2. **Brace lists**: `registry/agents/{a,b,c}` must list **exactly** the directories
   present. To mention a subset, write separate paths.
3. **Counts**: a number word `one|two|three|four|five|six|seven|eight|nine|ten`
   directly followed by `entries` or `entry`, inside a sentence (split on `.` + space
   or a blank line) that also contains `registry/agents`, must equal the directory
   count.

## D-SPEC: spec directory paths (both files)

- Every match of `specs/(\d{3}-[a-z0-9][a-z0-9-]*)` must be a directory under
  `specs/`. The literal placeholder `specs/NNN-slug` doesn't match (not digits).
- **In-flight features are referenced by number only**: "feature 009 (credential
  pool, unmerged)", never `specs/009-…`, until that directory exists on this tree.

## D-ID: code identifiers (reviewer prompt)

Candidates are the contents of single-backtick spans. Within a span, each
whitespace/comma/slash-separated token is classified:

| Class | Pattern | Check |
|---|---|---|
| private name | `^_[A-Za-z0-9_]+(\(\))?$` | word-boundary match in some `*.py` |
| constant / env name | `^[A-Z][A-Z0-9]*(_[A-Z0-9]+)+$` | word-boundary match in some `*.py` |
| env-name wildcard | `^[A-Z][A-Z0-9_]*_\*$` (e.g. `ANTHROPIC_*`, `CLAUDE_OAUTH_SEAT_*`) | some `*.py` contains the prefix before `*` |
| file name | `^[\w.-]+\.(py\|yaml\|toml)$` | some file with that basename exists |
| repo path | contains `/` and starts with a top-level dir that exists | the path exists. Tokens containing glob chars (`*?[`) or `<…>` placeholders are skipped |
| anything else | dotted names (`workflow.now()`), plain words, flags | **not checked** |

The search space is the repo tree excluding `specs/`, `.claude/`, `.specify/`,
`.git/`, `**/.venv/` and `node_modules/`. **Tests are included** (`_connect_or_skip`
lives only in tests).

## Conditional marker (FR-021)

```
`seat_guard.py` (pending 009)
`CLAUDE_OAUTH_SEAT_*` (pending 009)
```

- Grammar: a backtick span immediately followed by optional spaces and then
  `(pending NNN)`, where `NNN` is three digits. It applies to every token in that
  span.
- A pending token whose check **fails** passes, because the work is in flight.
- A pending token whose check **passes** fails with: `<file>:<line>: <token> now
  exists; remove the "(pending NNN)" marker`.

## Failure message (FR-022)

```
<file>:<line>: [D-ID] `<token>` not found in repo code (expected: a definition or use in *.py outside specs/ and .claude/)
<file>:<line>: [D-REG] "two entries" but registry/agents/ has 3: architect-agent, pm-agent, swe-agent
<file>:<line>: [D-SPEC] specs/008-foo does not exist
```

The test collects all violations and fails once, listing all of them.
