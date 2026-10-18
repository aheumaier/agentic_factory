# Academic Research on Code Localization and Repository Search for Agents

Access date: 2026-10-17.

## Executive Summary

Recent academic research (2024–2026) has produced measured comparisons of code localization methods for AI agents across codebases from 300 to 2.4M lines. Key finding: **graph-based and embedding-based methods achieve 80–90% file-level accuracy on standard benchmarks, but performance collapses sharply above 50K LOC**. Repository context files (AGENTS.md, CLAUDE.md) show marginal or no improvement and increase cost 20%, while grep-based retrieval is surprisingly effective at small scale. No study isolates search tool impact at constant agent performance.

---

## Code Localization Methods: Measured Accuracy

### LocAgent (Graph-Guided LLM Agents)
Access date: 2026-10-17.

**What they built:** Heterogeneous code graph (files, classes, functions, dependencies) indexed offline; agent performs multi-hop graph traversal to find relevant code.

**Benchmark:** SWE-bench-Lite (300 instances), Loc-Bench (560 instances).

**Baseline (SWE-bench-Lite, file Acc@1):** BM25 38.69%, Agentless (Claude-3.5) 72.63%, SWE-Agent (Claude-3.5) 77.37%.

**LocAgent Results (SWE-bench-Lite):**

| Metric | Qwen-7B | Qwen-32B | Claude-3.5 |
|--------|---------|---------|-----------|
| File Acc@5 | 70.80% | 75.91% | 77.74% |
| Module Acc@10 | 82.85% | 87.23% | 87.59% |
| Function Acc@10 | 71.53% | 77.01% | 77.37% |

**End-to-end:** 12% improvement in GitHub issue resolution rate (Pass@10) over baselines.

**Model:** Qwen-2.5-Coder-32B (fine-tuned), Claude-3.5-Sonnet.

