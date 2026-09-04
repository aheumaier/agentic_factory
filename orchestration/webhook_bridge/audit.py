"""Structured audit logging (data-model.md AuditLogEntry, FR-011/FR-012).

Kept separate from server.py: server.py imports temporal_client.py for
dispatch, and temporal_client.py needs to emit signal_failed/
signal_issued_no_handler entries too — putting the logger in server.py
would force a circular import (research.md/M3).
"""
import json
import logging
from typing import Literal

Outcome = Literal[
    "ignored",
    "permission_denied",
    "malformed",
    "signal_failed",
    "fork_rejected",
    "repo_not_allowed",
    "signal_issued_no_handler",
    "duplicate_ignored",
    "mode_not_supported",
    "started",
]

logger = logging.getLogger("webhook_bridge.audit")

# Every rejection/failure outcome maps to the same "confused" reaction;
# a started run and an issued signal each get their own (FR-012/FR-015).
_REACTION_BY_OUTCOME: dict[str, str] = {
    "started": "rocket",
    "signal_issued_no_handler": "eyes",
}
_DEFAULT_REJECTION_REACTION = "confused"

# Outcomes with no comment context to react to (never reach a comment_id).
_NO_REACTION_OUTCOMES = {"ignored"}


def reaction_for_outcome(outcome: str) -> str | None:
    """GitHub reaction content for a terminal outcome, or None if none applies."""
    if outcome in _NO_REACTION_OUTCOMES:
        return None
    return _REACTION_BY_OUTCOME.get(outcome, _DEFAULT_REJECTION_REACTION)


def log_entry(author: str, comment: str, reason: str, outcome: Outcome) -> None:
    """Write one structured (JSON-per-line) AuditLogEntry."""
    entry = {
        "author": author,
        "comment": comment,
        "reason": reason,
        "outcome": outcome,
    }
    logger.info(json.dumps(entry))
