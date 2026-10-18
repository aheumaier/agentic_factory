#!/usr/bin/env bash
# Turn-scoped ruff + pytest gate for this repo (feature 010, User Story 1).
# Wired in .claude/settings.json:
#   py-check.sh turn-start — UserPromptSubmit: fingerprint every TURN_PATHS
#                            file (lib.sh) once per
#                            turn, adopting a snapshot left pending by an
#                            interrupted turn (e.g. before /clear). Then
#                            warns once per level as context nears the
#                            CTX_BUDGET (FR-028). Always exits 0; stdout is
#                            empty or one JSON object.
#   py-check.sh edit       — PostToolUse (Edit|Write|MultiEdit): ruff on the
#                            edited .py file only. Never runs pytest.
#   py-check.sh stop       — Stop: diff the tree against the turn snapshot (or
#                            HEAD if none is usable). A full-tier change runs
#                            ruff on the changed .py files and both suites; a
#                            drift-tier-only change (docs the context-drift
#                            test reads) runs only that test (012 FR-021), so
#                            a docs-only turn stays fast. Renames outside
#                            TURN_PATHS that break the drift test are caught
#                            at AF-COMMIT, not here (012 R15). Edits made through any tool,
#                            shell included, are in the diff. The loop guard
#                            (stop_hook_active) is read before the uv and
#                            timeout-tool checks; a missing uv is a red run;
#                            a second red keeps the snapshot for the next
#                            turn (012 FR-012, FR-013).
# Exit 2 feeds stderr back to Claude (PostToolUse) or blocks the stop (Stop).
# State lives in $(git rev-parse --git-path claude-harness)/, per worktree.
#
# Both suites run together: orchestration/activities.py loads harness/*/agent.py
# by path, so a harness edit can break the orchestration suite (and vice versa
# for tests/). Contract: specs/010-dev-harness-hardening/contracts/hook-interface.md,
# amended by specs/012-dev-harness-followups/contracts/hook-interface.md.
# shellcheck source-path=SCRIPTDIR
set -uo pipefail

MODE="${1:-}"
# A lib.sh that loads without its helpers counts as not loaded: each call
# would return 127 and the edit or the turn would pass with no check (US1).
if ! . "$(dirname "$0")/lib.sh" \
  || ! declare -F gate_start require_tools run_check run_suites state_dir session_key \
    rel_path turn_fingerprint resolve_snapshot >/dev/null \
  || ! declare -p TURN_PATHS >/dev/null 2>&1; then
  # turn-start must never block or erase the operator's prompt.
  [ "$MODE" = "turn-start" ] && exit 0
  echo "py-check.sh: cannot load lib.sh" >&2
  exit 2
fi
# Any other exit than 0 or 2 is a non-blocking hook error, which would let
# the edit or the turn through unchecked, so it blocks instead (as policy.sh).
case "$MODE" in
  edit | stop)
    trap 'rc=$?; [ "$rc" -eq 0 ] || [ "$rc" -eq 2 ] || { echo "py-check.sh stopped on an unexpected error (exit $rc); see the error above." >&2; exit 2; }' EXIT
    ;;
esac

ROOT=$(cd "$(dirname "$0")/../.." && pwd) || {
  [ "$MODE" = "turn-start" ] && exit 0
  echo "py-check.sh: cannot resolve the repo root from $0" >&2
  exit 2
}
INPUT=""
# Bounded read: a hand run with an open, never-closing pipe must not hang.
[ -t 0 ] || IFS= read -r -d '' -t 5 INPUT || true

TAB=$'\t'

# snapshot_usable <file> <current-fingerprint> — readable, every line
# "<40-hex sha>\t<path>", and non-empty when TURN_PATHS files exist.
snapshot_usable() {
  [ -n "$1" ] && [ -r "$1" ] || return 1
  if [ -s "$1" ]; then
    ! grep -qvE "^[0-9a-f]{40}${TAB}.+\$" "$1"
  else
    [ -z "$2" ]
  fi
}