**Source (PRIMARY):** [LocAgent: Graph-Guided LLM Agents for Code Localization](https://arxiv.org/abs/2503.09089)

### CoSIL (Issue Localization via LLM-Driven Iterative Code Graph Searching)
Access date: 2026-10-17.

**What they built:** Iterative graph traversal using LLM-guided code repository graph searching.

**Benchmark:** SWE-bench Lite (300), SWE-bench Verified (500).

**Baseline (SWE-bench Lite):** Agentless 58.3% (file Top-1), OrcaLoca 59.0%, LocAgent 64.7%.

**CoSIL Results (Qwen2.5-Coder-32B):**

| Metric | File Top-1 | Function Top-1 |
|--------|-----------|----------------|
| SWE-bench Lite | 61.3% | 43.3% |
| SWE-bench Verified | 64.0% | 44.6% |

**Key:** 96.04% relative improvement at function level vs. baselines.

**Model:** Qwen2.5-Coder-32B.

**Source (PRIMARY):** [Issue Localization via LLM-Driven Iterative Code Graph Searching](https://arxiv.org/abs/2503.22424)

### Agentless (Procedure-Based Hierarchical Localization)
Access date: 2026-10-17.

**What they built:** Hierarchical localization combining prompt-based and embedding-based retrieval.

**Benchmark:** SWE-bench Lite (300).

**Results:**
- File-level: 69.7%
- Function-level: 52.0%
- Line-level: 35.3%

**End-to-end:** 27.33% issue resolution rate at $0.34/task.

**Cost advantage:** 35% cheaper than agent-based competitors.

**Source (PRIMARY):** [Agentless: Demystifying LLM-based Software Engineering Agents](https://arxiv.org/abs/2407.01489)

### OrcaLoca (LLM Agent Framework)
Access date: 2026-10-17.

**Benchmark:** SWE-bench Lite (300).

**Results:**
- Function Match Rate: 65.33%
- File Match Rate: 83.33%

**Integrated task resolution:** 41.00% when paired with patch generation (6.33 pp improvement over Agentless).

**Source (PRIMARY):** [OrcaLoca: An LLM Agent Framework for Software Issue Localization](https://arxiv.org/abs/2502.00350)

### SweRank (Embedding-Based Retriever + LLM Reranker)
Access date: 2026-10-17.

**What they built:** SweRankEmbed (bi-encoder, 137M–7B parameters) + SweRankLLM (instruction-tuned reranker).

**Benchmark:** SWE-Bench-Lite, LocBench.

**Results (SweRankLLM-Large):**

| Benchmark | File | Function |
|-----------|------|----------|
| SWE-Bench-Lite | 83.21% Acc@1 | 88.69% Acc@10 |
| LocBench | 86.61% Acc@5 | 76.25% Acc@15 |

**Advantage over agent-based methods:** SOTA accuracy with lower token cost.

**Source (PRIMARY):** [SweRank: Software Issue Localization with Code Ranking](https://arxiv.org/abs/2505.07849)

### FastCode (Fast and Cost-Efficient Code Understanding)
Access date: 2026-10-17.

**Benchmark:** Loc-Bench (SWE-Bench-Lite subset).

**Key result:** 86.13% Acc@1 file-level localization, outperforming LocAgent (77.74%).

**Advantage:** Significantly lower token consumption.

**Source (PRIMARY):** [FastCode: Fast and Cost-Efficient Code Understanding and Reasoning](https://arxiv.org/abs/2603.01012)

---

## Whole-Task Resolution Rates (End-to-End)

### SWE-Agent (Agent-Computer Interface Optimized Design)
Access date: 2026-10-17.

**What they built:** Specialized file viewer (100-line window, summarized search) and tool set designed for LLM ergonomics.

**Benchmark:** SWE-bench (2,294), SWE-bench Lite (300).

**Results (GPT-4 Turbo):**
- Full SWE-bench: 12.47% resolved
- SWE-bench Lite: 18.00% resolved
- HumanEvalFix: 88.3% pass@1

**ACI ablation finding:** 100-line viewer 18.0% vs. 30-line 14.3% vs. full-file 12.7%; summarized search 18.0% vs. iterative 12.0%.

**Source (PRIMARY):** [SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering](https://arxiv.org/abs/2405.15793)

### RepoGraph (Repository-Level Code Graph Plug-in)
Access date: 2026-10-17.

**What they built:** Plug-in module managing repo-level structure for LLMs, compatible with existing agents/procedural methods.

**Benchmark:** SWE-bench-Lite, CrossCodeEval.

**Results (absolute resolve rates):**

| Method | Baseline | + RepoGraph | Improvement |
|--------|----------|-----------|------------|
| RAG | 2.67% | 5.33% | +99.63% relative |
| Agentless | 27.33% | 29.67% | +8.56% relative |
| AutoCodeRover | 19.00% | 21.33% | +12.3% relative |
| SWE-agent | 18.33% | 20.33% | +10.9% relative |

**Average relative improvement:** 32.8%.

**Source (PRIMARY):** [RepoGraph: Enhancing AI Software Engineering with Repository-level Code Graph](https://arxiv.org/abs/2410.14684)

### SWE-Search (Monte Carlo Tree Search + Iterative Refinement)
Access date: 2026-10-17.

**Benchmark:** SWE-Bench Lite (300).

**Results (23% relative improvement across five models):**

| Model | Baseline | SWE-Search | Improvement |
|-------|----------|-----------|------------|
| GPT-4o | 25.7% | 31.0% | +17% |
| Qwen-2.5-72b | 18.0% | 24.7% | +27% |
| DeepSeek-V2.5 | 16.3% | 21.0% | +22% |
| Llama-3.1-70b | 13.6% | 17.7% | +23% |

**Key:** SWE-Search with open-source model (Qwen-72B) matches GPT-4o baseline.

**Source (PRIMARY):** [SWE-Search: Enhancing Software Agents with Monte Carlo Tree Search and Iterative Refinement](https://arxiv.org/abs/2410.20285)

### CodexGraph (LLM-Driven Code Graph + Graph Query)
Access date: 2026-10-17.

**What they built:** Code graph database + Cypher query generation from LLM.

**Benchmark:** SWE-bench Lite, CrossCodeEval Lite, EvoCodeBench.

**Results (GPT-4o):**

| Benchmark | Metric | Result |
|-----------|--------|--------|
| SWE-bench Lite | Pass@1 | 22.96% |
| CrossCodeEval (Python) | Exact Match | 27.90% |
| CrossCodeEval (Python) | Edit Similarity | 67.98% |
| EvoCodeBench | Pass@1 | 22.96% |

**Source (PRIMARY):** [CodexGraph: Bridging Large Language Models and Code Repositories](https://arxiv.org/abs/2408.03910)

---

## Localization on Large Repositories (Scale Effect)

### LoLBench (Long-Horizon Tasks on Large Systems)
Access date: 2026-10-17.

**Scale:** 100 tasks across 29 systems, average 2.4M source lines of code.

**Finding:** File tree + API spec context improves resolution by 16–22 percentage points.

**Major bottleneck:** Incomplete code localization on large systems.

**Source (PRIMARY):** [LoLBench: Evaluating Coding Agents with Long-Horizon Proposals on Large Software Systems](https://arxiv.org/abs/2609.37143)

### RepoMod-Bench (Repository Modernization on Real Systems)
Access date: 2026-10-17.

**Scale:** 21 repositories, 1.6M LOC, 8 languages.

**Scaling collapse:**
- Projects < 10K LOC: 91.3% pass rate
- Projects 10K–50K LOC: 66.9% average pass rate, "with striking variance"
- Projects > 50K LOC: 15.3% average pass rate; above 100K LOC most projects average below 20%, and uncrustify (162K LOC) scores 0% for all four agents

(Corrected 2026-10-17 against the full text: the first draft had a "50K–100K, 35.5%" bucket that the paper does not have.)

**Inference:** Success falls steeply with repo size, well below 1M LOC. The paper does not test which search method the agents used, so it does not show that grep is the cause. (The first draft's "grep struggles above ~400K LOC" had no source and is removed.)

**Source (PRIMARY):** [RepoMod-Bench: A Benchmark for Code Repository Modernization via Implementation-Agnostic Testing](https://arxiv.org/abs/2602.22518)

---

## Grep vs. Index: Direct Comparison

### GrepRAG Study
Access date: 2026-10-17.

**What they tested:** Naive GrepRAG (LLM generates ripgrep commands) vs. sophisticated baselines.

**Result:** Even basic GrepRAG achieves performance comparable to graph-based baselines on CrossCodeEval.

**Improvement margin:** GrepRAG improves exact match by 7.04%–15.58% relative to best baselines across tasks.

**Inference:** Grep-based retrieval is surprisingly effective at typical benchmark scales; graph advantage emerges in multi-file scenarios.

**Source (PRIMARY):** [GrepRAG: An Empirical Study and Optimization of Grep-Like Retrieval for Code Completion](https://arxiv.org/abs/2601.23254)

### Code Isn't Memory (Structural Index vs. Grep)
Access date: 2026-10-17.

**What they measured:** Localization accuracy with and without a structural codebase index.

**Result on multi-file changes:**
- With structural index: 91.3% accuracy
- With grep-only (agentic search): 44.9% accuracy

**Gap widens with file count:** 3+ file changes show largest structural advantage.

**Source (PRIMARY):** [Code Isn't Memory: A Structural Codebase Index Inside a Coding Agent](https://arxiv.org/abs/2606.22417)

---

## Code Embeddings and Retrieval at Repository Scale

### CoIR Benchmark (Code Information Retrieval Models)
Access date: 2026-10-17.

**What they measured:** Code embedding models on 4 distinct and 8 fine-grained retrieval tasks, 14 languages, 2M+ code snippets.

**Top Performers:**

| Model | Size | CoIR Score | Benchmark | Source |
|-------|------|-----------|-----------|--------|
| CodeXEmbed-7B | 7B | SOTA | Multi-task, 14 languages | PRIMARY |
| SFR-Embedding-Code-7B | 7B | 20% over second | General-purpose | PRIMARY |
| Qodo-Embed-1 | 1.5B | 68.53 | Outperforms 7B models | PRIMARY |
| SweRankEmbed-Large | 7B | 82.12% Acc@10 (func) | SWE-Bench-Lite | PRIMARY |

**Large-scale training:** Pull request data from 628 repos, 53K queries, 29M code chunks.

**Inferred:** Multi-task embeddings outperform single-task; scale of training corpus matters.

**Source (PRIMARY):** [CoIR: A Comprehensive Benchmark for Code Information Retrieval Models](https://arxiv.org/abs/2407.02883)

---

## Repository Context Files (AGENTS.md, CLAUDE.md)

### Evaluating AGENTS.md (ETH Zurich Study, 2026)
Access date: 2026-10-17.

**What they tested:** Impact of LLM-generated vs. human-written context files on agent task success.

**Baseline (no context, Sonnet-4.5):** 59.9% on SWE-bench Lite, 40.7% on CTXbench. (The first draft gave a 48.8% / 40.6% average across 4 models; that is not in the current paper.)

**Impact of LLM-Generated Context Files:**
- Change: –0.5% (SWE-bench Lite) and –2% (CTXbench, 138 instances from 12 repos); p = 87% and 37%, so not significant
- Steps +2.45 and +3.92; cost +20% and +23% (p < 0.001%)

**Impact of Human-Written Context Files:**
- Change: +2.4% on average (p=21%, not significant)
- Steps +3.34; cost up to +19%
- Significantly better than LLM-generated files (p=3.8%)

**Key Finding:** Context files do not generally improve task success. Instructions in them are followed, but "repository overviews ... are not helpful". The paper also says "neither context file length nor specific instruction categories have a strong effect on performance" (files averaged 641 words).

(Checked 2026-10-17 against https://arxiv.org/html/2602.11988, current version. Note 04's first draft named the benchmark "AGENTbench" and gave +4% for human files; the current text says CTXbench and +2.4%. An earlier version may have used other names; the current one is cited here.)

**Not from this paper:** the "20–30 lines maximum, index-only" advice and the Vercel Next.js 16 result (100% pass with an 8KB index) come from a secondary blog, not from the ETH study (SECONDARY: see note 04).

**Source (PRIMARY):** [Evaluating AGENTS.md: Are Repository-Level Context Files Helpful for Coding Agents?](https://arxiv.org/abs/2602.11988)

### ContextBench (Process-Oriented Context Retrieval Evaluation)
Access date: 2026-10-17.

**What they measured:** Context exploration, retrieval, and utilization process (not just task outcome).

**Benchmark released:** February 2026.

**Best Performer (Sep 2026 update):** openJiuwen-JiuwenSwarm + DeepSeek-V4-Pro, 60.4% Pass@1, context F1 0.376.

**Finding:** Removed 2026-10-17. The first draft quoted a "hotel-expense benchmark" result (71.0% → 91.6%) here; it is not about code retrieval and could not be tied to this paper. The leaderboard line above is from the benchmark site (not re-checked).

**Source (PRIMARY):** [ContextBench: A Benchmark for Context Retrieval in Coding Agents](https://arxiv.org/abs/2602.05892)

---

## Auto-Generated Repository Documentation

### RepoAgent (LLM-Powered Documentation Generation)
Access date: 2026-10-17.

**What they built:** Framework that generates functionality descriptions, parameter docs, and usage examples; integrates with GitBook for navigation.

**Measured results:** No quantitative agent task success metrics reported in the paper.

**Scope:** Documentation quality and coverage for developers, not agent task performance.

**Source (PRIMARY):** [RepoAgent: An LLM-Powered Open-Source Framework for Repository-level Code Documentation Generation](https://arxiv.org/abs/2402.16667)

**Inferred gap:** Auto-generated documentation effectiveness for agent tasks is unmeasured; likely related to AGENTS.md finding (marginal impact).

---

## Summary Table: Localization and Task Resolution

| System | Benchmark | Baseline | Result | Metric | Model | Source Tag |
|--------|-----------|----------|--------|--------|-------|-----------|
| **LocAgent** | SWE-Bench-Lite | 77.37% (SWE-Agent file Acc@5) | 77.74% | File Acc@5 | Claude-3.5 | PRIMARY |
| **CoSIL** | SWE-Bench-Lite | 58.3% (Agentless file Top-1) | 61.3% | File Top-1 | Qwen-2.5-32B | PRIMARY |
| **SweRank** | SWE-Bench-Lite | – | 83.21% | File Acc@1 | SweRankLLM-Large | PRIMARY |
| **FastCode** | Loc-Bench | 77.74% (LocAgent) | 86.13% | File Acc@1 | FastCode system | PRIMARY |
| **Agentless** | SWE-Bench-Lite | – | 69.7% (file) | File-level | Claude-3.5 | PRIMARY |
| **OrcaLoca** | SWE-Bench-Lite | – | 83.33% | File Match | Agent | PRIMARY |
| **SWE-Agent** | SWE-Bench Lite | 11.0% (shell-only) | 18.0% | Task Resolved | GPT-4 Turbo | PRIMARY |
| **RepoGraph+Agentless** | SWE-Bench-Lite | 27.33% | 29.67% | Task Resolved | Agentless+RepoGraph | PRIMARY |
| **SWE-Search** | SWE-Bench Lite | 25.7% (GPT-4o baseline) | 31.0% | Task Resolved | GPT-4o | PRIMARY |
| **CodexGraph** | SWE-Bench Lite | – | 22.96% | Pass@1 | GPT-4o | PRIMARY |
| **GrepRAG** | CrossCodeEval | Baselines | +7–15.6% | Relative EM gain | LLM-driven grep | PRIMARY |
| **Code Isn't Memory** | 3+ file tasks | 44.9% (index OFF) | 91.3% (index ON) | Accuracy | With struct. index | PRIMARY |
| **Context Files (None)** | SWE-bench Lite / CTXbench | – | 59.9% / 40.7% | Task Success | Sonnet-4.5 (first draft's 48.8% multi-model avg not found) | PRIMARY |
| **Context Files (Human)** | CTXbench + SWE-bench | — | — | Task Success | +2.4% avg, not sig. (p=21%) | PRIMARY |
| **RepoMod-Bench** | Repos >50K LOC | 91.3% (small) | 15.3% | Pass rate | Agents | PRIMARY |

---

## Key Gaps in Research

1. **No isolated search-tool comparison:** No study holds agent constant while varying only grep vs. index/graph/embedding. Most papers compare whole systems.

2. **Repository scale ceiling undocumented:** RepoMod-Bench shows pass rates falling from 91.3% (<10K LOC) to 15.3% (>50K LOC), and LoLBench reports weak results on large systems, but neither tests search methods. No paper says *which* localization method (grep, index, embedding, graph) holds up at that scale.

3. **Context file dosage unmeasured:** The AGENTS.md study finds that file length and instruction category have no strong effect, and that repository overviews do not help. No study tests a file built for the task at hand.

4. **Embedding training corpus effects unclear:** CoIR shows multi-task embeddings outperform single-task, but no head-to-head comparison of embedding training data size vs. retrieval accuracy on agent tasks.

5. **Grep + embedding hybrid untested:** GrepRAG shows grep works surprisingly well; no paper combines grep for initial pass + embedding reranking on large codebases.

6. **Documentation-as-context unmeasured:** RepoAgent generates docs; Evaluating AGENTS.md tests static context. No empirical link between auto-generated docs and agent task success.

---

## Inferences

- **Graph-based methods (LocAgent, CoSIL) win on standardized benchmarks at ~80% file-level accuracy**, but these benchmarks use 300–560 repos at typical sizes (Python, single to few-file issues).
- **Grep-based retrieval is surprisingly capable** per GrepRAG and early LocAgent baselines; gap vs. graph emerges only in multi-file scenarios.
- **Performance falls sharply above 50K LOC** on RepoMod-Bench (a modernization task, not issue fixing). The paper does not test why; search is one possible cause, task size another. Most papers never test this scale.
- **Embedding reranking (SweRank, SFR-Embedding-Code) achieves SOTA parity with graph** on standard benchmarks, possibly at lower inference cost than agentic graph traversal.
- **Context files (AGENTS.md)**: human-written files gave +2.4% (not significant) at up to +19% cost; LLM-generated ones lowered success and raised cost 20–23%. The 8KB-index result is a secondary blog claim, not from this study.
- **ACI design matters**: SWE-Agent's ablation (100-line viewer vs. full file) shows 5–6 pp difference in task resolution, suggesting tool ergonomics rival localization accuracy.

---

## References

### Primary Papers
- [LocAgent: Graph-Guided LLM Agents for Code Localization](https://arxiv.org/abs/2503.09089) — ACL 2025
- [Issue Localization via LLM-Driven Iterative Code Graph Searching](https://arxiv.org/abs/2503.22424) — CoSIL, 2025
- [Agentless: Demystifying LLM-based Software Engineering Agents](https://arxiv.org/abs/2407.01489)
- [OrcaLoca: An LLM Agent Framework for Software Issue Localization](https://arxiv.org/abs/2502.00350)
- [SweRank: Software Issue Localization with Code Ranking](https://arxiv.org/abs/2505.07849)
- [FastCode: Fast and Cost-Efficient Code Understanding and Reasoning](https://arxiv.org/abs/2603.01012)
- [SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering](https://arxiv.org/abs/2405.15793) — NeurIPS 2024
- [RepoGraph: Enhancing AI Software Engineering with Repository-level Code Graph](https://arxiv.org/abs/2410.14684) — ICLR 2025
- [SWE-Search: Enhancing Software Agents with Monte Carlo Tree Search](https://arxiv.org/abs/2410.20285) — ICLR 2025
- [CodexGraph: Bridging Large Language Models and Code Repositories](https://arxiv.org/abs/2408.03910)
- [LoLBench: Evaluating Coding Agents with Long-Horizon Proposals on Large Software Systems](https://arxiv.org/abs/2609.37143)
- [RepoMod-Bench: A Benchmark for Code Repository Modernization](https://arxiv.org/abs/2602.22518)
- [GrepRAG: An Empirical Study and Optimization of Grep-Like Retrieval](https://arxiv.org/abs/2601.23254)
- [Code Isn't Memory: A Structural Codebase Index Inside a Coding Agent](https://arxiv.org/abs/2606.22417)
- [CoIR: A Comprehensive Benchmark for Code Information Retrieval Models](https://arxiv.org/abs/2407.02883)
- [Evaluating AGENTS.md: Are Repository-Level Context Files Helpful for Coding Agents?](https://arxiv.org/abs/2602.11988) — ETH Zurich, 2026
- [ContextBench: A Benchmark for Context Retrieval in Coding Agents](https://arxiv.org/abs/2602.05892)
- [RepoAgent: An LLM-Powered Open-Source Framework for Repository-level Code Documentation Generation](https://arxiv.org/abs/2402.16667)
