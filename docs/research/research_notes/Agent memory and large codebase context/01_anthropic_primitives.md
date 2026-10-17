# Anthropic Primitives: Agent Memory and Context Management

Access date for every URL: 2026-10-17.

## 1. Claude API Memory Tool

### Takeaway
The memory tool lets Claude store and retrieve information across conversations in a client-managed directory of files. Memory operates client-side: Claude requests file operations (view, create, str_replace, insert, delete, rename), and the application executes them against storage you control. It enables just-in-time context retrieval—agents record what they learn in memory files and read them on demand, avoiding context window overload in long-running sessions.

### Cited Findings
- Memory tool is available on all Claude 4 and later models; configured with `{"type": "memory_20250818", "name": "memory"}` — [Memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool) PRIMARY
- No measured gains or quantified benefits published; documentation frames it as a pattern for keeping context focused on current task — [Memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool) PRIMARY
- SDKs ship ready-made local-filesystem implementation `BetaLocalFilesystemMemoryTool` (Python, TypeScript); path validation required for security (reject paths outside `/memories`) — [Memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool) PRIMARY
- Pairs with compaction: "For long-running agents, consider using both: compaction keeps the active context small without client-side bookkeeping, and memory preserves the information that must survive summarization" — [Memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool) PRIMARY
- Multisession pattern: first session creates progress log + feature checklist + startup script; subsequent sessions resume from memory files, treating them as recovery mechanism — [Memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool) PRIMARY

### Inferences
Memory is client-side by design (your app executes the file ops), making it maximally flexible but requiring application-layer implementation. The multisession pattern is key for long-running agentic work: mark features complete only after end-to-end verification, not when code is written.

### Gaps
No published evaluations or token-usage measurements. No guidance on optimal memory file organization for large-scale agent systems (e.g., indexing strategies).

---

## 2. Context Editing and Clearing

### Takeaway
Context editing allows selective removal of old content (tool results or thinking blocks) by rule, on the server before the prompt reaches Claude. Two strategies: Tool Result Clearing (clears oldest tool results when input tokens exceed threshold, replaces with placeholder text) and Thinking Block Clearing (manages `thinking` blocks, configurable per model). Both run server-side; the client maintains the full conversation.