# context_warn <state-dir> <key> — FR-028: one notice per level (warn, then
# budget) from the last main-thread assistant usage in the transcript's tail;
# re-armed once usage drops below CTX_WARN. Any unreadable input -> silent.
# Prints nothing or exactly one JSON object; never fails the hook.
context_warn() {
  local sd="$1" key="$2" tp n level marker prev k msg ctx int_re='^(0|[1-9][0-9]{0,14})$'
  tp="$(jq -r '.transcript_path // empty' <<<"$INPUT" 2>/dev/null)"
  [ -n "$tp" ] && [ -r "$tp" ] || return 0
  # try/catch: one malformed entry must not abort the stream. Non-numeric fields
  # (jq's + would concatenate digit strings) and any error give "invalid", which
  # fails the integer check below, so the reading is unknown. No leading zeros:
  # $(( )) would read them as octal. 012 FR-017: a compaction boundary gives
  # "unknown" (silent, marker kept) until the next usage after it.
  n="$(tail -n 200 "$tp" 2>/dev/null | jq -R -r 'fromjson? | objects
    | select((.type == "system" and .subtype == "compact_boundary")
        or (.type == "assistant" and (.isSidechain != true) and (try .message.usage catch null)))
    | if .type == "system" then "unknown" else try (.message.usage
        | [.input_tokens, .cache_read_input_tokens, .cache_creation_input_tokens]
        | map(. // 0) | if all(type == "number") then add else "invalid" end) catch "invalid" end' \
    2>/dev/null | tail -n 1)"
  [[ $n =~ $int_re ]] || return 0

  marker="$sd/ctx-$key.level"
  level=none
  [ "$n" -ge "$CTX_WARN" ] && level=warn
  [ "$n" -ge "$CTX_BUDGET" ] && level=budget
  if [ "$level" = none ]; then
    rm -f "$marker" 2>/dev/null
    return 0
  fi
  prev="$(cat "$marker" 2>/dev/null)"
  case "$prev:$level" in
    budget:* | warn:warn) return 0 ;;
  esac

  k="$((n / 1000))k"
  if [ "$level" = budget ]; then
    msg="[context] ${k}, at or over the $((CTX_BUDGET / 1000))k budget (warn at $((CTX_WARN / 1000))k). /compact <focus> at the next task boundary, or /clear between tasks."
    ctx="Context is at ${k}, at or over the $((CTX_BUDGET / 1000))k budget the operator set."
  else
    msg="[context] ${k} of $((CTX_BUDGET / 1000))k budget (warn at $((CTX_WARN / 1000))k). /compact <focus> at the next task boundary, or /clear between tasks."
    ctx="Context is at ${k} of the operator's $((CTX_BUDGET / 1000))k budget."
  fi
  ctx="${ctx} Finish the current task, tick tasks.md, and write any undocumented decisions to the spec directory, then suggest /compact <focus> or /clear to the operator."
  printf '%s\n' "$level" >"$marker" 2>/dev/null
  jq -n --arg m "$msg" --arg c "$ctx" \
    '{systemMessage: $m,
      hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: $c}}' 2>/dev/null
  return 0
}

