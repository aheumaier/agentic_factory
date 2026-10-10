# Data Model: Dev-Harness Hardening (010)

There's no database. The "entities" are small on-disk state files the hooks keep,
the rule catalogue, and the facts the drift test asserts. All hook state lives in
the per-worktree **state dir** `$(git rev-parse --git-path claude-harness)/`
(research R3). It is never committed.

---

## Turn snapshot

The baseline used to tell which Python-relevant files *this turn* changed.

| Field | Type | Notes |
|---|---|---|
| file name | `turn-<session_id>.tsv` | `session_id` from the hook payload, sanitised to `[A-Za-z0-9_-]`, or `nosession` |
| lines | `<blob-sha>\t<repo-relative path>` | one per file matching `*.py`, `*pyproject.toml` or `*uv.lock` that is tracked or untracked, not ignored, and present on disk |
| order | byte-sorted (`LC_ALL=C sort`) | needed by `comm` |

**Validation**: a file that is unreadable, empty while files exist on disk, or has
malformed lines counts as *missing*, so the gate falls back to HEAD (FR-010).

**Resolve step** (`resolve_snapshot` in `lib.sh`, run first by both `turn-start` and
`stop`; research R14):

1. Own file `turn-<own id>.tsv` exists → use it. Done. Other sessions' pending files
   are deliberately left alone here, neither pruned nor deleted. That state arises
   only after a mid-turn `session_id` change. A leftover file is adopted on a later
   turn as a wider baseline, or pruned once it's older than 7 days. Both fail toward
   checking more (tasks.md T014(e) pins this).
2. Delete every other `turn-*.tsv` older than 7 days (**prune before adopt**).
3. If any other `turn-*.tsv` remains, rename the **oldest** (mtime) to the own key,
   which is the widest baseline. Delete the rest, which it supersedes. → own file
   now PENDING.
4. Nothing remains: no snapshot. turn-start takes a fresh one, and stop falls back to
   HEAD (FR-010).

**State transitions** (per worktree; FR-011 makes "other session" mean an earlier
session, e.g. before `/clear`):

```
            UserPromptSubmit                 Stop: no change / green / still-red notice
 (none) ─────────────────────▶ PENDING ───────────────────────────────────────────▶ (none)
   ▲     (resolve found none)     │  ▲
   │                              │  │ Stop: red, first block (stop_hook_active=false)
   │                              └──┘ (kept; retry compares against same baseline)
   │   UserPromptSubmit while own PENDING → no-op (FR-001: mid-turn message)
   │
 PENDING(other session, ≤ 7 days) ──resolve (turn-start or stop)──▶ PENDING(own)   [adopt]
 PENDING(other session, > 7 days) ──resolve──▶ (deleted)                            [prune]
```

Prune-before-adopt is deliberate. A snapshot older than a week predates edits the
operator made outside any session, so adopting it would falsely block a clean turn
(SC-001). AF-COMMIT backstops the rare interrupted turn that ages out.

**Derived: changed set** = paths in `comm -3 <snapshot> <current>`, which is
everything added, modified or deleted. From it:
- **lint set** = changed paths ending `.py` that still exist;
- **run suites** = changed set non-empty (FR-003/FR-004).

## Policy rule

A named, deterministic check. The catalogue is fixed in code (`policy.sh`) and in
`.claude/settings.json` `permissions`, and documented in CLAUDE.md.

| Field | Values |
|---|---|
| `id` | `AF-SPEC`, `AF-SECRET`, `AF-COMMIT`, `AF-REGISTRY`, `AF-HARNESS` (stable; tests and docs key on them) |
| `mechanism` | `hook` (policy.sh, PreToolUse) · `permission` (`permissions.ask`/`deny`) |
| `scope.tools` | subset of `Edit Write MultiEdit NotebookEdit Read Grep Glob Bash` |
| `scope.match` | path prefix, path glob, or command regex (research R8) |
| `verdict` | `deny` (hook) · `ask` (permission rule) · none (falls through) |
| `reason` | one sentence |
| `remediation` | the concrete action that satisfies the rule |

**Evaluation order in policy.sh** (first deny wins, otherwise no decision):
AF-SECRET → AF-SPEC → AF-COMMIT. The cheap path checks run before the expensive
commit gate, so a `cat .env && git commit` is refused for the secret without running
the suites.

