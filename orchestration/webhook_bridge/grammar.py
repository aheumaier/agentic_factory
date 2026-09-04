"""Comment -> RunCommand | GateCommand | None (data-model.md PipelineCommand).

Grammar-anchoring rule (research.md): a comment is a recognized command
only if its first non-empty line, trimmed, either exactly matches a gate
keyword, matches a `<gate>_rejected: <feedback>` prefix, or is a run
command carrying exactly the three `key=value` tokens (`mode=`, `agent=`,
`version=`) in any order, each exactly once. Anything else (mid-sentence
keywords, later lines) is not a command at all.
"""
import re
from dataclasses import dataclass
from typing import Literal

_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

_RUN_PREFIX = ("@pipeline-agent", "run")
_RUN_KEYS = {"mode", "agent", "version"}

_Gate = Literal["pm", "plan", "security"]

_GATE_EXACT: dict[str, tuple[_Gate, Literal["approved"]]] = {
    "pm_approved": ("pm", "approved"),
    "plan_approved": ("plan", "approved"),
    "security_cleared": ("security", "approved"),
}
_GATE_REJECTED_RE = re.compile(r"^(pm_rejected|plan_rejected|security_rejected):\s*(.+)$")
_GATE_REJECTED_KEY: dict[str, _Gate] = {
    "pm_rejected": "pm",
    "plan_rejected": "plan",
    "security_rejected": "security",
}


@dataclass(frozen=True)
class RunCommand:
    kind: Literal["run"]
    mode: str  # parsed as-is; full/vibe validity is a dispatch-time concern (mode_not_supported)
    agent_name: str
    version: str


@dataclass(frozen=True)
class GateCommand:
    kind: Literal["gate"]
    gate: Literal["pm", "plan", "security"]
    decision: Literal["approved", "rejected"]
    feedback: str | None


def is_valid_slug(value: str) -> bool:
    """agent_name/version MUST disallow '/' so workflow_id's '/' separators
    stay unambiguous (data-model.md PipelineRunIdentity, research.md).
    """
    return bool(_SLUG_RE.match(value))


def parse(comment_body: str) -> RunCommand | GateCommand | None:
    line = _first_non_empty_line(comment_body)
    if line is None:
        return None
    run = _parse_run(line)
    if run is not None:
        return run
    return _parse_gate(line)


def _first_non_empty_line(text: str) -> str | None:
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped:
            return stripped
    return None


def _parse_run(line: str) -> RunCommand | None:
    tokens = line.split()
    if len(tokens) != 5 or tuple(tokens[:2]) != _RUN_PREFIX:
        return None
    values: dict[str, str] = {}
    for token in tokens[2:]:
        key, sep, value = token.partition("=")
        if not sep or key not in _RUN_KEYS or key in values or not value:
            return None
        values[key] = value
    if values.keys() != _RUN_KEYS:
        return None
    agent_name, version = values["agent"], values["version"]
    if not is_valid_slug(agent_name) or not is_valid_slug(version):
        return None
    return RunCommand(kind="run", mode=values["mode"], agent_name=agent_name, version=version)


def _parse_gate(line: str) -> GateCommand | None:
    if line in _GATE_EXACT:
        gate, decision = _GATE_EXACT[line]
        return GateCommand(kind="gate", gate=gate, decision=decision, feedback=None)
    match = _GATE_REJECTED_RE.match(line)
    if match:
        gate = _GATE_REJECTED_KEY[match.group(1)]
        return GateCommand(kind="gate", gate=gate, decision="rejected", feedback=match.group(2))
    return None
