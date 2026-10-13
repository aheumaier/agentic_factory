# shellcheck shell=bash
# Shared helpers for .claude/hooks/*.sh. Sourced, never executed; no `set -e`.
# Must stay bash 3.2-compatible (macOS /bin/bash): no mapfile, no associative
# arrays, no ${v,,}, no declare -n. Commands are always passed as argv arrays,
# never re-parsed by a shell, so paths with quotes/$()/backticks can't inject.
# Design: specs/010-dev-harness-hardening/ (research R3-R5, R7, R14;
# contracts/hook-interface.md; data-model.md).

# Context budget (US4). Single source of truth: the settings test asserts
# env.CLAUDE_CODE_AUTO_COMPACT_WINDOW in .claude/settings.json equals CTX_BUDGET.
# shellcheck disable=SC2034
CTX_BUDGET=150000
# shellcheck disable=SC2034
CTX_WARN=120000

failures=""

# Gate time limit (012 FR-003, R3; data-model "Gate run"). Clamped to 240 s so
# the gate ends before the 300 s PreToolUse/Stop hook timeouts in settings.json.
GATE_LIMIT="${AF_GATE_LIMIT:-240}"
_gate_limit_re='^[1-9][0-9]{0,2}$'
if ! [[ $GATE_LIMIT =~ $_gate_limit_re ]] || [ "$GATE_LIMIT" -gt 240 ]; then
  GATE_LIMIT=240
fi
gate_deadline=""
gate_outcome=""
gate_cmd=""

# gate_runner — the GNU timeout command on PATH (timeout, else gtimeout), or
# return 1 when there is none.
gate_runner() {
  local r
  for r in timeout gtimeout; do
    if command -v "$r" >/dev/null 2>&1; then
      printf '%s\n' "$r"
      return 0
    fi
  done
  return 1
}

# gate_start — arm one deadline for every following run_check. With no runner
# the outcome is "no timeout tool" and run_check runs nothing (fail closed).
gate_start() {
  if gate_cmd="$(gate_runner)"; then
    gate_deadline=$((SECONDS + GATE_LIMIT))
  else
    gate_outcome="no timeout tool"
    failures="${failures}"$'\n'"=== gate FAILED ==="$'\n'"timeout or gtimeout is required (brew install coreutils)"$'\n'
  fi
}

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
# After gate_start, each step runs under the runner with the time left, and an
# exit of 124 or 137 ends the gate with the outcome "timed out".
run_check() {
  local label="$1" out rc left
  shift
  [ -z "$gate_outcome" ] || return 0
  if [ -n "$gate_deadline" ]; then
    left=$((gate_deadline - SECONDS))
    [ "$left" -ge 1 ] || left=1
    set -- "$gate_cmd" --kill-after=5 "${left}s" "$@"
  fi
  out="$("$@" 2>&1)"
  rc=$?
  if [ -n "$gate_deadline" ] && { [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; }; then
    gate_outcome="timed out"
    failures="${failures}"$'\n'"=== gate TIMED OUT after ${GATE_LIMIT}s ==="$'\n'"${label} timed out after ${GATE_LIMIT}s"$'\n'
    return 0
  fi
  if [ "$rc" -ne 0 ]; then
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

# rel_path <root> <path> — path relative to <root>, or nothing (status 1) when
# it is outside <root>. Lexical only (data-model "AF-SPEC path"): a relative
# path is put under <root>, then the whole path drops empty and `.` segments
# and each `..` pops one; a `..` at `/` stays at `/`, as the kernel reads it.
# Only then is it compared with <root>/. No realpath: /var vs /private/var on
# macOS must compare the way Claude Code reports them.
rel_path() {
  local root="${1%/}" p="$2" seg out=""
  [ -n "$p" ] || return 1
  case "$p" in
    /*) ;;
    *) p="$root/$p" ;;
  esac
  p="$p/"
  while [ -n "$p" ]; do
    seg="${p%%/*}"
    p="${p#*/}"
    case "$seg" in
      "" | .) ;;
      ..) out="${out%/*}" ;;
      *) out="$out/$seg" ;;
    esac
  done
  case "$out" in
    "$root"/?*) printf '%s\n' "${out#"$root"/}" ;;
    *) return 1 ;;
  esac
}

