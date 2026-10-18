# Context Rot: LLM Quality Degradation in Long Contexts and Agent Mitigations

**Access date for every URL: 2026-10-17.**

Source tags corrected by hand on 2026-10-17: vendor blogs and summaries of someone else's work are SECONDARY, even where the agent wrote PRIMARY. Everything under "Practical Budgets" that cites LangWatch is one vendor's analysis. Anthropic's own compaction defaults (150K server-side, 100K in the SDK's `compaction_control`) are in note 01 and take precedence.

Context rot is the empirically measured degradation of LLM reasoning quality as input context length increases, even within a model's claimed context window. This manifests as lower retrieval accuracy, weaker reasoning, and systematic failures in agent reasoning—failures that compound during long-horizon agentic tasks.

---

## Evidence of Degradation

### Takeaway

Models do not use context uniformly. Measured performance declines are substantial and systematic across all major vendors; the gap between claimed and effective context length is 40–50% for production models.

### Cited Findings

**Chroma Context Rot (July 2025)** — PRIMARY
- **Tested:** 18 models (Claude Opus 4, Sonnet 3.5/3.7, GPT-4.1/o3, Gemini 2.5, Qwen3)
- **Metrics measured:** Needle-question cosine similarity (0–1 scale), distractors (0, 1, 4), Levenshtein distance for text replication, position accuracy
- **Finding:** "Models do not use their context uniformly; performance grows increasingly unreliable as input length grows" (Chroma statement)
- **Distractor impact:** Single topically-related distractors significantly reduce baseline; impact amplifies with longer contexts
- **Haystack structure:** Models perform *worse* on structured (coherent) haystacks than shuffled (incoherent) ones
- **Source:** https://www.trychroma.com/research/context-rot

**Lost in the Middle (Liu et al., 2024 TACL)** — PRIMARY
- **Task:** Multi-document QA and key-value retrieval across 20-document contexts
- **Finding:** Performance is highest at document position 1 and end; substantially degrades when relevant information is centrally located
- **Accuracy drop:** 30%+ reduction in multi-document QA when answer document moves from position 1 to position 10 (20-document context)
- **Mechanism:** Tokens at beginning and end receive disproportionately strong attention; middle tokens receive less
- **Source:** https://arxiv.org/abs/2307.03172v1

**NoLiMa (ICML 2025)** — PRIMARY
- **Test design:** Needle-in-haystack without literal matching; requires latent semantic reasoning
- **Baseline short-context performance:** Near-perfect (>90%) at <1K tokens across 10 models
- **At 32K tokens:** 11 models drop below 50% of short-baseline, i.e., >50% accuracy loss
- **GPT-4o specific:** Baseline 99.3% (short context) → 89.2% (8K) → 69.7% (32K) → 56.0% (128K)
- **Finding:** Even top-tier models "fail to generalize effectively beyond 8K tokens" on reasoning tasks
- **Source:** https://huggingface.co/papers/2502.05167

**RULER Benchmark (NVIDIA, April 2024)** — PRIMARY
- **Effective vs. claimed context length ratio:** 50–65% effective; only half of advertised length maintains satisfactory performance
- **At 32K tokens:** Only 4 of ~15 models tested (GPT-4, Command-R, Yi-34B, Mixtral) maintain satisfactory performance
- **Beyond 32K:** Most models exhibit "large performance drops as context length increases"
- **Key finding:** Performance ceiling bends sharply at vendor's claimed maximum, not beyond
- **Source:** https://arxiv.org/abs/2404.06654v2

**Michelangelo (DeepMind, Sept 2024)** — PRIMARY
- **Task design:** Latent Structure Queries—models must reason over real-world data and extract implicit structure
- **Finding:** Despite perfect retrieval on vanilla needle-in-haystack, models struggle with complex reasoning at long contexts
- **Models tested:** GPT-4, Llama, Claude, Gemini
- **Key limitation:** Extended context windows improve info retrieval but *not* complex reasoning tasks
- **Source:** https://arxiv.org/abs/2409.12640v2

