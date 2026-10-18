# Academic frameworks for LLM-based multi-agent and agentic software engineering

Access dates: 2026-10-13 (existing research) and 2026-10-17 (new research). Items marked UNVERIFIED were not checked against a live source.

## Key question 1: Role-based SDLC multi-agent systems

### Takeaway
Role-based systems (ChatDev, MetaGPT, AgentCoder, MapCoder) split work into fixed roles with a fixed handover order. The strongest evidence is for test-driven loops with a separate tester and for structured handovers. The MAST study (below) finds that many failures in these same frameworks come from design and coordination, not from the base model.

### Cited Findings
- ChatDev: virtual software company with chief-officer, programmer, tester and designer roles, run as waterfall stages (design, code, test, document). Agents talk in a "chat chain" and use a "dehallucination" step where an agent asks for detail before answering. Reported full run under 7 minutes at under $1 — [arXiv:2307.07924](https://arxiv.org/pdf/2307.07924), accessed 2026-10-13.
- MetaGPT: encodes human Standardized Operating Procedures (SOPs) into prompt sequences and uses an assembly-line design with structured handovers, to avoid "idle chatter" between agents. Claims more coherent solutions than chat-based multi-agent systems on collaborative SE benchmarks; ICLR 2024 — [arXiv:2308.00352](https://arxiv.org/pdf/2308.00352), accessed 2026-10-13.
- AgentVerse: open platform (OpenBMB community) for studying emergent agent behaviors with dynamic agent recruitment based on task requirements (contrasts with fixed roles in ChatDev/MetaGPT) — [papers.cool/arxiv/2509.06216](https://papers.cool/arxiv/2509.06216), accessed 2026-10-17.
- AgentCoder: three agents: programmer, test designer (writes tests independently of the code, to avoid bias), and a test executor that is a plain Python script, not an LLM. v3 reports 96.3% (HumanEval) and 91.8% (MBPP) pass@1 with GPT-4 — [arXiv:2312.13010](https://arxiv.org/html/2312.13010v3), accessed 2026-10-13. Version numbers changed across revisions; cite v3.
- MapCoder: four agents (retrieve similar examples, plan, code, debug) in a fixed pipeline with an adaptive traversal step. Reports pass@1 of 93.9% (HumanEval), 83.1% (MBPP), 22.0% (APPS), 28.5% (CodeContests), 45.3% (xCodeEval); ACL 2024 — [arXiv:2405.11403](https://arxiv.org/pdf/2405.11403), accessed 2026-10-13.
- Self-Organized Agents (SoA): agents spawn in number according to problem size; each handles a bounded amount of code, so output size can grow. Reports about 5% pass@1 gain over Reflexion on HumanEval — [arXiv:2404.02183](https://arxiv.org/abs/2404.02183), accessed 2026-10-13. Only abstract-level checks.
- MAST failure taxonomy (Berkeley, NeurIPS 2025): 14 failure modes in three categories. Share of observed failures: specification issues 41.77%, inter-agent misalignment 36.94%, task verification 21.30%. Largest single modes: step repetition 17.14%, reasoning-action mismatch 13.98%, failure to ask for clarification 11.65%, disobey task specification 10.98%. Seven frameworks studied, including MetaGPT and ChatDev. The paper says many failures come from organization and coordination, not only from model limits. Its ChatDev intervention gave "+15.6%" — [arXiv:2503.13657](https://arxiv.org/html/2503.13657v2), accessed 2026-10-13. Root cause analysis: "failures stem primarily from system design issues and inter-agent misalignment, rather than solely from underlying LLM limitations"; public dataset (MAST-Data, 1,600+ annotated traces) released for future research — [arXiv:2503.13657](https://arxiv.org/pdf/2503.13657.pdf), accessed 2026-10-17. The trace count differs across the paper's own sections (200 vs 150+); cite as "about 200 traces."
- CodeAgent (EMNLP 2024; arXiv 2402.02172): multi-agent LLM code review. Mechanism, tasks and results were not read in this pass — UNVERIFIED beyond the title and venue. [arXiv:2402.02172](https://arxiv.org/pdf/2402.02172), accessed 2026-10-13.
- Ablation evidence for role systems is thin in the sources I checked. Not found: a clean ablation that removes SOPs or roles from MetaGPT or ChatDev and reports the drop.

### Inferences
- Separating the test writer from the implementer (AgentCoder) and using a deterministic executor, not an LLM, is a cheap, checkable pattern. It fits a gate that is code, not model judgment.
- Structured handovers (MetaGPT's SOP documents) are the design that MAST's misalignment category points toward. Free chat between agents is the mode with most failures.

### Gaps
- No source found that compares structured artifacts against chat handovers with matched tasks and budgets.
- Not found: a numeric result for CodeAgent (see above).

---

## Key question 2: Single-agent and agent-computer interface (ACI) line

### Takeaway
Agent-computer interface design (SWE-agent) and pipeline designs (Agentless) both beat free-form agent loops on SWE-bench Lite at low cost. The evidence says tool design and verification matter more than the agent loop itself.

### Cited Findings
- SWE-agent: a custom agent-computer interface (ACI) for file editing, repo navigation and test running. Reports 12.5% pass@1 on SWE-bench and 87.7% on HumanEvalFix; ablation shows 10.7 percentage points improvement from specialized shell environment vs. bare Linux shell — [arXiv:2405.15793](https://arxiv.org/abs/2405.15793), accessed 2026-10-13. SWE-bench Verified leaderboard (April 2025): SWE-agent achieves 33.83%, with top variants reaching 52.62% — [swebench.com](https://benchmarklist.com/benchmarks/swebench_full/), accessed 2026-10-17.
- OpenHands (formerly OpenDevin, CodeAct): platform with a CodeAct-based generalist agent, evaluation on 15 benchmarks, MIT license. 72,500+ GitHub stars as of May 2026, v1.7.0 released May 1, 2026. Uses isolated environment with three tool categories (browser, editor, shell). Scored 60.6% baseline / 66.4% with inference-time scaling on SWE-bench Verified (April 2025) — [arXiv:2407.16741](https://arxiv.org/html/2407.16741v3), accessed 2026-10-13; [codesota.com](https://codesota.com/agentic/openhands-vs-swe-agent), accessed 2026-10-17. A separate OpenHands Software Agent SDK paper (MLSys 2026) describes the V1 architecture: agent core separated from applications, four packages (SDK, Tools, Workspace, Server) — [MLSys 2026](https://proceedings.mlsys.org/paper_files/paper/2026/hash/8ae9cf363ea625161f885b798c1f1f78-Abstract-Conference.html), accessed 2026-10-13.
- AutoCodeRover: combines LLMs with sophisticated code search using abstract syntax trees (classes/methods) and spectrum-based fault localization when a test suite exists — [arXiv:2404.05427](https://arxiv.org/pdf/2404.05427), accessed 2026-10-17. Exact resolve numbers were not read in this pass.
- Agentless (FSE 2025): drops the agent loop. Three fixed phases: hierarchical localization, patch generation (40 candidates per bug: 4 location sets × 10 patches), and validation by generated reproduction tests plus regression tests and majority vote. Result on SWE-bench Lite: 96 of 300 (32.00%), $0.70 per problem, 78,166 tokens on average — [arXiv:2407.01489v2](https://arxiv.org/html/2407.01489v2), accessed 2026-10-13. Ablations: reproduction-test selection gave the largest gain (77 → 81 → 96 correct as selection steps were added). The authors identified dataset issues in SWE-bench Lite (problems with exact ground truth patches or insufficient/misleading descriptions), constructing SWE-bench Lite-S for more rigorous evaluation; argument: "simple, interpretable technique" outperforms elaborate agent approaches — [arXiv:2407.01489](https://arxiv.org/abs/2407.01489v2), accessed 2026-10-17. Other baseline costs in the same paper: SWE-agent with Claude 3.5 Sonnet $1.62, OpenDevin+CodeAct $1.14, AutoCodeRover (GPT-4) $0.45, Moatless $0.17. The paper's numbers differ slightly from the FSE listing (32.67%, 98) — cite the arXiv version or check the FSE version before quoting.
- SWE-Search (ICLR 2025): Monte Carlo tree search over agent actions, with a value agent and a discriminator agent that debates. Reports 23% relative improvement across five models over agents without MCTS, and gains with more inference-time search — [arXiv:2410.20285](https://arxiv.org/pdf/2410.20285), accessed 2026-10-13.
- Moatless (project README, self-reported, not peer reviewed): reports a 70.8% solve rate at $0.63 per instance on SWE-bench with Claude 4 Sonnet — UNVERIFIED. [GitHub README](https://github.com/aorwall/moatless-tools), accessed 2026-10-13. No Moatless paper found. Agentless's table lists $0.17 for Moatless.

### Inferences
- Agentless shows that a fixed pipeline with strong validation (generated tests, voting) can match or beat some autonomous agents at a fraction of the cost. The lesson is that verification and candidate selection carry the score. The loop itself does not.
- The ACI result says the tool surface an agent sees is a design choice to make on purpose. The factory should treat the agent's tools as a versioned contract, not an afterthought.

### Gaps
- Not found: a head-to-head at equal budget between Agentless-style pipelines and agent loops on the same newer model generation (2025-2026). The comparisons above use 2024 models.

---

## Key question 3: Roadmap and vision papers

### Takeaway
The 2025 roadmap papers argue that SE moves from "AI helps humans" (SE 2.0) to agents as team members with human oversight. They offer vocabulary, not measured results.

### Cited Findings
- Hassan et al., "Agentic Software Engineering: Foundational Pillars and a Research Roadmap" (arXiv 2509.06216, posted September 2025, authors from Queen's University + Huawei/Concordia/Nara). Frames "SE for Humans" and "SE for Agents" as fundamental duality, reimagining SE's classical pillars (actors, processes, tools, artifacts) across both modalities — [arXiv:2509.06216](https://arxiv.org/html/2509.06216v2), accessed 2026-10-17. Proposes **Agent Command Environment (ACE)** — human-managed command center orchestrating agent teams, handling outputs (Merge-Readiness Packs, Consultation Request Packs), providing mentorship and validation — and **Agent Execution Environment (AEE)** — digital workspace where agents execute independently and proactively invoke human expertise for ambiguity/trade-offs, enabling bi-directional partnership. Names "Structured Agentic SE (SASE)." Self-described as a conceptual framework, not a validated solution.
- Hassan et al., "Towards AI-Native Software Engineering (SE 3.0): A Vision and a Challenge Roadmap" (arXiv 2410.06107, revised 2026-01-09). Argues for intent-centric, conversation-based development with AI teammates — [arXiv:2410.06107](https://arxiv.org/abs/2410.06107), accessed 2026-10-13. Component names (Teammate.next, IDE.next, Compiler.next) come from secondary summaries; check the PDF before citing them.
- He, Treude and Lo, "LLM-Based Multi-Agent Systems for Software Engineering: Literature Review, Vision, and the Road Ahead" (ACM TOSEM 2025, reviewed 71 primary studies). Systematic review of LMA systems in SE; documents taxonomy and research opportunities — [ACM TOSEM](https://ink.library.smu.edu.sg/sis_research/10487), accessed 2026-10-17.
- FSE/ICSE 2025-2026 roadmap papers beyond these were not searched in this pass.

### Inferences
- The two-environment split (command vs execution) matches the factory's own split of "operator control" from "agent run." It is a useful naming check, not evidence for a design.
- SE 3.0 claims are unmeasured. Treat them as design goals to test, not facts.

### Gaps
- Not found: measured outcomes for any SE 3.0 system.

---

## Key question 4: Surveys (2024-2026)

### Takeaway
Surveys use taxonomies by agent role, collaboration mechanism, and SE task. The most SE-specific source found is Liu et al. (arXiv 2409.02977). Verification and human interaction are less covered than planning and tools.

### Cited Findings
- Liu et al., "Large Language Model-Based Agents for Software Engineering: A Survey" (arXiv 2409.02977, September 2024; revised December 2025). Reviews 124 papers from two angles: SE tasks and agent design. Emphasizes "synergy between multiple agents and human interaction" for complex real-world SE problems — [arXiv:2409.02977](https://arxiv.org/pdf/2409.02977), accessed 2026-10-17.
- "A Comprehensive Survey on Benchmarks and Solutions in Software Engineering of LLM-Empowered Agentic System" (arXiv 2510.09721, Oct 2025). Covers 150+ papers. Solutions split into prompt-based, fine-tuning-based, and agent-based paradigms — [arXiv:2510.09721](https://arxiv.org/html/2510.09721v1), accessed 2026-10-13.
- **From LLMs to LLM-based Agents for Software Engineering: A Survey** (April 2025, U. Chicago + U. Sydney). Distinguishes standalone LLMs vs. LLM-based agents in SE; documents research explosion: 1 paper (2022) → 42 papers (2024). Shows dramatic surge in LLM-based agent research activity — [FindAnExpert](https://findanexpert.unimelb.edu.au/scholarlywork/1969924-llm-based-multi-agent-systems-for-software-engineering--literature-review--vision--and-the-road-ahead), accessed 2026-10-17.
- **Agents in Software Engineering: Survey, Landscape, and Vision** (2024). In-depth analysis combining LLM-based agents with SE; summarizes current challenges and proposes opportunities for future research — [alphaxiv.org](https://alphaxiv.org/abs/2409.09030), accessed 2026-10-17.
- Tran et al., "Multi-Agent Collaboration Mechanisms: A Survey of LLMs" (2025). Taxonomy: actors, types, structures, strategies — UNVERIFIED (from search snippet only, no URL fetched).
- The brief's common taxonomy list (planning, memory, tools, verification, human interaction) observed across multiple surveys, with verification and human interaction less covered than planning and tools — [arXiv PDF](https://arxiv.org/pdf/2409.02977), accessed 2026-10-17.

### Inferences
- A factory taxonomy should cover at least roles, handover format, tools, verification, and human checkpoints. Verification and human checkpoints are where the MAST and PR studies show the most failures.

### Gaps
- Full text of Liu et al. was not read; section names are unconfirmed.

---

## Key question 5: Empirical studies of agent-authored PRs

### Takeaway
On GitHub, agent PRs are often merged, but the rates differ by agent and by task. Failures are mostly reviewer abandonment and unwanted work, not broken code. Figures differ between studies, so treat each one as a separate source.

### Cited Findings
- **AIDev dataset** (Li, Zhang, Hassan; arXiv 2602.09185, Feb 2026): 932,791 agent PRs from five agents (OpenAI Codex, Devin, GitHub Copilot, Cursor, Claude Code), 116,211 repositories, 72,189 developers. A curated subset of 33,596 PRs from 2,807 repos with more than 100 stars — [arXiv:2602.09185](https://arxiv.org/html/2602.09185v1), accessed 2026-10-13. Expanded dataset (2026-10-17): 220,612 closed PRs from 489 popular Python repositories, 9,428 from the five agents, spanning 2024-12 to 2025-07 (agent PRs) and 2025-01 to 2025-06 (human PRs) — [alphaxiv.org](https://www.alphaxiv.org/abs/2605.22534), accessed 2026-10-17. An earlier snapshot (arXiv 2507.15003) reported 456,000+ PRs.
- **Merge rates by agent** (AIDev dataset, 2026-10-17): Claude Code 84.3%, OpenAI Codex 73.5%, Copilot varies (43.04%-68.0% across different studies), Cursor 62.4%, Devin 43.0% — [alphaxiv.org](https://www.alphaxiv.org/abs/2605.22534), accessed 2026-10-17. Rejection analysis: only 35.7% reflect clear agentic failures; 31.2% driven by workflow constraints; 33.1% lack observable decision rationale. Reviewer mediation patterns: Copilot/Devin more often in reviewer-mediated workflows; Codex/Cursor typically merged with minimal interaction.
- Pinna, Gong, Williams, Sarro, "Comparing AI Coding Agents: A Task-Stratified Analysis of Pull Request Acceptance" (arXiv 2602.08915; MSR 2026) — [arXiv HTML](https://arxiv.org/html/2602.08915v2), accessed 2026-10-13. 7,156 closed PRs (filtered from 33,596), about 8 months, MIT/Apache repos with an outside review. Overall acceptance (merged share of closed PRs) 69.3%. Per agent: Codex 77.9% (2,002 PRs), Cursor 74.5% (569), Claude Code 71.9% (139), Copilot 68.0% (2,194), Devin 61.6% (2,252). Task type drives the spread: chore 84.0%, docs 82.1%, ci 75.0%, build 72.5%, refactor 71.2%, feat 66.1%, fix 66.0%, test 61.5%, perf 55.4%. The paper's own finding: "no single agent performs best across all task types." Limits: observational, no clustering by repository, Claude Code sample small. Acceptance is not a quality measure.
- **Security in the Age of AI Teammates: An Empirical Study of Agentic Pull Requests on GitHub** (arXiv 2601.00477): examines security implications of agent-authored code — [arXiv](https://arxiv.org/pdf/2601.00477), accessed 2026-10-17.
- **How Do AI Coding Agents Contribute to Software Development? An Empirical Study of Agentic Pull Requests** (2026): further empirical study of agent contributions and integration outcomes — [alphaxiv.org](https://www.alphaxiv.org/abs/2607.21832), accessed 2026-10-17.

### Inferences
- Merge rate is a poor proxy for quality. Reviewer abandonment dominates rejections, so the factory's human checkpoint is the main risk, not the code.
- Infrastructure and config changes merge more often than logic changes. A factory might start with those task types, or gate logic changes more tightly.
- Agent rankings disagree across studies. Do not pick a default agent from these numbers alone.

### Gaps
- The 33k-PR study and the Mazloomzadeh study were not located as primary papers; their figures stay UNVERIFIED.
- The Pinna per-agent rates mix periods (Devin spans 32 weeks, Claude Code 19). Its own aligned 11-week window gives Codex 79.9%, Cursor 74.4%, Claude Code 72.6%, Devin 68.0%, Copilot 68.0%.

---

## Key question 6: Failure modes of multi-agent systems

### Takeaway
MAST (about 200 traces, seven frameworks) is the best-cited failure taxonomy. Its main message is that organization and verification fail more often than the model itself.

### Cited Findings
- Full figures in Key question 1 above — [arXiv:2503.13657](https://arxiv.org/html/2503.13657v2), accessed 2026-10-13.
- Annotation reliability: kappa = 0.88 for human annotators; an LLM-as-judge pipeline with high agreement with humans (value not read) — [arXiv:2503.13657](https://arxiv.org/html/2503.13657v3), accessed 2026-10-13 (v3 wording: 14 modes, three categories).
- Dataset and annotator are public at [github.com/multi-agent-systems-failure-taxonomy/MAST](https://github.com/multi-agent-systems-failure-taxonomy/MAST), accessed 2026-10-13.

### Inferences
- Verification failures (premature termination, no verification, incorrect verification: about 21% combined) argue for a separate, deterministic verification gate outside the agents that wrote the code. This matches AgentCoder's external executor.
- Step repetition (17%) and failure to ask for clarification (12%) argue for hard step budgets and an explicit "ask the human" path.

### Gaps
- MAST's figures are for 2025-era frameworks. Not found: a rerun on 2026 agents.

---

## Key findings from 2026-10-17 research pass (updates to 2026-10-13 baseline)

New sources accessed:
- **Hassan et al. ACE/AEE architecture**: detailed mechanisms for Agent Command Environment (human mentorship) and Agent Execution Environment (agent execution with human callbacks)
- **OpenHands performance**: 66.4% on SWE-bench Verified with inference-time scaling (April 2025), 72,500+ GitHub stars
- **Agentless implications**: simple three-phase pipelines (32% on Lite at $0.70) validate non-agentic baselines as tighter evaluation bounds
- **AIDev dataset expansion**: 220,612 PRs, detailed merge rates (Claude 84.3%, Devin 43%), rejection analysis showing organizational context drives 64% of outcomes
- **MAST root-cause findings**: 41-86.7% failure rates; structural system design issues identified as primary lever, not LLM limitations alone
- **Survey research explosion**: documented 1→42 papers in 2-year period; four complementary surveys (Liu, He, comprehensive survey, vision papers) provide converging taxonomy

---

## Summary implications for factory architecture

1. Use a fixed pipeline with strong, deterministic validation (Agentless, AgentCoder) for well-specified tasks. Keep the agent loop for tasks that need exploration.
2. Give the test writer and the executor roles separate from the implementer. Make the executor a script, not an LLM.
3. Use structured, versioned handover artifacts (SOP-style, MetaGPT) rather than free chat, and cap step counts.
4. Treat tool and interface design (SWE-agent ACI) as a versioned contract.
5. Plan for reviewer abandonment and unwanted PRs: the human checkpoint is the biggest risk to merge throughput (64% of rejections driven by context, not agent).
6. Measure per task type. Infrastructure changes and logic changes behave differently in the PR studies.
7. **ACE/AEE pattern (Hassan et al.)**: Factory's Temporal orchestration aligns with ACE (mentorship + oversight); sandbox isolation aligns with AEE. Formalize escalation mechanics (when swe-agent requests human input) as first-class workflow signals.
8. **MAST and failure prevention**: System design discipline (task specifications, state management, verification gates) is the primary lever. Factory's structured specs/MRP/signal-based gates directly address MAST's modal failure categories (specification, inter-agent misalignment, verification).
