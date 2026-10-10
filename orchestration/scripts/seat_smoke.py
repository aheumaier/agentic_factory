"""Live seat smoke test (specs/009-credential-pool-handoff quickstart V4).

Proves, against a real subscription seat, that a seat-backed call through
`seat_guard` (a) authenticates with the seat token even when the parent
process carries a competing API key / base URL (SC-007, research R1), and
(b) yields a real last-seen utilization figure (research R2).

    cd orchestration && uv run python scripts/seat_smoke.py [SEAT_ENV_VAR]

Reads the token from the repo .env itself and never prints it. Costs one
tiny model call on that seat.
"""
import asyncio
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage
from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_guard():
    path = REPO_ROOT / "harness" / "swe-agent" / "seat_guard.py"
    spec = importlib.util.spec_from_file_location("seat_guard", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def main(token_env: str) -> int:
    token = dotenv_values(REPO_ROOT / ".env").get(token_env) or os.environ.get(token_env)
    if not token:
        print(f"{token_env} is not set in .env or the environment", file=sys.stderr)
        return 2
    guard = _load_guard()

    # Poison the parent env the way a LiteLLM-configured worker would be.
    os.environ["ANTHROPIC_API_KEY"] = "sk-bogus-not-a-key"
    os.environ["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:9"

    options = ClaudeAgentOptions(
        tools=[], setting_sources=[], permission_mode="default", max_turns=1,
        cwd=tempfile.mkdtemp(), env=guard.seat_options_env(token),
    )
    usage: dict = {}
    result = None
    try:
        async for message in guard.guarded_query("Reply with exactly: OK", options, usage):
            if isinstance(message, ResultMessage):
                result = message.result
    except (guard.SeatExhausted, guard.SeatInvalid) as e:
        print(f"SEAT OUTCOME: {type(e).__name__} usage={e.usage}")
        return 1

    print(f"result={result!r} usage={usage}")
    ok = (result or "").strip() == "OK" and isinstance(usage.get("utilization"), float)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "CLAUDE_OAUTH_SEAT_A")))
