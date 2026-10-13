"""Context-drift test (specs/010-dev-harness-hardening, FR-020..FR-022).

Checks the facts in the always-loaded context files against the tree, per
contracts/drift-conventions.md:

- D-REG (CLAUDE.md): `registry/agents/...` paths, brace lists and entry counts;
- D-SPEC (both files): `specs/NNN-slug` paths;
- D-ID (reviewer prompt): backticked code identifiers exist in repo code.

A backtick span followed by `(pending NNN)` is exempt while its check fails,
and is a violation once it passes (FR-021).

Run as a script (`uv run --locked python tests/test_context_drift.py`) to
print violations; `--candidates` also prints every classified D-ID token.
"""
import functools
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MD = "CLAUDE.md"
REVIEWER_MD = ".claude/agents/py-codereviewer.md"

# Search space for D-ID: top-level dirs skipped outright, and dir names
# skipped at any depth.
_EXCLUDED_TOP = {"specs", ".claude", ".specify", ".git"}
_EXCLUDED_ANY = {".venv", "node_modules", ".git"}

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

_REG_PATH_RE = re.compile(r"registry/agents/([a-z0-9][a-z0-9-]*)(?![a-z0-9*?\[-])")
_REG_BRACE_RE = re.compile(r"registry/agents/\{([^}]*)\}")
_REG_COUNT_RE = re.compile(
    r"\b(" + "|".join(_NUMBER_WORDS) + r")\s+(entries|entry)\b", re.IGNORECASE
)
_SENTENCE_SPLIT_RE = re.compile(r"\.\s|\n\s*\n")
_SPEC_RE = re.compile(r"specs/(\d{3}-[a-z0-9][a-z0-9-]*)")
_SPAN_RE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
_PENDING_RE = re.compile(r"[ \t]*\(pending (\d{3})\)")
_FENCE_RE = re.compile(r"^\s*```")

_PRIVATE_RE = re.compile(r"^_[A-Za-z0-9_]+(\(\))?$")
_CONSTANT_RE = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)+$")
_WILDCARD_RE = re.compile(r"^[A-Z][A-Z0-9_]*_\*$")
_FILENAME_RE = re.compile(r"^[\w.-]+\.(py|yaml|toml)$")

_CODE_EXPECTED = "a definition or use in *.py outside specs/ and .claude/"


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _registry_dirs(repo_root: Path) -> list[str]:
    agents = repo_root / "registry" / "agents"
    if not agents.is_dir():
        return []
    return sorted(p.name for p in agents.iterdir() if p.is_dir())


@functools.cache
def _corpus(repo_root: Path) -> tuple[str, frozenset[str]]:
    """All `*.py` text in the D-ID search space, joined, plus the basename of
    every file in it. The space is what git sees, tracked plus untracked
    files that are not ignored (FR-020), so a local scratch file never counts.
    Cached per repo root, so tmp trees get their own."""
    listed = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "-co", "--exclude-standard", "-z"],
        check=True, capture_output=True, text=True,
    ).stdout
    py_texts: list[str] = []
    basenames: set[str] = set()
    for rel in listed.split("\0"):
        parts = rel.split("/")
        if not rel or parts[0] in _EXCLUDED_TOP or _EXCLUDED_ANY.intersection(parts[:-1]):
            continue
        path = repo_root / rel
        if not path.is_file():  # a deleted tracked file, or a nested repo's dir
            continue
        basenames.add(path.name)
        if path.suffix == ".py":
            try:
                py_texts.append(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
    return "\n".join(py_texts), frozenset(basenames)


def _in_code(repo_root: Path, name: str) -> bool:
    py_text, _ = _corpus(repo_root)
    pattern = r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])"
    return re.search(pattern, py_text) is not None


def _spans(text: str):
    """Yield (start, content, pending_nnn_or_None) for each single-backtick
    span outside fenced code blocks. Fenced lines are blanked to spaces of
    the same length, so offsets still index into `text`."""
    lines = text.split("\n")
    in_fence = False
    for i, line in enumerate(lines):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            lines[i] = " " * len(line)
        elif in_fence:
            lines[i] = " " * len(line)
    unfenced = "\n".join(lines)
    for m in _SPAN_RE.finditer(unfenced):
        pending = _PENDING_RE.match(unfenced, m.end())
        yield m.start(), m.group(1), pending.group(1) if pending else None


def _pending_ranges(text: str) -> list[tuple[int, int, str]]:
    return [
        (start, start + len(content) + 2, nnn)
        for start, content, nnn in _spans(text)
        if nnn is not None
    ]


