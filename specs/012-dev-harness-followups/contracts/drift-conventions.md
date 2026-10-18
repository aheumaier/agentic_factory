# Contract: Drift Conventions, 012 amendments

This file amends `specs/010-dev-harness-hardening/contracts/drift-conventions.md`.
Anything not named here stays as 010 states it. 010's contract gets one pointer line
at the top, added by the tasks of this feature:

> Amended by `specs/012-dev-harness-followups/contracts/drift-conventions.md`
> (extractor rules as shipped, D-ID corpus, Stop coverage).

FR-018 and FR-019 change no code: they bring the contract in line with
`tests/test_context_drift.py` as it ships. FR-020 and FR-021 change code.

---

## D-REG sentence split (replaces 010's "on `.` + space or a blank line"; FR-018)

A sentence ends at a `.` followed by **any** whitespace, a newline included, or at a
blank line (regex `\.\s|\n\s*\n`). So a `.` at the end of a line ends the sentence,
the same as `. ` inside a line.

## D-ID tokens and classes (amends 010's class table; FR-018, FR-019)

**Tokens.** The text of each backticked span is split on whitespace and `,` (010 said
"whitespace/comma/slash-separated"; a `/` does not split a token).

**A token with `/`:**

- If its first segment is an existing top-level directory of the repo, the whole token
  is a **path** and must exist. A path token that holds a placeholder is skipped: a
  glob character (`*`, `?`, `[`), an angle-bracket name (`<name>`), or the word `NNN`
  (as in D-SPEC).
- Otherwise each `/` part is classified on its own, as if it were a separate token.
  So `Read/Grep/Glob` is three tokens.

**Unchecked by ruling: lowercase public names.** A lowercase name without a leading
underscore, for example `shape_issue`, `execute_activity` or `retry_policy`, is not
checked. Such names are also common English or config words, and checking them would
flag prose.

The cost, accepted by the operator on 2026-10-11: when such a name is renamed in the
code, a stale mention in the docs goes unnoticed. The checked classes in 010's table
(private name, constant or env name, env-name wildcard, file name, repo path) are
unchanged.

## D-ID search space (replaces 010's corpus; FR-020)

The corpus is the output of `git ls-files -co --exclude-standard`: tracked files plus
untracked files that git does not ignore. The same prefixes as in 010 are then left
out: `specs/`, `.claude/`, `.specify/`, `.git/`, any `.venv/`, `node_modules/`. Only
regular files are read.

So an identifier that exists only in a git-ignored file (a scratch `*.py` file, a
build output) counts as **missing**. 010 walked the file system and pruned only
some ignored dirs by hand.

## When the drift test runs (new; FR-021)

| Trigger | What runs |
|---|---|
| Stop, the turn changed a full-tier file (`*.py`, `*pyproject.toml`, `*uv.lock`, `.claude/hooks/*.sh`, `.claude/settings.json`) | both suites, which include the drift test |
| Stop, the turn changed only drift-tier files (`CLAUDE.md`, `.claude/agents/py-codereviewer.md`, `registry/agents/*/manifest.yaml`, `specs/*/spec.md`) | `tests/test_context_drift.py` only |
| AF-COMMIT | the root suite, which includes the drift test (as in 010) |

A spec directory that is added, renamed or removed always moves its `spec.md`, so
D-SPEC is covered at Stop. A registry entry always has a `manifest.yaml`, so D-REG is
covered at Stop.

**Gap that stays.** An identifier can live in a file that is neither Python nor in
scope, for example a YAML or Markdown file elsewhere. If a turn removes it there, Stop
does not notice. AF-COMMIT catches it before the commit.

**Second gap that stays: untracked files count at commit time** (T006 review,
2026-10-13). AF-COMMIT runs the same drift test with the same corpus, untracked files
included, and no CI job runs pytest. So a session can write an untracked `foo.py` that
defines `_helper`, mention `_helper` in `CLAUDE.md`, and commit only `CLAUDE.md`: the
drift test finds `_helper` in the untracked file and passes, and the commit points at a
name it does not contain. This is accepted: FR-020 puts untracked files in the corpus
on purpose, so that a new file can be documented before it is staged, and the next
drift run in a checkout without the untracked file fails. Closing it would mean a
tracked-only corpus (`git ls-files -c`) for the AF-COMMIT run only, through an env
flag; that is left for later.
