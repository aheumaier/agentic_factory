# Quickstart: Validating Dev-Harness Hardening (010)

These validation scenarios show the feature works. The automated proof is the two
new test modules. The manual scenarios repeat the spec's Independent Tests against a
live Claude Code session. Hook I/O is specified in `contracts/hook-interface.md`
and drift grammar in `contracts/drift-conventions.md`. Neither is restated here.

## Prerequisites

- Claude Code with this repo's project settings, plus `jq`, `uv` (0.10.0) and `git`
  on `PATH`.
- Run from a dedicated worktree (one session per worktree, FR-011).
- `make up` is optional. Without Temporal, the `temporal`-marked tests skip.

## 1. Automated (CI-equivalent)

```bash
uv run --locked pytest tests/ -q                       # includes test_harness_hooks.py + test_context_drift.py
(cd orchestration && uv run --locked pytest -q)        # unchanged behaviour; temporal tests skip if server down
(cd orchestration && uv run --locked pytest -q -m "not temporal")   # FR-008: group is selectable
uv run --locked ruff check .
```

Expected: all green.

- `test_harness_hooks.py` has an allow test and a refuse test for AF-SPEC,
  AF-SECRET and AF-COMMIT (SC-004). Every refusal asserts `[AF-…]` and
  `To proceed:` (SC-005). For the `permissions.ask` rules (AF-REGISTRY,
  AF-HARNESS) it checks that the patterns are present in `settings.json` and match
  the right paths. The prompt itself can only be verified live (§3.5–3.6).
- `test_context_drift.py` passes on the tree (SC-006).
- US4 in `test_harness_hooks.py`:
  - **Warn (SC-008)**, using fixture transcripts with synthetic `usage`: one notice
    at the first crossing of each level, none on a repeat, re-armed after a below-warn
    reading, and silent on a missing, malformed or partial last line. Exit 0 and
    valid-JSON-or-empty stdout in every case.
  - **Adoption (SC-010)**: after a `session_id` change, at turn-start and at stop;
    prune before adopt for files over 7 days old; multiple pending files.
  - **`session-context.sh` (SC-009)**: output on a feature branch with a
    `tasks.md`; nothing off-branch or for `source: "startup"`.
  - **Settings**: SessionStart wiring is present, and
    `env.CLAUDE_CODE_AUTO_COMPACT_WINDOW` equals `CTX_BUDGET`.

### Scratch clone for hand-run hook checks

The hooks keep their state in the repo's own git dir. With FR-001 adoption, a
`turn-start` or `stop` run by hand with a made-up `session_id` would **take over
the live session's pending snapshot** and delete the others (data-model.md
"Resolve step"). So every hand-run `py-check.sh` check, including T011, T033 and
the lockfile check below, runs against a scratch clone that has its own git dir:

```bash
SMOKE="$SCRATCH/smoke"   # SCRATCH = the session scratchpad dir
rm -rf "$SMOKE" && git clone -q -b "$(git branch --show-current)" . "$SMOKE"
rsync -a --exclude .git --exclude .venv --exclude node_modules \
      --exclude .env --exclude .env.braintrust ./ "$SMOKE"/   # carry uncommitted work, never secrets
export CLAUDE_PROJECT_DIR="$SMOKE"
(cd "$SMOKE" && uv sync --locked -q && (cd orchestration && uv sync --locked -q))   # warm the venvs once
```

Then run the hooks as `"$SMOKE"/.claude/hooks/<script>` from inside `$SMOKE`.
`policy.sh` and `session-context.sh` never touch `turn-*.tsv`, so they're safe in
the live tree too. The scratch clone keeps them consistent with everything else.

**Lockfile invariance (SC-007)**, in the scratch clone:

```bash
cd "$SMOKE"
shasum uv.lock orchestration/uv.lock > "$SCRATCH/before"
echo '{"session_id":"qs","stop_hook_active":false}' | .claude/hooks/py-check.sh stop
echo '{"tool_name":"Bash","tool_input":{"command":"git commit --dry-run"}}' | .claude/hooks/policy.sh
shasum -c "$SCRATCH/before"          # both OK
```

The clone's lockfiles are byte-copies of the worktree's (`rsync`). So invariance
there proves that the gates don't rewrite them, without risking the live session's
snapshot.

## 2. Story 1: turn-scoped gate (live session)

