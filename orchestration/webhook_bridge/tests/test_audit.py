import json
import logging

from webhook_bridge import audit


def test_log_entry_writes_structured_json_line(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="webhook_bridge.audit"):
        audit.log_entry(author="alice", comment="pm_approved", reason="ok", outcome="signal_issued_no_handler")
    assert len(caplog.records) == 1
    entry = json.loads(caplog.records[0].message)
    assert entry == {
        "author": "alice",
        "comment": "pm_approved",
        "reason": "ok",
        "outcome": "signal_issued_no_handler",
    }


def test_reaction_for_outcome_started_is_rocket() -> None:
    assert audit.reaction_for_outcome("started") == "rocket"


def test_reaction_for_outcome_signal_issued_is_eyes() -> None:
    assert audit.reaction_for_outcome("signal_issued_no_handler") == "eyes"


def test_reaction_for_outcome_rejection_is_confused() -> None:
    for outcome in (
        "permission_denied",
        "malformed",
        "signal_failed",
        "fork_rejected",
        "repo_not_allowed",
        "mode_not_supported",
    ):
        assert audit.reaction_for_outcome(outcome) == "confused"


def test_reaction_for_outcome_ignored_has_no_reaction() -> None:
    assert audit.reaction_for_outcome("ignored") is None
