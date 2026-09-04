"""Braintrust eval config (§3.6). Braintrust has no self-host tier — pilot
volume fits the free Starter plan (1GB trace, 10k scores/mo).

`run_eval` is a v1 binary coverage gate, not a semantic scorer: no labeled
dataset or per-criterion LLM judge exists in this repo yet. It only checks
that the sandbox run succeeded, produced a PR, and that success criteria
were found to check against — it does not verify any criterion's *content*
was actually met. Real per-criterion scoring is a follow-up.
"""
import os
import re

import braintrust

PROJECT = os.environ.get("BRAINTRUST_PROJECT", "agent-factory-pilot")

# Matches a "- **SC-NNN**: <text>" bullet under spec.md's mandatory
# "## Success Criteria" -> "### Measurable Outcomes" section, capturing
# everything up to the next "- **SC-" bullet or the next heading, so a
# criterion's text can wrap across multiple lines.
_SC_BULLET_RE = re.compile(
    r"-\s+\*\*SC-\d+\*\*:\s*(.+?)(?=\n-\s+\*\*SC-\d+\*\*:|\n#{1,6}\s|\Z)",
    re.DOTALL,
)


def load_success_criteria(spec_path: str) -> list[str]:
    """Parse `- **SC-NNN**: ...` bullets out of a Spec Kit `spec.md`'s
    `## Success Criteria` -> `### Measurable Outcomes` section."""
    text = open(spec_path, encoding="utf-8").read()
    marker = "### Measurable Outcomes"
    idx = text.find(marker)
    if idx == -1:
        raise ValueError(f"{spec_path!r} has no '### Measurable Outcomes' section")
    section = text[idx + len(marker) :]
    return [
        " ".join(match.group(1).split())
        for match in _SC_BULLET_RE.finditer(section)
    ]


# Separate regex (not a second capture group on _SC_BULLET_RE): that regex's
# group(1) is read as the criterion text by load_success_criteria() above,
# so adding an id-capturing group would shift numbering and change its
# return value.
_SC_BULLET_ID_RE = re.compile(
    r"-\s+\*\*(SC-\d+)\*\*:\s*(.+?)(?=\n-\s+\*\*SC-\d+\*\*:|\n#{1,6}\s|\Z)",
    re.DOTALL,
)


def load_success_criteria_ids(spec_path: str) -> list[tuple[str, str]]:
    """Like `load_success_criteria`, but returns `(id, text)` pairs so a
    caller (harness/architect-agent/agent.py) can key structures on the
    same `SC-NNN` id set the Eval-Gate uses."""
    text = open(spec_path, encoding="utf-8").read()
    marker = "### Measurable Outcomes"
    idx = text.find(marker)
    if idx == -1:
        raise ValueError(f"{spec_path!r} has no '### Measurable Outcomes' section")
    section = text[idx + len(marker) :]
    return [
        (match.group(1), " ".join(match.group(2).split()))
        for match in _SC_BULLET_ID_RE.finditer(section)
    ]


def run_eval(spec_path: str, sandbox_trace: dict) -> dict:
    """Binary coverage gate: pass iff the sandbox run exited 0, produced a
    PR, and at least one success criterion was found to check against.
    Returns a plain dict (not raise-only) — a failed gate is a normal
    business outcome the caller branches on, not an execution failure."""
    criteria = load_success_criteria(spec_path)

    if not criteria:
        result = {"passed": False, "criteria": criteria, "reason": "no success criteria found in spec.md"}
    elif sandbox_trace.get("exit_code") != 0:
        result = {"passed": False, "criteria": criteria, "reason": f"sandbox exit_code={sandbox_trace.get('exit_code')}"}
    elif not sandbox_trace.get("pr_url"):
        result = {"passed": False, "criteria": criteria, "reason": "no pr_url in sandbox_trace"}
    else:
        result = {"passed": True, "criteria": criteria, "reason": "coverage gate passed (binary check only, no semantic scoring)"}

    logger = braintrust.init_logger(project=PROJECT)
    with logger.start_span(name="eval_gate") as span:
        span.log(input={"spec_path": spec_path, "sandbox_trace": sandbox_trace}, output=result)
    logger.flush()
    return result


if __name__ == "__main__":
    raise SystemExit("wire this to a sandbox trace before running")
