# Codebase Knowledge Layer: Repo Maps, Auto-Generated Docs, and Context Files

Access date for all URLs: 2026-10-17.

## Ranked Repository Maps

### Takeaway
Aider's PageRank + tree-sitter approach sets the standard for production repo maps: structural AST extraction (tree-sitter), centrality ranking (PageRank), token-budget fitting (binary search, default "1k tokens" per aider.chat/docs/repomap.html). Tree-sitter is named only by secondary sources, not the repomap page. Aider reported 26.3% on SWE-bench Lite (PRIMARY: aider.chat/2024/05/22/swe-bench-lite.html; GPT-4o plus Opus, several attempts) with 70.3% correct file identification, but this reflects the full Aider stack, not the map in isolation. The pattern underperforms in rapidly-changing monorepos, heavy metaprogramming (Rails, Python metaclasses), and small repos under 20 files.

### Cited Findings
- Aider repo-map: tree-sitter extraction (secondary) + PageRank ranking + 1k-token default budget (binary search fit, ±15% of target). No isolated measurement of map contribution (SECONDARY: https://www.agentpatterns.ai/context-engineering/repository-map-pattern/).
- Full Aider performance: 26.3% resolve rate on SWE-bench Lite, 70.3% file-identification accuracy (not map-isolated) (SECONDARY: https://www.agentpatterns.ai/context-engineering/repository-map-pattern/).
- Personalized PageRank seeding in task context: conversation identifiers get 10x weight, added files 50x weight. Reranked inverse-rank-weighted seed distribution anchors restart term (SECONDARY: https://agentpatterns.ai/context-engineering/seeding-agent-context/).

### Inferences
Map quality is a proxy for agent orientation cost, not success rate. The 1k-token default budget competes with conversation context; smaller budgets accelerate queries at cost of omitted dependencies. PageRank trades startup cost (precomputation) for steady-state context quality by discovering transitive dependencies from the repo's actual call graph, unlike lexical/semantic seeding alone.

### Gaps
- No direct measurement of map contribution to agent success (isolated from full Aider stack).
- No evidence on map staleness under continuous code change.
- No comparison with hierarchical summaries (e.g., per-directory, per-module).

## Auto-Generated Codebase Documentation

### Takeaway
Three main production systems exist: DeepWiki (Cognition, heuristic + graph + agentic), Google Code Wiki (Gemini-powered, regenerates post-commit), and Windsurf Codemaps (task-specific, SWE-1.5 or Claude Sonnet 4.5). DeepWiki is production-proven at 1.4M repos; the others are recent. All three prioritize generation speed over accuracy measurement. No system publishes agent-task success impact.

### Cited Findings
- DeepWiki (Cognition): 1.4M indexed repos, 20M+ queries served. Uses heuristic file scoring (directory structure, symbol graphs, git history, runtime data) + graph clustering + agentic v2 architecture (agents given tools to pull clusters). Table-of-contents generation prioritized; "TOC is the hardest part" (SECONDARY, talk write-up: https://www.zenml.io/llmops-database/auto-generated-codebase-documentation-and-intelligence-at-scale).
- Google Code Wiki: Regenerates automatically after every single commit. Generates architecture diagrams, class diagrams, sequence diagrams, API references, module walkthroughs, and context-aware chatbot. Free public preview, private repos coming (SECONDARY, video summary: https://www.chaindesk.ai/tools/youtube-summarizer/gemini-code-wiki-googles-ai-that-understands-your-code-fully-free-X7iwxc_MRAg).
- Windsurf Codemaps: Just-in-time mapping. Users choose Fast (SWE-1.5) or Smart (Claude Sonnet 4.5). Produces visual node maps, expandable trace guides, referenced via `@{codemap}` in Cascade agent. "We have yet to benchmark how much better they can make our coding agents" (PRIMARY: https://cognition.com/blog/codemaps).
- RepoAgent: LLM-powered framework using AST analysis (Abstract Syntax Trees for object-level docs), Git integration (detect file changes, trigger auto-update), multi-threaded operations, pre-commit hook support (PRIMARY: https://arxiv.org/html/2402.16667v1).

### Inferences
Generation performance (scale, latency) has matured; quality measurement (agent success impact) has not. DeepWiki's agentic v2 indicates high-quality generation is achievable but requires expensive orchestration (per-repo tuning). Fast generation (SWE-1.5) is favored in interactive tools (Windsurf Codemaps); slow generation (Sonnet 4.5) deferred to "Smart" option. No system measures whether agent succeeds *faster* with this documentation vs. without.

### Gaps
- No published success-rate or cost measurements for any system.
- Windsurf Codemaps: acknowledged as unbenchmarked; refresh strategy unclear.
- DeepWiki: staleness handling not documented.
- RepoAgent: refresh frequency depends on pre-commit hook adoption; no measurement of documentation usefulness to agents.

## Context Files: AGENTS.md, CLAUDE.md, and llms.txt

### Takeaway
2026 research (ETH Zurich, February) found that LLM-generated context files reduce task success by 0.5–2% and increase inference cost 20–23%. Developer-written files improve success by 2.4% (not significant) and still increase cost up to 19%. The paper finds that file length has no strong effect. The "100–150 lines sweet spot" comes from a vendor eval (AuggieBench) reported only by a secondary blog, not from the ETH paper. Stripe and OpenAI practice scoped, hierarchical AGENTS.md (root conventions, subdirectory specifics) with an llms.txt file listing documentation endpoints and LLM-agent best practices. llms.txt adoption by major platforms (Anthropic, Stripe, Cloudflare, Vercel, OpenAI) is real but narrow: mainly for API documentation sites, not generic repos.

### Cited Findings
- ETH Zurich (February 2026): LLM-generated context reduces success 0.5% (SWE-bench Lite) to 2% (CTXbench), neither significant; increases cost 20–23%; adds 2.45–3.92 steps. Developer-written improves success 2.4% on average (p=21%, not significant), costs up to 19% more and adds 3.34 steps. The paper finds no strong effect of file length (corrected 2026-10-17 against the current HTML text; the first draft said "AGENTbench" and "+4%"). LLM files encouraged broader exploration (more tests, file reads, e.g. `uv` used 1.6 times per instance when the file mentions it vs. under 0.01 when it does not; the first draft's "2.5x" is not in the paper). Recommendation: "human-written context files should describe only minimal requirements" (PRIMARY: https://arxiv.org/html/2602.11988, https://iclr.cc/virtual/2026/10021235).
- Vercel eval (January 2026): AGENTS.md with compressed docs index achieved 100% pass; Skills-based approach max 79%; 56% of tasks never invoked available Skill. Passive context (always present) beats active retrieval (agent must decide to look up) (SECONDARY: https://mcp.directory/blog/claude-md-vs-agents-md-vs-skills-2026).
- AuggieBench eval (2026): 100–150 lines optimal, equivalent to Haiku→Opus upgrade; diminishing returns after ~150; poorly constructed files worse than none (SECONDARY: https://mcp.directory/blog/claude-md-vs-agents-md-vs-skills-2026).
- Stripe practice: Hierarchical AGENTS.md (root + subdirectory); scoped rule files (Cursor format) load by pattern; llms.txt with "Instructions for LLM Agents" section listing best practices (e.g., always use Checkout Sessions not Charges API) (SECONDARY: https://codex.danielvaughan.com/2026/04/10/stripe-ai-agent-patterns-enterprise-codex-cli/).
- llms.txt standard: Open standard, adopted by OpenAI, Anthropic, Cloudflare, Stripe, Vercel; narrows effective scope to sites with structured, stable API/framework docs; Cursor, Claude Code read it natively (SECONDARY: https://www.quattr.com/blog/llms-txt-vs-agents-md, https://ulement.com/what-is-llms-txt/).

### Inferences
Context files fix *orientation cost* (what to look at first) but increase *exploration cost* (why look further?). The small (2.4%, not significant) developer-written gain sits next to a cost increase: success margin may come from intent-clarifying comments rather than bulk documentation. The 100–150 line figure is secondary and conflicts with ETH's finding that length has no strong effect; treat it as unproven. Vercel's finding (Skills unused) indicates agents struggle with retrieval-decision heuristics; always-present passive context is safer than optional active lookup. Stripe's scoped hierarchy works because file count stays manageable per scope.

### Gaps
- No direct A/B test of minimal (under 50 lines) vs. comprehensive (>200 lines) context files on same task.
- No measurement of whether human-written files' 4% gain comes from content or from reduced hallucination about conventions.
- Stripe's actual file sizes and scoping rules not published.
- llms.txt: no measurement of agent benefit on real-world tasks; adoption limited to stable API surfaces.

## Staleness and Drift Detection

### Takeaway
Four strategies exist: (1) doc-verification workflows (humans re-bless on schedule, e.g., Guru, Notion); (2) freshness metadata (timestamps, decay functions favor recent content); (3) docs-from-code generation (Backstage TechDocs, Swimm keep docs in repo, visible at code review); (4) authority-weighted retrieval (Unblocked: outrank stale pages at answer time via merge history, review status). No auto-generated documentation system (DeepWiki, Code Wiki, Codemaps) publishes drift detection; the problem is framed as a retrieval-time ranking issue, not a maintenance one.

### Cited Findings
- Four strategies to prevent agents using stale docs: (1) Doc-verification workflows with scheduled human re-check; (2) Freshness metadata (timestamps, decay functions); (3) Docs-from-code generation (co-locate docs and code); (4) Authority-weighted retrieval (outrank stale content at search time using merge history, review status, shipped code) (PRIMARY: https://getunblocked.com/blog/stop-agents-using-stale-documentation/index.md).
- Root cause: "Stale documentation is not a hygiene problem you can clean your way out of, because docs go stale at the speed of merges and humans re-verify at the speed of quarters" (PRIMARY: https://getunblocked.com/blog/stop-agents-using-stale-documentation/index.md).
- Staleness detection: chunk age (6+ months → flag for review); monitor merge frequency vs. doc update frequency; compare docs against test counts, file lists, imports (SECONDARY, vendor help page: https://help.twig.so/rag-scenarios-and-solutions/accuracy/factual-drift).
- Google Code Wiki regenerates post-commit; no drift window published (SECONDARY, video summary: https://www.chaindesk.ai/tools/youtube-summarizer/gemini-code-wiki-googles-ai-that-understands-your-code-fully-free-X7iwxc_MRAg).

### Inferences
Production systems avoid drift by shifting cost upstream (regenerate on commit, Unblocked's strategy) rather than downstream (human verification). Authority-weighted retrieval is cheapest; post-commit regeneration (Google Code Wiki) guarantees freshness but requires orchestration. Verification workflows fail at scale (humans are bottleneck). Staleness is retrievable (not fixable) — agents can be trained to prefer authority signals over recency alone.

### Gaps
- No measurement of drift-detection false-positive rate (flagging stale when up-to-date).
- No data on how often agents actually use authority signals vs. recency when both conflict.
- DeepWiki: staleness handling not documented; hard to assess drift risk at 1.4M scale.

## Task-Seeded Context (Personalized Ranking)

### Takeaway
Identifiers and files named in the task prompt or issue receive personalization boosts in PageRank (10x for mentioned identifiers, 50x for added files). High-quality initial context (hand-curated "gold context") improves agent success rate and reduces token cost. No direct measurement of task-seeded vs. global-ranked maps on the same agent.

### Cited Findings
- Personalized PageRank: conversation identifiers get 10x weight; files added to chat get 50x. Inverse-rank-weighted seed distribution; graph propagation allows related skills to enter context even if not direct semantic neighbors (SECONDARY: https://agentpatterns.ai/context-engineering/seeding-agent-context/).
- Gold context study: agents started with hand-curated context achieved higher final success rate with fewer tool calls and fewer tokens than those without. Implication: better initial context reduces exploration cost (SECONDARY: https://agentpatterns.ai/context-engineering/seeding-agent-context/).
- No direct comparison of task-seeded personalized PageRank vs. unsorted global PageRank on same benchmark.

### Inferences
Task seeding is a form of agent "scaffolding" — reducing decision space (where to look) before exploration starts. The 10x/50x weights are heuristic, not empirically tuned. Gold-context study suggests initial context quality (not quantity) is the lever: better prune search space than saturate it with facts. Task seeding likely works because it disambiguates the repo's structure for the agent's first N moves; diminishing returns likely after context is already focused.

### Gaps
- No published hyperparameter tuning (why 10x and 50x, not 5x and 25x?).
- No measurement of task-seeded performance on codebases where mentioned identifiers are decoys (red herrings).
- No data on whether seeding helps more on small repos (high signal-to-noise) or large (high baseline confusion).

## References

- Aider Repository Map Pattern. https://www.agentpatterns.ai/context-engineering/repository-map-pattern/
- Agentpatterns: Seeding Agent Context. https://agentpatterns.ai/context-engineering/seeding-agent-context/
- Augmentcode: Self-Updating Documentation. https://www.augmentcode.com/guides/self-updating-documentation-docs-agents-sync
- Cognition: Windsurf Codemaps. https://cognition.com/blog/codemaps
- ETH Zurich Study (2026): Evaluating AGENTS.md. https://arxiv.org/html/2602.11988 and https://iclr.cc/virtual/2026/10021235
- Getunblocked: Tools Preventing Stale Documentation. https://getunblocked.com/blog/stop-agents-using-stale-documentation/index.md
- Google Code Wiki Overview. https://www.chaindesk.ai/tools/youtube-summarizer/gemini-code-wiki-googles-ai-that-understands-your-code-fully-free-X7iwxc_MRAg
- MCP Directory: CLAUDE.md vs AGENTS.md vs Skills. https://mcp.directory/blog/claude-md-vs-agents-md-vs-skills-2026
- RepoAgent. https://arxiv.org/html/2402.16667v1
- Stripe AI Agent Patterns. https://codex.danielvaughan.com/2026/04/10/stripe-ai-agent-patterns-enterprise-codex-cli/
- Twig: Knowledge Base Drift. https://help.twig.so/rag-scenarios-and-solutions/accuracy/factual-drift
- Zenml: DeepWiki and Auto-Generated Documentation. https://www.zenml.io/llmops-database/auto-generated-codebase-documentation-and-intelligence-at-scale
