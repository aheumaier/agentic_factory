#!/usr/bin/env bash
# Continuity context after /compact or /clear (feature 010, User Story 4).
# Wired in .claude/settings.json as SessionStart, matcher compact|clear. On a
# feature branch (NNN-slug or worktree-NNN-slug) with a specs/NNN-*/ dir it
# injects where to resume from disk: branch, spec dir, the next unchecked
# tasks, whether a turn-gate snapshot is pending, and the policy rule IDs.
# During a rebase it names the branch being rebased; when tasks.md is only on
# that branch's tip, the next tasks are read from there (012 FR-014).
# Anything else (other source, other branch, missing jq/git) injects nothing.
#
# Never blocks (FR-029, FR-031): always exits 0, stdout is empty or one JSON
# object. No `set -u`, which would exit non-zero on a bug. There is
# deliberately no PreCompact hook: compaction is never held up.
# Contract: specs/010-dev-harness-hardening/contracts/hook-interface.md, amended
# by specs/012-dev-harness-followups/contracts/hook-interface.md.
# shellcheck source-path=SCRIPTDIR

command -v jq >/dev/null 2>&1 || exit 0
command -v git >/dev/null 2>&1 || exit 0
. "$(dirname "$0")/lib.sh" 2>/dev/null || exit 0

INPUT=""
# Bounded read: a hand run with an open, never-closing pipe must not hang.
[ -t 0 ] || IFS= read -r -d '' -t 5 INPUT || true

src="$(jq -r '.source // empty' <<<"$INPUT" 2>/dev/null)"
case "$src" in
  compact) how=compacted ;;
  clear) how=cleared ;;
  *) exit 0 ;;
esac

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
branch="$(feature_branch "$ROOT" 2>/dev/null)"
dir="$(feature_spec_dir "$ROOT" 2>/dev/null)"
[ -n "$branch" ] && [ -n "$dir" ] || exit 0

tasks=""
files="(spec.md, plan.md, tasks.md)"
md=""
if [ -f "$ROOT/$dir/tasks.md" ]; then
  md="$(cat "$ROOT/$dir/tasks.md" 2>/dev/null)"
elif tip="$(tip_tasks "$ROOT" 2>/dev/null)" && [ -n "$tip" ] \
  && md="$(git -C "$ROOT" show "refs/heads/${branch}:${tip}" 2>/dev/null)"; then
  # 012 FR-014: a stopped rebase whose worktree predates the spec dir. The
  # dir is the tip's, the one policy.sh judged, even if another is on disk.
  dir="${tip%tasks.md}"
  files="(on the tip of ${branch} only: git show refs/heads/${branch}:${tip})"
else
  tasks=" no tasks.md"
fi
if [ -z "$tasks" ]; then
  while IFS= read -r line; do
    tasks="${tasks}"$'\n'"  ${line:0:160}"
  done < <(grep -m 3 -E '^- \[ \] T[0-9]+' <<<"$md" 2>/dev/null)
  [ -n "$tasks" ] || tasks=$'\n'"  (no unchecked tasks)"
fi

gate=clear
if sd="$(state_dir "$ROOT" 2>/dev/null)"; then
  for f in "$sd"/turn-*.tsv; do
    if [ -e "$f" ]; then
      gate="snapshot pending (this turn's changes will be checked at Stop)"
      break
    fi
  done
fi

block="[harness] Context was ${how}. Resume from disk, not memory:
- branch: ${branch}
- spec dir: ${dir} ${files}
- next tasks:${tasks}
- turn gate: ${gate}
- policy rules: AF-SPEC AF-SECRET AF-COMMIT AF-REGISTRY AF-HARNESS AF-HOOKS (see CLAUDE.md)"

jq -n --arg c "$block" \
  '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $c}}' 2>/dev/null
exit 0