case "$MODE" in
  turn-start)
    command -v git >/dev/null 2>&1 || exit 0
    command -v jq >/dev/null 2>&1 || exit 0
    sd="$(state_dir "$ROOT")" || exit 0
    key="$(session_key "$(jq -r '.session_id // empty' <<<"$INPUT" 2>/dev/null)")"
    # 012 FR-016: markers older than 7 days, like stale snapshots, are dropped.
    find "$sd" -maxdepth 1 \( -name 'ctx-*.level' -o -name 'exception-*.notified' \) \
      -mmin +10080 -delete 2>/dev/null || true
    resolve_snapshot "$sd" "$key"
    snap="$sd/turn-$key.tsv"
    # FR-001: never retake on a mid-turn message; a pending snapshot stays.
    if [ ! -e "$snap" ]; then
      tmp="$(mktemp "$sd/.turn-$key.XXXXXX" 2>/dev/null)" || exit 0
      if turn_fingerprint "$ROOT" >"$tmp" 2>/dev/null; then
        mv -f "$tmp" "$snap" 2>/dev/null
      fi
      rm -f "$tmp" 2>/dev/null
    fi
    context_warn "$sd" "$key"
    exit 0
    ;;

  edit)
    require_tools py-check.sh jq
    file="$(jq -r '.tool_input.file_path // .tool_response.filePath // empty' <<<"$INPUT")"
    case "$file" in
      *.py) ;;
      *) exit 0 ;;
    esac
    rel="$(rel_path "$ROOT" "$file")"
    [ -n "$rel" ] || exit 0
    require_tools py-check.sh uv
    # --frozen: mid-edit lock drift isn't flagged here; stop and commit catch it.
    # --force-exclude: honour extend-exclude even for an explicitly named file.
    run_check "ruff check $rel" \
      uv run --frozen --directory "$ROOT" ruff check --force-exclude --output-format concise -- "$rel"
    if [ -n "$failures" ]; then
      printf 'ruff failed after editing %s:%s' "$rel" "$failures" >&2
      exit 2
    fi
    exit 0
    ;;

  stop)
    require_tools py-check.sh jq git
    snap=""
    if sd="$(state_dir "$ROOT")"; then
      key="$(session_key "$(jq -r '.session_id // empty' <<<"$INPUT")")"
      # Adopts a pending snapshot if session_id changed mid-turn (R14).
      resolve_snapshot "$sd" "$key"
      snap="$sd/turn-$key.tsv"
    fi
    current="$(turn_fingerprint "$ROOT")"

    changed=()
    if snapshot_usable "$snap" "$current"; then
      while IFS= read -r p; do
        [ -n "$p" ] && changed+=("$p")
      done < <(
        { if [ -n "$current" ]; then printf '%s\n' "$current"; fi; } \
          | LC_ALL=C comm -3 "$snap" - | sed "s/^${TAB}//" | cut -f2- | LC_ALL=C sort -u
      )
    else
      # FR-010: no usable snapshot -> judge everything changed vs HEAD.
      # -z: a quoted non-ASCII name would match no tier pattern.
      while IFS= read -r -d '' p; do
        [ -n "$p" ] && changed+=("$p")
      done < <(
        {
          git -C "$ROOT" diff --name-only -z HEAD -- "${TURN_PATHS[@]}" 2>/dev/null
          git -C "$ROOT" ls-files --others --exclude-standard -z -- "${TURN_PATHS[@]}" 2>/dev/null
        } | LC_ALL=C sort -z -u
      )
    fi

    if [ "${#changed[@]}" -eq 0 ]; then
      rm -f "$snap"
      exit 0
    fi
    # 012 FR-012: read the loop guard before anything can turn the run red.
    active="$(jq -r '.stop_hook_active // false' <<<"$INPUT" 2>/dev/null)"
    # 012 FR-003, FR-012: one deadline for lint and both suites; a missing uv, a
    # timeout or a missing timeout tool lands in $failures and takes the red
    # path below (a set gate_outcome makes run_check run nothing).
    if command -v uv >/dev/null 2>&1; then
      gate_start
    else
      gate_outcome="uv missing"
      failures="${failures}"$'\n'"=== uv FAILED ==="$'\n'"uv is required"$'\n'
    fi

    # 012 R15: only drift-tier paths are listed; any other path runs the full
    # gate, so a path missing from this list can't skip the suites.
    full=0
    lint=()
    for p in "${changed[@]}"; do
      case "$p" in
        CLAUDE.md|.claude/agents/py-codereviewer.md|registry/agents/*/manifest.yaml|specs/*/spec.md) ;;
        *.py) full=1; [ -f "$ROOT/$p" ] && lint+=("$p") ;;
        *) full=1 ;;
      esac
    done
    if [ "$full" -eq 0 ]; then
      run_check "pytest tests/test_context_drift.py" \
        uv run --locked --directory "$ROOT" pytest tests/test_context_drift.py -q --tb=short -rfE
    else
      if [ "${#lint[@]}" -gt 0 ]; then
        run_check "ruff check (${#lint[@]} changed files)" \
          uv run --locked --directory "$ROOT" ruff check --force-exclude --output-format concise \
          -- "${lint[@]}"
      fi
      run_suites "$ROOT"
    fi

    if [ -z "$failures" ]; then
      rm -f "$snap"
      exit 0
    fi
    if [ "$active" = "true" ]; then
      # Already blocked once this turn; don't loop forever, tell the operator.
      # 012 FR-013: keep the snapshot, so the next turn still judges this
      # turn's changes.
      jq -n --arg m "ruff/pytest gate is still RED at end of turn:${failures}" \
        '{systemMessage: $m}'
      exit 0
    fi
    # Keep the snapshot so the retry is judged against the same baseline.
    printf "ruff/pytest gate is red for this turn's changes (%d files) — fix before ending the turn:%s" \
      "${#changed[@]}" "$failures" >&2
    exit 2
    ;;

  *)
    echo "py-check.sh: unknown mode '$MODE' (expected turn-start|edit|stop)" >&2
    exit 1
    ;;
esac
