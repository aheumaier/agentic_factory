# Contract: Harness Hook Interface (010)

> Amended by `specs/012-dev-harness-followups/contracts/hook-interface.md` (launcher, AF-HOOKS, gate time limit, stop steps 1-5, matching rules).

The interface between Claude Code and this repo's hook scripts. Tests in
`tests/test_harness_hooks.py` are written against this contract.

## Wiring (`.claude/settings.json`)

| Event | Matcher | Command | Timeout |
|---|---|---|---|
| `UserPromptSubmit` | — | `"$CLAUDE_PROJECT_DIR"/.claude/hooks/py-check.sh turn-start` | 30 |
| `PostToolUse` | `Edit\|Write\|MultiEdit` | `… py-check.sh edit` | 60 |
| `Stop` | — | `… py-check.sh stop` | 300 |
| `PreToolUse` | `Edit\|Write\|MultiEdit\|NotebookEdit\|Read\|Grep\|Glob\|Bash` | `… policy.sh` | 300 |
| `SessionStart` | `compact\|clear` | `… session-context.sh` | 10 |

No `PreCompact` hook (FR-031).

`env`:

```json
{ "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "150000" }
```

The value MUST equal `CTX_BUDGET` in `lib.sh` (settings test). If the live check
(quickstart §6.1) shows it isn't honoured from project settings, it stays in place
harmlessly, and CLAUDE.md documents `claude --autocompact 150k` (FR-027).

`permissions`:

```json
{
  "deny": ["Read(/.env)", "Read(/.env.braintrust)"],
  "ask": [
    "Edit(/registry/agents/*/manifest.yaml)",
    "Edit(/registry/agents/*/versions/**)",
    "Edit(/.claude/settings.json)",
    "Edit(/.claude/settings.local.json)",
    "Edit(/.claude/hooks/**)"
  ]
}
```

## Inputs read from the payload (stdin JSON)

| Field | Used by |
|---|---|
| `session_id` | turn-start, stop, policy (exception marker), context-level marker |
| `transcript_path` | turn-start (context warn; read-only, tail only) |
| `source` | session-context (`compact` / `clear`; anything else → no output) |
| `stop_hook_active` | stop (loop guard) |
| `tool_name` | policy |
| `tool_input.file_path` / `.notebook_path` | edit, policy (AF-SPEC, AF-SECRET) |
| `tool_input.path`, `tool_input.pattern`, `tool_input.glob` | policy (AF-SECRET for Grep/Glob) |
| `tool_input.command` | policy (AF-SECRET, AF-COMMIT) |
| `tool_response.filePath` | edit (fallback) |

