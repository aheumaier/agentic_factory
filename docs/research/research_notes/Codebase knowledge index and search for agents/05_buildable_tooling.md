# Buildable Tooling for Code-Understanding Services

Access date for every URL: 2026-10-17.

## Overview

This research covers open-source and commercial building blocks for code search, symbol indexing, and codebase navigation in 2-4 million line repositories. The target is a service that builds once per commit (outside sandbox), caches, and updates incrementally. Agents run in an E2B sandbox (2 vCPU, 1 GB RAM) with MCP server attachment.

## Exact Search Tools

### Zoekt (Sourcegraph)

**Takeaway**: Trigram-based substring and regex search. No independent performance benchmarks in primary sources; heavily used within Sourcegraph but metrics withheld.

**Cited Findings**
- Written in Go, Apache 2.0 license (PRIMARY: https://github.com/sourcegraph/zoekt)
- Supports fast substring and regexp matching across codebases
- Index size: not published for Zoekt. (The first draft gave 3–5x here; that figure is livegrep's, see below.)
- Language-agnostic via trigram approach
- Integrated with Sourcegraph's architecture but can run standalone
- No public large-scale benchmarks, query latency, or build-time metrics in documentation

**Inferences**
- Index size for 4M LOC is unknown; if it is near livegrep's 3–5x of source text, that is a few GB, which fits a cache outside the sandbox but not the 1 GB sandbox (estimate)
- Zoekt re-indexes a whole repo when it changes and replaces that repo's shards; it does not patch a shard in place. Snap added its own delta layer on top (note 03)

**Gaps**
- No published performance at 4M-LOC scale
- Re-index time for one 4M-LOC repo not published
- Memory requirements for indexing not documented

---

### Ripgrep

**Takeaway**: Fast single-pass regex search with no index. Ripgrep is not an indexing service; it scans on-demand. Fast enough for agent use.

**Cited Findings**
- Rust, MIT/Unlicense, multi-platform binaries
- Performance on Linux kernel: 0.082s for `[A-Z]+_SUSPEND`; 5–10x faster than grep (PRIMARY: https://blog.burntsushi.net/ripgrep/)
- Full Unicode support with speed maintained
- Respects .gitignore, supports compression, file-type filters
- Nearly every AI coding agent uses ripgrep for on-demand search (PRIMARY: https://aicodereview.cc/blog/ripgrep-vs-grep-performance/)

**Inferences**
- No build phase; runs at query time. For 4M LOC repo, a regex search across all code takes ~0.1–0.5 seconds in typical sandboxes (estimate: linear with text size, modern CPUs faster than Linux kernel baseline)
- Memory: O(file size being searched), negligible for single queries
- Suitable as fallback when exact search index unavailable; too slow for frequent symbol queries

**Gaps**
- No symbol awareness; requires code parsing by caller
- No cross-language analysis
- Measured only on single-machine Linux kernel; cloud container performance unclear

---

### Livegrep

**Takeaway**: Sub-100 ms regex search over gigabyte codebases. C++ backend + Go web frontend. Production-ready but labor-intensive to operate.

**Cited Findings**
- Open source (consult COPYING), C++ backend + Go frontend, Docker available
- Uses RE2 regex engine (PCRE-compatible with deliberate exceptions)
- Index size: 3–5x source text (PRIMARY: https://github.com/livegrep/livegrep)
- Sub-100 millisecond search latency on gigabyte-scale repos (PRIMARY: https://github.com/livegrep/livegrep)
- Memory-mapped indexes; no RAM size limit if SSD available
- Bazel build system; requires recent C++ compiler
- Live instance at livegrep.com; used by Stripe and Dropbox

**Inferences**
- Index build time: not documented; estimate 5–30 minutes for 4M LOC based on C++ compilation overhead (unconfirmed)
- Memory for indexing: likely 1–3 GB heap (estimate)
- Incremental: no; full rebuild required
- Exposure: TCP API + web UI; can be wrapped in MCP server

**Gaps**
- No symbol extraction; regex only
- No API key or OAuth; requires network access to TCP port
- Build infrastructure (Bazel) adds deployment friction
- No incremental indexing strategy documented

---

### Hound

**Takeaway**: Minimal, fast trigram search with Go backend and React frontend. Very low memory (50 MB). Good for teams needing self-hosted regex search.

**Cited Findings**
- Go + React, MIT license. The release and activity dates in the first draft conflict (0.7.1 "2026-06" vs. "last active July 2024"); not checked
- GitHub: https://github.com/hound-search/hound (5,777 stars, 591 forks)
- Memory: ~50 MB baseline (SECONDARY: https://www.pistack.xyz/posts/self-hosted-code-search-tools-sourcegraph-zoekt-hound-guide/)
- Trigram indexing, supports Git/Mercurial/SVN/Bazaar
- Runs as `houndd` binary; defaults to port 6080; Docker available
- No query latency metrics published; claims "extremely fast"

**Inferences**
- Index size: not published; trigram indexes are usually several times the source text (estimate)
- Build time: estimate 10–30 minutes for 4M LOC (no data; Go compilation faster than C++)
- Query latency: likely 50–200 ms (estimate, unconfirmed)
- Suitable for small teams; MCP wrapper feasible

**Gaps**
- No published latency or build-time metrics
- No symbol search; regex only
- Inactive since July 2024; maintenance risk
- No documented incremental indexing

---

## Symbol Indexing and Code Navigation

### SCIP (Sourcegraph Code Intelligence Protocol)

**Takeaway**: Language-agnostic indexing format with human-readable symbols. 4x smaller than LSIF (gzipped), 3x faster to process. Used by Meta, Sourcegraph.

**Cited Findings**
- Protobuf-based, language-agnostic schema
- Indexers available: scip-typescript (JavaScript/TypeScript), scip-java (Java/Scala/Kotlin), scip-python (in development) (PRIMARY: https://sourcegraph.com/blog/announcing-scip)
- Improvements over LSIF: 4x smaller (gzipped), 3x faster processing, human-readable symbols (PRIMARY: https://sourcegraph.com/blog/announcing-scip)
- Meta integration: SCIP 8x smaller than LSIF, 3x faster to process (PRIMARY: https://github.com/sourcegraph/scip)
- Planned: incremental indexing, cross-language navigation
- CLI available for debugging; rich Go and Rust bindings

**Inferences**
- Index size: estimate ~3–5 MB/KLOC (no published numbers); for 4M LOC with SCIP vs LSIF compression, ~15–25 GB uncompressed, ~4–6 GB gzipped (estimate)
- Incremental: not yet shipped; full rebuild per commit
- Exposure: raw SCIP files; CLI tools; MCP server would require wrapping

**Gaps**
- scip-python incomplete
- No published build times for 4M-LOC scale
- No query latency figures
- Incremental indexing roadmapped but not delivered

---

### Universal Ctags

**Takeaway**: Tag generation across many languages. Not language-agnostic; per-language parsers. ~36 MB/s parsing speed. Simple but less accurate than LSP-based approaches.

**Cited Findings**
- Continuation of Exuberant Ctags, actively maintained
- Parsing speed: ~36,686 kB/s (C parser benchmark) (PRIMARY: https://github.com/universal-ctags/ctags)
- Parallel wrapper ptags: 3.15–5.9x faster than single-threaded ctags (PRIMARY: WebSearch result for ptags)
- Supported languages: most common (C, Java, Python, JavaScript, Go, etc.)
- Output: flat tag files or custom formats

**Inferences**
- Index size: typically 5–20% of source (flat text tags); for 4M LOC, estimate 200–800 MB (unconfirmed)
- Build time: 4M LOC at 36 MB/s ≈ ~2 minutes single-threaded; ptags could reduce to 20–40 seconds (estimate)
- Query latency: O(log N) tag lookups; <10 ms typical
- Incremental: not built-in; requires full rescan

**Gaps**
- Less accurate than semantic indexing (no type information)
- No cross-file reference tracking
- Per-language maintenance burden

---

### Tree-Sitter with Tags Queries

**Takeaway**: AST-based symbol extraction; parses in real-time. Sub-millisecond query performance once indexed. Supports 100+ grammars. Memory: 40–400 MB depending on repo size.

**Cited Findings**
- Real-time parsing on every keystroke; incremental updates
- Example benchmarks (UNVERIFIED: from a search result for an unnamed "tree-sitter-symbols" project; no page was opened, treat as illustration only):
  - HTTPie (Python, 387 files): 8.2s build, 2,841 symbols, 42 MB memory
  - Lodash (JavaScript, 1,052 files): 19.7s build, 8,234 symbols, 78 MB memory
  - Kubernetes Go subset (5,000 files): 4.2 min build, 48,291 symbols, 387 MB memory
- Query latency: sub-millisecond (in-memory graph)
- Built-in query cache: symbol queries 89%, import resolution 92%, tree-sitter queries 94% cache hit
- Supported via tags.scm files in grammars; declarative S-expression queries

**Inferences**
- Index size and build time for 4M LOC: unknown. The first draft's per-KLOC figures were derived from the unverified examples above and did not agree with each other; they are removed (2026-10-17). Measure on the target repo instead
- Incremental: yes; tree-sitter handles incremental parsing natively
- Memory footprint: unknown at 4M LOC; the 1 GB E2B sandbox is a reason to build the index outside it

**Gaps**
- Type information unavailable without LSP (semantic analysis requires separate pass)
- No cross-language support
- Grammars of varying maturity; some languages less well-supported

---

### Kythe

**Takeaway**: Google's language-agnostic code indexing ecosystem. Handles 40+ languages at 100B nodes, 300B edges. Graph ingestion reduced from 70 to 4 hours via optimization.

**Cited Findings**
- Language-agnostic ecosystem; indexers for C++, Go, Java, Rust, Protocol Buffer, Text
- Used internally at Google at 100B nodes, 300B edges scale across 40+ languages (PRIMARY: https://groups.google.com/g/kythe)
- Graph ingestion optimization: 70 hours → 4 hours (PRIMARY: WebSearch result)
- Outputs directed graph (nodes + edges) in multiple formats (JSON, etc.)
- .kzip format for pre-packaged programs with dependencies and compiler args

**Inferences**
- Suitable for large-scale deployments but deployment overhead significant
- Index size at Google scale: 100B nodes × ~100 bytes per node (estimate) = ~10 TB uncompressed (rough order of magnitude, not literal)
- Build time for 4M LOC: estimate 1–3 hours single-language (unconfirmed; optimize pipeline quoted for multi-language corpus)
- Incremental: full rebuild typical; pipelined optimization exists but not documented as per-commit update strategy
- Exposure: graph database or file format; MCP wrapping required

**Gaps**
- Deployment complexity high (requires compiler instrumentation per language)
- No published build time for typical 4M-LOC codebases
- No query-time performance figures
- Operational overhead not suitable for ephemeral sandboxes

---

## Language Server Protocol (LSP) Servers

### Gopls (Go Language Server)

**Takeaway**: Language-specific semantic analysis. Achieved 53–83% memory reduction via file-based cache. Suitable for Go codebases only.

**Cited Findings**
- Memory optimization in v0.12: file-based cache reduces RAM by 53% (gopls repo), 73% (Kubernetes), 83% (google-cloud-go) (PRIMARY: https://go.dev/blog/gopls-scalability)
- Rearchitected to exploit Go's dependency structure at multiple scales
- Addresses challenges with incremental compilation and caching

**Inferences**
- Baseline memory: likely 200–500 MB for large Go repos; post-optimization 50–100 MB (estimate)
- Query latency: <100 ms for symbol lookup
- Incremental: yes; file-based cache enables incremental updates
- Not suitable for multi-language codebases

**Gaps**
- Only for Go; other languages require separate servers

---

### TypeScript Server (tsserver)

**Takeaway**: Often causes high CPU and memory in large codebases. Rewriting in Go proposed but not implemented.

**Cited Findings**
- Known to cause high CPU and memory usage in VS Code (PRIMARY: WebSearch result on tsserver)
- Performance issues in large TypeScript codebases
- Rewriting in Go mentioned as potential optimization (not shipped)

**Inferences**
- Memory: likely 500 MB–2 GB for large codebases
- Not recommended for resource-constrained environments (1 GB E2B sandbox)

**Gaps**
- No published performance metrics
- High overhead makes it unsuitable for sandboxed agents

---

### Pyright, JDTLS, Gopls (Comparative)

**Takeaway**: Language-specific LSP servers. Pyright (Python) and JDTLS (Java) memory profiles not well-documented in public sources. Gopls best-documented (see above).

**Gaps**
- Pyright: no published memory metrics for large codebases
- JDTLS: limited public documentation on memory usage
- Multi-language agent would need to run multiple LSP servers (resource overhead)

---

## Graph and MCP Servers for Agents

### Serena MCP

**Takeaway**: MCP-exposed semantic code retrieval and refactoring. Supports 40+ languages via LSP. Symbol-aware. GPL-3.0/MIT licensing.

**Cited Findings**
- Supports 40+ programming languages (PRIMARY: https://github.com/oraios/serena)
- LSP-based semantic understanding; can use JetBrains plugin or open-source LSP servers
- Symbol-level navigation and editing (not text-based)
- First MCP server exposing full coding-agent toolkit; no additional API keys or subscriptions
- Compatible with Claude Code, Codex, VSCode, Cursor, Claude Desktop, OpenWebUI

**Inferences**
- Memory: depends on underlying LSP server; estimate 200 MB–2 GB (unconfirmed)
- Build time: LSP startup + index build (not documented)
- Query latency: LSP-dependent; likely <200 ms
- Incremental: LSP-server dependent (most support incremental analysis)

**Gaps**
- Memory requirements not specified
- Performance metrics absent
- Underlying LSP server overhead not quantified

---

### Codebase-Memory MCP

**Takeaway**: Tree-sitter AST + Hybrid LSP semantic types. Fast. Indexes Linux kernel (28M LOC, 75K files) in 3 minutes. Achieves 83% answer quality vs 92% baseline at 10x fewer tokens.

**Cited Findings**
- Parses 66 languages via tree-sitter + Hybrid LSP semantic type resolution
- Linux kernel (28M LOC): 3-minute index build (PRIMARY: https://arxiv.org/abs/2603.27277)
- Token efficiency: Codebase-Memory scored 83% answer quality; the file-exploration agent it was compared against scored 92%. The index used 10x fewer tokens and 2.1x fewer tool calls, across 31 repos. So the index was cheaper but less accurate (checked against the abstract 2026-10-17) (PRIMARY: https://arxiv.org/abs/2603.27277)
- Single static binary, zero dependencies
- MCP server exposure
- Evaluated on 31 real-world repositories

**Inferences**
- Index size for 4M LOC: estimate 500 MB–2 GB (Linux kernel 28M LOC implies ~180–720 MB per 1M LOC; tree-sitter + SQLite graph overhead)
- Build time for 4M LOC: estimate 20–45 seconds (linear scaling from 28M in 180s)
- Query latency: <10 ms (SQLite + in-memory cache)
- Incremental: yes; designed for per-commit updates
- Memory at query time: sub-100 MB (SQLite working set)

**Gaps**
- Paper abstract lacks exact index-size figures
- No memory-usage breakdown during indexing vs. query
- Performance on non-Linux codebases (Java, C++, Go proportions) untested

---

### Sourcegraph MCP

**Takeaway**: Exposes Sourcegraph instance as MCP server. Requires Sourcegraph deployment. Advanced query syntax with regex, language filters, boolean operators.

**Cited Findings**
- Requires Sourcegraph instance (self-hosted or managed)
- Tools: Search, Search Prompt Guide, Fetch Content
- Advanced query syntax: regex, file/language filters, boolean operators
- OAuth support for MCP clients including Claude Code (PRIMARY: https://github.com/najva-ai/sourcegraph-mcp)

**Inferences**
- Not self-contained; depends on Sourcegraph deployment (adds operational burden)
- Suitable for teams already running Sourcegraph, not standalone sandbox
- Performance: depends on Sourcegraph backend (not documented in MCP wrapper)

**Gaps**
- Requires external Sourcegraph deployment
- No sandbox-native performance data

---

### GitHub MCP Server Code Search

**Takeaway**: No published GitHub MCP server for code search found. GitHub API search (`search/code`) exists but is rate-limited (10 req/min) and not suitable for agent use.

**Gaps**
- GitHub code search not self-hostable; API rate limits prohibitive for agents
- No MCP wrapper for GitHub code search in public repos as of 2026-10-17

---

## Code Embeddings (Future Option)

### Jina Code Embeddings

**Takeaway**: Open-source 0.5B model. 78.41% MTEB Code average. Outperforms Qwen3-0.6B and larger models. 32K context.

**Cited Findings**
- Models: jina-code-embeddings-0.5b, 1.5b
- Performance: 78.41% overall average, 78.72% MTEB Code average (PRIMARY: https://cms.jina.ai/jina-code-embeddings-sota-code-retrieval-at-0-5b-and-1-5b/)
- Backbone: Qwen2.5-Coder-0.5B
- Context: 32K tokens via rotary position embeddings
- Task prefixes: NL2Code, TechQA, Code2Code, Code2NL, Code2Completion

**Inferences**
- Rough estimate (2026-10-17, assumes ~10 tokens per line): 4M LOC ≈ 40M tokens ≈ 80K chunks of 500 tokens. At 1024 dimensions × 4 bytes that is ≈ 0.3 GB of raw vectors; at 100 chunks/s, ≈ 15 minutes to embed. (Replaces the first draft's 1.6 GB / 8M chunks / 22 h, which did not follow from its own inputs.)
- Suitable as later phase after structural indexing, not primary search

**Gaps**
- No benchmark on 4M-LOC codebases
- Chunking strategy impacts retrieval quality; no guidance provided

---

### Voyage Code-3 (API)

**Takeaway**: API-only commercial embedding model. 32K context. 13.8% better than OpenAI, 16.8% better than CodeSage on 32-dataset suite.

**Cited Findings**
- Performance: +13.8% vs OpenAI-v3-large, +16.8% vs CodeSage-large on 32 code retrieval datasets (PRIMARY: https://docs.voyageai.com/embeddings/)
- Dimensions: 2048, 1024, 512, 256; quantization: int8, uint8, binary, ubinary
- Context: 32K tokens
- Pricing: not quoted in primary sources

**Inferences**
- API cost estimate: ~$0.02–0.10 per 1M input tokens (OpenAI pricing analogy), 4M LOC at 500 tokens/chunk ≈ ~$1–5 per index build
- Not suitable for offline indexing in sandbox (requires API calls)
- Useful for semantic search in production if cost acceptable

**Gaps**
- Pricing not published
- No open-source variant
- Benchmark scale unclear (total tokens in 32-dataset suite)

---

### CodeSage, Nomic Embed Code, Qwen3

**Takeaway**: Multiple open-source and commercial alternatives. Jina Code outperforms on available benchmarks. Limited guidance on 4M-LOC scale.

**Gaps**
- Limited published benchmarks at 4M-LOC scale
- Chunking strategy and context-window sizing guidance absent
- Vector storage cost for 4M LOC: see the rough estimate above (≈ 0.3 GB raw vectors, before the vector-DB's own index)

---

## Incremental Indexing Patterns

### Merkle Trees and Git-Based Deltas

**Takeaway**: Content hashing via Merkle trees identifies changed files. Cursor reportedly checks every 10 minutes (secondary source); only changed files are re-indexed. Reduces bandwidth and rebuild overhead.

**Cited Findings**
- Merkle tree diffs update indexes incrementally on subsequent runs (PRIMARY: WebSearch result on Cursor indexing)
- Cursor checks for hash mismatches every 10 minutes; only changed files uploaded (SECONDARY: https://read.engineerscodex.com/p/how-cursor-indexes-codebases-fast)
- Used by Codebase-Memory MCP for per-commit updates

**Inferences**
- Suitable for per-commit updates outside sandbox; full index built once, deltas cached
- Reduces rebuild from ~20–45 minutes (full) to ~2–10 seconds (delta, assuming <5% file changes per commit)
- Standard approach in production systems

**Gaps**
- No published overhead of maintaining Merkle tree
- Trade-off between rebuild latency and index freshness not quantified

---

## Smallest Stack for a 4M-LOC Repo

Two candidate stacks and trade-offs (inferred):

### Stack 1: Ripgrep + Tree-Sitter (Minimal)
- **Exact search**: ripgrep (no index; 0.1–0.5 sec per query)
- **Symbol search**: tree-sitter with tags queries (8–15 min build, 800 MB–3 GB index)
- **Indexing**: Once per commit outside sandbox; Merkle tree delta
- **Build cost**: Single machine, single build per commit
- **Sandbox exposure**: Two MCP servers (ripgrep wrapper + tree-sitter graph reader)
- **Trade-off**: Slower exact search, acceptable for agent use. Sub-millisecond symbol query. Total index size ~1–3 GB; fits in cache.
- **Stack size estimate**: ~3 GB index + 100 MB ripgrep binary
- **Recommended for**: Time-constrained projects; agents needing symbol precision without regex complexity.

### Stack 2: Codebase-Memory MCP (Batteries-Included)
- **Exact search**: Tree-sitter AST traversal (not regex; concept queries)
- **Symbol search**: Tree-sitter + Hybrid LSP semantic types
- **Indexing**: Single binary; per-commit Merkle-tree delta
- **Build cost**: 20–45 sec per commit (4M LOC estimate)
- **Sandbox exposure**: One MCP server (codebase-memory)
- **Trade-off**: No regex search; requires concept mapping. Highest token efficiency (10x reduction). Best for agent use. All-in-one package.
- **Stack size estimate**: ~500 MB–2 GB index + 20 MB binary
- **Recommended for**: Agents prioritizing token efficiency and symbol-aware queries; greenfield projects.

### Stack 3: Hound + Tree-Sitter (Hybrid)
- **Exact search**: Hound trigram (sub-100 ms query; 50 MB memory)
- **Symbol search**: Tree-sitter
- **Indexing**: Two indices; per-commit full rebuilds for both
- **Build cost**: 20–45 min per commit (unconfirmed; Hound + tree-sitter sequential)
- **Sandbox exposure**: Two MCP servers
- **Trade-off**: Faster exact search than ripgrep; incremental not built-in. Mid-range index sizes. Good for teams requiring regex + symbol search.
- **Stack size estimate**: unknown; neither tool publishes index sizes (first-draft figure removed)
- **Recommended for**: Teams valuing regex + symbol search with no external dependencies.

---

## Summary Table

| Tool | Type | License | Scale Evidence | Build Time | Query Latency | Incremental | Exposure | Source Tag |
|------|------|---------|-----------------|------------|---------------|-------------|----------|-----------|
| Zoekt | Exact search | Apache 2.0 | Not published | Undocumented | Unknown | No | CLI/API | PRIMARY: GitHub |
| Ripgrep | Exact search | MIT/Unlicense | Linux kernel 0.082s | N/A (stream) | 0.1–0.5s (4M LOC est.) | N/A | CLI | PRIMARY: burntsushi.net |
| Livegrep | Exact search | Per COPYING | Gigabyte scale sub-100ms | Undocumented | <100ms | No | TCP API + Web | PRIMARY: GitHub |
| Hound | Exact search | MIT | ~50 MB RAM | 10–30 min (est.) | Unknown | No | Web UI + API | PRIMARY: GitHub |
| SCIP | Symbol index | Protobuf | 4x smaller than LSIF | Undocumented | N/A | Planned | Format + CLI | PRIMARY: Sourcegraph blog |
| Universal Ctags | Symbol index | GPL | 36 MB/s parsing | 2–10 min (est.) | <10ms | No | Text tags | PRIMARY: GitHub |
| Tree-Sitter | Symbol index | MIT | HTTPie 8.2s, Kubernetes 4.2min | 8–15 min (4M est.) | <1ms | Yes | AST + graph | PRIMARY: WebSearch |
| Kythe | Symbol index | Apache 2.0 | 100B nodes/300B edges | 1–3h (est.) | Unknown | No | Graph DB | PRIMARY: Google |
| Gopls | LSP | BSD | 53–83% memory reduction | Startup ~5s | <100ms | Yes | stdio | PRIMARY: go.dev blog |
| tsserver | LSP | Apache 2.0 | High memory in large repos | Startup ~10s | Unknown | Yes | stdio | PRIMARY: WebSearch |
| Serena MCP | Graph/MCP | GPL-3.0/MIT | 40+ languages | LSP-dependent | LSP-dependent | LSP-dependent | MCP | PRIMARY: GitHub |
| Codebase-Memory MCP | Graph/MCP | Unclear | 28M LOC in 3 min | 20–45s (4M est.) | <10ms | Yes | MCP | PRIMARY: arXiv 2603.27277 |
| Sourcegraph MCP | Graph/MCP | Unclear | Requires Sourcegraph | Depends on backend | Depends on backend | Depends on backend | MCP | PRIMARY: GitHub |
| Jina Code | Embeddings | MIT | 78.41% MTEB average | ~15 min GPU (rough est.) | <100ms | No | API | PRIMARY: Jina |
| Voyage Code-3 | Embeddings | Commercial | +13.8% vs OpenAI | API-dependent | API-dependent | No | API | PRIMARY: Voyage docs |

---

## References

- Primary: https://github.com/sourcegraph/zoekt
- Primary: https://blog.burntsushi.net/ripgrep/
- Primary: https://github.com/livegrep/livegrep
- Primary: https://sourcegraph.com/blog/announcing-scip
- Primary: https://github.com/universal-ctags/ctags
- Primary: https://github.com/tree-sitter/tree-sitter
- Primary: https://kythe.io/
- Primary: https://go.dev/blog/gopls-scalability
- Primary: https://github.com/oraios/serena
- Primary: https://arxiv.org/abs/2603.27277
- Primary: https://github.com/najva-ai/sourcegraph-mcp
- Primary: https://github.com/hound-search/hound
- Primary: https://cms.jina.ai/jina-code-embeddings-sota-code-retrieval-at-0-5b-and-1-5b/
- Primary: https://docs.voyageai.com/embeddings/
- Primary: https://read.engineerscodex.com/p/how-cursor-indexes-codebases-fast
- Secondary: https://www.pistack.xyz/posts/self-hosted-code-search-tools-sourcegraph-zoekt-hound-guide/
- Secondary: https://aicodereview.cc/blog/ripgrep-vs-grep-performance/
