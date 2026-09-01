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
# Mirrors the single dependency in harness/swe-agent/pyproject.toml; the
# project isn't pip-installable (no build-system), so it's named directly.
RUN pip install --no-cache-dir claude-agent-sdk

COPY harness/swe-agent/agent.py ./agent.py

# ANTHROPIC_API_KEY and GH_TOKEN are passed as sandbox env vars at
# creation time (see .github/workflows/swe-agent-build.yml), never baked
# into the image.
