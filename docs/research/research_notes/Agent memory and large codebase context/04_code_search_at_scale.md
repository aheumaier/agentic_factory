# Code Search at Scale: Approaches for Coding Agents in Large Codebases

Access date for every URL: 2026-10-17.

Source tags corrected by hand on 2026-10-17: vendor blogs, mirrors and summaries of someone else's work are SECONDARY, even where the agent wrote PRIMARY. Index costs and latencies for 4M LOC are the agent's estimates, not measurements.

## Overview

Coding agents spend 40-60% of their token budget locating code before reasoning about it. At scale—4M LOC monorepos, 100K+ files—no single search strategy dominates. Instead, agents layer three complementary approaches: exact-match keyword search (ripgrep), structural code graphs (LSP, tree-sitter), and semantic embeddings (Greptile, Sourcegraph Cody). This research examines measured trade-offs, benchmarks, and industrial practice.

## Approach 1: Agentic Search (Grep/Ripgrep) vs Semantic/Vector Index

### Takeaway

Ripgrep is the productivity baseline for all major coding agents (Claude Code, Cursor, Codex, Aider). Semantic search adds 12-31% accuracy gain but requires embedding maintenance and index staleness overhead. Hybrid (exact + semantic) is state-of-the-art; pure semantic-only agents are rare.

### Cited Findings

**Ripgrep dominance for agents:** Ripgrep is 10x faster than GNU grep on Linux kernel searches (0.06s vs 0.67s) and returns clean results by default—respects `.gitignore`, skips binaries, searches recursively without flags. Coding agents prefer it because noisy grep output (e.g., node_modules, build artifacts) inflates context tokens (input tokens are ~87% of LLM cost). Ripgrep's filtered output directly reduces latency and operational cost (SECONDARY: https://www.codeant.ai/blogs/why-coding-agents-should-use-ripgrep).

