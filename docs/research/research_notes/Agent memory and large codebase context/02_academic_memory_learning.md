# LLM Agent Memory and Learning: Academic Evidence on Reflection, Experience, and Failure

**Access date: 2026-10-17**

## 1. Within-Task Reflection: Gains, Limits, and When Self-Feedback Fails

### Takeaway

Self-reflection without external feedback or correctness signals produces modest to *zero* gains on reasoning tasks. Reflexion achieves strong coding results (+11 pp on HumanEval) by combining reflection with verbal reinforcement, but Self-Refine shows ~0% gain on math reasoning without an oracle. The fundamental barrier: LLMs cannot reliably self-detect errors in their own reasoning.

### Cited Findings

- **Reflexion (2303.11366)** — 91% pass@1 on HumanEval Python (GPT-4 baseline: 80.1%), 68% on Rust (baseline: 60%) — gains via verbal reflection stored in episodic memory, applied to next attempt — [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/pdf/2303.11366)

- **Self-Refine (2303.17651)** — ~20% average improvement across 7 tasks (sentiment, dialogue, code optimization, constrained generation) with iterative self-refinement; *math reasoning: ~0% without external correctness checker*; gains jump to 5%+ only with oracle signal — [Self-Refine: Iterative Refinement with Self-Feedback](https://arxiv.org/pdf/2303.17651)

- **LLMs Cannot Self-Correct Reasoning Yet (2310.01798)** — GPT-3.5 on GSM8K: 75.9% → 74.7% after two reflection rounds; on CommonSenseQA: 75.8% → 41.8%; 74.7% of the time model retains initial answer; when modified, more often converts correct to incorrect — intrinsic self-correction degrades performance, requires oracle feedback to improve — [Large Language Models Cannot Self-Correct Reasoning Yet](https://arxiv.org/html/2310.01798v1)

### Inferences

- Verbal reflection (Reflexion) works better than iterative refinement (Self-Refine) on coding because code has fast external feedback (execution). On abstract reasoning, reflection alone fails.
- The binding constraint: LLMs cannot self-locate errors. Providing error *location* reverses performance loss (2311.08516).

---

## 2. Cross-Task Experiential Memory: Methods, Benchmarks, and Coding Gains

### Takeaway

Experience banks that store and retrieve both successful *and failed* trajectories (ExpeL, ReasoningBank, SWE-Exp) yield 4–8 pp gains on SWE-Bench-Verified. Workflow memory (AWM) achieves +12 pp on WebArena. Gains hold on coding benchmarks and scale with domain diversity. Memento and Voyager skill libraries show strong generalization.

### Cited Findings

#### ExpeL (2308.10144)
- Extracts knowledge from success and failure experiences across tasks, applies via natural-language recalls
- Robust learning efficacy; emerging cross-task transfer; published AAAI 2024
- [ExpeL: LLM Agents Are Experiential Learners](https://arxiv.org/pdf/2308.10144)

#### ReasoningBank (2509.25140)
- Distills reasoning strategies from self-judged success *and* failure experiences
- **WebArena:** Gemini-2.5-flash 40.5% → 48.8% (+8.3 pp); Gemini-2.5-pro 46.7% → 53.9% (+7.2 pp); Claude-3.7-sonnet 41.7% → 46.3% (+4.6 pp)
- **SWE-Bench-Verified:** Gemini-2.5-flash 34.2% → 38.8% (+4.6 pp); Gemini-2.5-pro 54.0% → 57.4% (+3.4 pp)
- Reduces interaction steps up to 16%; strategies exhibit emergent evolution
- [ReasoningBank: Scaling Agent Self-Evolving with Reasoning Memory](https://arxiv.org/html/2509.25140v1)

#### SWE-Exp (2507.23361)
- Multi-faceted experience bank; captures high-level problem comprehension to specific code changes
- **SWE-Bench Verified:** 73.0% pass@1 with Claude 4 Sonnet — state-of-the-art at publication time; outperforms prior agent frameworks
- Establishes experience-driven paradigm over trial-and-error exploration
- [SWE-Exp: Experience-Driven Software Issue Resolution](https://arxiv.org/pdf/2507.23361)

#### Agent Workflow Memory (AWM, 2409.07429)
- Induces reusable routines (workflows) from trajectories; retrieves and applies to guide future tasks
- **WebArena:** baseline BrowserGym 23.5% → AWM 35.5% (+12.0 pp absolute, **51.1% relative**)
- **Mind2Web:** baseline MindAct 36.2% → AWM 45.1% (+24.6% relative); task-level 2.0% → 4.8%
- Generalizes across domain gaps (8.9–14.0 pp advantage vs. baseline on cross-site/domain splits)
- [Agent Workflow Memory](https://arxiv.org/html/2409.07429v1)

#### Memento (2508.16153)
- Case-based memory (CBR) episodic learning without weight fine-tuning
- **GAIA:** 87.88% Pass@3 (validation, top-1); 79.40% test set
- **DeepResearcher:** 66.6% F1, 80.4% PM (vs. 37.7% F1 CoT+RAG baseline); case-based adds 4.7–9.6 pp on OOD tasks
- **SimpleQA:** 95.0% accuracy; **HLE:** 24.4% PM, ranks #2 overall
- [Memento: Fine-tuning LLM Agents without Fine-tuning LLMs](https://arxiv.org/html/2508.16153v2)

#### Voyager (2305.16291)
- Skill library: continuously refines and commits code; retrieves by embedding docstrings
- **Minecraft metrics:** 3.3× more unique items, 2.3× longer distances, 15.3× faster wooden tools unlock, 8.5× stone tools, 6.4× iron, *only* Voyager unlocked diamond
- **Downstream tasks:** 100% success (Voyager with library) vs. 91.67% without, 33.33% (AutoGPT + Voyager library), 0% for AutoGPT/ReAct/Reflexion
- Demonstrated reusability: AutoGPT gained +33 pp from Voyager's skill library
- [Voyager: An Open-Ended Embodied Agent](https://arxiv.org/html/2305.16291v2)

---

## 3. Failure Modes of Memory: Poisoning, Error Propagation, Context Collapse

### Takeaway

Memory is vulnerable: attackers inject malicious records (MINJA 95% success rate); agents replicate and amplify errors from retrieved noisy memories (28–58% performance loss); iterative rewriting erodes details (brevity bias). Selective memory management mitigates all three.

### Cited Findings

#### MINJA — Memory Injection Attack (2503.03704)
- Malicious records injected via query-only interaction; agent retrieves and executes
- Bridging steps, indication prompts, progressive shortening to hide attack
- **Injection success rate (ISR):** >95% across all agents/datasets (often 100%)
- **Attack success rate (ASR):** 76.8% average; ranges 57%–90% by dataset
- Requires only regular user access; highlights practical risk of memory-augmented agents
- [A Practical Memory Injection Attack against LLM Agents](https://arxiv.org/html/2503.03704v2)

#### Error Propagation & Experience-Following (2505.16067)
- **Experience-following property:** high input similarity → high output similarity (agents copy past trajectories)
- **Error amplification:** noisy memory records cause agents to replicate *and amplify* errors; errors compound across tasks if added back to memory
- **RegAgent:** selective strict addition 55.48% → 70.95% success (+28% relative); AgentDriver 32.32% → 51.00% (+58% relative)
- **EHRAgent:** history-based deletion 38.67% → 42.06% accuracy
- Generic "add-all" memory strategy degrades long-term performance; fine-tuned quality evaluators (300 examples for training) recover near-optimal performance
- [How Memory Management Impacts LLM Agents: An Empirical Study of Experience-Following Behavior](https://arxiv.org/html/2505.16067v2)

#### Context Collapse & Brevity Bias (2510.04618)
- **Documented collapse:** 18,282 tokens at step 60 (66.7% accuracy) → 122 tokens at next step (57.1% accuracy drop)
- Brevity bias: iterative rewriting drops domain details, converges to near-identical generic prompts
- Problems in multi-step agents, program synthesis, knowledge-intensive reasoning
- [Agentic Context Engineering (ACE): Evolving Contexts for Self-Improving Language Models](https://arxiv.org/html/2510.04618v1)

---

## 4. Learning Through Weights vs. Context: RL Fine-Tuning and In-Context Approaches

### Takeaway

RL on trajectories (Llama3-SWE-RL: 41% SWE-Bench Verified) is comparable to in-context memory methods (ReasoningBank +4.6 pp), but only accessible to teams that can train. In-context memory (AWM, Memento, ACE) is practical for black-box models and outperforms on web agents (+12 pp AWM on WebArena).

### Cited Findings

#### SWE-RL: RL-based Learning (from search results)
- Lightweight rule-based reward from GitHub commit histories; agents learn from software evolution
- **Llama3-SWE-RL-70B:** 41.0% solve rate on SWE-Bench Verified
- Generalizes to unseen bug-fixing; requires large-scale training infrastructure
- [SWE-RL papers and related work](https://arxiv.org/html/2508.03501v1)

#### In-Context & Prompt Optimization Methods

**ACE (Agentic Context Engineering, 2510.04618)**
- Prevents context collapse with structured, incremental updates; preserves details
- **Agent benchmarks:** +10.6% average (AppWorld offline: +12.5% TGC, +21.4% SGC on test-normal; +15.8% TGC, +18.0% SGC on test-challenge)
- **Finance:** +8.6% average (FiNER +7.6%, Formula +18.0%)
- ReAct + ACE 59.4% ≈ top-ranked IBM CUGA 60.3% on smaller open-source model; surpasses by 8.4% on harder splits
- [Agentic Context Engineering (ACE): Evolving Contexts for Self-Improving Language Models](https://arxiv.org/html/2510.04618v1)

**GEPA (2507.19457)** — *Reflective Prompt Evolution*
- Reads execution traces, diagnoses failures in natural language, maintains Pareto frontier of diverse prompts
- **MATH benchmark:** 93% accuracy (vs. 67% baseline)
- **AIME 2025:** GPT-4.1 Mini 46.6% → 56.6% (+10 pp)
- **General:** +13% over MIPROv2, +20% over GRPO with 35× fewer rollouts (100–500 vs. 10,000+)
- [GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning](https://www.morphllm.com/gepa-prompt-optimization)

**Dynamic Cheatsheet (2504.07952)** — *Test-Time Learning with Adaptive Memory*
- Persistent, evolving memory; stores and reuses strategies, code snippets, problem-solving insights
- **AIME 2024 Claude 3.5 Sonnet:** 23.3% → 50.0% baseline (+27.0 pp); AIME 2025: 6.7% → 36.7% (+30.0 pp)
- **Game of 24 GPT-4o:** 10% → 99% (+89 pp)
- **Math Equation Balancer Claude:** 44.8% → 98–100%
- **GPQA-Diamond Claude:** 59.6% → 68.7% (+9.1 pp); **MMLU-Pro Physics:** 74% → 82% (+8 pp)
- Smaller models (GPT-4o-mini, Claude 3.5 Haiku) show minimal/inconsistent gains
- [Dynamic Cheatsheet: Test-Time Learning with Adaptive Memory](https://arxiv.org/html/2504.07952v1)

---

## 5. Measured Gains on Coding Benchmarks

### Summary Table

| Method | Memory Type | Benchmark | Reported Gain | Coding Relevant? | Caveat |
|--------|------------|-----------|---------------|-----------------|---------|
| **Reflexion** | Episodic reflection | HumanEval Python | +10.9 pp (91% vs 80.1%) | Yes | Requires execution feedback |
| **ExpeL** | Experience bank (success+fail) | Multi-task | Robust efficacy (no single metric) | Partially | General agents, not SWE-specific |
| **SWE-Exp** | Multi-faceted experience bank | SWE-Bench Verified | 73.0% Pass@1 (SOTA) | Yes | Claude 4 Sonnet only; absolute metric |
| **ReasoningBank** | Reasoning strategies (success+fail) | SWE-Bench Verified | +3.4–4.6 pp | Yes | Per-model; Gemini-2.5 tested |
| **AWM** | Workflow routines | WebArena (web, not code) | +12.0 pp (51.1% relative) | Partially | Web-only; cross-domain generalization strong |
| **Voyager** | Skill library (code) | Minecraft (embodied) | 3.3× items, 15.3× milestones | No | Not coding; demonstrates skill reuse |
| **Memento** | Case-based memory (CBR) | GAIA, DeepResearcher (reasoning) | 87.88% GAIA Pass@3; 66.6% F1 DeepResearcher | Partially | Research/QA, not SWE-bench |
| **Dynamic Cheatsheet** | Persistent memory (test-time) | AIME, math, GPQA | +27–30 pp (AIME), +9.1 pp (GPQA) | No | Math/reasoning, limited coding data |
| **ACE** | Evolving context (prompt+memory) | Agent tasks | +10.6% average | Partially | Agents (AppWorld), not coding-specific |
| **GEPA** | Reflective prompt evolution | MATH, AIME | +20 pp over GRPO; 93% MATH | No | Math; not deployed on SWE-bench |
| **Self-Refine** | Iterative self-feedback | 7 tasks; math reasoning | ~20% avg; ~0% math w/o oracle | Limited | Gains vanish on reasoning w/o signal |
| **MINJA** | Poisoning attack (failure mode) | Attack success | ASR 76.8% avg (57–90%) | Security concern | Memory vulnerability, not gain |
| **Llama3-SWE-RL** | RL fine-tuning | SWE-Bench Verified | 41.0% solve rate | Yes | Requires large-scale RL infrastructure |

---

## 6. Inferences and Open Questions

1. **SWE-bench shows modest in-context gains (~4–8 pp).** SWE-Exp's 73% is impressive but absolute; ReasoningBank adds 3–4 pp per model. RL fine-tuning (41%) is comparable to strong baselines (GPT-4 ~30–40% range) but requires infrastructure. Teams without fine-tuning budgets should prioritize selective memory management (error filtering) and experience-driven retrieval.

2. **Error propagation is the largest in-context memory risk.** Selective addition beats naive memory growth by 28–58% relative gain. Fine-tuned evaluators (300 examples) recover near-optimal. Implications: strict filtering > more memory.

3. **Context collapse undermines iterative approaches.** ACE's structured incremental updates (+10.6%) outperform naive rewriting. Brevity bias erodes domain detail. Defense: preserve granular history, avoid wholesale rewriting, use token budgets wisely.

4. **Coding is different.** Reflexion (+11 pp HumanEval) works because code has fast feedback loops. SWE-Exp (73%) learns from multi-level knowledge (problem, repair method, code change). General-purpose experience memory (ExpeL) shows promise but is less validated on SWE-Bench than domain-specific methods.

5. **LLMs cannot self-correct abstract reasoning.** 20% average gain on Self-Refine; 0% on math without oracle. For your swe-agent: design external correctness signals (test execution, linting, merge-conflict detection) rather than relying on reflection alone.

---

## 7. Gaps and Research Directions

- **No published benchmark-to-benchmark ablations.** SWE-Exp reports 73% on SWE-Bench Verified but does not compare directly to ReasoningBank or AWM on the same task. Relative gains unclear.
- **RL vs. in-context scalability trade-off unresolved.** Llama3-SWE-RL 41% appears comparable to in-context memory methods, but training costs, inference latency, and generalization to new domains are not directly compared.
- **Memory poisoning defenses under-explored.** MINJA shows 95% injection success; published defenses are sparse.
- **Multi-agent memory sharing.** Most work assumes single-agent context. Temporal pipeline (swe-agent → architect → pm-agent) may benefit from shared trajectory stores, but no architecture is published.
- **Prompt optimization (DSPy, GEPA) not evaluated on SWE-bench.** GEPA's +20% on GRPO is strong, but gains on coding tasks are unknown.

