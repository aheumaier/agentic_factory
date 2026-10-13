#!/usr/bin/env bash
# Repo policy for this repo (feature 010, User Story 2). The single PreToolUse
# hook for Edit|Write|MultiEdit|NotebookEdit|Read|Grep|Glob|Bash, wired in
# .claude/settings.json. Rules, evaluated in this order; the first deny wins,
# and no match means no decision (exit 0, no stdout):
#   AF-SECRET — Read/Grep/Glob of .env or .env.braintrust (any directory, any
#               case, or a Grep/Glob glob that can name one), or a Bash command
#               naming either. .env.example never matches.
#   AF-SPEC   — Edit-family write under harness/, orchestration/ or eval/
#               without a feature branch (NNN-slug or worktree-NNN-slug) that
#               has specs/NNN-*/tasks.md. AF_SPEC_EXCEPTION (non-empty, set at
#               launch) turns that deny into an allow, announced once per
#               session; it never bypasses AF-SECRET or AF-COMMIT (FR-018).
#   AF-COMMIT — a Bash command containing the words `git` and `commit` runs
#               whole-repo ruff and both pytest suites; red denies the commit.
# A deny is a permissionDecision JSON on stdout with exit 0; a missing
# jq/git/uv, or an [AF-HOOKS] repo root that cannot be resolved, is exit 2
# (fail closed). AF-REGISTRY and AF-HARNESS are
# permissions.ask rules in settings.json, not checks here.
#
# Documented gaps: shell writes under guarded dirs are not pre-checked
# (FR-013; the turn gate still judges them at Stop), and shell secret reads are
# best-effort pattern matching, not a boundary (FR-016).
# Contract: specs/010-dev-harness-hardening/contracts/hook-interface.md.
set -uo pipefail

if ! . "$(dirname "$0")/lib.sh"; then
  echo "policy.sh: cannot load lib.sh" >&2
  exit 2
fi

INPUT=""
# Bounded read: a hand run with an open, never-closing pipe must not hang.
[ -t 0 ] || IFS= read -r -d '' -t 5 INPUT || true
require_tools policy.sh jq git
ROOT=$(cd "$(dirname "$0")/../.." 2>/dev/null && pwd) || {
  echo "[AF-HOOKS] policy.sh cannot resolve the repo root from $0, so this call cannot be checked. To proceed: check that the worktree directory exists and can be entered, or start a new Claude Code session in an existing worktree of this repo." >&2
  exit 2
}

MSG_SECRET='[AF-SECRET] .env and .env.braintrust hold live credentials and are never read by the agent. To proceed: read .env.example for variable names and ask the operator for any value you need.'
MSG_SPEC='[AF-SPEC] Code under harness/, orchestration/ and eval/ needs a planned feature: branch NNN-slug (or worktree-NNN-slug) with specs/NNN-*/tasks.md. To proceed: run /speckit-specify → /speckit-plan → /speckit-tasks and work on that feature'"'"'s branch, or have the operator relaunch with AF_SPEC_EXCEPTION="<reason>".'
MSG_COMMIT='[AF-COMMIT] Commits require ruff (whole repo) and both pytest suites to be green. To proceed: fix the failures below, then commit again.'

q="'"
# A .env / .env.braintrust word: glob and brace characters may follow, so
# `cat .env*` and `cat .env{,.braintrust}` match; a `.` may not (.env.example).
SECRET_RE="(^|[[:space:]/${q}\"=<])\\.env(\\.braintrust)?(\$|[[:space:];|&)${q}\"<>*?[{])"
GIT_RE='(^|[^[:alnum:]_.-])git($|[^[:alnum:]_.-])'
COMMIT_RE='(^|[^[:alnum:]_.-])commit($|[^[:alnum:]_.-])'

field() {
  jq -r "$1 // empty" <<<"$INPUT" 2>/dev/null
}