**1M-Token Context Degradation (2026)** — SECONDARY (vendor blog)
- **Opus 4.6 on MRCR multi-needle at 1M tokens:** 76% accuracy (degraded from <90% at 128K)
- **General pattern:** Claude, GPT, and others show 30–40% degradation before their stated limit
- **Cliff discovery (Gemini 2.5 paper):** Performance "went south" beyond 200K tokens despite claimed 1M window
- **Finding:** Degradation starts around 300K–400K tokens (30–40% of 1M ceiling)
- **Source:** https://www.morphllm.com/claude-context-window

**LongBench v2 (2025)** — PRIMARY
- **Scale:** 503 multiple-choice questions; contexts 8K to 2M words; 6 task categories
- **Finding:** Tests long-context understanding requiring "deep reasoning," not just retrieval
- **Verdict:** Open context lengths alone do not guarantee usable context quality
- **Source:** https://arxiv.org/abs/2412.15204v1

**Fiction.LiveBench (2025–2026)** — SECONDARY (leaderboard mirror)
- **Test:** Story comprehension with character tracking, implicit inference, chronology
- **Top performers (16K tokens):** GPT-5 medium 97.2%, o3-pro 97.2%, Grok 4 94.4%, Gemini 2.5-Pro 91.7%
- **Finding:** Even state-of-the-art models show measurable degradation on long-form reasoning
- **Source:** https://www.datalearner.com/en/benchmarks/fiction-livebench

### Inferences

- **Directional:** Degradation is monotonic and systematic (no surprise reversals).
- **Vendor-independent:** Occurs across Anthropic, OpenAI, Google, Alibaba, open models; not an artifact of one implementation.
- **Non-obvious causes:** Haystack coherence and distractor topical similarity matter more than document count alone.

---

## Agent-Specific Degradation

### Takeaway

Long-horizon agent performance falls sharply with trajectory length, with success rates falling 50–80% on tasks embedded in long interaction histories. Context "poisoning" and "clash" compound over multiple turns.

### Cited Findings

**Drew Breunig on Context Failure Modes** — SECONDARY (interview; the 39% figure comes from Laban et al. 2025, "LLMs Get Lost in Multi-Turn Conversation", arXiv 2505.06120, not fetched here)
- **Context poisoning:** Hallucinations or errors enter context and are repeatedly referenced, compounding mistakes over time
- **Context clash:** Accumulated contradictions derail reasoning; standard benchmark tasks "sharded" across multiple turns show **39% average performance drop** across all models tested
- **Agent-specific degradation pattern:** Success rates reaching 40–50% on short-horizon tasks fall to **below 10%** once embedded in longer interaction history; trace analysis attributes this to agents losing task objective track and entering repetitive loops
- **Performance cliff:** "Anytime we went over 200,000 tokens, it all kind of went south"
- **Mechanism:** Tool-call confusion, inappropriate tool selection, distraction from intended task
- **Source:** https://www.trychroma.com/interviews/drew-breunig-context-engineering-ep-2

**SWE Agent Context Degradation (Empirical)** — PRIMARY (JetBrains paper)
- **Observation token fraction:** Observations comprise ~84% of average turn context in SWE-Bench Lite-50 (from the paper body; not in the abstract and not re-checked on 2026-10-17)
- **Tool output verbosity:** A single action (file read, directory listing, test output) can yield thousands of tokens
- **Implication:** Context rot is unavoidable without active mitigation in coding tasks
- **Source:** https://arxiv.org/pdf/2508.21433

**Multi-Agent Context Partitioning (Cognition)** — PRIMARY
- **Key principle:** Multi-agent systems systematically violate two reliability principles: sharing context and respecting action-embedded decisions
- **Failure mode:** Subagents receive only summaries or single messages; they lack full context of upstream decisions and miss nuance
- **Result:** Miscommunication compounds; conflicting design choices made independently
- **Example:** Separate agents building Flappy Bird clone create inconsistent styles and functionality
- **Cognition's solution:** Single-threaded agent with LLM-based compression of history into key details, events, decisions
- **Source:** https://cognition.com/blog/dont-build-multi-agents

