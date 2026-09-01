# Triage Policy (§3.1 Spec/Intake — schema + triage, assemble-only layer)

No vendor sells this decision; it is encoded here, versioned, not left to
reviewer judgment (per the architecture doc's §1.3 rationale).

## Auto-approve
A spec auto-approves to Build when **all** hold:
- `tools` is a subset of the existing registry catalog (`../registry/agents/`)
- `guardrails.requires_human_approval` is empty
- `success_criteria` has at least one measurable item

## Escalate to human review
Any of:
- New tool/MCP server not yet in the catalog
- Spec touches auth, secrets, or production credentials
- `guardrails.requires_human_approval` is non-empty

Escalation routes through the touchpoint layer (Slack/Teams + HumanLayer or
gotoHuman — see architecture doc §3.1) — not implemented in this scaffold yet.

## Reject
- Missing `success_criteria` (ungradeable — no eval target)
- Owner field empty
