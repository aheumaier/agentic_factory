#!/usr/bin/env bash
# Repo policy for this repo (feature 010, User Story 2). The single PreToolUse
# hook for Edit|Write|MultiEdit|NotebookEdit|Read|Grep|Glob|Bash, wired in
# .claude/settings.json. Rules, evaluated in this order; the first deny wins,
# and no match means no decision (exit 0, no stdout):
#   AF-SECRET — Read/Grep/Glob of .env or .env.braintrust (any directory, any
#               case, or a Grep/Glob glob that can name one, best effort), or a Bash command
#               naming either. .env.example never matches.
#   AF-SPEC   — Edit-family write under harness/, orchestration/ or eval/
#               without a feature branch (NNN-slug or worktree-NNN-slug) that
#               has specs/NNN-*/tasks.md. AF_SPEC_EXCEPTION (non-empty, set at
#               launch) turns that deny into an allow, announced once per
#               session; it never bypasses AF-SECRET or AF-COMMIT (FR-018).
#   AF-COMMIT — a Bash command containing the word `git` and one of commit,
#               revert, cherry-pick, merge, am, rebase, pull runs whole-repo
#               ruff and both pytest suites under the gate time limit; red, a
#               timeout or no timeout tool denies it. Only `<verb> --abort|--quit`
#               and a plain `git pull --ff-only` are exempt (012 R5).
# A deny is a permissionDecision JSON on stdout with exit 0; a missing
# jq/git/uv, or an [AF-HOOKS] case (repo root that cannot be resolved, empty
# or invalid input), is exit 2 (fail closed). AF-REGISTRY and AF-HARNESS are
# permissions.ask rules in settings.json, not checks here.
#
# Documented gaps: shell writes under guarded dirs are not pre-checked
# (FR-013; the turn gate still judges them at Stop), and shell secret reads are
# best-effort pattern matching, not a boundary (FR-016).
# Contract: specs/010-dev-harness-hardening/contracts/hook-interface.md, amended
# by specs/012-dev-harness-followups/contracts/hook-interface.md.
set -uo pipefail

if ! . "$(dirname "$0")/lib.sh"; then
  echo "policy.sh: cannot load lib.sh" >&2
  exit 2
fi

INPUT=""
# Bounded read: a hand run with an open, never-closing pipe must not hang.
[ -t 0 ] || IFS= read -r -d '' -t 5 INPUT || true
require_tools policy.sh jq git
# FR-004: with no trusted input there is nothing to answer in JSON (AF-HOOKS).
if ! jq -e 'type == "object" and (.tool_name | type == "string")' >/dev/null 2>&1 <<<"$INPUT"; then
  echo '[AF-HOOKS] The repo policy hook got no valid input, so it cannot judge this call. To proceed: retry the call; if it repeats, restart the session and report it.' >&2
  exit 2
fi
ROOT=$(cd "$(dirname "$0")/../.." 2>/dev/null && pwd) || {
  echo "[AF-HOOKS] policy.sh cannot resolve the repo root from $0, so this call cannot be checked. To proceed: check that the worktree directory exists and can be entered, or start a new Claude Code session in an existing worktree of this repo." >&2
  exit 2
}

MSG_SECRET='[AF-SECRET] .env and .env.braintrust hold live credentials and are never read by the agent. To proceed: read .env.example for variable names and ask the operator for any value you need.'
MSG_SECRET_SHELL='[AF-SECRET] Shell commands may not name .env or .env.braintrust: these files hold live credentials, and reading, writing or copying them from the shell is refused. To proceed: use .env.example for variable names and ask the operator for any value you need. If the command only mentions the name as text (a commit message, a search string), write that text to a file and pass the file (git commit -F <file>, grep -f <file>), or ask the operator.'
MSG_SPEC='[AF-SPEC] Code under harness/, orchestration/ and eval/ needs a planned feature: branch NNN-slug (or worktree-NNN-slug) with specs/NNN-*/tasks.md. To proceed: run /speckit-specify → /speckit-plan → /speckit-tasks and work on that feature'"'"'s branch, or have the operator relaunch with AF_SPEC_EXCEPTION="<reason>".'
MSG_COMMIT='[AF-COMMIT] git commands that write commits (commit, revert, cherry-pick, merge, am, rebase, pull) require ruff (whole repo) and both pytest suites to be green. To proceed: fix the failures below, then run the command again.'
MSG_TIMEOUT="[AF-COMMIT] The commit gate timed out after ${GATE_LIMIT}s, so this commit cannot be checked. To proceed: find the slow test (--durations=10), fix it, then commit again."
MSG_NO_RUNNER='[AF-COMMIT] The commit gate needs GNU timeout (timeout or gtimeout) to bound its run. To proceed: install it with brew install coreutils, then commit again.'