Environment: `CLAUDE_PROJECT_DIR` (falls back to the script's `../..`) and
`AF_SPEC_EXCEPTION`.

Paths outside `$CLAUDE_PROJECT_DIR` are ignored by every rule and check.

## Outputs

### Common

| Situation | Behaviour |
|---|---|
| `jq`, `git` or `uv` missing (`edit`, `stop`, `policy.sh`) | stderr `"<script>: <tool> is required"`, **exit 2** (fail closed; FR-009). `uv` is checked only on paths that run it |
| unknown mode | stderr, exit 1 |

### `py-check.sh turn-start`
**Always exit 0, including when a tool is missing or a write fails.** Under
`UserPromptSubmit`, exit 2 would block and erase the operator's prompt, which would
lock them out of the session. If the snapshot can't be written, none is pending, so
Stop falls back to HEAD (FR-010) and fails closed on its own.

**Stdout is either empty or exactly one valid JSON object.** Under UserPromptSubmit,
plain stdout would be injected into the model's context as raw text.

1. **Snapshot**: `resolve_snapshot` (data-model.md: prune, then adopt). If no
   snapshot results, write a fresh one.
2. **Context warn** (FR-028; data-model.md "Context budget"):
   `tail -n 200 "$transcript_path" | jq -R 'fromjson? | select(.type=="assistant" and (.isSidechain != true) and .message.usage)'`,
   take the last match, and sum the three token fields. Any failure → skip silently.
   When a notice is due, print:

```json
{"systemMessage": "[context] 131k of 150k budget (warn at 120k). /compact <focus> at the next task boundary, or /clear between tasks.",
 "hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
   "additionalContext": "Context is at 131k of the operator's 150k budget. Finish the current task, tick tasks.md, and write any undocumented decisions to the spec directory, then suggest /compact <focus> or /clear to the operator."}}
```

At the `budget` level the wording says `at or over the 150k budget`. Sizes are
rounded down to whole k.

### `py-check.sh edit`
- Non-`.py` file, or outside the project → exit 0.
- `ruff check --force-exclude --output-format concise <file>` via
  `uv run --frozen`. Red → stderr `ruff failed after editing <rel>:` + findings,
  **exit 2** (fed back to the model). **Never runs pytest** (FR-005).

### `py-check.sh stop`

> Steps 1-5 are replaced by 012's contract, "`stop`" (a red-twice turn keeps its snapshot, FR-013).

1. `resolve_snapshot` (adopts a pending snapshot if `session_id` changed mid-turn),
   then compute the changed set (snapshot, or the HEAD fallback). Empty → delete the
   snapshot, exit 0, no checks (FR-003).
2. `uv run --locked ruff check --force-exclude --output-format concise <lint set>`
   (skipped if the lint set is empty), then `run_suites`.
3. Green → delete the snapshot, exit 0.
4. Red, `stop_hook_active=false` → stderr
   `ruff/pytest gate is red for this turn's changes (<n> files) — fix before ending the turn:` + failures,
   **exit 2**, keep the snapshot.
5. Red, `stop_hook_active=true` → stdout
   `{"systemMessage": "ruff/pytest gate is still RED at end of turn: …"}`, delete the
   snapshot, exit 0 (FR-009 loop guard).

`run_suites` = `uv run --locked --directory <root> pytest tests/ -q --tb=short -rfE`
and `uv run --locked --directory <root>/orchestration pytest -q --tb=short -rfE`.
The failure text per suite is all `^(FAILED|ERROR) ` lines first, then the output
tail, ≤ 60 lines in total (FR-006).

### `policy.sh` (PreToolUse)
- No rule matched → exit 0 with no stdout (no decision; normal permission flow).
- Deny → exit 0 with stdout:

```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse",
  "permissionDecision": "deny",
  "permissionDecisionReason": "[AF-…] <rule sentence>. To proceed: <action>.\n<optional detail>"}}
```

- Exception notice (first bypassed AF-SPEC deny per session) → exit 0 with stdout
  `{"systemMessage": "[AF-SPEC] exception active for this session (AF_SPEC_EXCEPTION=<value>)."}`
  and no `permissionDecision`.

### `session-context.sh` (SessionStart, `compact|clear`)
**Always exit 0. Never blocks** (FR-029, FR-031). Missing `jq`/`git`, a `source`
other than `compact`/`clear`, a branch outside the FR-012 grammar, or no
`specs/<NNN>-*/` → no stdout. Otherwise:

```json
{"hookSpecificOutput": {"hookEventName": "SessionStart",
  "additionalContext": "<continuity block>"}}
```

Continuity block (fields per data-model.md "Continuity context"):

```text
[harness] Context was <compacted|cleared>. Resume from disk, not memory:
- branch: 010-dev-harness-hardening
- spec dir: specs/010-dev-harness-hardening/ (spec.md, plan.md, tasks.md)
- next tasks:
  - [ ] T024 [US2] Create `.claude/hooks/policy.sh` …
  - [ ] T025 …
  - [ ] T026 …
- turn gate: snapshot pending (this turn's changes will be checked at Stop) | clear
- policy rules: AF-SPEC AF-SECRET AF-COMMIT AF-REGISTRY AF-HARNESS (see CLAUDE.md)
```

Task lines are copied verbatim, each truncated to 160 characters.

## Rule messages (first line, exact prefixes)

| ID | First line |
|---|---|
| AF-SPEC | `[AF-SPEC] Code under harness/, orchestration/ and eval/ needs a planned feature: branch NNN-slug (or worktree-NNN-slug) with specs/NNN-*/tasks.md. To proceed: run /speckit-specify → /speckit-plan → /speckit-tasks and work on that feature's branch, or have the operator relaunch with AF_SPEC_EXCEPTION="<reason>".` |
| AF-SECRET | `[AF-SECRET] .env and .env.braintrust hold live credentials and are never read by the agent. To proceed: read .env.example for variable names and ask the operator for any value you need.` |
| AF-COMMIT | `[AF-COMMIT] Commits require ruff (whole repo) and both pytest suites to be green. To proceed: fix the failures below, then commit again.` followed by trimmed failures |

The detail after the first line in AF-SPEC names the observed branch and whether
`tasks.md` was found.

## Matching rules (normative)

- **AF-SPEC**: tool in the Edit family. `rel` = path relative to the project; it
  matches `^(harness|orchestration|eval)/`. Branch = `git symbolic-ref --short -q
  HEAD`; detached HEAD is treated as no branch. Pass iff the branch matches
  `^(worktree-)?([0-9]{3})-` **and** `specs/<NNN>-*/tasks.md` exists.
- **AF-SECRET**:
  - Read: basename of `file_path` ∈ {`.env`, `.env.braintrust`}.
  - Grep/Glob: same test on `path`, and on `pattern`/`glob` when the tool is Glob.
  - Bash: `command` matches
    `(^|[[:space:]/'"=<])\.env(\.braintrust)?($|[[:space:];|&)'"<>*?[{])`, so
    `cat .env*` and `cat .env{,.braintrust}` match too.
  - `.env.example` never matches.
- **AF-COMMIT**: Bash `command` contains `(^|[^[:alnum:]_.-])git($|[^[:alnum:]_.-])`
  **and** `(^|[^[:alnum:]_.-])commit($|[^[:alnum:]_.-])`. On a match, run whole-repo
  `uv run --locked ruff check --output-format concise .` and `run_suites`. False
  positives are accepted; false negatives are not.
