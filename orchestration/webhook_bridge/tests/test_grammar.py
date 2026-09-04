from webhook_bridge.grammar import GateCommand, RunCommand, parse


def test_run_command_design_doc_ordering_parses() -> None:
    result = parse("@pipeline-agent run agent=widget-export version=3 mode=full")
    assert result == RunCommand(kind="run", mode="full", agent_name="widget-export", version="3")


def test_run_command_any_token_order_parses() -> None:
    a = parse("@pipeline-agent run mode=full agent=x version=1")
    b = parse("@pipeline-agent run version=1 mode=full agent=x")
    c = parse("@pipeline-agent run agent=x version=1 mode=full")
    assert a == b == c == RunCommand(kind="run", mode="full", agent_name="x", version="1")


def test_run_command_missing_token_does_not_match() -> None:
    assert parse("@pipeline-agent run mode=full agent=x") is None


def test_run_command_duplicate_token_does_not_match() -> None:
    assert parse("@pipeline-agent run mode=full mode=vibe agent=x version=1") is None


def test_run_command_unrecognized_mode_still_parses() -> None:
    result = parse("@pipeline-agent run mode=turbo agent=x version=1")
    assert result == RunCommand(kind="run", mode="turbo", agent_name="x", version="1")


def test_run_command_invalid_slug_rejected() -> None:
    assert parse("@pipeline-agent run mode=full agent=x/y version=1") is None


def test_gate_exact_matches() -> None:
    assert parse("pm_approved") == GateCommand(kind="gate", gate="pm", decision="approved", feedback=None)
    assert parse("plan_approved") == GateCommand(kind="gate", gate="plan", decision="approved", feedback=None)
    assert parse("security_cleared") == GateCommand(
        kind="gate", gate="security", decision="approved", feedback=None
    )


def test_gate_rejected_forms() -> None:
    assert parse("pm_rejected: needs more detail") == GateCommand(
        kind="gate", gate="pm", decision="rejected", feedback="needs more detail"
    )
    assert parse("plan_rejected:use candidate C") == GateCommand(
        kind="gate", gate="plan", decision="rejected", feedback="use candidate C"
    )
    assert parse("security_rejected: found a CVE") == GateCommand(
        kind="gate", gate="security", decision="rejected", feedback="found a CVE"
    )


def test_gate_keyword_embedded_in_prose_does_not_match() -> None:
    assert parse("this looks great, pm_approved of it I think") is None


def test_unrecognized_comment_returns_none() -> None:
    assert parse("just a regular comment") is None


def test_only_first_non_empty_line_considered() -> None:
    assert parse("\n\n  pm_approved  \nsome other text") == GateCommand(
        kind="gate", gate="pm", decision="approved", feedback=None
    )
