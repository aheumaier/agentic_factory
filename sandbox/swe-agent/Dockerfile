# Execution Sandbox (§3.3) for harness/swe-agent, the one real agent in
# registry/agents/. Build context is the repo root:
#   docker build -f sandbox/swe-agent/Dockerfile .
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates gnupg jq \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# jq + uv: this repo's own Claude Code hooks (.claude/hooks/) need both and
# fail closed without them. swe-agent loads project settings, so those hooks
# run here whenever the target repo is agentic_factory itself (specs/010
# FR-014). uv is pinned to the version the operator's host runs.
COPY --from=ghcr.io/astral-sh/uv:0.10.0 /uv /uvx /bin/

WORKDIR /app
# Mirrors the dependencies in harness/swe-agent/pyproject.toml; the project
# isn't pip-installable (no build-system), so they're named directly.
RUN pip install --no-cache-dir "braintrust>=0.36.0" "claude-agent-sdk>=0.2.152"

COPY harness/swe-agent/agent.py ./agent.py
# Imported by agent.py as a sibling module (specs/009 seat guard).
COPY harness/swe-agent/seat_guard.py ./seat_guard.py

# Credentials are passed as sandbox env vars at creation time, never baked
# into the image: GH_TOKEN plus either CLAUDE_CODE_OAUTH_TOKEN (a credential-
# pool seat, Temporal path — orchestration/activities.py, specs/009) or
# ANTHROPIC_PLATFORM_API_KEY (GitHub-comment path,
# .github/workflows/swe-agent-build.yml).