def check_reg(repo_root: Path, text: str, source_name: str) -> list[str]:
    dirs = _registry_dirs(repo_root)
    listing = f"registry/agents/ has {len(dirs)}: {', '.join(dirs)}"
    out: list[str] = []
    for m in _REG_PATH_RE.finditer(text):
        if m.group(1) not in dirs:
            out.append(
                f"{source_name}:{_line_of(text, m.start())}: [D-REG] "
                f"registry/agents/{m.group(1)} does not exist ({listing})"
            )
    for m in _REG_BRACE_RE.finditer(text):
        listed = sorted(n.strip() for n in m.group(1).split(",") if n.strip())
        if listed != dirs:
            out.append(
                f"{source_name}:{_line_of(text, m.start())}: [D-REG] "
                f"registry/agents/{{{m.group(1)}}} lists {len(listed)} but {listing}"
            )
    bounds = [0]
    for m in _SENTENCE_SPLIT_RE.finditer(text):
        bounds.append(m.end())
    bounds.append(len(text))
    for m in _REG_COUNT_RE.finditer(text):
        start = max(b for b in bounds if b <= m.start())
        end = min(b for b in bounds if b > m.start())
        if "registry/agents" not in text[start:end]:
            continue
        if _NUMBER_WORDS[m.group(1).lower()] != len(dirs):
            out.append(
                f'{source_name}:{_line_of(text, m.start())}: [D-REG] '
                f'"{m.group(0)}" but {listing}'
            )
    return out


def check_spec(repo_root: Path, text: str, source_name: str) -> list[str]:
    pending = _pending_ranges(text)
    out: list[str] = []
    for m in _SPEC_RE.finditer(text):
        exists = (repo_root / "specs" / m.group(1)).is_dir()
        nnn = next((n for s, e, n in pending if s <= m.start() < e), None)
        where = f"{source_name}:{_line_of(text, m.start())}"
        if nnn is None and not exists:
            out.append(f"{where}: [D-SPEC] {m.group(0)} does not exist")
        elif nnn is not None and exists:
            out.append(
                f'{where}: [D-SPEC] {m.group(0)} now exists; '
                f'remove the "(pending {nnn})" marker'
            )
    return out


def _classify(repo_root: Path, token: str) -> list[tuple[str, str]]:
    """Split one whitespace/comma token into (token, class) pairs. A token
    with `/` is a repo path when its first segment is an existing top-level
    dir; otherwise each `/`-separated part is classified on its own."""
    if "/" in token:
        first = token.split("/", 1)[0]
        if first and (repo_root / first).is_dir():
            # Globs, `<name>` and `NNN` are placeholders, not paths.
            if re.search(r"[*?\[]|<[^>]*>|\bNNN\b", token):
                return [(token, "skip")]
            return [(token, "path")]
        return [p for part in token.split("/") if part for p in _classify(repo_root, part)]
    if _PRIVATE_RE.match(token):
        return [(token, "private")]
    if _CONSTANT_RE.match(token):
        return [(token, "constant")]
    if _WILDCARD_RE.match(token):
        return [(token, "wildcard")]
    if _FILENAME_RE.match(token):
        return [(token, "filename")]
    return [(token, "skip")]


def id_candidates(repo_root: Path, text: str):
    """Yield (line, token, class, pending_nnn_or_None) for every D-ID token."""
    for start, content, nnn in _spans(text):
        for raw in re.split(r"[\s,]+", content):
            if raw:
                for token, cls in _classify(repo_root, raw):
                    yield _line_of(text, start), token, cls, nnn


def _id_failure(repo_root: Path, token: str, cls: str) -> str | None:
    """None if the token's check passes, else the expected-value text."""
    if cls == "private":
        name = token.removesuffix("()")
        return None if _in_code(repo_root, name) else _CODE_EXPECTED
    if cls == "constant":
        return None if _in_code(repo_root, token) else _CODE_EXPECTED
    if cls == "wildcard":
        prefix = token[:-1]
        return None if prefix in _corpus(repo_root)[0] else (
            f"a name starting with {prefix} in *.py outside specs/ and .claude/"
        )
    if cls == "filename":
        return None if token in _corpus(repo_root)[1] else (
            f"a file named {token} outside specs/ and .claude/"
        )
    if cls == "path":
        return None if (repo_root / token.rstrip("/")).exists() else "an existing repo path"
    return None


def check_id(repo_root: Path, text: str, source_name: str) -> list[str]:
    out: list[str] = []
    for line, token, cls, nnn in id_candidates(repo_root, text):
        if cls == "skip":
            continue
        failure = _id_failure(repo_root, token, cls)
        where = f"{source_name}:{line}"
        if nnn is None and failure is not None:
            out.append(f"{where}: [D-ID] `{token}` not found in repo code (expected: {failure})")
        elif nnn is not None and failure is None:
            out.append(
                f'{where}: [D-ID] `{token}` now exists; remove the "(pending {nnn})" marker'
            )
    return out


def collect_violations(repo_root: Path) -> list[str]:
    claude = (repo_root / CLAUDE_MD).read_text(encoding="utf-8")
    reviewer = (repo_root / REVIEWER_MD).read_text(encoding="utf-8")
    return [
        *check_reg(repo_root, claude, CLAUDE_MD),
        *check_spec(repo_root, claude, CLAUDE_MD),
        *check_spec(repo_root, reviewer, REVIEWER_MD),
        *check_id(repo_root, reviewer, REVIEWER_MD),
    ]


