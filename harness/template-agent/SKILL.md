---
name: template-agent
description: Skeleton skill definition for a factory-built agent. Copy this directory per new agent (§3.2 Harness/Runtime — Claude Agent SDK, MIT-licensed, markdown skills).
---

# Template Agent

Replace this file's frontmatter and body with the agent's actual skill
definition once its spec (`../../spec/`) is accepted. This file is the
portable artifact the registry (`../../registry/`) tracks per §3.7 — keep
tool bindings and scope declared here, not buried in `agent.py`.

## Scope
<from accepted spec's `goal` field>

## Tools
<from accepted spec's `tools` field — bind as MCP servers or SDK tools>

## Guardrails
<from accepted spec's `guardrails` field>