### Inferences

- **Trajectory length is primary degradation driver,** not just window size.
- **Observation verbosity is the kingmaker** in SE tasks; mitigations target this first.
- **Multi-agent partitioning masks, not solves,** context rot; it creates additional fragmentation.

---

## Mitigations and Their Measured Effects

### Takeaway

Simple observation masking matches LLM summarization at half the cost. KV-cache optimization yields 10× cost difference. Compacting at 250K–450K tokens maximizes long-term cost-quality tradeoff. MCP tool deferred loading saves 47%–85% upfront token overhead.

### Mitigation Table

| Mitigation | What It Does | Measured Effect | Source |
|---|---|---|---|
| **Observation masking** | Remove irrelevant tool observations without summarizing | Solve rate 54.8% (Qwen3-32B), cost parity with summarization | JetBrains "Complexity Trap," https://arxiv.org/abs/2508.21433v3 |
| **Hybrid (mask + summarize)** | Mask old observations, summarize only recent | 7–11% cost reduction vs. mask-only or summarize-only | JetBrains "Complexity Trap" |
| **KV-cache optimization** | Ensure prompt prefix is cached; reuse on subsequent turns | 10× cost difference: $0.30/M cached vs. $3.00/M uncached (Claude Sonnet) | Manus via a third-party summary (SECONDARY), https://tianpan.co/blog/2026/03/02/context-engineering-lessons-from-manus |
| **Prompt caching** | Reuse precomputed KV tensors from prompt prefix on repeated calls | 41–80% cost reduction; strategic cache block placement critical | "Don't Break the Cache," https://arxiv.org/abs/2601.06007 |
| **Compaction at 250K–450K** | Summarize trajectory, reset context; task-specific timing varies | Optimal cost-quality: avoids 2.3× worse economics of 1M-token approaches; 10–50% solve-rate drop immediately after, then stabilizes | LangWatch (SECONDARY, vendor blog), https://langwatch.ai/blog/context-tax-when-to-compact |
| **File system context** | Store large outputs to disk; preserve paths/URLs for later retrieval | 100:1 compression ratio achievable; agents retrieve on demand | Manus |
| **Task recitation (todo.md)** | Rewrite task list at end of context every step | Combats "lost-in-the-middle"; keeps objectives in high-attention recency zone | Manus |
| **Preserve errors in context** | Keep failed actions and error messages visible | Agents reason about mistakes and adjust; prevents repeated failures | Manus |
| **Deferred tool loading** | Expose small set of always-loaded primitives + tool search for rest | 47%–85% reduction in upfront token overhead (Jira servers: 3.75K–6.25K → ~2K); one latency round-trip on first use | Anthropic Tool Search (shipped Nov. 2025) via a personal blog (SECONDARY), https://codex.danielvaughan.com/2026/04/23/mcp-schema-bloat-system-prompt-tax-tool-definition-performance/ |
| **Subagent isolation** | Each subagent operates in its own context; prevents cross-contamination | Prevents one agent's exploration from contaminating another's; scales to large task decomposition | LangChain context engineering |
| **Structured notes** | Progress files (tasks.md, decision log) act as lightweight external memory | Agents retrieve specific decisions without full history replay | Manus |
| **Observation variation** | Introduce minor structured variation in tool output formatting | Prevents "pattern overgeneralization" across repetitive tool calls | Manus |

### Inferences

- **Simplicity is often correct:** Masking beats summarization on cost-effectiveness; no fine-tuning required.
- **Cache hits are leverage:** 10× cost difference makes KV-cache strategy dominant; tool caching strategy (deferred loading) saves before the model ever runs.
- **Task-specific timing matters:** Research and QA compact at 250K–300K; building and code understanding at 300K–450K; PR work at 200K–250K.
- **Multi-layered:** No single mitigation suffices; compacting + masking + caching + tool deferred loading are stacked.

