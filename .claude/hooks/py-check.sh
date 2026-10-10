#!/usr/bin/env bash
# Enforces ruff + pytest on every Python change Claude makes in this repo.
# Wired in .claude/settings.json:
#   py-check.sh edit  — PostToolUse (Edit|Write|MultiEdit): ruff on the changed
#                       .py file, then both test suites.
#   py-check.sh stop  — Stop: ruff on the whole repo, then both test suites,
#                       so a turn can't end red.
# Exit 2 feeds stderr back to Claude (PostToolUse) or blocks the stop (Stop).
#
# Both suites run every time: they take ~3s together, and
# orchestration/activities.py loads harness/*/agent.py by path, so a harness
# edit can break the orchestration suite (and vice versa for tests/).
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
MODE="${1:-edit}"
INPUT="$(cat)"

# Fail closed: without jq the edit gate would silently match nothing.
command -v jq >/dev/null || { echo "py-check.sh: jq is required" >&2; exit 2; }

failures=""

run_check() {
  local label="$1"
  shift
  local out
  if ! out="$("$@" 2>&1)"; then
    failures+=$'\n'"=== ${label} FAILED ==="$'\n'"$(printf '%s\n' "$out" | tail -n 40)"$'\n'
  fi
}

# Args are passed as argv (never re-parsed by a shell), so paths containing
# quotes/$()/backticks can't break or inject into the command.
run_suites() {
  run_check "pytest tests/" uv run --directory "$ROOT" pytest tests/ -q -x
  run_check "pytest orchestration/" uv run --directory "$ROOT/orchestration" pytest -q -x
}

case "$MODE" in
  edit)
    file="$(jq -r '.tool_input.file_path // .tool_response.filePath // empty' <<<"$INPUT")"
    case "$file" in
      *.py) ;;
      *) exit 0 ;;
    esac
    case "$file" in
      "$ROOT"/*) ;;
      *) exit 0 ;;
    esac
    # --force-exclude: honour extend-exclude even for an explicitly named file.
    run_check "ruff check ${file#"$ROOT"/}" \
      uv run --directory "$ROOT" ruff check --force-exclude --output-format concise "$file"
    run_suites
    if [[ -n "$failures" ]]; then
      printf 'ruff/pytest gate failed after editing %s — fix before continuing:%s' \
        "${file#"$ROOT"/}" "$failures" >&2
      exit 2
    fi
    ;;

  stop)
    # Nothing Python-related changed vs HEAD -> nothing to re-check.
    # pyproject.toml/uv.lock count too: a [tool.ruff] or dependency change
    # can turn the baseline red without touching any .py file.
    cd "$ROOT" || exit 0
    watched=('*.py' '*pyproject.toml' '*uv.lock')
    if git diff --quiet HEAD -- "${watched[@]}" 2>/dev/null \
      && [[ -z "$(git ls-files --others --exclude-standard -- "${watched[@]}")" ]]; then
      exit 0
    fi
    run_check "ruff check ." uv run --directory "$ROOT" ruff check --output-format concise .
    run_suites
    if [[ -n "$failures" ]]; then
      if [[ "$(jq -r '.stop_hook_active // false' <<<"$INPUT")" == "true" ]]; then
        # Already blocked once this turn; don't loop forever — tell the user.
        jq -n --arg m "ruff/pytest gate is still RED at end of turn:${failures}" \
          '{systemMessage: $m}'
        exit 0
      fi
      printf 'ruff/pytest gate is red — fix before ending the turn:%s' "$failures" >&2
      exit 2
    fi
    ;;

  *)
    echo "py-check.sh: unknown mode '$MODE' (expected edit|stop)" >&2
    exit 1
    ;;
esac

exit 0
