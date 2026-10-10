# shellcheck shell=bash
# Shared helpers for .claude/hooks/*.sh. Sourced, never executed; no `set -e`.
# Must stay bash 3.2-compatible (macOS /bin/bash): no mapfile, no associative
# arrays, no ${v,,}, no declare -n. Commands are always passed as argv arrays,
# never re-parsed by a shell, so paths with quotes/$()/backticks can't inject.
# Design: specs/010-dev-harness-hardening/ (research R3-R5, R7, R14;
# contracts/hook-interface.md; data-model.md).

# Context budget (US4). Single source of truth: the settings test asserts
# env.CLAUDE_CODE_AUTO_COMPACT_WINDOW in .claude/settings.json equals CTX_BUDGET.
CTX_BUDGET=150000
CTX_WARN=120000

failures=""

# require_tools <script-name> <tool>... — fail closed (exit 2) naming each
# missing tool; any other non-zero exit would be a non-blocking hook error.
require_tools() {
  local script="$1" tool missing=0
  shift
  for tool in "$@"; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      echo "${script}: ${tool} is required" >&2
      missing=1
    fi
  done
  [ "$missing" -eq 0 ] || exit 2
}

# trim_pytest — stdin -> every FAILED/ERROR summary line first, then the tail of
# the rest, 60 lines at most in total, so no failing test ID is cut (FR-006).
trim_pytest() {
  awk -v max=60 '
    /^(FAILED|ERROR) / { s[++ns] = $0; next }
    { r[++nr] = $0 }
    END {
      for (i = 1; i <= ns && i <= max; i++) print s[i]
      left = max - (ns < max ? ns : max)
      for (i = nr - left + 1; i <= nr; i++) if (i >= 1) print r[i]
    }'
}

# run_check <label> <cmd> [args...] — run argv; on a non-zero exit append
# "=== <label> FAILED ===" plus trimmed output to the global $failures.
run_check() {
  local label="$1" out
  shift
  if ! out="$("$@" 2>&1)"; then
    case "$label" in
      pytest*) out="$(printf '%s\n' "$out" | trim_pytest)" ;;
      *) out="$(printf '%s\n' "$out" | tail -n 40)" ;;
    esac
    failures="${failures}"$'\n'"=== ${label} FAILED ==="$'\n'"${out}"$'\n'
  fi
}

# run_suites <root> — both suites, no -x (each failure is reported), --locked
# so uv never rewrites a lockfile (FR-007).
run_suites() {
  run_check "pytest tests/" \
    uv run --locked --directory "$1" pytest tests/ -q --tb=short -rfE
  run_check "pytest orchestration/" \
    uv run --locked --directory "$1/orchestration" pytest -q --tb=short -rfE
}

# state_dir <root> — absolute per-worktree state dir, created if missing.
state_dir() {
  local root="$1" d
  d="$(git -C "$root" rev-parse --git-path claude-harness 2>/dev/null)" || return 1
  [ -n "$d" ] || return 1
  case "$d" in
    /*) ;;
    *) d="$root/$d" ;;
  esac
  mkdir -p "$d" 2>/dev/null || return 1
  printf '%s\n' "$d"
}

# session_key <raw> — session_id reduced to [A-Za-z0-9_-], or "nosession".
session_key() {
  local k
  k="$(printf '%s' "$1" | LC_ALL=C tr -cd 'A-Za-z0-9_-')"
  printf '%s\n' "${k:-nosession}"
}

# rel_path <root> <path> — path relative to <root>, or nothing when it is
# outside <root>. Plain string prefix (no realpath): /var vs /private/var on
# macOS must compare the way Claude Code reports them.
rel_path() {
  local root="${1%/}" p="$2" rel
  case "$p" in
    "$root"/*) rel="${p#"$root"/}" ;;
    /*) return 0 ;;
    *) rel="${p#./}" ;;
  esac
  case "/$rel/" in
    */../*) return 0 ;;
  esac
  [ -n "$rel" ] && printf '%s\n' "$rel"
  return 0
}

# python_fingerprint <root> — "<blob-sha>\t<path>" for every tracked or
# untracked, non-ignored *.py / *pyproject.toml / *uv.lock on disk, C-sorted.
python_fingerprint() {
  local root="$1" p shas
  local -a paths=()
  while IFS= read -r -d '' p; do
    [ -f "$root/$p" ] && paths+=("$p")
  done < <(git -C "$root" ls-files -co --exclude-standard -z -- \
    '*.py' '*pyproject.toml' '*uv.lock' 2>/dev/null)
  [ "${#paths[@]}" -gt 0 ] || return 0
  shas="$(printf '%s\n' "${paths[@]}" | git -C "$root" hash-object --stdin-paths)" || return 1
  printf '%s\n' "${paths[@]}" | paste <(printf '%s\n' "$shas") - | LC_ALL=C sort -u
}

# resolve_snapshot <state-dir> <key> — the adoption step (FR-001): keep our own
# pending snapshot; else prune others older than 7 days, adopt the oldest
# remaining one (widest baseline) as ours and drop the rest. Never fails.
resolve_snapshot() {
  local sd="$1" key="$2" own f oldest=""
  own="$sd/turn-$key.tsv"
  [ -e "$own" ] && return 0
  find "$sd" -maxdepth 1 -name 'turn-*.tsv' -mmin +10080 -exec rm -f {} + 2>/dev/null
  # Every loop skips $own by name, so even a dangling own symlink survives.
  for f in "$sd"/turn-*.tsv; do
    [ -f "$f" ] && [ "$f" != "$own" ] || continue
    if [ -z "$oldest" ] || [ "$f" -ot "$oldest" ]; then
      oldest="$f"
    fi
  done
  [ -n "$oldest" ] && mv -f "$oldest" "$own" 2>/dev/null
  for f in "$sd"/turn-*.tsv; do
    [ "$f" = "$own" ] || rm -f "$f" 2>/dev/null
  done
  return 0
}

# feature_number <root> — NNN from a branch named NNN-slug or worktree-NNN-slug;
# nothing for other branches or a detached HEAD.
feature_number() {
  local b re='^(worktree-)?([0-9]{3})-'
  b="$(git -C "$1" symbolic-ref --short -q HEAD 2>/dev/null)" || return 0
  if [[ $b =~ $re ]]; then
    printf '%s\n' "${BASH_REMATCH[2]}"
  fi
  return 0
}

# feature_spec_dir <root> — first C-sorted specs/<NNN>-*/ (repo-relative,
# trailing /) for the branch's feature number, or nothing.
feature_spec_dir() {
  local root="$1" n d
  n="$(feature_number "$root")"
  [ -n "$n" ] || return 0
  for d in "$root/specs/$n"-*/; do
    [ -d "$d" ] && printf '%s\n' "${d#"$root"/}"
  done | LC_ALL=C sort | head -n 1
}