def test_context_files_match_tree():
    violations = collect_violations(REPO_ROOT)
    assert not violations, "context drift:\n" + "\n".join(violations)


# Injected staleness (SC-006): synthetic text against a tmp_path tree.


def _tree(root: Path, agents=("architect-agent", "pm-agent", "swe-agent"), specs=()) -> Path:
    # A git repo, because the D-ID corpus is what `git ls-files` sees (FR-020).
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for name in agents:
        (root / "registry" / "agents" / name).mkdir(parents=True)
    for name in specs:
        (root / "specs" / name).mkdir(parents=True)
    return root


def test_wrong_entry_count_is_flagged(tmp_path):
    root = _tree(tmp_path)
    text = "`registry/agents/` has the two entries we ship.\n"
    assert check_reg(root, text, "CLAUDE.md") == [
        'CLAUDE.md:1: [D-REG] "two entries" but registry/agents/ has 3: '
        "architect-agent, pm-agent, swe-agent"
    ]


def test_brace_list_missing_a_dir_is_flagged(tmp_path):
    root = _tree(tmp_path)
    violations = check_reg(root, "x\n`registry/agents/{pm-agent,swe-agent}/`\n", "CLAUDE.md")
    assert len(violations) == 1
    assert violations[0].startswith("CLAUDE.md:2: [D-REG] registry/agents/{pm-agent,swe-agent}")


def test_missing_spec_dir_is_flagged(tmp_path):
    root = _tree(tmp_path, specs=("004-real",))
    text = "see `specs/004-real/` and `specs/099-nope`\n"
    assert check_spec(root, text, "CLAUDE.md") == [
        "CLAUDE.md:1: [D-SPEC] specs/099-nope does not exist"
    ]


def test_unknown_identifier_is_flagged(tmp_path):
    root = _tree(tmp_path)
    (root / "orchestration").mkdir()
    # Made-up names: this file is in the live D-ID corpus, so a real name here
    # would count as "in code" even after a rename.
    (root / "orchestration" / "activities.py").write_text("def _frob_target(): ...\n")
    violations = check_id(root, "call `_frob_targets` first\n", "rev.md")
    assert violations == [
        "rev.md:1: [D-ID] `_frob_targets` not found in repo code "
        f"(expected: {_CODE_EXPECTED})"
    ]


def test_pending_token_absent_from_code_passes(tmp_path):
    root = _tree(tmp_path)
    assert check_id(root, "a copied `seat_guard.py` (pending 009)\n", "rev.md") == []


def test_pending_token_present_in_code_demands_marker_removal(tmp_path):
    root = _tree(tmp_path)
    (root / "orchestration").mkdir()
    (root / "orchestration" / "seat_guard.py").write_text("SEATS = 1\n")
    assert check_id(root, "a copied `seat_guard.py` (pending 009)\n", "rev.md") == [
        'rev.md:1: [D-ID] `seat_guard.py` now exists; remove the "(pending 009)" marker'
    ]


def test_dotted_names_and_placeholders_are_not_flagged(tmp_path):
    # `specs/` must exist, or the span is never classified as a repo path.
    root = _tree(tmp_path, specs=("004-real",))
    text = "use `workflow.now()`; specs live in `specs/NNN-slug/`\n"
    assert check_id(root, text, "rev.md") == []
    assert check_spec(root, text, "rev.md") == []


def test_ignored_file_is_not_in_the_corpus(tmp_path_factory):
    # FR-020: the D-ID corpus is tracked plus untracked-but-not-ignored files.
    # Two roots, because _corpus is cached per root. They differ only in the
    # ignore rule (FR-020): the same top-level file, untracked in both.
    ignored = _tree(tmp_path_factory.mktemp("ignored"))
    (ignored / ".gitignore").write_text("secret_mod.py\n")
    (ignored / "secret_mod.py").write_text("def only_here(): ...\n")
    assert not _in_code(ignored, "only_here")

    visible = _tree(tmp_path_factory.mktemp("visible"))
    (visible / "secret_mod.py").write_text("def only_here(): ...\n")
    assert _in_code(visible, "only_here")


if __name__ == "__main__":
    if "--candidates" in sys.argv[1:]:
        reviewer_text = (REPO_ROOT / REVIEWER_MD).read_text(encoding="utf-8")
        for line, token, cls, nnn in id_candidates(REPO_ROOT, reviewer_text):
            pending = f" (pending {nnn})" if nnn else ""
            print(f"{REVIEWER_MD}:{line}: {cls:9} {token}{pending}")
        print("---")
    violations = collect_violations(REPO_ROOT)
    for v in violations:
        print(v)
    print(f"{len(violations)} violation(s)")
    sys.exit(1 if violations else 0)