| Step | Action | Expected |
|---|---|---|
| 1 | Outside the session, append `import os` (unused) to an untouched `.py` file. Start a turn and ask for a lint-clean edit to a different `.py` file | Turn ends unblocked; the pre-existing F401 isn't reported (SC-001) |
| 2 | New turn: "use `printf` in Bash to add `x = undefined_name` to `harness/template-agent/agent.py`" | Turn is blocked at Stop, and feedback names that file and `F821` (SC-002) |
| 3 | Leave it red and let the agent try to stop again | Turn ends; operator sees "gate is still RED" |
| 4 | Turn that only edits `pyproject.toml` (e.g. a comment) | Lint + suites run at Stop |
| 5 | Turn that edits only a Markdown file | Stop returns instantly, no checks |
| 6 | Watch an edit-tool `.py` change | Only ruff runs, under 2s, no pytest output (SC-003) |

Revert the step 1/2 edits afterwards.

## 3. Story 2: policy (live session)

| Step | Action | Expected |
|---|---|---|
| 1 | `git switch -c scratch-nospec`, then ask the agent to edit `harness/template-agent/agent.py` | Refused with `[AF-SPEC] … To proceed: …` |
| 2 | Same request on `010-dev-harness-hardening` (has `specs/010-*/tasks.md`) | Proceeds |
| 3 | With a failing test in the tree, ask the agent to commit | Refused with `[AF-COMMIT]` + trimmed failure |
| 4 | Ask it to read `.env`, then `cat .env`, then read `.env.example` | First two refused (`[AF-SECRET]`), third succeeds |
| 5 | Ask it to edit `registry/agents/swe-agent/manifest.yaml` (auto mode on) | Claude Code permission prompt appears |
| 6 | Ask it to edit `.claude/hooks/py-check.sh` | Permission prompt (AF-HARNESS) |
| 7 | Relaunch with `AF_SPEC_EXCEPTION="quickstart" claude` on `scratch-nospec`, repeat step 1 twice | Proceeds; one "exception active" notice on the first edit only |

Delete `scratch-nospec` afterwards.

## 4. Story 3: drift (manual injection)

Each injection must make `uv run --locked pytest tests/test_context_drift.py -q` fail with
`file:line` and the token. Revert each one before the next.

1. In CLAUDE.md, change "three entries" to "two entries" → `[D-REG]`.
2. In CLAUDE.md, add a reference to `specs/099-nope` → `[D-SPEC]`.
3. In the reviewer prompt, rename `_validate_target` to `_validate_targets`, which
   no code defines → `[D-ID] _validate_targets`.
4. Remove `(pending 009)` after `seat_guard.py` in the reviewer prompt → `[D-ID]`.

## 5. Sandbox parity (FR-025)

```bash
docker build -t swe-agent-sandbox-check -f sandbox/swe-agent/Dockerfile .   # context is the repo root
docker run --rm swe-agent-sandbox-check sh -c 'jq --version && uv --version'   # uv 0.10.0
docker rmi swe-agent-sandbox-check
```

## 6. Story 4: context budget and continuity (live session)

| Step | Action | Expected |
|---|---|---|
| 1 | **Cap (FR-027).** Fresh session in the worktree. Work until a compaction fires on its own, or until `/context` shows the size approaching 150k | Auto-compaction fires at or before about 150k, not near the model's full window. **If it doesn't**, the project `env` key isn't honoured: relaunch with `claude --autocompact 150k`, confirm that works, and record the fallback in CLAUDE.md (FR-027) |
| 2 | **Warn (FR-028).** Continue a session past 120k (or use step 1's session) and submit a prompt | One `[context] …k of 150k budget …` notice. The agent acknowledges it and persists its state. The next prompt shows no notice |
| 3 | **Continuity (FR-029).** On `010-dev-harness-hardening`, run `/clear`, then ask "what's next?" | The agent names the branch, `specs/010-dev-harness-hardening/` and the first unchecked task without reading files first |
| 4 | Same as step 3, but on `main` | Nothing injected; the agent has no feature context |
| 5 | **Adoption (FR-001, SC-010).** Start a turn that edits a `.py` file to fail lint, press Esc before it ends, run `/clear`, then send "say hi" | The new turn's Stop is blocked, naming the edited file. The interrupted edit wasn't lost from the baseline |

Step 5 also settles research R3's *[unverified]* "does Stop fire on Esc?". If the
gate blocks right at Esc, Stop fires and adoption wasn't needed. Either outcome
passes, but record which one happened in research.md. Revert step 5's edit
afterwards.