**Cursor semantic search gains:** Cursor reports adding custom semantic search to their grep-based agent improved accuracy by 12.5% on average; 56% on large codebases (1000+ files). However, the full report omits specifics on freshness lag, index overhead, or failure modes (SECONDARY: https://www.plushcap.com/content/cursor/blog/cursor-improving-agent-with-semantic-search).

**Greptile hybrid approach:** Greptile parses the AST, recursively generates docstrings per node, embeds those (not raw code), and supports "agentic search"—the agent reviews relevance and traces references—alongside keyword search. Marketed as handling codebases as "interconnected graphs" rather than documents (SECONDARY: graph/codegraph claims unverified: https://graphify.com/blog/best-codebase-context-tools-for-ai-coding-assistants-2026.md).

### Inferences

Pure vector search fails agents because LLMs hallucinate on approximate matches; exact search succeeds but requires good keyword choice. Hybrid wins: ripgrep for precision + embeddings for discovery ("where do we handle auth?") when grep terms are unknown. Cursor's ~12% gain suggests marginal ROI on complex embedding pipelines—not transformative for agents with access to tool loops.

### Gaps

No published A/B test compares grep-only vs semantic-only agents on SWE-Bench or LoCoBench. Cursor's 12.5% figure lacks method detail (same task distribution? A/B or sequential?). No data on embedding staleness cost (how often re-index for moving targets?).

---

## Approach 2: Repo Maps & Structural Context

### Takeaway

PageRank-based repo maps (Aider, Stripe Minions) achieve 99% context savings (87 tokens instead of 12,000) by ranking symbols by reference frequency. LSP/tree-sitter symbol indexing scales to 28M LOC in 3 minutes; fresh queries complete in <1ms. Reusable across agents.

### Cited Findings

**Aider repo-map (tree-sitter + PageRank):** Three-stage pattern: parse source into ASTs (tree-sitter extracts function signatures, class names, call signatures without bodies), rank files by personalized PageRank on a symbol-reference graph, fit top symbols into token budget via binary search (default 1,024 tokens, 15% overage tolerance). Example codebase: consumed 87 tokens vs ~12,000 raw files—99% reduction. Most effective for large, stable codebases; less suitable for rapidly-changing monorepos or heavy metaprogramming (SECONDARY, Aider's own docs are the primary: https://www.agentpatterns.ai/context-engineering/repository-map-pattern/).

**Codebase-Memory (tree-sitter + knowledge graph MCP):** Indexes Linux kernel (28M LOC, 75K files) in 3 minutes producing 4.81M nodes, 7.72M edges; Django in 6 seconds (49K nodes, 196K edges). Incremental re-indexing via content-hash 4x faster than full. Query performance: Cypher relationship <1ms, regex name search <10ms, call-path trace (depth 5) <10ms. Structural index did not increase costs—agents found right code faster, wasted fewer turns on dead ends (PRIMARY: https://arxiv.org/pdf/2603.27277).

**Serena MCP (LSP tools for agents):** Exposes 21+ LSP tools (30+ languages) as MCP. Agents call `find_symbol`, `find_referencing_symbols`, `insert_after_symbol` with semantic context—tells a column definition from a model field, both named `user_id`. Avoids hallucination on text-only grep (SECONDARY: https://mcp.directory/blog/serena-mcp-complete-guide-2026, https://alguidelines.dev/docs/agentic-coding/communityresources/tools/serena-mcp/).

**Stripe Minions repo map:** Dynamic context selection via personalized PageRank on import/reference graph. Repo map lists files + key symbols (class names, function signatures, exported types) in ~1,000 tokens, giving agent a topology. Agent asks for specific file contents rather than inferring from memory. Coupled with Sourcegraph for precise cross-codebase search (SECONDARY, a newsletter summary of Stripe's posts: https://blog.bytebytego.com/p/how-stripes-minions-ship-1300-prs).

### Inferences

PageRank scales better than naive embedding-based retrieval for monorepos because import graphs are deterministic and reflect actual dependencies. LSP is faster for symbol queries than any embedded model but requires a live server per language.

### Gaps

No comparison of PageRank repo map vs semantic embeddings on the same codebase. Stripe reports 1,300 PRs/week but discloses no code-finding success rate or error budget. Serena's 21+ tools lack a benchmark showing when symbol tools outperform grep.

---

## Approach 3: Code Graph / Symbol Index (SCIP, LSP, tree-sitter)

### Takeaway

Symbol-based code graphs (RepoGraph, LocAgent, AutoCodeRover) reduce token cost 2.5–9x and find answers 9x faster on monorepos than unaided agents. Monorepo-specific: RepoGraph traces cross-language calls (frontend→backend HTTP to handler) without manual annotation.

### Cited Findings

**RepoGraph:** Creates a repo-level code graph (nodes: LOC; edges: dependencies, invocations, containment). Includes ego-graph retrieval (extract sub-graphs around keywords). In a Go+Angular monorepo, RepoGraph achieved 2.5x fewer tokens and ~9x faster results vs baseline for a bug fix. Most effective where hardest by hand: large repos, monorepos spanning languages, multi-service features crossing file/stack/language boundaries (PRIMARY, but PDF slides unreadable: https://www.iclr.cc/media/iclr-2025/Slides/28957.pdf, SECONDARY verified: https://themoonlight.io/review/repograph-enhancing-ai-software-engineering-with-repository-level-code-graph).

**LocAgent (hierarchical code graph):** Parses codebase into directed heterogeneous graph (files, classes, functions, imports, invocations, inheritance). Lightweight representation; enables LLM agents to search and locate entities effectively (PRIMARY: https://arxiv.org/abs/2503.09089v2, detailed method unknown without paper text).

**AutoCodeRover (AST search):** Two-stage: context retrieval using LLM + code-search APIs for AST navigation (methods/classes, not plain-text files); patch generation. Uses stratified multi-API invocation on locally-analyzed AST. When tests exist, applies spectrum-based fault localization. Reported 19% success on SWE-Bench-lite (300 issues), $0.43 USD cost per resolution (PRIMARY: https://arxiv.org/abs/2404.05427).

**Snap's Zoekt (exact-match code search):** Sharded trigram-based search engine indexing millions of files, ~1TB source, updated within minutes of push. Two search modes: exact (sub-second p95 latency for regex/literal/symbol searches), AI (agent loop with planning, evaluation, synthesis—not RAG). "Almost all Code Search traffic comes from agents." Avoids vector DBs: exact matches prevent confident wrong answers, intelligence lives in model's reasoning loop (PRIMARY: https://eng.snap.com/code_search).

### Inferences

Code graphs are fastest for cross-file, cross-language reasoning (RepoGraph's 9x speedup). Exact-match search (Zoekt, ripgrep) beats embeddings for preventing hallucination on large monorepos because agents can iterate through searches and verify. LSP-based approaches (Serena) win for refactoring and safety.

### Gaps

RepoGraph's arXiv link (ICLR 2025) slides not readable; token/latency numbers unverified. LocAgent, AutoCodeRover papers referenced but not fetched in full. Snap's "almost all traffic from agents" is anecdotal, not measured.

---

## Benchmarks Stressing Large Repos

### Takeaway

LoCoBench-Agent (8,000 scenarios, 10K–1M token context) shows agents' comprehension scores 0.71–0.75, efficiency 0.59–0.64. SWE-bench Pro (1,865 enterprise tasks, 41 repos) reveals gap: Claude Opus, GPT-5 ~23% pass rate vs >70% on SWE-Bench Verified. RepoBench (Python, Java, 3 tasks) is the only benchmark isolating retrieval (RepoBench-R) from completion (RepoBench-C).

### Cited Findings

**LoCoBench-Agent:** Extends LoCoBench's 8,000 scenarios across 10 languages into interactive agent environments. Provides 8 tools (file ops, grep, glob, codebase_search, fuzzy file_search). Scores comprehension (5 metrics: execution success, memory retention, cross-file consistency, dependency traversal, solution usability) = 0.71–0.75; efficiency (4 metrics: runtime, memory, info coverage, long-range dependency) = 0.59–0.64. Tests 10K–1M token context lengths (PRIMARY: https://arxiv.org/html/2511.13998v1).

**SWE-bench Pro:** 1,865 problems from 41 real repositories (public, held-out, commercial). Long-horizon tasks (hours to days for engineer). Results: Claude Opus 4.1 = 23.1% (public) → 17.8% (commercial); GPT-5 = 23.3% (public) → 14.9% (commercial). Baseline models on unified scaffold <25%. Compared to SWE-Bench Verified >70%, the gap is stark (PRIMARY: https://arxiv.org/abs/2509.16941).

**RepoBench:** Evaluates repository-level code completion across three tasks: RepoBench-R (retrieval of cross-file context), RepoBench-C (next-line prediction given context), RepoBench-P (end-to-end pipeline). Python and Java; context lengths 2k–16k tokens; metrics EM, Edit Similarity, CodeBLEU (PRIMARY: https://arxiv.org/abs/2306.03091v1; the agent also gave arXiv 2607.24882, which is UNVERIFIED).

**SWE-bench Multilingual:** 300 tasks across 9 languages, 42 repos. Claude 3.7 Sonnet = 43% resolve rate (vs 63% on Verified). Baseline agents on unified scaffold show language-dependent performance gaps (PRIMARY ref: https://swebench.com/multilingual).

### Inferences

LoCoBench efficiency scores (0.59–0.64) suggest agents waste 36–41% of their reads on non-essential code, pointing to a real localization gap. The 46–53% drop from Verified to Pro/commercial tasks shows enterprise codebases (larger, less documented, cross-language) remain hard.

### Gaps

No benchmark isolates impact of code-search tool (grep vs embedding vs graph) on agent performance; all benchmarks use agent frameworks that bundle multiple strategies. RepoBench is the only one isolating retrieval, but results not cited.

---

## Industrial Practice: Monorepo / Large-Scale Deployment

### Takeaway

Stripe (1,300 PRs/week), Uber (84% of devs using agents, 65K diffs/week across 6 monorepos), Meta, and Google use scoped context (AGENTS.md files, per-directory rules), dynamic selection (PageRank), and exact-match search (Sourcegraph, Zoekt, ripgrep). Vector-only approaches are rare; all mature deployments layer exact + structural.

### Cited Findings

**Stripe Minions:** Operates across a 50-service monorepo (tens of millions of tokens). Scopes coding rules to subdirectories—agent picks up only relevant conventions as it moves through the filesystem. Curates tool subsets per task (~500 tools available via MCP Toolshed; agents given small default set). Personalized PageRank on dependency graph ranks files; repo map fits into ~1,000 tokens. Integrates Sourcegraph for precise code search. Reported 1,300 PRs/week with zero human code; devbox startup ~10 seconds; 3M tests available; max 2 CI iterations before returning to humans (SECONDARY, a newsletter summary of Stripe's posts: https://blog.bytebytego.com/p/how-stripes-minions-ship-1300-prs; secondary claims lack specifics on code-finding error rate or review backlog).

**Uber (agentic SDLC):** Four-layer architecture: AI platform, context sources, industry tools, specialized agents. Internal "Minion" background agent with monorepo access and optimized defaults. GenAI code reviewer (uReview) analyzes >90% of ~65K diffs/week across 6 monorepos; 84% of developers using agentic coding (March 2026). Internal tools: MCP Gateway, Uber Agent Builder, AIFX CLI (PRIMARY: https://newsletter.pragmaticengineer.com/p/how-uber-uses-ai-for-development, https://ai.engineer/talks/17-YSUHo6Lk-agentic-sdlc-at-uber-building-blocks-ubers).

**Google Code Search + Kythe:** Code Search (internal tool; open-source version available) with cross-references powered by Kythe (symbol index). Supports Bazel, CMake, Maven, Go for open-source integration. Agents and engineers use it for "searching half-remembered functions, jumping through the codebase, identifying when/why a line changed" (PRIMARY: https://opensource.googleblog.com/2020/04/code-search-for-google-open-source.html).

**Sourcegraph Cody/Amp on monorepos:** Uses code graph (symbol references, definitions, callers—not naive embeddings) for retrieval. Correctly answers "find every caller of this function" across millions of lines. Indexes horizontally via sharding; agnostic to monorepo vs multi-repo. Stripe, Meta, and others rely on it for agent context (PRIMARY: https://5.10.sourcegraph.com/admin/monorepo, secondary: Stripe blog and others).

**Snap's Zoekt:** Sharded trigram search engine indexing millions of files (~1TB source), updated within minutes. Sub-second p95 latency. "Almost all Code Search traffic comes from agents." Language-agnostic (no compiler plugins), exact-first approach (PRIMARY: https://eng.snap.com/code_search).

**Windsurf Fast Context:** "SWE-grep" and "SWE-grep-mini" custom models for rapid code retrieval, 20x faster than agentic search. Separates indexed context (full semantic graph) from active context (what model processes). Performs reliably on ~50K files; above 100K files indexing time increases, accuracy decreases (PRIMARY: https://docs.windsurf.com/context-awareness/fast-context).

### Inferences

Mature monorepo deployments converge on three layers: (1) exact-match search (ripgrep, Zoekt, Code Search) as foundation, (2) structural context via PageRank repo maps or symbol graphs, (3) semantic search as optional discovery. Scoped rules (AGENTS.md, per-directory conventions) matter as much as code search. No published data on code-finding success rates, only task completion counts (PRs, diffs).

### Gaps

Stripe, Uber, Google, Meta publish no benchmarks isolating code-search tool impact. "1,300 PRs/week" is an output metric, not a localization metric. Windsurf's "20x faster" claims lack method detail or independent verification. No monorepo vendor publishes recall or precision for their code-finding pipeline.

---

## Practical Tooling & Costs

### Takeaway

Ripgrep + tree-sitter cover 80% of agent code-search needs with <100ms indexing latency. Full semantic indexing (Codebase-Memory, Greptile) is optional and costs 3–10 seconds per full rebuild. LSP scales to 30+ languages; tree-sitter supports 158 grammars. No single tool fits all use cases; agents need composition.

### Cited Findings

**Ripgrep:** Written in Rust, parallelizes across CPU cores by default. Respects `.gitignore`, skips binaries, searches recursively without flags. 10x faster than grep on large codebases. Every major agent ships it (Claude Code, Cursor, Codex, Aider) (SECONDARY: https://www.codeant.ai/blogs/why-coding-agents-should-use-ripgrep).

**Tree-sitter:** Parses 158 grammars (embedded in static binary, no dynamic loading). Supports nested tree parsing; used by Aider repo-map, Codebase-Memory, RepoGraph. Fast incremental updates via content-hash (PRIMARY: https://arxiv.org/pdf/2603.27277).

**LSP (Language Server Protocol):** Serena MCP exposes 30+ languages via LSP. Live servers; no static indexing overhead. <1ms queries after parse. Primary tools: `find_symbol`, `find_references`, `insert_after_symbol`. (SECONDARY: https://alguidelines.dev/docs/agentic-coding/communityresources/tools/serena-mcp/).

**Codebase-Memory (tree-sitter + graph MCP):** Linux kernel: 3 minutes to 4.81M nodes, 7.72M edges. Incremental 4x faster. Query times: <1ms Cypher, <10ms regex, ~150ms dead-code scan, <10ms call-path (depth 5). Structural index reduced agent costs by speeding up correct-code discovery (PRIMARY: https://arxiv.org/pdf/2603.27277).

**Zoekt:** Trigram-based, no compiler integration. Shards horizontally. Maintains freshness within minutes (PRIMARY: https://eng.snap.com/code_search).

**SCIP:** Google/Sourcegraph code intelligence protocol. Powers Sourcegraph code graph; supports multiple languages and build systems. Not directly benchmarked here, but widely adopted for symbol-aware retrieval (SECONDARY).

### Inferences

For a 4M LOC codebase (the agent's estimates, not measured):
- **Ripgrep alone:** Ready immediately, <100ms per query, high false-positive rate (binary matches, comments).
- **Ripgrep + repo-map (tree-sitter):** 3–10 seconds initial parse, <1ms guided queries thereafter, 99% context savings.
- **Full semantic (embeddings):** 10–30 seconds, requires re-indexing on pushes, 12–31% accuracy gain.
- **LSP-backed (Serena):** Millisecond queries, requires live server per language, best for refactoring and safety.

### Gaps

No agent published a full cost model (indexing time + query latency + token cost per solve) across tool combinations. Moatless Tools reports 38.3% on SWE-Bench Lite but doesn't isolate which code-search component contributed.

---

## Summary Table: Approaches, Evidence, Tradeoffs

| **Approach** | **Example Systems** | **Index Cost (4M LOC, estimated)** | **Query Latency** | **Freshness** | **Measured Evidence** | **Source** |
|---|---|---|---|---|---|---|
| **Exact-match grep** | ripgrep, GNU grep | <100ms | 30ms–1s | Real-time | 10x faster than grep on Linux kernel; all major agents ship it | SECONDARY: CodeAnt |
| **Semantic embeddings** | Cursor, Greptile, Windsurf | 10–30s | 5–50ms | Stale (minutes–hours) | 12–56% accuracy gain (size-dependent); no SWE-bench isolation | PRIMARY: Cursor (SECONDARY) |
| **Hybrid (exact + semantic)** | Cursor, Sourcegraph Cody | 10–30s | <50ms | Stale | "31% overall, 56% on large codebases" (unverified method) | SECONDARY: morphllm.com |
| **PageRank repo-map** | Aider, Stripe, Moatless | 1–3s | <1ms guided | Real-time | 99% token reduction (87 vs 12,000); agents waste fewer turns | SECONDARY: AgentPatterns, ByteByteGo |
| **Code graph (nodes/edges)** | RepoGraph, LocAgent, Codebase-Memory | 3–10s | <1ms | Real-time | 2.5–9x fewer tokens, 9x faster (monorepo bug fix); 4.81M nodes for Linux | PRIMARY: ArXiv, Codebase-Memory |
| **Exact-match search engine** | Zoekt (Snap), Code Search (Google) | Sharded (minutes) | <1s p95 | Within minutes | Sub-second p95; "almost all traffic from agents"; prevents hallucination | PRIMARY: Snap, Google |
| **LSP symbol tools** | Serena, Sourcegraph | Varies (live servers) | <1ms | Real-time | 30+ languages; used for safety; no benchmark | PRIMARY: Serena MCP |
| **LLM-trained code retrieval** | Windsurf Fast Context, Moatless | Unknown | <100ms | Unknown | "20x faster than agentic search" (unverified); 38.3% SWE-Bench Lite solve | SECONDARY: Windsurf, Moatless |

---

## Key Decision Points for Large-Codebase Agents

1. **Start with ripgrep + repo-map (tree-sitter)**: Achieves 99% context savings, <1ms guided queries, real-time freshness. Sufficient for most tasks under 4M LOC.

2. **Add semantic embeddings if exact-match failures are frequent:** 12–56% gain on discovery tasks ("where do we handle X?") but maintain cost discipline—embed docstrings, not raw code; re-index on push timing (not per-commit).

3. **Add code graph (RepoGraph, LocAgent) for cross-language, cross-service monorepos:** 9x speedup proven for multi-file, multi-stack tasks; payoff highest when team already maintains import/dependency metadata.

4. **Use LSP (Serena, Sourcegraph) for refactoring and safety-critical code changes:** Symbol-aware tools prevent hallucination; trade-off is live-server overhead (one per language).

5. **Layer exact-match search engine (Zoekt, Code Search) for >100K files or cross-org repos:** Zoekt scales to millions of files; prevents embedding staleness; agents iterate through exact searches and verify rather than trust approximate matches.

6. **Scope context per directory (AGENTS.md, per-service rules):** Stripe's "dynamic context selection" reduces noise and token cost more than any single retrieval algorithm.

---

## References

- ArXiv: SWE-Bench Pro (2509.16941)
- ArXiv: LoCoBench-Agent (2511.13998)
- ArXiv: AutoCodeRover (2404.05427)
- ArXiv: LocAgent (2503.09089)
- ArXiv: Codebase-Memory (2603.27277)
- ArXiv: RepoBench (2306.03091, 2607.24882)
- Snap Engineering: Code Search (eng.snap.com/code_search)
- Google Open Source: Code Search + Kythe (opensource.googleblog.com)
- Stripe Blog: How Minions Ship PRs (bytebytego.com, blog.bytebytego.com/p/how-stripes-minions-ship-1300-prs)
- Uber Engineering: Agentic SDLC (ai.engineer/talks, newsletter.pragmaticengineer.com)
- Sourcegraph Docs: Monorepo Support (sourcegraph.com/admin/monorepo)
- Serena MCP: LSP Tools for Agents (mcp.directory, alguidelines.dev)
- Aider: Repository Map Pattern (agentpatterns.ai)
- CodeAnt: Ripgrep for Agents (codeant.ai/blogs)
- Windsurf Docs: Fast Context, Local Indexing (docs.windsurf.com)
- Cursor Blog: Semantic Search (plushcap.com/content/cursor/blog)

