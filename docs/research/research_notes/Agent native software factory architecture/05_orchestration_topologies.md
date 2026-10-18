# Orchestration, Durable Execution, and Multi-Agent Topology for Agent-Native Software Factories

## Durable Execution Engines for Long-Running Agent Workflows

### Takeaway
Temporal dominates AI agent orchestration with event-sourced replay and automatic state management; a competitive landscape including Restate (push-based, sub-50ms latency), DBOS (database-native, 25x faster than AWS Lambda+Step Functions), and Inngest (event-driven SDK) offers alternatives with different latency/determinism tradeoffs.

### Cited Findings
- **Temporal's durable execution model:** Workflows are deterministic in execution (though not predetermined); when a workflow must recover from a crash, it "replays" an agent's progress to date via event sourcing, automatically handling retries, network failures, and LLM rate-limit backoff without developer code. — [Temporal durable execution for AI](https://temporal.io/blog/durable-execution-meets-ai-why-temporal-is-the-perfect-foundation-for-ai)
- **Temporal raises $300M at $5B valuation in 2025 driven largely by AI workloads**, indicating market-level adoption for agentic systems. — [Temporal's funding](https://www.infoq.com/news/2025/09/temporal-aiagent)
- **Temporal + OpenAI Agents SDK:** Public preview integration (2025) introduces Temporal durable execution to OpenAI Agent workflows, enabling automatic handling of rate limits, network disruptions, and crashes without added complexity. — [Temporal and OpenAI partnership](https://temporal.io/blog/durable-execution-meets-ai-why-temporal-is-the-perfect-foundation-for-ai)
- **LangGraph checkpointing and interrupts:** LangGraph supports human-in-the-loop workflows via `interrupt()` and persistent checkpointing (SqliteSaver for local, PostgresSaver for production); workflows pause, save state, and resume on human approval or input. — [LangGraph interrupts](https://changelog.langchain.com/announcements/interrupt-simplifying-human-in-the-loop-agents)
- **Restate challenges replay-based architectures:** Restate adds journals, state, reliable calls, and workflows to normal service code, achieving sub-50ms latencies through push-based (not replay-based) architecture, distinguishing it from Temporal's deterministic replay model. — [Restate durable execution](https://www.diagrid.io/faq/alternatives-dbos-inngest)
- **DBOS launched in March 2024:** Open-source durable execution and workflow orchestration system building workflows on database foundations (co-founded by Postgres creator Mike Stonebraker alongside MIT and Stanford computer scientists); DBOS Cloud runs serverless workflows 25x faster than AWS Lambda + Step Functions. — [DBOS comparison](https://www.diagrid.io/faq/alternatives-dbos-inngest)
- **Inngest AgentKit:** Event-driven platform combining queues and step functions; SDKs for TypeScript, Python, Go; built as an alternative to Temporal for teams that don't want to manage orchestration infrastructure but need durable execution. — [Inngest alternatives](https://www.zenml.io/blog/inngest-alternatives)
- **AWS Step Functions + Bedrock AgentCore (2026):** Step Functions expanded SDK integrations to include BedrockAgentCore service; enables multi-agent parallelism via Map states, agent-provisioning workflows, and Lambda durable execution APIs for idempotent invocations. — [AWS Step Functions Bedrock integration](https://aws.amazon.com/about-aws/whats-new/2026/03/aws-step-functions-sdk-integrations)
- **Determinism vs. nondeterminism:** Temporal's replay model requires deterministic workflows (no random IDs inside); Activities (tool calls, LLM invocations) are where nondeterminism lives. Restate's push model avoids replay-determinism constraints but incurs different latency tradeoffs. — [Temporal determinism constraints](https://temporal.io/blog/of-course-you-can-build-dynamic-ai-agents-with-temporal)

### Inferences
- Temporal's event-sourced replay is the industry standard for long-lived agent workflows, but market alternatives (Restate, DBOS, Inngest) target specific concerns: latency (Restate), infrastructure simplicity (Inngest), or database-native deployment (DBOS). A factory choosing orchestration must weigh automatic state recovery and reproducibility (Temporal advantage) against infrastructure complexity and latency requirements.
- OpenAI and Anthropic now integrate with Temporal or Temporal-adjacent patterns, signaling that durable execution is not a niche requirement for agents but a baseline expectation for production multi-model pipelines.

### Gaps
- No comparative benchmarks found on throughput (workflows/min), memory footprint, or cost-per-workflow across Temporal, Restate, DBOS, and Inngest for agent workloads at scale (e.g., 1000+ concurrent agent instances).
- Minimal public data on Bedrock AgentCore's orchestration semantics (determinism requirements, signal handling, retry budgets) relative to Temporal.
- No evidence found on whether AWS Step Functions or Bedrock AgentCore support credential pooling / seat rotation for quota management.

---

## Multi-Agent Topology: Centralized vs. Distributed Orchestration

### Takeaway
Multi-agent systems deliver quantified gains (Anthropic's research system: 90.2% improvement over single-agent Claude Opus 4; best-of-N code selection: 15.6% pass@1 boost) but face a context-sharing and miscommunication tax. Cognition's single-agent position argues that unified context prevents coordination failure; Anthropic's framing places the decision on task complexity: multi-agent for open-ended problems, workflows for predefined control flow.

### Cited Findings
- **Anthropic's multi-agent research system beats single-agent by 90.2%** (Claude Opus 4 as coordinator, Sonnet 4 as workers), but token consumption is 15x higher than single-agent chats. Token usage accounts for ~80% of the performance gap; upgrading model quality (Sonnet 3.7 → Sonnet 4) delivered bigger gains than doubling token budget on the older model. — [Anthropic multi-agent research system](https://the-decoder.com/anthropic-shares-blueprint-for-claude-research-agent-using-multiple-ai-agents-in-parallel/)
- **Anthropic's framework divides approaches by control flow ownership:** Workflows (augmented LLM + predefined control flow) vs. Agents (LLM directs own control flow). Recommendation: "find the simplest solution possible, and only increase complexity when needed." — [Anthropic's Building Effective Agents](https://resources.anthropic.com/ty-building-effective-ai-agents)
- **Cognition's counter-argument: "Don't Build Multi-Agents"** — Cognition (Devin team) argues single agents are reliable; multi-agent systems are hard to debug and fail due to context loss. Example: in a Flappy Bird task, one subagent built a Mario-like background while another built a mismatched bird, leaving the final agent with unreconcilable outputs. — [Cognition Don't Build Multi-Agents](https://jxnl.co/writing/2025/09/11/why-cognition-does-not-use-multi-agent-systems/)
- **Multi-agent research papers quantify topology selection:** ArXiv papers on topology selection and agent orchestration propose dynamic topology selection for code generation, suggesting best-of-N candidates under an orchestrator. — [ArXiv topology research](https://arxiv.org/pdf/2605.05657)
- **Anthropic's multi-agent architecture sidesteps context limits:** Each sub-agent gets its own context window (solving 200k token ceiling), parallel processing cuts research time by 90% (hours → minutes), and token distribution matters more than raw budget increase. — [Anthropic multi-agent efficiency](https://the-decoder.com/anthropic-shares-blueprint-for-claude-research-agent-using-multiple-ai-agents-in-parallel/)
- **Orchestrator-guided topologies:** Recent work proposes orchestrator agents that emit deterministically decodable plans into strict layered DAGs, enabling predictable multi-agent interaction without emergent miscommunication. — [Goal-Directed Systems evolution](https://arxiv.org/pdf/2602.10479)

### Inferences
- The debate is not "multi-agent vs. single agent" but rather "task complexity determines topology." Cognition's argument applies to tightly-coupled tasks where context loss is catastrophic; Anthropic's applies to large research tasks where parallelism and specialized roles exceed single-agent capacity. A factory should model task complexity at intake and use workflow orchestration (deterministic topologies) for well-defined problems, multi-agent fan-out (N candidates + judge) for open-ended architecture or design work.
- Token cost scaling (15x for 90% improvement) is material but not prohibitive for high-value work. The factory's cost model must account for multi-agent token budgets upfront; credential pooling becomes critical to avoid runaway costs.

### Gaps
- No longitudinal data on Cognition's success with pure single-agent Devin vs. problems where Devin fails and would benefit from multi-agent refactoring.
- Limited quantitative guidance on task-complexity thresholds (e.g., "best-of-N fan-out if task >X LOC or >Y complexity score").
- Insufficient evidence on whether dynamic topology selection is implementable in production orchestration engines.

---

## Patterns: Best-of-N Selection, Planner-Executor-Verifier, and Judge Panels

### Takeaway
Best-of-N candidate selection with LLM judges achieves 15.6% pass@1 improvement for code generation; thinking models (Qwen3-8B, etc.) now outperform specially-trained judge models up to 70B, but all judges exhibit randomness in verdict (order-sensitive), limiting reliability for mission-critical selection.

### Cited Findings
- **Best-of-N for code generation:** By generating 2, 5, or 10 candidates and having a judge select the best, overall performance improved 15.6% in "team settings." Using smaller-language-models-as-judge works better than log-likelihood ranking or random selection. — [Best-of-N code generation](https://arxiv.org/pdf/2602.11911)
- **Judge model selection:** GPT-4-turbo is the best LLM judge for code and summarization; smaller LLMs cannot cope with judging tasks. Recent evaluations show Gemini 2.5 Flash achieves 74.66% accuracy on CodeJudgeBench with lower verdict-shift under perturbations than GPT-4o. — [LLM-as-Judge effectiveness](https://arxiv.org/pdf/2507.16587)
- **Thinking models exceed specialized judges:** Qwen3-8B (thinking model) outperforms specially-trained LLM-as-Judge models up to 70B in code judging, suggesting reasoning depth matters more than model size for selection tasks. — [Thinking models for code judgment](https://arxiv.org/pdf/2507.16587)
- **Judge verdict instability:** All models exhibit randomness in judging; changing presentation order of candidates can substantially impact accuracy. This order-sensitivity limits applicability for high-stakes selection. — [Verdict randomness in LLM judges](https://arxiv.org/pdf/2507.16587)

### Inferences
- Best-of-N with thinking-model judges is practical for code architecture/skeleton generation but requires human review for final selection in safety-critical contexts. Factories should implement best-of-N as a **scoring gate** (ranks N candidates, presents top K to human reviewer) not as an autonomous decision.
- Judge instability (order-sensitivity) suggests implementing N>3 candidate evaluation with consensus thresholds rather than single-judge verdicts.
- Planner-executor-verifier patterns fit naturally into best-of-N: fan-out N plan candidates (from distinct stated angles), score via coverage + consistency (deterministic, not LLM-judged), synthesize one winner, and run an independent completeness critic.

### Gaps
- No evidence on best-of-N selection success rate for architectural decisions (plan quality, coverage) vs. code correctness.
- Minimal guidance on N-value tuning: diminishing return curves of additional candidates.
- No data on whether consensus judging (multiple judges, majority vote) improves verdict stability vs. single-judge selection.

---

## Human-in-the-Loop Workflow Design: Approval Gates, Escalation, and Signals

### Takeaway
Approval gates pause workflows until human input arrives; escalation gates auto-escalate after SLA timeout (to backup approver, on-call rotation, then safe fallback). Temporal and LangGraph both support wait-state orchestration and signal-based resumption, enabling production-grade HITL workflows with automatic escalation and audit trails.

### Cited Findings
- **Temporal's HITL pattern:** Workflows pause on `WaitForSignal()` awaiting human approval (via REST or Activity callback); on signal arrival, execution resumes from the exact paused state with no replay of earlier steps. — [Temporal human-in-the-loop approvals](https://temporal.io/blog/human-in-the-loop-approvals)
- **LangGraph's interrupt model:** `interrupt()` pauses graph execution, saves state to persistence layer, and allows human to approve/reject/edit; resumed via `graph.invoke(Command(resume="user_response"), thread)`. Requires persistent checkpointer. — [LangGraph interrupts](https://changelog.langchain.com/announcements/interrupt-simplifying-human-in-the-loop-agents)
- **Escalation via timeout boundary events:** A user task + timer: if no approval within SLA window, workflow escalates to secondary approver, then on-call rotation, then expires to safe fallback. Escalations fire automatically when reviewers go silent. — [HITL escalation patterns](https://gravitee.io/corpus/gen-1026/autonomous-agent/human-in-the-loop-escalation-and-approval-workflows-for-autonomous-agents.html)
- **Gate types:** Approval gates (block until approval); review gates (human reviews, auto-proceed on timeout); escalation gates (triggered by budget overrun, confidence drop, or retry count). — [HITL gate taxonomy](https://cdn.jsdelivr.net/npm/aiwg@2026.7.12/agentic/code/frameworks/sdlc-complete/rules/hitl-gates.md)
- **Trust scoring for agents:** Agents assigned runtime Trust Score based on tool access patterns, response latencies, escalation frequency; approvals scale with confidence (low-trust agents require more gates, high-trust agents auto-proceed). — [Trust-scaled HITL](https://gravitee.io/corpus/gen-1026/autonomous-agent/human-in-the-loop-escalation-and-approval-workflows-for-autonomous-agents.html)
- **Exception handling taxonomy:** Business exceptions (retry, fallback, compensation); technical exceptions (retry, timeout); governance exceptions (escalation, termination). Each maps to a workflow response pattern. — [Exception handling in HITL workflows](https://gravitee.io/corpus/gen-1286/workflow-engine/human-in-the-loop-approvals-and-exception-handling-in-workflow-engines.html)

### Inferences
- HITL is not a bottleneck if escalation and timeout thresholds are set correctly: review windows of 2–4 hours with 2-tier escalation can cover 99%+ of use cases without requiring 24/7 staffing.
- Trust-scored gates enable progressive automation: low-stage agents (PM review) require approval on every signal; high-stage agents (Build with green tests) auto-proceed on gate pass. This reduces review burden while maintaining control on risky steps.
- Temporal's signal-based HITL is superior to polling-based workflows for resource efficiency; LangGraph's interrupt + checkpointing is better suited for iterative agent development (stop, edit state, resume) than production gate enforcement.

### Gaps
- No data on approval latency impact on overall pipeline SLA.
- Minimal guidance on escalation paths for organizational structures.
- No evidence on whether Trust Scores should be static or dynamic.

---

## Rate Limiting and Credential Pool Orchestration

### Takeaway
Token bucket and leaky bucket rate-limiting algorithms are standard for quota enforcement; credential pooling (multiple API accounts/seats with independent reset windows) enables quota-aware orchestration where agents hand off to fresh credentials when one is exhausted, critical for cost control in multi-agent factories.

### Cited Findings
- **Token bucket and leaky bucket algorithms:** Token bucket limits allow bursts up to capacity while enforcing steady refill (used for per-minute/per-day quotas); leaky bucket enforces smoother output; concurrency gates limit simultaneous operations. — [Rate limiting strategies](https://gravitee.io/corpus/gen-459/bella-s-tree/rate-limit-strategies.html)
- **Agent identity and per-agent quotas:** Register each agent as an OAuth client; apply limits to correct principal (agent ID), then aggregate at team/workspace/tenant level for policy enforcement and chargeback. — [Agent rate limiting](https://www.gravitee.io/corpus/gen-2330/robo-advisor/agent-rate-limiting.html)
- **Workflow-level limits:** Distinct from per-request rate limits; cap step count, delegated tasks, runtime duration, or total external side effects per workflow execution. — [Workflow rate limiting](https://gravitee.io/corpus/gen-993/global-value-chain/rate-limiting-and-quotas-for-distributed-agent-consumers.html)
- **Protected pools for automated agents:** Reserve a protected pool with strict caps and audit trails for automated agents (remediation, incident response workflows) separate from human-initiated jobs. — [Protected agent pools](https://gravitee.io/corpus/gen-2125/plantuml/agent-rate-limiting-workflow.html)
- **Observability metrics:** Track accepted, delayed, rejected job submissions (by project/actor); queue times and runner utilization (by pool/label); external dependency error rates; budget burn-down with forecasted depletion dates. — [CI quota observability](https://gravitee.io/corpus/gen-993/global-value-chain/rate-limiting-and-quotas-for-distributed-agent-consumers.html)

### Inferences
- Token bucket with per-agent quotas and workflow-level caps (e.g., max 50 tasks/workflow, max 10M tokens/run) provides fine-grained cost control without blocking all agents on one quota spike.
- Credential pooling is essential for multi-agent factories running 24/7; without it, a single agent's quota exhaustion blocks all downstream work. Temporal supports seat rotation patterns, making it a natural fit for quota-aware orchestration.
- Budget burn-down visualization (projected cost + depletion date) enables ops teams to forecast quota restarts and provision seats in advance, preventing cascading quota failures.

### Gaps
- No comparative analysis of quota enforcement strategies on fairness, cost control, and latency.
- Missing guidance on optimal seat pool size (N credentials) given expected concurrent load and per-seat reset times.
- No evidence on whether quota-aware agent hand-offs improve cost efficiency vs. random seat assignment.
