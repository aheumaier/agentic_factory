# Execution Sandbox (§3.3) for harness/swe-agent, the one real agent in
# registry/agents/. Build context is the repo root:
#   docker build -f sandbox/swe-agent/Dockerfile .
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates gnupg \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY harness/swe-agent/pyproject.toml ./
RUN pip install --no-cache-dir claude-agent-sdk

COPY harness/swe-agent/agent.py ./agent.py

# ANTHROPIC_API_KEY (and, later, a scoped GH_TOKEN) are passed as sandbox
# env vars at creation time, not baked into the image.