# The files a turn is judged on (012 R15; data-model "Turn snapshot"). Full
# tier: Python code and config, the hook scripts and settings. Drift tier: the
# files the context-drift test reads. py-check.sh stop picks the tier by path.
TURN_PATHS=('*.py' '*pyproject.toml' '*uv.lock' '.claude/hooks/*.sh' '.claude/settings.json'
  'CLAUDE.md' '.claude/agents/py-codereviewer.md' 'registry/agents/*/manifest.yaml'
  'specs/*/spec.md')

# turn_fingerprint <root> — "<blob-sha>\t<path>" for every tracked or
# untracked, non-ignored TURN_PATHS file on disk, C-sorted.
turn_fingerprint() {
  local root="$1" p shas
  local -a paths=()
  while IFS= read -r -d '' p; do
    [ -f "$root/$p" ] && paths+=("$p")
  done < <(git -C "$root" ls-files -co --exclude-standard -z -- \
    "${TURN_PATHS[@]}" 2>/dev/null)
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

# feature_branch <root> — the checked-out branch. While a rebase is stopped
# (HEAD detached), the branch in the first readable rebase-merge/head-name or
# rebase-apply/head-name, without refs/heads/ (012 FR-014, R10). Nothing for
# any other detached HEAD.
feature_branch() {
  local root="$1" b f state
  if b="$(git -C "$root" symbolic-ref --short -q HEAD 2>/dev/null)"; then
    printf '%s\n' "$b"
    return 0
  fi
  for state in rebase-merge rebase-apply; do
    f="$(git -C "$root" rev-parse --git-path "$state/head-name" 2>/dev/null)" || continue
    case "$f" in
      /*) ;;
      *) f="$root/$f" ;;
    esac
    [ -f "$f" ] && [ -r "$f" ] || continue
    b="$(head -n 1 "$f" 2>/dev/null)"
    b="${b#refs/heads/}"
    [ -n "$b" ] && printf '%s\n' "$b"
    return 0
  done
  return 0
}

# feature_number <root> — NNN from a branch named NNN-slug or worktree-NNN-slug;
# nothing for other branches or a detached HEAD outside a rebase.
feature_number() {
  local b re='^(worktree-)?([0-9]{3})-'
  b="$(feature_branch "$1")"
  if [[ $b =~ $re ]]; then
    printf '%s\n' "${BASH_REMATCH[2]}"
  fi
  return 0
}

# tip_tasks <root> — during a rebase (HEAD detached), the first C-sorted
# specs/<NNN>-*/tasks.md committed on the rebased branch's tip, or nothing.
# The worktree can predate the commit that added it (012 FR-014, R10). On an
# attached branch only the working tree counts, as in 010.
tip_tasks() {
  local root="$1" b n
  git -C "$root" symbolic-ref -q HEAD >/dev/null 2>&1 && return 0
  b="$(feature_branch "$root")"
  n="$(feature_number "$root")"
  [ -n "$b" ] && [ -n "$n" ] || return 0
  git -C "$root" ls-tree -r --name-only "refs/heads/$b" -- specs/ 2>/dev/null \
    | grep -E "^specs/$n-[^/]*/tasks\.md\$" | LC_ALL=C sort | head -n 1
  return 0
}

# feature_spec_dir <root> — first C-sorted specs/<NNN>-*/ (repo-relative,
# trailing /) for the branch's feature number, else the dir of tip_tasks, or
# nothing.
feature_spec_dir() {
  local root="$1" n d
  n="$(feature_number "$root")"
  [ -n "$n" ] || return 0
  d="$(for d in "$root/specs/$n"-*/; do
    [ -d "$d" ] && printf '%s\n' "${d#"$root"/}"
  done | LC_ALL=C sort | head -n 1)"
  if [ -z "$d" ]; then
    d="$(tip_tasks "$root")"
    d="${d%tasks.md}"
  fi
  [ -z "$d" ] || printf '%s\n' "$d"
  return 0
}