**Validation**: every hook deny message matches
`^\[AF-[A-Z]+\] .+\. To proceed: .+$` on its first line (FR-017, SC-005). Further
lines may carry trimmed failures (AF-COMMIT).

## Spec-rule exception

| Field | Notes |
|---|---|
| source | env var `AF_SPEC_EXCEPTION` in Claude Code's launch environment; active iff non-empty; value = free-text reason |
| scope | AF-SPEC only. Never consulted by AF-SECRET or AF-COMMIT (FR-018) |
| notice marker | `exception-<session_id>.notified` in the state dir; created the first time the exception turns a would-be deny into an allow |

**States**: `inactive` → (env set at launch) `active-unannounced` → (first bypassed
AF-SPEC deny: `systemMessage` emitted, marker written) `active-announced`.

## Drift assertion

One fact claimed in a context file, paired with the tree check that confirms it.
Defined fully in `contracts/drift-conventions.md`.

| Field | Notes |
|---|---|
| `family` | `D-REG` · `D-SPEC` · `D-ID` |
| `source` | `CLAUDE.md` or `.claude/agents/py-codereviewer.md`, with line number |
| `token` | the extracted text (`registry/agents/{…}`, `three entries`, `specs/004-…`, `_scrubbed()`, `seat_guard.py`) |
| `conditional` | true iff followed by `(pending NNN)` |
| `check` | existence or equality against the tree |
| `expected` | what the tree shows (the dir set, the count, "exists") |

**Rules**:
- A failure reports `source:line`, `token` and `expected` (FR-022).
- `conditional` + check fails → pass (in-flight).
- `conditional` + check passes → **fail** (stale marker; remove it).
- **Path reference** (`specs/009-…`) vs **number reference** ("feature 009"): only
  path references are checked. In-flight features MUST be referenced by number
  (FR-023(d)).

## Context budget (US4)

| Field | Notes |
|---|---|
| `CTX_BUDGET` | `150000`, a constant in `lib.sh`. It's the single source of truth: a settings test asserts `env.CLAUDE_CODE_AUTO_COMPACT_WINDOW` equals it (FR-027) |
| `CTX_WARN` | `120000`, a constant in `lib.sh` (FR-028) |
| reading | `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` from the last `type=="assistant"`, non-sidechain entry with `.message.usage` in the last 200 lines of `transcript_path`. Absent or invalid → *unknown* |
| level | `none` (< WARN) · `warn` (≥ WARN, < BUDGET) · `budget` (≥ BUDGET) |
| marker | `ctx-<session_id>.level` in the state dir. It holds the highest level already announced (`warn` or `budget`) |

**Transitions at turn-start** (all exit 0; at most one notice per prompt):

```
 reading unknown                    → nothing (marker untouched)
 level none                         → delete marker (re-arm after compaction); nothing
 level > marker (or no marker)      → emit notice for level; marker := level
 level ≤ marker                     → nothing
```

Example: 125k emits a `warn` notice. 140k is silent. 152k emits a `budget` notice.
After compaction, 40k deletes the marker. 121k emits a `warn` notice again.

**Re-arm likely lags compaction by one prompt.** The first UserPromptSubmit after a
compaction probably still sees the pre-compaction assistant entry as the last one,
so it reads high, stays silent and leaves the marker alone. Re-arm happens on the
next prompt, once a post-compaction reply exists. This is benign. Tests MUST NOT
expect re-arm on the very first post-compaction prompt.

## Continuity context (US4)

Produced by `session-context.sh` on `SessionStart` with `source` ∈ {`compact`,
`clear`}. It's never stored, only emitted.

| Field | Source |
|---|---|
| branch | `git symbolic-ref --short -q HEAD` |
| spec dir | `feature_spec_dir`: the branch's NNN from `^(worktree-)?([0-9]{3})-`, then the first sorted `specs/<NNN>-*/`. **Not** `.specify/feature.json`, which can be stale |
| next tasks | the first 3 lines matching `^- \[ \] T[0-9]+` in `<spec dir>/tasks.md`, or "no tasks.md" |
| gate | `pending` if any `turn-*.tsv` is in the state dir, else `clear` |
| rules | the fixed list `AF-SPEC AF-SECRET AF-COMMIT AF-REGISTRY AF-HARNESS` |

**Validation**: no branch match, no spec dir, or a missing `git`/`jq` → no output
(FR-029 "inject nothing"). The block is plain text of at most about 12 lines.