q="'"
# A .env / .env.braintrust word: glob and brace characters may follow, so
# `cat .env*` and `cat .env{,.braintrust}` match; a `.` may not (.env.example).
# It may also sit after a backtick, `>`, `@`, `{`, `,`, `:` or `(`
# (`` `cat .env` ``, `echo x >.env`, `cp {.env,x}`, `scp host:.env .`,
# `less (.env)`) and before a backtick, `,` or `}` (`cat {x,.env}`).
# Matched against the lower-cased command, so `.ENV` counts (012 R6).
SECRET_RE="(^|[[:space:]/${q}\"=<>\`@{,:(])\\.env(\\.braintrust)?(\$|[[:space:];|&)${q}\"<>*?[{}\`,])"
GIT_RE='(^|[^[:alnum:]_.-])git($|[^[:alnum:]_.-])'
VERB_RE='(^|[^[:alnum:]_.-])(commit|revert|cherry-pick|merge|am|rebase|pull)($|[^[:alnum:]_.-])'
PLAIN_RE='^[[:alnum:]_./:@+=-]+$'
nl=$'\n'

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
# outside path still names the file). With "glob", the whole glob is matched
# against SECRET_RE after `*` and `?` become spaces, so `.env*`, `*.env`,
# `**/*.env`, `.env{,.braintrust}` and `{.env,pkg/x.py}` match too. Best
# effort: a glob such as `[.]env` still gets through (012 contract).
is_secret_path() {
  local p base
  p="$(printf '%s' "${1%/}" | LC_ALL=C tr '[:upper:]' '[:lower:]')"
  base="${p##*/}"
  [ -n "$base" ] || return 1
  case "$base" in
    .env | .env.braintrust) return 0 ;;
  esac
  p="${p//[*?]/ }"
  [ "${2:-}" = glob ] && [[ $p =~ $SECRET_RE ]]
}

# verb_count <segment> — how many of the seven verb words the segment holds.
verb_count() {
  local s="$1" n=0
  while [[ $s =~ $VERB_RE ]]; do
    n=$((n + 1))
    s="${s#*"${BASH_REMATCH[0]}"}"
  done
  printf '%s\n' "$n"
}

# exempt_segment <segment> — one of the two shapes that cannot write a commit
# (012 R5): `git [-C p|-c k=v]… (rebase|cherry-pick|merge|am|revert)
# (--abort|--quit)`, or `git pull` whose only option is --ff-only while
# pull.rebase is unset or false. Plain tokens only, so the shell can neither
# strip nor expand one into an option (PLAIN_RE: letters, digits and _ . / : @
# + = - only; quotes, backslash, $ ` ( ) < >, braces, globs and ~ are refused).
exempt_segment() {
  local i=1 n tok ff=""
  local -a t
  [ "$(verb_count "$1")" -eq 1 ] || return 1
  read -ra t <<<"$1"
  for tok in "${t[@]}"; do
    [[ $tok =~ $PLAIN_RE ]] || return 1
  done
  n=${#t[@]}
  [ "$n" -ge 2 ] && [ "${t[0]}" = git ] || return 1
  while [ "$i" -lt "$n" ] && { [ "${t[$i]}" = -C ] || [ "${t[$i]}" = -c ]; }; do
    i=$((i + 2))
  done
  [ "$i" -lt "$n" ] || return 1
  case "${t[$i]}" in
    rebase | cherry-pick | merge | am | revert)
      [ $((i + 2)) -eq "$n" ] || return 1
      case "${t[$((i + 1))]}" in
        --abort | --quit) return 0 ;;
      esac
      return 1
      ;;
    pull)
      [ "$i" -eq 1 ] || return 1
      for ((i = 2; i < n; i++)); do
        tok="${t[$i]}"
        case "$tok" in
          --ff-only) ff=1 ;;
          -*) return 1 ;;
        esac
      done
      [ -n "$ff" ] || return 1
      case "$(git -C "$ROOT" config --get pull.rebase 2>/dev/null)" in
        "" | false) return 0 ;;
      esac
      return 1
      ;;
  esac
  return 1
}

# commit_gated <command> — the 010 floor (the words git and a verb), unless
# every segment that holds a verb is an exempt segment (012 FR-005, R5).
commit_gated() {
  local c="${1//\\$nl/}" seg
  [[ $c =~ $GIT_RE ]] && [[ $c =~ $VERB_RE ]] || return 1
  c="${c//&&/$nl}"
  c="${c//||/$nl}"
  c="${c//;/$nl}"
  c="${c//|/$nl}"
  while IFS= read -r seg; do
    [[ $seg =~ $VERB_RE ]] || continue
    exempt_segment "$seg" || return 0
  done <<<"$c"
  return 1
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
    # Lower-cased copy for the match only; AF-COMMIT below needs $cmd as is.
    lc_cmd="$(printf '%s' "$cmd" | LC_ALL=C tr '[:upper:]' '[:lower:]')"
    [[ $lc_cmd =~ $SECRET_RE ]] && deny "$MSG_SECRET_SHELL"
    ;;
esac

# --- AF-SPEC ----------------------------------------------------------------
case "$tool" in
  Edit | Write | MultiEdit | NotebookEdit)
    rel="$(rel_path "$ROOT" "$(field '.tool_input.file_path // .tool_input.notebook_path')")"
    # Case-insensitive volume: Harness/ is harness/. Only the first segment.
    top="$(printf '%s' "${rel%%/*}" | LC_ALL=C tr '[:upper:]' '[:lower:]')"
    case "$top${rel#"${rel%%/*}"}" in
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
if [ "$tool" = Bash ] && commit_gated "$cmd"; then
  require_tools policy.sh uv
  gate_start
  run_check "ruff check ." \
    uv run --locked --directory "$ROOT" ruff check --output-format concise .
  run_suites "$ROOT"
  case "$gate_outcome" in
    "timed out") deny "${MSG_TIMEOUT}${failures}" ;;
    "no timeout tool") deny "$MSG_NO_RUNNER" ;;
  esac
  [ -z "$failures" ] || deny "${MSG_COMMIT}${failures}"
fi
exit 0