### Cited Findings
- Tool result clearing invalidates cached prompt prefixes; use `clear_at_least` parameter to clear enough tokens to justify cache invalidation cost — [Context Editing](https://platform.claude.com/docs/en/build-with-claude/context-editing) PRIMARY
- Thinking block clearing preserves prompt cache when thinking is kept (not cleared), but clears cache when thinking is removed; configuration of `keep` parameter affects tradeoff between cache performance and context availability — [Context Editing](https://platform.claude.com/docs/en/build-with-claude/context-editing) PRIMARY
- For most use cases, server-side compaction is the primary strategy; context editing is useful for specific scenarios requiring fine-grained control — [Context Editing](https://platform.claude.com/docs/en/build-with-claude/context-editing) PRIMARY
- Response includes `context_management.applied_edits` showing what was cleared (number of tool uses, input tokens cleared) — [Context Editing](https://platform.claude.com/docs/en/build-with-claude/context-editing) PRIMARY

### Inferences
Context editing is a complement to compaction, not a replacement. It is best for agentic workflows with heavy tool use where old results are no longer relevant. The interaction with prompt caching is critical: clearing invalidates caches, so the decision to clear must balance context savings against cache costs.

### Gaps
No published evaluations of token savings on real workloads. No guidance on optimal thresholds for tool result clearing.

---

## 3. Prompt Caching

### Takeaway
Prompt caching reduces cost and latency by caching and reusing prompt prefixes. Content that stays constant (system prompt, tool definitions, CLAUDE.md) is cached once and reused across requests. Cache reads cost 0.1× base input price (or 0.025-0.05× on some models); cache writes cost 1.25× (5-min TTL, default) or 2× (1-hour TTL). Breaks even after one cache read at 5-min TTL, after two reads at 1-hour TTL.

### Cited Findings
- Cache writes (5-min): 1.25x base input tokens; writes (1-hour): 2x base input — [Prompt Caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) PRIMARY
- Cache reads: 0.1x base input on most models; Claude Fable 5.1 / Mythos 5.1 use 0.025x; Opus 5.5 / Sonnet 5.5 use 0.05x — [Prompt Caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) PRIMARY
- Minimum cacheable prompt: 512 tokens (varies by model); exact 100% match required for cache hits; up to 4 explicit breakpoints per request; 20-block lookback window — [Prompt Caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) PRIMARY
- TTL measured from start of request, not end. Cache entries available only after first response begins — [Prompt Caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) PRIMARY
- Recommended for: prompts with many examples, large background context, repetitive tasks, long multi-turn conversations, large documents, stable tool definitions — [Prompt Caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) PRIMARY

### Inferences
Prompt caching is most valuable for agentic systems where the same system prompt and tool definitions are reused across many turns. The cost formula (1.25x write, 0.1x read) makes caching economical only when the same prefix is reused at least twice.

### Gaps
No measured adoption rates or typical cost savings on published workloads.

---

## 4. Compaction (Server-Side)

### Takeaway
Compaction replaces older turns of a conversation with a summary Claude writes on the server. Two variants: on-demand (you request summary when needed) and threshold-based (API triggers when tokens exceed threshold). On-demand is recommended; recent turns stay word-for-word if preserved. Keeps long conversations inside context window and keeps active context small.

### Cited Findings
- On-demand compaction: you send a request, API returns a summary block that replaces the messages it summarizes; you send the block first in next request — [Compaction](https://platform.claude.com/docs/en/build-with-claude/compaction) PRIMARY
- Threshold compaction: one parameter on ordinary requests; API drops what came before the summary block automatically — [Compaction](https://platform.claude.com/docs/en/build-with-claude/compaction) PRIMARY
- On-demand supports keeping recent turns (summary covers only older turns, recent ones stay verbatim) and background processing (summary request runs while work continues) — [Compaction](https://platform.claude.com/docs/en/build-with-claude/compaction) PRIMARY
- Kept turns preserve their `thinking` blocks on models with preserved thinking (conditional) — [Compaction](https://platform.claude.com/docs/en/build-with-claude/compaction) PRIMARY
- No quantified token-saving measurements in documentation — [Compaction](https://platform.claude.com/docs/en/build-with-claude/compaction) PRIMARY

### Inferences
On-demand compaction gives you control over when summarization happens and what to keep; threshold compaction automates the decision but lacks the flexibility. Neither has published token-usage benchmarks.

### Gaps
No measured token savings or quality impact on real multi-hour agent tasks.

---

## 5. Claude Agent SDK: Automatic Context Compaction

### Takeaway
The Agent SDK's `compaction_control` parameter automatically summarizes conversation history when token usage exceeds a threshold (default 100k). Results show 58.6% token savings on a customer service ticket workflow (204k → 82k input tokens). Compaction clears conversation history and discards detailed tool results but preserves the summary. Configuration allows custom thresholds, optional cheaper summarization model (e.g., Haiku), and custom summary prompt.

### Cited Findings
- Customer service workflow (5 tickets): input tokens 204k → 82k, total 208k → 86k with compaction = 58.6% savings — [Automatic Compaction](https://platform.claude.com/cookbook/tool-use-automatic-context-compaction) PRIMARY
- Configuration: `compaction_control={"enabled": True, "context_token_threshold": 5000, "model": "claude-haiku-4-5", "summary_prompt": "..."}` — [Automatic Compaction](https://platform.claude.com/cookbook/tool-use-automatic-context-compaction) PRIMARY
- Low threshold (5-20k): frequent compaction for sequential processing; medium (50-100k): multi-phase; high (100-150k+): substantial history needed; default 100k — [Automatic Compaction](https://platform.claude.com/cookbook/tool-use-automatic-context-compaction) PRIMARY
- Not optimal with server-side sampling (web search, extended thinking); summaries lose details; not for full audit trails — [Automatic Compaction](https://platform.claude.com/cookbook/tool-use-automatic-context-compaction) PRIMARY
- Ideal for sequential processing, multi-phase workflows, iterative data processing, extended analysis, customer service tickets — [Automatic Compaction](https://platform.claude.com/cookbook/tool-use-automatic-context-compaction) PRIMARY

### Inferences
The 58.6% savings (real measured data) is the strongest quantified benefit for context management in the Anthropic docs. The pattern is SDK-level automation that trades some detail loss for significant token savings. Threshold defaults (100k) are conservative; lower thresholds useful for sequential batch operations.

### Gaps
Results on only one workflow. No data on quality/correctness impact of summarization.

---

## 6. Effective Context Engineering for AI Agents

### Takeaway
Anthropic's context engineering post identifies five core strategies: system prompt optimization (find "right altitude"—specific enough to guide, flexible enough to provide heuristics), tool design (minimal, well-understood, minimal overlap), few-shot prompting (diverse canonical examples, not exhaustive edge cases), just-in-time context retrieval (dynamically load via tools, don't preprocess everything), and long-horizon techniques (compaction, structured note-taking, sub-agent architectures). No quantified metrics; emphasis on practical improvements: enhanced agent coherence, reduced context pollution, better autonomy.

### Cited Findings
- Five core strategies: system prompt altitude, tool design, few-shot examples, just-in-time retrieval, long-horizon techniques — [Effective Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) PRIMARY
- Practical improvements: enhanced coherence across extended tasks, reduced context pollution, better autonomy — [Effective Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) PRIMARY
- Case study: Claude Code file navigation and Pokémon agent maintaining "multi-hour training sequences" — [Effective Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) PRIMARY
- Overarching principle: find "the smallest set of high-signal tokens that maximize the likelihood of your desired outcome" — [Effective Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) PRIMARY
- No quantitative benchmarks or token-usage measurements — [Effective Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) PRIMARY

### Inferences
This post frames context engineering as a top-level design discipline, not a tactical fix. The emphasis on "right altitude" and "high-signal tokens" applies across all the mechanisms (memory, compaction, caching, skills). No measured gains published, but examples (Claude Code, Pokémon) suggest multi-hour coherence is feasible.

### Gaps
No quantified token savings or task-completion metrics. No guidance on how to systematically measure context engineering effectiveness.

---

## 7. Claude Code Memory: CLAUDE.md and Auto-Memory

### Takeaway
Claude Code sessions start fresh but carry forward knowledge via two mechanisms: CLAUDE.md files (you write instructions, project-scoped or user-scoped) and auto-memory (Claude writes learnings). CLAUDE.md is loaded into every session as context; auto-memory is first 200 lines or 25KB. Project-root CLAUDE.md survives `/compact`—re-injected from disk after compaction. Nested CLAUDE.md in subdirectories load on demand per file touched.

### Cited Findings
- CLAUDE.md files: instructions you write, project/user/org scope, loaded into every session — [Memory](https://code.claude.com/docs/en/memory) PRIMARY
- Auto-memory: notes Claude writes itself based on corrections/preferences, per-repository, shared across worktrees, capped at first 200 lines or 25KB — [Memory](https://code.claude.com/docs/en/memory) PRIMARY
- Project-root CLAUDE.md re-injected after `/compact`; nested files reload on demand — [Memory](https://code.claude.com/docs/en/memory) PRIMARY
- SessionStart hook fires on new session, resume, or after `/clear`; can inject additional context, set initial message, watch paths, reload skills — [Hooks](https://code.claude.com/docs/en/hooks) PRIMARY
- PreCompact hook fires before compaction; can block with `decision: "block"` and reason — [Hooks](https://code.claude.com/docs/en/hooks) PRIMARY

### Inferences
Claude Code's memory design separates static instructions (CLAUDE.md) from dynamic learnings (auto-memory). Hooks enable automation and validation around context events (SessionStart, PreCompact). The 200-line auto-memory cap keeps it lean; CLAUDE.md persists instructions indefinitely.

### Gaps
No guidance on CLAUDE.md organization for very large projects (what goes in project vs user vs org scope). No metrics on auto-memory effectiveness.

---

## 8. Agent Skills: Progressive Disclosure

### Takeaway
Skills use filesystem-based progressive disclosure: metadata (name, description) pre-loaded at startup; SKILL.md read on-demand when triggered; reference files and scripts loaded only as needed. No context penalty for bundled content until accessed. This architecture lets skills include comprehensive docs, examples, data, and scripts without bloating context. Patterns: high-level guide with references, domain-specific organization, conditional details, one-level-deep references (avoid nested links).

### Cited Findings
- Metadata pre-loaded at startup; SKILL.md read on-demand when skill triggered; files accessed as needed via bash Read — [Skills Best Practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) PRIMARY
- No context penalty for large files until accessed; example: BigQuery skill has separate `reference/finance.md`, `reference/sales.md`, etc.; when user asks about revenue, Claude reads only `finance.md` — [Skills Best Practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) PRIMARY
- Keep SKILL.md body under 500 lines; split into reference files beyond that — [Skills Best Practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) PRIMARY
- Pattern 1: High-level guide + references; Pattern 2: Domain-specific organization (finance, sales, product modules); Pattern 3: Conditional details (basic first, link advanced) — [Skills Best Practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) PRIMARY
- One-level-deep references avoid partial reads; nested references (reference → reference → reference) cause Claude to preview with `head -100` instead of reading complete files — [Skills Best Practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) PRIMARY

### Inferences
Progressive disclosure is a filesystem-based implementation of "load on demand." The 500-line SKILL.md cap and one-level-deep references are concrete design constraints that ensure Claude can navigate and load precisely what's needed. The BigQuery example (four domain modules) shows how domain-specific org scales without context bloat.

### Gaps
No metrics on typical skill context overhead or discovery latency. No guidance on skill organization for 100+ skills per user.

---

## 9. Building Agents with Claude Agent SDK

### Takeaway
Core pattern: gather context → take action → verify work → repeat. Practical techniques: agentic search (filesystem exploration via grep/tail, not semantic search), subagents (parallelization + context isolation), compaction (auto-summarize), tools (primary execution), bash scripts (flexible work), MCPs (external services), feedback (rule-based linting, visual screenshots, LLM judging). No published evaluations.

### Cited Findings
- Core loop: gather → act → verify → repeat, with feedback mechanisms — [Building Agents](https://claude.com/blog/building-agents-with-the-claude-agent-sdk) PRIMARY
- Agentic search: filesystem exploration via bash (grep, tail) as "form of context engineering," not semantic search — [Building Agents](https://claude.com/blog/building-agents-with-the-claude-agent-sdk) PRIMARY
- Subagents: enable parallelization, context isolation, filtering irrelevant info back to main agent — [Building Agents](https://claude.com/blog/building-agents-with-the-claude-agent-sdk) PRIMARY
- Compaction: SDK auto-summarizes conversation as context limit approaches — [Building Agents](https://claude.com/blog/building-agents-with-the-claude-agent-sdk) PRIMARY
- Feedback: rule-based (linting), visual (screenshots), LLM-judging (fuzzy evaluation) — [Building Agents](https://claude.com/blog/building-agents-with-the-claude-agent-sdk) PRIMARY

### Inferences
The emphasis on filesystem-based agentic search (not semantic) aligns with Claude Code's Read/Grep/Glob tools. Subagents are presented as a scaling mechanism (parallelization) and context management tool (isolation). Feedback loops are key to error correction.

### Gaps
No published agent evaluations. No guidance on when to use tools vs bash vs code generation.

---

## 10. Effective Harnesses for Long-Running Agents

### Takeaway
Two-part architecture: initializer agent (first-run setup, create foundational files) + coding agent (subsequent sessions, incremental progress). Memory consists of three components: progress file (log of what was done), feature list (JSON, complete vs failing), git history (revert mechanism). Session startup routine: read progress, review git logs, run basic tests, select next priority. Work one feature at a time; mark complete only after end-to-end verification. Clean handoffs leave each session in production-ready state.

### Cited Findings
- Two-part harness: initializer (first run) + coding agent (subsequent) — [Effective Harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) PRIMARY
- Memory architecture: progress file (log), feature list (JSON, complete vs failing), git history — [Effective Harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) PRIMARY
- Feature list prevents premature completion; process one feature at a time — [Effective Harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) PRIMARY
- Session startup: read progress, review git logs, run basic tests, select next feature — [Effective Harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) PRIMARY
- Git discipline: descriptive commit messages, revert broken changes; testing via browser automation like human users — [Effective Harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) PRIMARY

### Inferences
This pattern combines external memory (progress file, feature list) with git-based recovery (revert) and human-like testing (browser automation). The emphasis on "mark complete only after end-to-end verification" prevents false progress. Session startup is optimized for rapid context acquisition (no re-discovery).

### Gaps
No published token-usage metrics or multi-session performance data.

---

## 11. Multi-Agent Research System

### Takeaway
Orchestrator-worker pattern: lead agent analyzes queries, develops strategy, spawns subagents that explore independently and return summaries. Token usage is substantial: regular agents use 4× more tokens than chat; multi-agent systems use 15× more. Token usage alone explains 80% of variance in performance. Context management: external memory for plan before reaching 200k-token limit, summarize completed work phases, spawn fresh subagents with clean contexts, store work in filesystem outputs to reduce copying through conversation.

### Cited Findings
- Regular agents: ~4x tokens vs chat; multi-agent: ~15x tokens vs chat — [Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system) PRIMARY
- Token usage explains 80% of performance variance in browsing evaluations — [Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system) PRIMARY
- External memory: lead saves research plan before context limit (200k+) — [Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system) PRIMARY
- Fresh subagents with clean contexts, continuity via careful handoffs; filesystem outputs reduce token copying — [Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system) PRIMARY
- Pattern: summarize completed phases, store in external memory before new tasks — [Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system) PRIMARY

### Inferences
This is the most token-intensive pattern (15× chat). The emphasis on external memory and filesystem outputs shows conscious design to avoid copying large results through conversation history. Fresh subagents with handoffs mirrors the "clean handoff" pattern from effective harnesses. Token usage as the dominant performance factor (80%) validates all context-management investment.

### Gaps
No per-component token-usage breakdown (lead vs subagent, search vs synthesis).

---

## 12. Writing Effective Tools for Agents

### Takeaway
Tool design is prompt engineering: selective (more tools ≠ better outcomes), namespaced (prefix-based grouping), context-aware (return high-signal info only), clearly described. Token-efficient responses are critical: pagination, filtering (sensible defaults), truncation with guidance, informative errors, strategic response format (XML/JSON/Markdown optimized per use case). Semantic identifiers (natural language names) outperform cryptic UUIDs.

### Cited Findings
- Selectivity: focus on high-impact workflows, consolidate functionality to reduce context — [Writing Tools](https://www.anthropic.com/engineering/writing-tools-for-agents) PRIMARY
- Namespacing: consistent prefixes (e.g., `asana_projects_search`, `asana_users_search`) help agents distinguish and select — [Writing Tools](https://www.anthropic.com/engineering/writing-tools-for-agents) PRIMARY
- Meaningful context: return only high-signal info; semantic identifiers (natural language) >> cryptic UUIDs; agents perform significantly better with natural names — [Writing Tools](https://www.anthropic.com/engineering/writing-tools-for-agents) PRIMARY
- Clear descriptions: explain as to a new team member; use unambiguous parameter names — [Writing Tools](https://www.anthropic.com/engineering/writing-tools-for-agents) PRIMARY
- Token efficiency: pagination, filtering with defaults, truncation + guidance, informative errors, strategic response format — [Writing Tools](https://www.anthropic.com/engineering/writing-tools-for-agents) PRIMARY

### Inferences
Tool design for agents is about controlling what information enters the context window. Semantic identifiers and natural language outperform technical IDs. Pagination + filtering with defaults is more context-efficient than flexible responses agents must interpret.

### Gaps
No measured impact of tool-description engineering on agent performance.

---

## 13. Code Search Strategy: Agentic vs Vector Index

### Takeaway
Claude Code uses agentic search (Grep, Glob, Bash find/grep) not vector embedding indices. This is implied rather than explicitly stated: the building-agents post frames agentic search as "a form of context engineering," and Claude Code docs show Read, Glob, Grep as primary search tools. No primary source found that explicitly addresses "why no embedding index."

### Cited Findings
- Agentic search (filesystem exploration via bash) described as "a form of context engineering" — [Building Agents](https://claude.com/blog/building-agents-with-the-claude-agent-sdk) PRIMARY
- Claude Code tools: Read (files), Grep (search text), Glob (find by name pattern), Bash (find, grep) — [Tools Reference](https://code.claude.com/docs/en/tools-reference) PRIMARY
- No explicit statement about why no vector index — SECONDARY (inference from docs structure, no primary source)

### Inferences
Agentic search (with exact pattern matching) is deterministic and doesn't consume inference tokens. It is easier to debug than semantic search. Exact-match search is also cache-friendly (same query hits same cache). However, this is inference; Anthropic has not published a direct comparison.

### Gaps
No primary source explaining design decision against vector embeddings. This is a significant gap in the published guidance.

---

## Summary of Decision-Relevant Findings

**Strongest quantified results:**
- Automatic compaction: 58.6% token savings on customer-service workflow (204k → 82k inputs)
- Multi-agent systems: 15× tokens vs single chat; token usage explains 80% of performance variance
- Prompt caching: breaks even after 1 cache hit (5-min TTL) or 2 hits (1-hour TTL)

**Most actionable patterns:**
- External memory (progress files, feature lists) + git for recovery (effective harnesses)
- Progressive disclosure via filesystem (skills load on-demand, no context penalty until accessed)
- Two-tier agents: lead orchestrates, subagents explore independently with clean contexts

**Largest gaps:**
- No published token-usage metrics for memory tool or on-demand compaction
- No agent-performance evaluations comparing context-engineering strategies
- No explanation of why Claude Code chose agentic search (grep/glob) over semantic search
