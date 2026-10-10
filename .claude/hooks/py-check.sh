#!/usr/bin/env bash
# Turn-scoped ruff + pytest gate for this repo (feature 010, User Story 1).
# Wired in .claude/settings.json:
#   py-check.sh turn-start — UserPromptSubmit: fingerprint every Python-relevant
#                            file (*.py, *pyproject.toml, *uv.lock) once per
#                            turn, adopting a snapshot left pending by an
#                            interrupted turn (e.g. before /clear). Then
#                            warns once per level as context nears the
#                            CTX_BUDGET (FR-028). Always exits 0; stdout is
#                            empty or one JSON object.
#   py-check.sh edit       — PostToolUse (Edit|Write|MultiEdit): ruff on the
#                            edited .py file only. Never runs pytest.
#   py-check.sh stop       — Stop: diff the tree against the turn snapshot (or
#                            HEAD if none is usable), then ruff the changed .py
#                            files and run both suites if anything changed, so
#                            a turn can't end red. Edits made through any tool,
#                            shell included, are in the diff.
# Exit 2 feeds stderr back to Claude (PostToolUse) or blocks the stop (Stop).
# State lives in $(git rev-parse --git-path claude-harness)/, per worktree.
#
# Both suites run together: orchestration/activities.py loads harness/*/agent.py
# by path, so a harness edit can break the orchestration suite (and vice versa
# for tests/). Contract: specs/010-dev-harness-hardening/contracts/hook-interface.md.
set -uo pipefail

MODE="${1:-}"
if ! . "$(dirname "$0")/lib.sh"; then
  # turn-start must never block or erase the operator's prompt.
  [ "$MODE" = "turn-start" ] && exit 0
  echo "py-check.sh: cannot load lib.sh" >&2
  exit 2
fi

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
INPUT=""
# Bounded read: a hand run with an open, never-closing pipe must not hang.
[ -t 0 ] || IFS= read -r -d '' -t 5 INPUT || true

WATCHED=('*.py' '*pyproject.toml' '*uv.lock')
TAB=$'\t'

# snapshot_usable <file> <current-fingerprint> — readable, every line
# "<40-hex sha>\t<path>", and non-empty when Python-relevant files exist.
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
  # $(( )) would read them as octal.
  n="$(tail -n 200 "$tp" 2>/dev/null | jq -R -r 'fromjson? | objects
    | select(.type == "assistant" and (.isSidechain != true) and (try .message.usage catch null))
    | try (.message.usage
        | [.input_tokens, .cache_read_input_tokens, .cache_creation_input_tokens]
        | map(. // 0) | if all(type == "number") then add else "invalid" end) catch "invalid"' \
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
    resolve_snapshot "$sd" "$key"
    snap="$sd/turn-$key.tsv"
    # FR-001: never retake on a mid-turn message; a pending snapshot stays.
    if [ ! -e "$snap" ]; then
      tmp="$(mktemp "$sd/.turn-$key.XXXXXX" 2>/dev/null)" || exit 0
      if python_fingerprint "$ROOT" >"$tmp" 2>/dev/null; then
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
    current="$(python_fingerprint "$ROOT")"

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
      while IFS= read -r p; do
        [ -n "$p" ] && changed+=("$p")
      done < <(
        {
          git -C "$ROOT" diff --name-only HEAD -- "${WATCHED[@]}" 2>/dev/null
          git -C "$ROOT" ls-files --others --exclude-standard -- "${WATCHED[@]}" 2>/dev/null
        } | LC_ALL=C sort -u
      )
    fi

    if [ "${#changed[@]}" -eq 0 ]; then
      rm -f "$snap"
      exit 0
    fi
    require_tools py-check.sh uv

    lint=()
    for p in "${changed[@]}"; do
      case "$p" in
        *.py) [ -f "$ROOT/$p" ] && lint+=("$p") ;;
      esac
    done
    if [ "${#lint[@]}" -gt 0 ]; then
      run_check "ruff check (${#lint[@]} changed files)" \
        uv run --locked --directory "$ROOT" ruff check --force-exclude --output-format concise \
        -- "${lint[@]}"
    fi
    run_suites "$ROOT"

    if [ -z "$failures" ]; then
      rm -f "$snap"
      exit 0
    fi
    if [ "$(jq -r '.stop_hook_active // false' <<<"$INPUT")" = "true" ]; then
      # Already blocked once this turn; don't loop forever, tell the operator.
      jq -n --arg m "ruff/pytest gate is still RED at end of turn:${failures}" \
        '{systemMessage: $m}'
      rm -f "$snap"
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
