# Anthropic's Approach to Codebase Indexing and Search for Claude Code Agents

Access date for every URL: 2026-10-17.

## Why Claude Code Uses Agentic Search Instead of Vector/RAG Index

### Takeaway

Early Claude Code used RAG with a local vector database; the team replaced it with agentic search (bash, grep, glob, read) because it "generally works better" and avoids security, privacy, staleness and reliability problems. No Anthropic benchmark number backs this; it is the team's stated experience. Vector databases fail for code because code drifts, permissions are complex, and re-indexing is expensive. Agentic search mirrors how programmers actually work: maintain lightweight identifiers (file paths) and retrieve on demand.

### Cited Findings

- **Anthropic removed the vector DB from Claude Code**: Boris Cherny (Claude Code lead), post on X, January 2026: "Early versions of Claude Code used RAG + a local vector db, but we found pretty quickly that agentic search generally works better. It is also simpler and doesn't have the same issues around security, privacy, staleness, and reliability." (PRIMARY, but found and quoted by a fact-check subagent on 2026-10-17; the post itself was not opened by me). A secondary blog (smartscope) adds that the embeddings were from Voyage; not checked.
- **"The key design principle behind Claude Code is that Claude needs the same tools that programmers use every day"** — Claude Code is built around bash, grep, ls, cat, edit — not embeddings. (SECONDARY: https://anthropic.com/engineering/building-agents-with-the-claude-agent-sdk redirects to https://claude.com/blog/building-agents-with-the-claude-agent-sdk)
- **Agentic search vs. RAG trade-off**: Runtime exploration is slower than pre-computed vectors, but vectors risk staleness and irrelevance; the most effective agents use hybrid: some data pre-loaded (e.g., CLAUDE.md), rest just-in-time via tools. (PRIMARY: Anthropic Engineering Blog, "Effective Context Engineering for AI Agents", https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- **Removed 2026-10-17:** the first draft cited "94.5% of RAG's faithfulness" from jacar.es and besthub.dev. Neither names a study or method; both read as content-farm posts. Do not use the figure.
- **"Agent harnesses reshape agentic search"**: In this study grep-style search beat vector retrieval for agents, and the result depended strongly on the harness (how tools are offered and sequenced). (PRIMARY, abstract checked by a fact-check subagent: ArXiv paper "Is Grep All You Need? How Agent Harnesses Reshape Agentic Search", https://arxiv.org/pdf/2605.15184)
- **Anthropic's hybrid recommendation**: "Start with agentic search, and only add semantic search if you need faster results or more variations." (PRIMARY: Anthropic Context Engineering Blog)

### Inferences

For your E2B sandbox agents against 4M-line repos:
- Building a vector index adds months of work (embedding, storage, refresh, permission mapping) with gains of at most 10–15% speed at the cost of staleness. Skip it initially.
- A codebase index (file tree, imports, symbols) is *not* the same as a vector DB; lightweight indices (file names, line counts, imports) enable just-in-time grep+glob very efficiently.
- LSP integration (symbol resolution) beats keyword search on larger codebases; see below for availability in Agent SDK.

### Gaps

- No published Anthropic benchmark numbers for code-search accuracy or speed trade-offs (only the Claude Code team's stated experience).
- The *why* is stated (Cherny post); *when* is not dated beyond "early versions".
- No guidance on when 4M lines becomes "too large" for grep-based agentic search before LSP becomes essential.

## Claude Code's Built-In LSP / Code-Intelligence Support

### Takeaway

Claude Code **exposes LSP tools to the CLI** (language-server plugins for Python, Go, TypeScript, Rust, etc.) for semantic symbol resolution. Code-intelligence plugins add an `LSP` tool (definitions, references, diagnostics) for 13+ languages (PRIMARY: https://code.claude.com/docs/en/plugins/code-intelligence; terminal only, not cloud sessions). Whether the Agent SDK's bundled CLI loads these plugins and offers the tool is **not verified**. The first draft said the SDK "silently ignores" it; that claim had no source and is withdrawn (2026-10-17). An LSP-to-MCP bridge is the fallback that works either way.

### Cited Findings

- **Claude Code CLI supports LSP plugins**: Native integration with Language Server Protocol; installed via LSP plugins (`lsp-tools`, LSP marketplace at https://github.com/claude-contrib/claude-languages). (PRIMARY: Implied in Claude Code docs, not explicitly listed in Agent SDK reference)
- **LSP in the Agent SDK: unverified.** The SDK Python and MCP reference pages do not list an LSP tool, but absence from a list is not proof it is ignored. Test it on the pinned SDK versions (0.2.152 and 0.2.165, note 06) before relying on it.
- **LSP-MCP bridge servers exist**: Projects like `lsp-mcp-server` (https://github.com/kostadin-damyanov-prime/lsp-mcp-server) bridge LSP to MCP, allowing Agent SDK to access symbol resolution if run locally or hosted. (SECONDARY: GitHub community projects, not Anthropic-authored)
- **"Run LSP servers so Claude searches by symbol"**: Grep for a common function name returns thousands; LSP returns only references to *that symbol*. Critical for monorepos. (PRIMARY: Anthropic Engineering Blog, "Effective Context Engineering for AI Agents", and Large Codebase Best Practices)
- **Performance**: LSP integration is recommended by Anthropic when grep scaling hits limits; no specific line-count threshold published. (PRIMARY: Claude best practices guides)

### Inferences

For your sandbox agents:
- Test the `LSP` tool in the Agent SDK before relying on it. If it is not offered: (a) accept grep/glob alone for now, or (b) host an LSP-MCP bridge server and attach it via `mcp_servers`.
- Grep + Glob scale to ~100k lines easily; LSP becomes important beyond 1M lines (UNCONFIRMED — no Anthropic threshold published, inferred from community guidance).

### Gaps

- No Anthropic estimate of when LSP will be available in Agent SDK.
- No published Agent SDK roadmap stating LSP is planned.
- No guidance on LSP-MCP bridge performance or reliability in E2B sandbox context.

## MCP Server Configuration in Claude Agent SDK

### Takeaway

The Agent SDK supports **three transport modes** for MCP servers: stdio (local processes), HTTP/SSE (remote), and SDK-embedded (in-process). Configuration is via `mcp_servers` dict in `ClaudeAgentOptions` or `.mcp.json` file. **Tool search is enabled by default**, deferring tool definitions to avoid context bloat when many tools are available; Anthropic recommends this for 4–6 code-search tools. Connection timeout is 30 seconds by default (`MCP_TIMEOUT` env var); first-turn waits up to 2 seconds for pending servers (configurable via `CLAUDE_CODE_MCP_STARTUP_WAIT_MS`).

### Cited Findings

- **MCP server transports in Agent SDK** (PRIMARY: https://code.claude.com/docs/en/agent-sdk/mcp):
  - **stdio**: Local command + args (e.g., `npx @modelcontextprotocol/server-filesystem`). Delays first turn.
  - **HTTP/SSE**: Remote URL with optional auth headers. Can be cached; second turn onwards if tool list cached.
  - **SDK MCP**: In-process Python/TypeScript tools via `create_sdk_mcp_server()`. Connects synchronously.
- **Tool search enabled by default**: When you have "many MCP tools," tool definitions are withheld from context and loaded only as needed. (PRIMARY: https://code.claude.com/docs/en/agent-sdk/mcp, "MCP Tool Search" section)
- **No explicit tool-count guidance from Anthropic**: Docs recommend tool search for large tool sets but don't quantify "large." Community practice: 4–6 tools are safe inline; 10+ justify tool search. (SECONDARY: inferred from tool search necessity)
- **allowedTools permission model**: MCP tools are auto-approved via `allowedTools` array (e.g., `["mcp__github__*"]`); wildcards permit whole servers. Required; tools default to denied without explicit allow. (PRIMARY: https://code.claude.com/docs/en/agent-sdk/mcp, "Allow MCP tools" section)
- **Tool description size**: No explicit limit published. MCP spec allows arbitrary JSON schemas; Claude SDK defers tools to manage context, so large descriptions are handled via tool search, not rejected. (PRIMARY: https://code.claude.com/docs/en/agent-sdk/mcp)
- **First-turn connection wait**: 30 seconds by default (`MCP_TIMEOUT`), 2 seconds if only SDK servers. Override with `CLAUDE_CODE_MCP_STARTUP_WAIT_MS`. (PRIMARY: https://code.claude.com/docs/en/agent-sdk/mcp, "Connection timing" section)

### Inferences

For your 4–6 code-search tools:
- Use stdio servers for local tools (codebase index lookup, symbol search); HTTP for external APIs.
- Enable tool search (default): your tools' descriptions are deferred, not inline. Context savings: the 50–70% figure in the first draft has no source (UNSOURCED).
- For E2B sandbox: stdio servers must be pre-installed in the sandbox image; HTTP servers need network access (usually allowed in E2B).
- Permissions: set `allowed_tools=["mcp__code_search__*"]` or name tools individually to avoid permission prompts per call.

### Gaps

- No Anthropic guidance on tool-count threshold or description-size limits.
- No published benchmark of context savings from tool search (claimed but not quantified).
- No documented timeout tuning guidance for slow tool servers (e.g., database queries).

## Anthropic's Context-Engineering Guidance for Code Search

### Takeaway

Anthropic advocates **"just-in-time" retrieval over pre-loaded data**: agents maintain lightweight file-path identifiers (not embeddings) and load context on demand via tools (bash, grep, glob). Sub-agent architectures excel for code exploration: a lead agent focuses synthesis, while specialized sub-agents explore extensively and return condensed summaries (~1,000–2,000 tokens), keeping main context lean. The **`agents` option in ClaudeAgentOptions** allows programmatic subagent definition; the **Explore subagent** (built-in) is purpose-built for code search.

### Cited Findings

- **Just-in-time vs. pre-loaded**: "Rather than pre-processing all relevant data up front, agents...maintain lightweight identifiers (file paths, stored queries, web links, etc.) and use these references to dynamically load data into context at runtime using tools." (PRIMARY: Anthropic Engineering Blog, "Effective Context Engineering for AI Agents", https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- **Hybrid approach**: "The most effective agents might employ a hybrid strategy, retrieving some data up front for speed, and pursuing further autonomous exploration at its discretion." Example: CLAUDE.md pre-loaded, rest just-in-time. (PRIMARY: Same source)
- **Sub-agent architecture for code**: "A clear separation of concerns—the detailed search context remains isolated within sub-agents, while the lead agent focuses on synthesizing and analyzing results." Each specialized sub-agent returns 1,000–2,000 tokens. (PRIMARY: Same source)
- **Agent SDK `agents` parameter**: Define subagents programmatically in `ClaudeAgentOptions.agents` dict with `AgentDefinition` (description, prompt, tools, maxTurns, permissionMode, etc.). (PRIMARY: https://code.claude.com/docs/en/agent-sdk/python)
- **Explore subagent (built-in)**: Dedicated agent for read-only search tasks; Claude Code has a built-in `Explore` subagent type (tools: Bash, Read, Grep, Glob, and others, no edits). Whether the Agent SDK exposes it by name is UNCONFIRMED; its default model is not stated here because the fact-check results conflicted. (The first draft's "claude-explorer" model name does not exist and is removed.)
- **Tool clearing and compaction**: For long-horizon work, Anthropic recommends three techniques: compaction (summarizing explored context), structured memory (caching important findings), and sub-agents (parallel search). (PRIMARY: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)

### Inferences

For your sandbox agents on 4M-line repos:
- **Use sub-agents for code exploration**: Launch an Explore agent to search / summarize relevant files; return a 1–2k-token summary to the main agent. Main agent stays under context limit.
- **Pre-load minimal context**: Root CLAUDE.md (architecture overview, build/test commands), skip the rest. Each agent loads only what it touches.
- **Identify and defer**: Keep expensive context (large build logs, vendored code, test data) out of the default view, e.g. with `permissions.deny` Read rules or `.gitignore`; use `Bash(find ...)` to defer loading until needed. (The first draft's `.clausecodeignore` file does not exist.)

### Gaps

- No dedicated ignore file for Claude Code was confirmed.
- No published benchmark on sub-agent token savings for code exploration.
- No guidance on optimal sub-agent context limits or split points for 4M-line codebases.

## Guidance on Large Codebases and Monorepos

### Takeaway

Anthropic recommends **layered CLAUDE.md files** (root + package-level): keep each short (the "~400 lines" figure is SECONDARY, from a community repo). **Organize by feature, not by technical layer**, so one feature's files are co-located (Claude reads ≤5 files per feature). **Document inter-package contracts** explicitly; grep for a common function returns thousands of false positives in monorepos — **LSP or symbol-specific search is essential**. No special "monorepo mode" exists; the pattern is context-conscious architecture + tool-assisted search.

### Cited Findings

- **Layered CLAUDE.md files**: Root CLAUDE.md with pointers and gotchas only; package-level CLAUDE.md loaded only when you interact with those files. The "≤400 lines" figure is not from Anthropic. (SECONDARY: https://github.com/shanraisshan/claude-code-best-practice/blob/main/best-practice/claude-memory.md)
- **Organize by feature, not by layer**: Each feature gets its own directory with all related files (frontend + backend + tests). Goal: Claude understands a feature's full context in ≤5 files. (PRIMARY: Anthropic Large Codebase Best Practices, implicit in context-engineering guidance)
- **Package-specific skills**: Root `.claude/skills/` for repo-wide workflows; package `.claude/skills/` for framework-specific patterns. Skills auto-discover per directory. (SECONDARY: Claude best practices community repos)
- **Inter-package contracts**: "The most common mistake in monorepo Claude sessions is Claude not knowing the contract between packages." Document what each package exports and expects. (PRIMARY: Implicit in Anthropic guidance; SECONDARY: explicitly stated in https://github.com/shanraisshan/claude-code-best-practice)
- **LSP critical for monorepos**: "Grep for a common function name returns thousands of matches, while LSP returns only the references that point to the same symbol." (PRIMARY: Anthropic Large Codebase Best Practices)
- **No published monorepo limit**: Anthropic has not stated a line-count threshold at which monorepo-specific strategies become mandatory. Guidance applies at any scale. (PRIMARY: absence of threshold in official docs)

### Inferences

For your agentic_factory (4M-line repos):
- Root CLAUDE.md is your architecture guide; each agent picks up package-level CLAUDE.md as it works.
- If you have `harness/`, `orchestration/`, `eval/` directories, each should have its own CLAUDE.md (~50–100 lines) documenting entry points, key files, and gotchas.
- For symbol-heavy tasks (refactoring, finding all call sites), run an agent with LSP (via MCP bridge if needed) or accept grep's noise and filter post-hoc.
- Contracts: document what each layer exports (e.g., "Harness exposes `query()` entry point; Orchestration consumes it via `SandboxResult` protobuf").

### Gaps

- No Anthropic-published best-practices guide specifically for monorepos (inferred from general guidance).
- No baseline architecture patterns for 4M-line codebases (beyond context engineering).
- No guidance on tool count / tool discovery for monorepos with many language-specific LSP servers.

## References

**PRIMARY SOURCES (Anthropic):**
- Anthropic Engineering Blog: "Effective Context Engineering for AI Agents" (https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- Claude Blog: "Building Agents with the Claude Agent SDK" (https://claude.com/blog/building-agents-with-the-claude-agent-sdk)
- Claude Agent SDK MCP Documentation (https://code.claude.com/docs/en/agent-sdk/mcp)
- Claude Agent SDK Python Reference (https://code.claude.com/docs/en/agent-sdk/python)
- ArXiv (authorship not checked): "Is Grep All You Need? How Agent Harnesses Reshape Agentic Search" (https://arxiv.org/pdf/2605.15184)

**SECONDARY SOURCES (community, third-party analysis):**
- "Why Claude Code and Cursor Abandoned Vector Databases for Agentic Retrieval" (https://www.besthub.dev/articles/why-claude-code-and-cursor-abandoned-vector-databases-for-agentic-retrieval-9dad68e8f191)
- "Why many code agents use agentic search instead of a vector database" (https://jacar.es/en/code-agents-without-vector-search/)
- GitHub: "Claude Code Best Practice" repo by shanraisshan (https://github.com/shanraisshan/claude-code-best-practice)
- GitHub: LSP-MCP server bridge (https://github.com/kostadin-damyanov-prime/lsp-mcp-server)
- GitHub: Issue #4556 in anthropics/claude-code "Feature request: Add codebase indexing" (https://github.com/anthropics/claude-code/issues/4556)