deny() {
  jq -n --arg r "$1" \
    '{hookSpecificOutput: {hookEventName: "PreToolUse",
      permissionDecision: "deny", permissionDecisionReason: $r}}'
  exit 0
}

# is_secret_path <path> [glob] — basename is .env or .env.braintrust, in any
# directory and any case (macOS volumes are case-insensitive, and a `..` or
# outside path still names the file). With "glob", a wildcard basename that can
# name either (`.env*`, `.env{,.braintrust}`) matches too.
is_secret_path() {
  local base="${1%/}"
  base="$(printf '%s' "${base##*/}" | LC_ALL=C tr '[:upper:]' '[:lower:]')"
  [ -n "$base" ] || return 1
  case "$base" in
    .env | .env.braintrust) return 0 ;;
  esac
  [ "${2:-}" = glob ] && [[ $base =~ $SECRET_RE ]]
}

tool="$(field .tool_name)"

# --- AF-SECRET --------------------------------------------------------------
case "$tool" in
  Read)
    is_secret_path "$(field .tool_input.file_path)" && deny "$MSG_SECRET"
    ;;
  Grep | Glob)
    is_secret_path "$(field .tool_input.path)" && deny "$MSG_SECRET"
    # Grep's `glob` filter names files too; Grep's `pattern` is file content.
    is_secret_path "$(field .tool_input.glob)" glob && deny "$MSG_SECRET"
    if [ "$tool" = Glob ]; then
      is_secret_path "$(field .tool_input.pattern)" glob && deny "$MSG_SECRET"
    fi
    ;;
  Bash)
    cmd="$(field .tool_input.command)"
    [[ $cmd =~ $SECRET_RE ]] && deny "$MSG_SECRET"
    ;;
esac

# --- AF-SPEC ----------------------------------------------------------------
case "$tool" in
  Edit | Write | MultiEdit | NotebookEdit)
    rel="$(rel_path "$ROOT" "$(field '.tool_input.file_path // .tool_input.notebook_path')")"
    case "$rel" in
      harness/* | orchestration/* | eval/*)
        n="$(feature_number "$ROOT")"
        found=""
        if [ -n "$n" ]; then
          for t in "$ROOT/specs/$n"-*/tasks.md; do
            [ -f "$t" ] && found=1 && break
          done
        fi
        if [ -z "$found" ]; then
          if [ -n "${AF_SPEC_EXCEPTION:-}" ]; then
            marker=""
            if sd="$(state_dir "$ROOT")"; then
              marker="$sd/exception-$(session_key "$(field .session_id)").notified"
            fi
            if [ -z "$marker" ] || [ ! -e "$marker" ]; then
              jq -n --arg m "[AF-SPEC] exception active for this session (AF_SPEC_EXCEPTION=${AF_SPEC_EXCEPTION})." \
                '{systemMessage: $m}'
              [ -z "$marker" ] || touch "$marker" 2>/dev/null
            fi
            exit 0
          fi
          branch="$(git -C "$ROOT" symbolic-ref --short -q HEAD 2>/dev/null)" || branch="(detached)"
          if [ -n "$n" ]; then
            detail="specs/$n-*/tasks.md: not found"
          else
            detail="specs/NNN-*/tasks.md: not checked (branch has no feature number)"
          fi
          deny "$MSG_SPEC"$'\n'"branch: ${branch:-(detached)}"$'\n'"$detail"
        fi
        ;;
    esac
    ;;
esac

# --- AF-COMMIT --------------------------------------------------------------
if [ "$tool" = Bash ] && [[ $cmd =~ $GIT_RE ]] && [[ $cmd =~ $COMMIT_RE ]]; then
  require_tools policy.sh uv
  run_check "ruff check ." \
    uv run --locked --directory "$ROOT" ruff check --output-format concise .
  run_suites "$ROOT"
  [ -z "$failures" ] || deny "${MSG_COMMIT}${failures}"
fi
exit 0
