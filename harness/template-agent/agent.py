"""Skeleton harness (§3.2). Model calls route through the self-hosted
LiteLLM proxy (§3.4), never directly to a provider, so key policy and cost
routing stay centralized.
"""
import os

import braintrust
from claude_agent_sdk import ClaudeAgentOptions, query

# Observability (§3.8): same project as eval/braintrust/eval.config.py and
# harness/swe-agent/agent.py, so every agent's traces land in one place.
BRAINTRUST_PROJECT = os.environ.get("BRAINTRUST_PROJECT", "agent-factory-pilot")

logger = braintrust.init_logger(project=BRAINTRUST_PROJECT)
braintrust.auto_instrument()

LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "http://localhost:4000")
LITELLM_API_KEY = os.environ.get("LITELLM_MASTER_KEY", "sk-local-master")


def build_options() -> ClaudeAgentOptions:
    # TODO: bind tools declared in this agent's SKILL.md / spec here.
    return ClaudeAgentOptions(
        system_prompt="Replace with this agent's scope from SKILL.md.",
    )


async def run(task: str) -> None:
    async for message in query(prompt=task, options=build_options()):
        print(message)


if __name__ == "__main__":
    import asyncio

    asyncio.run(run("TODO: task from an accepted spec"))
    logger.flush()