---

## Practical Budgets

### Takeaway

Compact between 250K and 450K tokens (task-dependent); every doubling of context costs roughly 6× more. At 900K tokens, economics reach 2.3× worse than optimal. Avoid 1M-token budgets.

### Cited Guidance

**Compaction Timing** — SECONDARY (LangWatch)
- **Sweet spot:** 250K–450K tokens depending on task type
  - PR driving: 200K–250K (minimal verbatim dependency: 2%)
  - Research: 250K–300K (self-contained; low degradation)
  - QA: 250K–350K
  - Building: 300K–450K (highest verbatim edit needs)
  - Code understanding: 300K–450K (cumulative value persists longest)
- **General rule:** When in doubt, "err late" (compact later rather than earlier)
- **Anti-pattern:** Approaching 1M-token limit yields "2.3× worse" cost-quality economics vs. compacting at 220K
- **Source:** https://langwatch.ai/blog/context-tax-when-to-compact

**Cost Scaling** — SECONDARY (LangWatch)
- **Power law:** Every doubling of context costs roughly **6× more**
- **Token tax at extremes:** At 900K tokens, ratio reaches **2,290:1** (tokens read per token produced) vs. **217:1** at optimal 220K range
- **Wide-window penalty:** Moving from 232K to 600K costs an additional **139M tokens per 1,000 productive steps**
- **Observation token burden:** Observations comprise ~84% of context in SWE tasks (from the paper body; not in the abstract and not re-checked on 2026-10-17)
- **Source:** LangWatch, JetBrains

**Cache Cost Ratio** — SECONDARY (Manus via a third-party summary)
- **Cached vs. uncached (Claude Sonnet):** $0.30/million cached vs. $3.00/million uncached = 10:1 difference
- **Implication at 100:1 input-output ratio:** Cache misses make production viability impossible at scale
- **Source:** Manus

**MCP Tool Overhead** — SECONDARY
- **Typical single tool:** 150–400 tokens
- **Server-level (15–25 tools):** 3.75K–6.25K tokens per server
- **Real-world (5 enterprise servers, 58 tools):** ~55K tokens (27% of 200K window) before user interaction
- **Deferred loading reduction:** 47%–85% depending on model and configuration
- **Source:** Codex/Decagon AI

**Context Window Thresholds** — SECONDARY (LangWatch; differs from Anthropic's documented defaults in note 01)
- **Default compaction trigger:** 90% of model window (adjustable to 80%)
- **LLM summarization cost:** Extra model call + token processing + latency
- **Observation masking cost:** Negligible vs. summarization; equivalent quality
- **No justifiable benefit:** Running past 450K tokens toward 1M on typical tasks
- **Source:** LangWatch, JetBrains

### Inferences

- **Sub-linear diminishing returns:** Each doubling costs 6×, but productivity gain drops faster; compaction ROI flips at 300–450K.
- **Cache as force multiplier:** Proper caching (both KV-cache and prompt caching) is mandatory for long-running agents; without it, costs are prohibitive.
- **Tool definition bloat is a hidden tax:** 27% of window before any user work is common; deferred loading is now a standard defense.

---

## Gaps

1. **Exact solve-rate deltas post-compaction:** LangWatch reports "10–50% drop immediately after compaction, then stabilizes" but exact curves by task type remain sparse.
2. **Interaction between mitigations:** How do KV-cache + deferred loading + masking + todo.md combine? Mostly anecdotal (Manus) vs. systematic ablation.
3. **1M-token models (Opus 4.6, GPT-5) edge cases:** Cliff behavior at 200K+ is documented but no published large-scale studies of intentional 500K–1M strategies with all mitigations stacked.
4. **Real-world agent studies on fiction.liveench, LongBench v2:** Most benchmarks are static passages, not agent trajectories; interactive evaluation under context rot is open.
5. **Fine-tuned vs. base models:** Anecdotal data (Cognition's compression model) but no systematic comparison of how fine-tuning for context robustness performs vs. architectural fixes.
