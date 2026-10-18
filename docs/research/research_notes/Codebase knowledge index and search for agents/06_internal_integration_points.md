# Internal map: where a code index would plug into the agents

Written 2026-10-17 from a read-only sweep of this repo (one Explore subagent). The SDK versions and
clone lines were re-checked by hand. Citations are `path:line` as of commit `704ed29`. Note 06 of
`Agent memory and large codebase context` covers clone depth, sandbox size and context budget; this
note does not repeat it.

### Takeaway

No agent attaches an MCP server or a subagent today, so a code-search service is a new, additive
option on `ClaudeAgentOptions`, not a change to any existing tool. Every agent works from its own
fresh clone, and each tool-using agent searches it with `Grep`/`Glob` (swe-agent also has `Bash`).

## 1. Agent options

### Cited Findings
- swe-agent `build_options`: `cwd`, `allowed_tools=["Bash", "Read", "Edit", "Write", "Grep", "Glob"]`,
  `permission_mode="bypassPermissions"`, `env` (set when a seat is used). `setting_sources` is left at
  its default (`harness/swe-agent/agent.py:318-337`).
- architect candidates: `cwd`, `tools=["Read", "Grep", "Glob"]`, `setting_sources=[]`, `model`, `env`
  (`harness/architect-agent/agent.py:313-321`). Judge, synthesis and critic: `tools=[]`,
  `setting_sources=[]` (`harness/architect-agent/agent.py:136-141`).
- pm `review_spec`: `cwd`, `tools=["Read", "Grep", "Glob"]`, `setting_sources=[]`, `env`
  (`harness/pm-agent/agent.py:294-305`). pm `shape_issue`: `tools=[]` (`harness/pm-agent/agent.py:202-206`).
- **Checked by hand:** no agent sets `mcp_servers` or `agents`.

### Inferences
- An index server would be passed as `mcp_servers=...` and its tools added to `allowed_tools`/`tools`.
  Because the architect candidates and `review_spec` use an explicit `tools` list, each one must name
  the new tools; nothing reaches them by default.

## 2. SDK versions

### Cited Findings
- **Checked by hand:** all three `pyproject.toml` files ask for `claude-agent-sdk>=0.2.152` (pm-agent
  has no lower bound). The locks pin 0.2.165 for swe-agent and 0.2.152 for architect-agent and pm-agent
  (`harness/*/uv.lock`). The sandbox image installs `claude-agent-sdk>=0.2.152` with no lock
  (`sandbox/swe-agent/Dockerfile:27`).

### Gaps
- Whether `mcp_servers` and the `LSP` tool behave the same in 0.2.152 and 0.2.165 is not checked.

## 3. Sandbox

### Cited Findings
- Base image `python:3.11-slim`; tools git, curl, jq, gh, uv, Braintrust and the Agent SDK
  (`sandbox/swe-agent/Dockerfile`). 2 vCPU, 1024 MB (`sandbox/swe-agent/e2b.toml:9-10`).
- The sweep found no network-egress restriction for the sandbox in `orchestration/activities.py`.

### Inferences
- A remote index service (HTTP MCP) would be reachable from the sandbox, as long as it is reachable
  from the internet or a network the sandbox can use. A local index built inside the sandbox would
  compete for the 1 GB of memory.

## 4. Clones and task lists

### Cited Findings
- **Checked by hand:** swe-agent clones with full history (`harness/swe-agent/agent.py:146`). The
  architect (`harness/architect-agent/agent.py:243`) and pm `review_spec`
  (`harness/pm-agent/agent.py:273`) each make their own `--depth 1 --branch` clone on the worker host.
  The Eval-Gate makes a fourth (`orchestration/activities.py:344`).
- swe-agent requires `specs/*/tasks.md` in the checkout (`harness/swe-agent/agent.py:159`) and names
  the tasks file in its per-task prompt (`harness/swe-agent/agent.py:61-68`).

### Inferences
- One run clones the same target repo up to four times. An index built once per commit could serve
  all of them.
- The file paths that `tasks.md` names are a ready seed for a task-specific repo map.

## 5. Existing mentions

### Cited Findings
- No agent code, spec under `specs/`, workflow or `CLAUDE.md` mentions a code index, repo map, ctags,
  LSP, Zoekt, Sourcegraph, Serena or embeddings. The only mentions are in
  `docs/research/research_notes/Agent memory and large codebase context/04_code_search_at_scale.md`
  and the report built on it.
- `docker-compose.yml` runs Temporal (+ Postgres, UI), Langfuse (+ Postgres, ClickHouse) and LiteLLM.
  No code-search service.

### Gaps
- The sweep did not check how the worker host would reach an index service, or where index files
  would be stored.
