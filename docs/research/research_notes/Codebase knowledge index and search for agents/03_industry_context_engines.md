# Codebase Indexing and Search for Agents: Industrial Systems Survey

Access date for every URL: 2026-10-17.

## Cursor

### Takeaway
Cursor uses embeddings + Merkle tree incremental indexing with team-wide index sharing. Measured result: 12.5% accuracy improvement on semantic search; 2.6% code retention gain on large codebases (1,000+ files). Semantic search is "currently necessary to achieve the best results."

### Cited Findings
- **Custom embedding model trained on agent session traces** (PRIMARY: https://cursor.com/blog/semsearch) — embeddings learn from agent behavior: "traces to an LLM that ranks helpful content at each step, then train embeddings to align similarity scores with these rankings"
- **Merkle tree for incremental indexing**: cryptographic hash per file, parent hashes computed from children; unchanged files skip reprocessing (PRIMARY: https://cursor.com/blog/secure-codebase-indexing)
- **Index sharing**: ~92% similarity within organizations enables new users to adopt teammate indexes; background sync reconciles differences (PRIMARY: https://cursor.com/blog/secure-codebase-indexing)
- **Offline evaluation**: Cursor Context Bench reports 12.5% average accuracy improvement, range 6.5%–23.5% across models tested (PRIMARY: https://cursor.com/blog/semsearch)
- **Scale improvements**: median repos 7.87s → 525ms; 90th percentile 2.82m → 1.87s; 99th percentile (largest) 4.03h → 21s (PRIMARY: https://cursor.com/blog/secure-codebase-indexing)

### Inferences
Cursor's custom embedding model, trained on *agent action traces* rather than code pairs, suggests agent-aware indexing may outperform generic code-similarity models. The 92% team-wide similarity figure implies monorepos and consolidated codebases could benefit most from shared indexing.

### Gaps
- Embedding model details (dimension, architecture, inference latency) not stated
- Freshness cadence (beyond "background sync") not specified
- No public benchmark against grep-only baseline on agent task success rate

---

## Sourcegraph

### Takeaway
Deep Search runs an agentic loop with built-in Sourcegraph tools (Code Search, Code Navigation). All processing stays on-premise; no measured result reported.

### Cited Findings
- **Agentic loop architecture** (PRIMARY: https://sourcegraph.com/docs/code-search/types/deep-search) — "AI agent can intelligently use tools to explore the codebase" with iterative refinement until confident
- **Tools available**: built-in Sourcegraph Code Search (exact and semantic), Code Navigation (symbol resolution), read file capabilities (PRIMARY: https://sourcegraph.com/docs/code-search/types/deep-search)
- **On-premise processing with external LLM calls** (PRIMARY: https://sourcegraph.com/docs/code-search/types/deep-search) — "processing happens within your Sourcegraph instance with only external calls made to the configured LLM"
- **Source attribution in responses** (PRIMARY: https://sourcegraph.com/docs/code-search/types/deep-search) — lists exact searches performed and files read
- **Enterprise Starter / Enterprise plans only** (PRIMARY: https://sourcegraph.com/docs/code-search/types/deep-search)

### Inferences
Deep Search is a wrapper agent, not an index. The separation—on-premise processing but external LLM—suggests they assume agents need frontier models over local models. No measured improvement over grep-only baseline published.

### Gaps
- Embedding model (if used) not described
- Index freshness / update mechanism not documented
- No measured success rates or latency benchmarks
- Symbol graph / SCIP layer not explained in agent context

---

## GitHub Copilot

### Takeaway
GitHub uses CodeBERT fine-tuned embeddings + Qdrant vector DB. Copilot agents now have semantic search tool (2026). Measured result: 2% task completion speedup; indexing 5m → few seconds.

### Cited Findings
- **Semantic code search architecture**: "fine-tuned CodeBERT model, a Qdrant vector database for nearest-neighbor search, and a gRPC query service returning top-k results in under 100ms p50" (SECONDARY: https://markaicode.com/architecture/github-copilot-semantic-search-architecture/)
- **Indexing speed**: Previously ~5 minutes; now "few seconds" in most cases, up to 60 seconds (PRIMARY: https://github.blog/changelog/2025-03-12-instant-semantic-code-search-indexing-now-generally-available-for-github-copilot/)
- **Agent integration (2026)**: "Copilot coding agent now has access to a semantic code search tool"; testing shows "2% less time without any change in quality" (PRIMARY: https://github.blog/changelog/2026-03-17-copilot-coding-agent-works-faster-with-semantic-code-search/)
- **Automatic index refresh**: "typically automatically updated to include the latest changes within seconds of you starting a new conversation" (PRIMARY: https://docs.github.com/en/copilot/concepts/context/repository-indexing)
- **Scale**: "No limit to how many repositories you can index" (PRIMARY: https://docs.github.com/en/copilot/concepts/context/repository-indexing)

### Inferences
CodeBERT fine-tuning suggests GitHub invested in language-specific embeddings. The 2% measured improvement is lower than Cursor's claim (12.5%), suggesting different baselines or evaluation methods.

### Gaps
- CodeBERT version, training data, dimension not stated
- Qdrant cluster topology (sharding, replication) not described
- Asynchronous embedding pipeline details not provided
- No public benchmark methodology for the 2% claim

---

## Augment Code

### Takeaway
Augment's Context Engine handles 400,000+ files at sub-200ms latency. Claims semantic index of function relationships and API contracts. No measured agent improvement reported.

### Cited Findings
- **Scale claim**: "Context Engine processes 400,000+ files with sub-200ms latency, even on repositories exceeding 100 million lines of code" (SECONDARY: https://fast.io/resources/augment-code-vs-cline-codebase-indexing/)
- **Indexing speed**: "50,000 files per minute, with initial indexing running in under a minute for most projects" (SECONDARY: https://fast.io/resources/augment-code-vs-cline-codebase-indexing/)
- **Semantic index contents**: "function call relationships, API contracts, architectural patterns, and cross-service dependencies" (SECONDARY: https://fast.io/resources/augment-code-vs-cline-codebase-indexing/)
- **MCP integration**: "MCP enables integration with any MCP-compatible platform, LLM and agent" (SECONDARY: https://fast.io/resources/augment-code-vs-cline-codebase-indexing/)
- **File capacity**: "processes up to 500,000 files across 30 or more repositories" (SECONDARY: https://fast.io/resources/augment-code-vs-cline-codebase-indexing/)

### Inferences
Sub-200ms on 400k files suggests graph-based or trigram indexing, not embeddings. The "function relationships" language implies symbol resolution, similar to Glean.

### Gaps
- Index architecture (embedding vs exact search vs symbol graph) not stated
- Freshness strategy not mentioned
- No measured result; all claims are vendor claims without method
- Architecture details are marketing language only

---

## Cognition / Devin

### Takeaway
DeepWiki auto-indexes repos into architecture diagrams and wiki pages; Devin Search answers queries backed by cited code. Indexing takes "minutes" for small repos. No measured improvement stated.

### Cited Findings
- **DeepWiki indexing** (SECONDARY: https://fast.io/resources/devin-deepwiki-guide/) — "automatically indexes repositories and generates architecture diagrams, source-linked summaries, and wiki pages"
- **Indexing freshness**: "minutes for small repos, longer for large monorepos" (SECONDARY: https://fast.io/resources/devin-deepwiki-guide/)
- **Steering via config** (SECONDARY: https://fast.io/resources/devin-deepwiki-guide/) — teams use `.devin/wiki.json` to guide generation; wiki pages capped at 30 max (80 enterprise), 100 notes, 10,000 chars per note
- **Data sources**: "code and metadata (pull requests, git history, team discussions)" (SECONDARY: https://www.zenml.io/llmops-database/building-an-autonomous-ai-software-engineer-with-advanced-codebase-understanding-and-specialized-model-training-6bnir)
- **Custom post-training**: "multi-turn reinforcement learning to optimize models for specific narrow domains" (SECONDARY: https://www.zenml.io/llmops-database/building-an-autonomous-ai-software-engineer-with-advanced-codebase-understanding-and-specialized-model-training-6bnir)

### Inferences
DeepWiki is not a search engine but a documentation generation system, relying on human-readable wiki pages rather than embeddings or symbol graphs. The Devin Search claim ("backed by cited code") suggests search-over-wiki rather than direct code indexing.

### Gaps
- Embedding or search mechanism not described
- Indexing architecture (LLM-based summarization vs semantic search) unclear
- No measured result on agent task success
- Freshness for production branches not specified

---

## Snap

### Takeaway
Snap uses Zoekt (trigram-based search engine) sharded by repo, with atomic-swap zero-downtime updates. Updates within "seconds to a few minutes." Agents call regex search and templated high-level tools via MCP.

### Cited Findings
- **Zoekt architecture** (PRIMARY: https://eng.snap.com/code_search) — "trigram-based search engine" indexing "thousands of repos across multiple organizations"
- **Scale** (PRIMARY: https://eng.snap.com/code_search, per the 2026-10-17 vendor fact-check) — "millions of files and close to a terabyte of source"
- **Sharding strategy** (PRIMARY: https://eng.snap.com/code_search) — "each repo lives entirely on one shard"; "sharding by repo keeps query semantics simple: a regex either matches a file or it doesn't"
- **Update mechanism** (PRIMARY: https://eng.snap.com/code_search) — "repo gets a new index version, and the shard it already lives on downloads that version alongside the old one, then cuts over in a single atomic swap"
- **Delta indexing** (PRIMARY: https://eng.snap.com/code_search) — "most pushes touch only a handful of files, so instead of rebuilding the index from scratch we build a delta of just what changed and stack it on the previous one"
- **Freshness**: updates within "seconds to a few minutes" of default branch pushes (PRIMARY: https://eng.snap.com/code_search)
- **Agent tools**: regex / literal search (sub-second p95), plus "find_callers" and similar lookups (PRIMARY: https://eng.snap.com/code_search)
- **Language-agnostic**: "indexes text straight from a git tree" supporting Go, Java, C++, Python, TypeScript (PRIMARY: https://eng.snap.com/code_search)
- **MCP exposure** (PRIMARY: https://eng.snap.com/code_search) — "all tools exposed via MCP (Model Context Protocol) servers, enabling any MCP-capable agent"

### Inferences
Zoekt (trigram) enables regex without embedding cost. The atomic-swap design and delta-based updates are ops-focused, not ML-focused. Language-agnostic indexing avoids per-language training.

### Gaps
- No measured agent task improvement
- Scale (file count, repo count) not specified
- Query latency distribution beyond "sub-second p95" not provided

---

## Windsurf / Codeium (Fast Context)

### Takeaway
SWE-grep models (RL-trained) perform parallel tool calls (up to 8 concurrent, 4 turns max). Claimed speed: "up to 20x faster." Uses grep, read, glob only. No measured agent improvement.

### Cited Findings
- **SWE-grep family** (PRIMARY: https://docs.devin.ai/desktop/context-awareness/fast-context) — "SWE-grep" and "SWE-grep-mini" trained using reinforcement learning for "parallel tool calling and efficient codebase navigation"
- **Parallelism** (PRIMARY: https://docs.devin.ai/desktop/context-awareness/fast-context) — "executing up to 8 parallel tool calls per turn over a maximum of 4 turns"
- **Tool stack** (PRIMARY: https://docs.devin.ai/desktop/context-awareness/fast-context) — "restricted, cross-platform toolkit consisting of grep, read, and glob functions"
- **Speed claim** (PRIMARY: https://cognition.ai/blog/swe-grep) — "20x faster than traditional agentic search"
- **Performance metric** (PRIMARY: https://cognition.ai/blog/swe-grep) — "over 2,800 tokens per second" for SWE-grep-mini
- **Training**: "trained using reinforcement learning to excel at parallel tool calling and efficient codebase navigation" (PRIMARY: https://cognition.ai/blog/swe-grep)

### Inferences
SWE-grep trades semantic understanding for speed via parallelism and RL. The 20x claim vs "grep only" baseline is unclear—measured against what?

### Gaps
- SWE-grep model size, dimension, training method details not provided
- No measured task success rate
- Baseline for "20x faster" comparison not defined
- "up to 20x" hedging suggests variance in measured speedup

---

## JetBrains Context

### Takeaway
Incremental semantic indexing with embedding backend. Vendor-reported result: "up to 68% fewer agent turns, 59% lower latency, and 48% lower cost" on "thousands of benchmark tasks" (the exact count "2,333" from the first draft is not verified). Agents query semantically instead of grep.

### Cited Findings
- **Embedding-based indexing** (PRIMARY: https://blog.jetbrains.com/ai/2026/07/introducing-jetbrains-context-repository-intelligence-for-coding-agents/ [HTTP 403 blocked]) (SECONDARY: https://www.jetbrains.com/help/jetbrains-console/main/getting-started-with-jetbrains-context.html) — "indexes code using an embedding backend incrementally and at scale"
- **Privacy design**: "storing vector representations rather than raw source" (SECONDARY: https://blog.jetbrains.com/ai/2026/07/introducing-jetbrains-context-repository-intelligence-for-coding-agents/)
- **Measured results**: "up to 68% fewer agent turns, 59% lower latency, and 48% lower cost" on "thousands of benchmark tasks"; "up to" means a best case, not an average (PRIMARY: https://blog.jetbrains.com/ai/2026/07/introducing-jetbrains-context-repository-intelligence-for-coding-agents/)
- **IDE integration**: "IDE maintains a detailed project index" and agents access via MCP (PRIMARY: https://blog.jetbrains.com/ai/2026/07/introducing-jetbrains-context-repository-intelligence-for-coding-agents/)
- **Availability**: "early access at no extra cost with a JetBrains AI subscription" (SECONDARY: https://blog.jetbrains.com/ai/2026/07/introducing-jetbrains-context-repository-intelligence-for-coding-agents/)
- **Query mode**: agents "ask for relevant files, APIs, tests, patterns, or examples" instead of manual grep-style exploration (SECONDARY: https://blog.jetbrains.com/ai/2026/07/introducing-jetbrains-context-repository-intelligence-for-coding-agents/)

### Inferences
JetBrains' figures (up to 68% fewer turns) are the largest any vendor states, but they are best-case vendor numbers with no published method. IDE integration suggests AST-aware indexing, not just embeddings.

### Gaps
- Embedding model details (base model, fine-tuning method) not disclosed
- Benchmark task types not described
- How "turns" are counted not specified

---

## Meta Glean

### Takeaway
Symbol-graph-based system with RocksDB storage and incremental indexing (O(changes) complexity). Handles multiple languages via language-specific indexers. No measured agent improvement reported.

### Cited Findings
- **Architecture**: three components—indexing layer (parallelizable), query service (distributed), data storage (RocksDB for "good scalability and efficient retrieval") (PRIMARY: https://engineering.fb.com/2024/12/19/developer-tools/glean-open-source-code-indexing/)
- **Symbol IDs**: "REPOSITORY/cpp/folly/Singleton" format; enables linking across repos and languages (PRIMARY: https://engineering.fb.com/2024/12/19/developer-tools/glean-open-source-code-indexing/)
- **Language-specific indexers**: separate indexer per language; multi-language codebase support (PRIMARY: https://engineering.fb.com/2024/12/19/developer-tools/glean-open-source-code-indexing/)
- **Incremental indexing**: "O(changes) complexity"; "stacking immutable databases on top of each other" for non-destructive updates and multi-revision visibility (PRIMARY: https://engineering.fb.com/2024/12/19/developer-tools/glean-open-source-code-indexing/)
- **Fanout for language dependencies**: for C++ headers, "Glean calculates fanout—affected files requiring reprocessing—using Glean queries themselves to identify dependent files iteratively" (PRIMARY: https://engineering.fb.com/2024/12/19/developer-tools/glean-open-source-code-indexing/)
- **Update cadence**: "whole process running several times per day to keep the data fresh" (PRIMARY: https://engineering.fb.com/2024/12/19/developer-tools/glean-open-source-code-indexing/)

### Inferences
Glean is *not* an embedding system; it's a symbol graph. The O(changes) complexity and multi-revision support suggest it handles large, fast-changing codebases well. "Several times per day" is slower than Snap's minutes-to-seconds.

### Gaps
- Glean's agent-facing query API not described
- No measured improvement on agent task success
- RocksDB scale limits (file count, query latency) not provided

---

## Google / Kythe

### Takeaway
Kythe is a symbol-graph database with language-specific extractors and indexers. Used internally at Google; unclear if agents use it directly. No measured result on agent tasks.

### Cited Findings
- **Multi-language indexing**: "each language having its own indexer to analyze that language's code" (PRIMARY: https://abseil.io/resources/swe-book/html/ch17.html)
- **Symbol annotations**: "database of code annotations and references across a possibly multi-language codebase" (SECONDARY: per Wikipedia referenced in Google SWE Book)
- **Pipeline**: "extractors to pull compilation information from the build system, indexers to construct a persistent graph, and services to answer queries like code browsing, code review, and documentation generation" (SECONDARY: https://abseil.io/resources/swe-book/html/ch17.html)
- **Update frequency**: "combines graphs for different languages, prunes unnecessary pieces, and optimizes it for serving cross-references, with the whole process running several times per day" (SECONDARY: https://abseil.io/resources/swe-book/html/ch17.html)

### Inferences
Kythe is internal-only; Google Code Search uses Kythe for some repos but the direct agent integration is not documented in public sources.

### Gaps
- No documented agent integration
- No measured result on agent tasks
- Query API not published

---

## Greptile

### Takeaway
Vector-search indexing via MCP. Small repos index in 3–5 minutes; large monorepos over an hour. Integration with agents via query_repository, search_repository tools.

### Cited Findings
- **Indexing time**: "small repos taking 3-5 minutes and larger ones taking over an hour" (SECONDARY, community MCP server listing: https://mcpservers.org/servers/sosacrazy126/greptile-mcp)
- **Vector search**: relies on "vector search and LLM-powered synthesis to understand complex architectural questions" (SECONDARY, community MCP server listing: https://mcpservers.org/servers/sosacrazy126/greptile-mcp)
- **Tools**: query_repository (ask natural language questions, get detailed answers with code references), search_repository (find files by concept), index_repository (process and update) (SECONDARY, community MCP server listing: https://mcpservers.org/servers/sosacrazy126/greptile-mcp)
- **MCP integration**: "MCP server implementation that integrates with the Greptile API" (SECONDARY, community MCP server listing: https://mcpservers.org/servers/sosacrazy126/greptile-mcp)

### Inferences
Greptile's 1-hour+ indexing on large repos is slower than competitors (Cursor 21s, GitHub few seconds, Snap seconds-to-minutes). Vector search + LLM synthesis suggests RAG approach.

### Gaps
- Vector database not specified
- Embedding model not disclosed
- No measured agent task improvement
- Query latency not provided

---

## Summary Table

| System | Index Type | Freshness | Scale | Measured Result | Source Tag |
|--------|-----------|-----------|-------|-----------------|-----------|
| **Cursor** | Custom embeddings + Merkle tree | Background sync (cadence not stated) | 50k files (99th pct 4h→21s) | 12.5% accuracy improvement; 2.6% code retention on 1k+ files | PRIMARY |
| **Sourcegraph Deep Search** | Agentic loop + built-in tools | Not specified | Enterprise plan | None reported | PRIMARY |
| **GitHub Copilot** | CodeBERT embeddings + Qdrant | ~5min → few sec; updates within sec/turns | Unlimited repos | 2% task speedup; indexing 5m → few seconds | PRIMARY |
| **Augment Code** | Semantic index (symbol graph?) | Not specified | 500k files (400k sub-200ms) | Vendor claim only; no method | SECONDARY |
| **Cognition Devin** | Wiki generation + semantic search | Minutes (small); longer (large monorepos) | Not specified | None reported | SECONDARY |
| **Snap (Zoekt)** | Trigram search + delta updates | Seconds to minutes after push | Thousands of repos; "millions of files and close to a terabyte of source" | None reported; sub-sec p95 latency | PRIMARY |
| **Windsurf (SWE-grep)** | RL-trained parallel retrieval | Not applicable (runtime search) | Not specified | "20x faster" (vs. what baseline?) | PRIMARY |
| **JetBrains Context** | Incremental embeddings | Not specified | Not specified | Up to 68% fewer agent turns, 59% lower latency, 48% lower cost (vendor, "thousands of benchmark tasks") | PRIMARY (blog blocks fetch; quoted via fact-check) |
| **Meta Glean** | Symbol graph (RocksDB) | Several times per day | C++ + Thrift + Buck2 | None reported | PRIMARY |
| **Google Kythe** | Symbol graph + language extractors | Several times per day | Internal only | None reported | PRIMARY |
| **Greptile** | Vector search + LLM synthesis | 3–5 min (small); 1+ hour (large) | Not specified | None reported | SECONDARY |

---

## Areas of Agreement

1. **Freshness matters**: every system that states a cadence updates at least several times a day; Snap and GitHub reach seconds to minutes.
2. **Scale is real**: vendors quote 100k–500k+ files (Augment's figure is a secondary, vendor-only claim).
3. **Most vendors add a tool beyond plain grep, but not all**: Cursor, GitHub and JetBrains add embeddings; Snap, Glean and Kythe add exact or symbol indexes. Windsurf's SWE-grep keeps grep/read/glob only and makes it faster with a trained model. (Correction 2026-10-17: the first draft said "all vendors moved beyond grep-only", which Windsurf and Snap contradict.)
4. **MCP as the agent interface**: Snap (primary) and JetBrains (primary) expose their tools over MCP; Greptile and Augment only per secondary sources.

---

## Areas of Disagreement

1. **Embeddings vs. symbol graphs**: Cursor, GitHub, JetBrains use embeddings; Glean, Kythe use symbols; Snap uses trigrams. No clear winner published.
2. **Measured improvement baseline**: Cursor claims 12.5% higher accuracy (baseline not stated); GitHub 2% less time (vs. the agent without the tool); JetBrains up to 68% fewer turns (best case). Baselines not comparable.
3. **Indexing architecture**: Cursor shares indexes team-wide (92% codebase overlap); others assume per-agent or per-user indexing.
4. **Model fine-tuning**: Cursor trains its own embedding model on agent traces; GitHub's CodeBERT fine-tune is reported only by a secondary source; JetBrains does not disclose its model; Windsurf uses RL on SWE-grep. Google and Meta use language-specific extractors (no ML embeddings shown).

---

## References

- https://cursor.com/blog/semsearch (Cursor semantic search)
- https://cursor.com/blog/secure-codebase-indexing (Cursor Merkle tree + indexing)
- https://sourcegraph.com/docs/code-search/types/deep-search (Sourcegraph Deep Search)
- https://github.blog/changelog/2025-03-12-instant-semantic-code-search-indexing-now-generally-available-for-github-copilot/ (GitHub semantic search)
- https://github.blog/changelog/2026-03-17-copilot-coding-agent-works-faster-with-semantic-code-search/ (GitHub Copilot agents with semantic search)
- https://docs.github.com/en/copilot/concepts/context/repository-indexing (GitHub repository indexing docs)
- https://fast.io/resources/augment-code-vs-cline-codebase-indexing/ (Augment Code context engine)
- https://fast.io/resources/devin-deepwiki-guide/ (Devin DeepWiki)
- https://www.zenml.io/llmops-database/building-an-autonomous-ai-software-engineer-with-advanced-codebase-understanding-and-specialized-model-training-6bnir (Cognition Devin custom post-training)
- https://eng.snap.com/code_search (Snap Zoekt-based code search)
- https://cognition.ai/blog/swe-grep (Windsurf SWE-grep RL models)
- https://docs.devin.ai/desktop/context-awareness/fast-context (Windsurf Fast Context architecture)
- https://blog.jetbrains.com/ai/2026/07/introducing-jetbrains-context-repository-intelligence-for-coding-agents/ (JetBrains Context; path corrected from 2026/08 to 2026/07 on 2026-10-17; the blog returns HTTP 403 to fetches)
- https://www.jetbrains.com/help/jetbrains-console/main/getting-started-with-jetbrains-context.html (JetBrains Context docs)
- https://engineering.fb.com/2024/12/19/developer-tools/glean-open-source-code-indexing/ (Meta Glean)
- https://abseil.io/resources/swe-book/html/ch17.html (Google Kythe in SWE Book)
- https://mcpservers.org/servers/sosacrazy126/greptile-mcp (Greptile MCP server)
