# Build from repo root: docker build -f sandbox/Dockerfile .
FROM python:3.11-slim

WORKDIR /app
COPY harness/template-agent/pyproject.toml ./
RUN pip install --no-cache-dir claude-agent-sdk openai

COPY harness/template-agent/agent.py ./agent.py

# No production credentials or network access beyond the LiteLLM proxy
# and this agent's declared tools — isolation boundary per §3.3.
