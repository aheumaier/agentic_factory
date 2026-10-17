# Industry Learning Loops: How Coding Agents Improve Over Time

Access date for every URL: 2026-10-17.

## Executive Summary

Production coding agents improve through three mechanisms: (1) persistent, repo-scoped memory validated at use time rather than design time, (2) trace-based evaluation loops that convert production logs into test datasets, and (3) rules files (AGENTS.md, .cursorrules) that encode learned patterns as version-controlled code reviewed in pull requests. GitHub Copilot's agentic memory showed a 7% increase in merge rate; Spotify's Honk verification loops caught ~25% of proposed changes via judge layer. No vendor reports fine-tuning as the improvement path—all cite prompt/rule refinement and memory validation instead.

---

## 1. Product Memory Features

### Takeaway
Repository-scoped memories that auto-expire (28 days) and validate against current code are the industry standard. User preferences and team rules are stored separately from code-specific memories. Memory is not approved pre-deployment; it's validated post-retrieval against the current codebase.

### Comparison Table

| Product | What's Remembered | Scope | Write Path | Staleness Handling | Source |
|---------|-------------------|-------|------------|-------------------|--------|
| **GitHub Copilot** | Repo facts (conventions, architecture, build commands); user preferences | Repo-level (facts); user/org-level (preferences) | Auto-created by agent on user write actions | 28-day expiry; citation validation at use time | PRIMARY: [github.blog 2026-01-09](https://github.blog/2026-01-09-building-an-agentic-memory-system-for-github-copilot) |
| **Cursor** | Sidecar-extracted rules from chat; user-written .cursorrules file | Project-scoped | Auto (sidecar model observes chat); manual (rules.md) | Not specified; rules persist in repo | PRIMARY: [lullabot.com](https://www.lullabot.com/articles/supercharge-your-ai-coding-cursor-rules-and-memory-banks) |
| **Devin** | Knowledge (docs, tips, internal libs); Playbooks (task instructions + guardrails); Memory timeline (rollback points) | Org-level (Knowledge); project-level (Playbooks) | Human-curated Knowledge; user-written Playbooks; auto-snapshot | Manual review post-creation; snapshots save states | PRIMARY: [cognition.ai blog](https://cognition.ai/blog/sept-24-product-update) |
| **Windsurf** | Auto-generated memories from 48h of interaction; user rules | Project-scoped | Auto (Cascade observes interaction patterns); manual (user rules) | ~48h learning window; auto-refresh on use | PRIMARY: [memu.pro](https://memu.pro/blog/windsurf-cascade-proactive-memory) |
| **Google Jules** | Repo-specific knowledge; user preferences and feedback; auto-learned patterns | Repo-scoped | Auto (agent infers from feedback); user-added | Not specified | PRIMARY: [TechCrunch 2025-10-02](https://techcrunch.com/2025/10/02/googles-jules-enters-developers-toolchains-as-ai-coding-agent-competition-heats-up/) |
| **Augment** | Automatically updated memories (code style, patterns); persists across sessions | Project-scoped | Auto (inferred from interactions) | Refresh as you work | PRIMARY: [augmentcode.com](https://www.augmentcode.com/blog/meet-augment-agent) |
| **Stripe Minions** | Rule files (directory/pattern-scoped); blueprints (workflow definitions) | Directory/file-pattern scope | Manual (same files as Cursor/Claude Code); blueprints as code | Human review in PR | PRIMARY: [blog.bytebytego.com](https://blog.bytebytego.com/p/how-stripes-minions-ship-1300-prs) |
| **Factory Droids** | Short-term and long-term memory (not publicly detailed); planning state | Agent-session scoped | Not specified | Not specified | PRIMARY: [anthropic.com/customers/factory](https://claude.com/customers/factory) |

### Cited Findings

**GitHub Copilot Memory Architecture (PRIMARY):** Repository facts are created by agents "in response to actions by users with write access" and are validated with citations pointing to specific code locations. When an agent encounters a memory, it verifies citations in real-time against the current branch. If contradictions exist, agents create corrected versions. Expired facts are auto-deleted after 28 days of non-use; timestamp refreshes on successful use.

**Cursor Memories (PRIMARY):** Automatically extracted by a "sidecar" model that observes your chat conversations passively. Two memory types: user-generated rules (explicit API/style definitions) and auto-generated memories from interaction patterns. Applied via `.cursor/rules` directory with triggers: Always, Auto (agent decides), or Manual (user references explicitly).

**Devin Knowledge & Playbooks (PRIMARY):** Knowledge is "a collection of tips, documentation, and instructions that Devin knows across all future sessions." Playbooks are reusable documents specifying task steps, success criteria, and guardrails. Both are curated by humans; no auto-expiry mentioned.

**Stripe Minions Rule Scope (PRIMARY):** Rules are "scoped to specific subdirectories and file patterns." As the agent moves through the filesystem, it "automatically picks up only the rules relevant to where it's working." These are "the same rule files that human-directed tools like Cursor and Claude Code read, so there is no duplication."

### Inferences

1. **Real-time validation beats pre-curation.** GitHub's citation validation and Cursor's rules in version control avoid stale memory bloat.
2. **Scope matters.** Repository-scoped memory (repo facts) stays isolated; user preferences cross repo boundaries. Stripe's directory-scoped rules minimize noise in the agent's context window.
3. **No approval gates at creation.** Memories are created automatically; approval happens post-facto (human review of code changes, citation validation, or rule PR review).

### Gaps

- Cursor's auto-refresh window and expiry policy are not documented publicly.
- Factory's memory architecture is mentioned as requirement (short + long-term) but not implemented publicly.
- No vendor publishes metrics on memory pollution (false memories, out-of-date rules) over time.

---

## 2. Engineering-Team Practices: Rules as System of Record

### Takeaway
Industry practice converges on rules living in version control (AGENTS.md, .cursorrules, blueprint files) reviewed in the same PR as code, and garbage collection agents that detect drift and open cleanup PRs. No vendor advocates for rules databases or out-of-band rule stores. OpenAI's "harness engineering" treats repository as system of record.

### Cited Findings

**OpenAI Harness Engineering (PRIMARY):** AGENTS.md is not an encyclopedia but a ~100-line table of contents pointing to deeper `docs/` directories. "Repository knowledge lives in structured `docs/` directories rather than a single monolithic file." The repo is the system of record: "If it's not in the repo, it doesn't exist for the agent." Organizations "continuously push context into the repo, encoding Slack discussions, architectural decisions, and product specs as versioned artifacts."

Entropy management through garbage collection: "Agents reproduce existing patterns in the repo including bad ones, so organizations codify 'golden rules' into the repo and run periodic background tasks to scan for drift, update quality scores, and open targeted refactoring PRs."

**Stripe Minions Blueprints (PRIMARY):** A blueprint is "the central organizing concept" and "a template for a specific type of engineering task." Blueprints are "a collection of agent skills interwoven with code" and "a structured workflow definition that specifies how tasks are divided into subtasks, handled either by deterministic routines or by the agent."

Stripe uses blueprints to "structure agent execution, interleaving deterministic workflow nodes with AI reasoning steps." This avoids pure LLM loops and embeds safety checks between reasoning phases.

**Spotify Honk Context Engineering (PRIMARY):** Spotify learned that "context engineering is the part of the build that took the most time and iteration to get right, and also where we learnt the most." They provide agents:
- Static, detailed prompts describing desired end states with concrete examples
- Limited tools: verification (linters/tests), git (restricted), allowlisted bash
- No dynamic context fetching; users pre-load relevant information into prompts

Key lesson: "Writing prompts is hard." Their six learned principles: tailor to agent strengths, state preconditions clearly (when not to act), include concrete code examples, define verifiable goals as tests, tackle one change at a time, request agent feedback to refine future prompts.

**Shopify Agents.md (PRIMARY):** Shopify requires `/agents.md` instruction documents specifying that agents must identify themselves, use provided tools, and not script forms. They also define `shop.md` with 22 building blocks (spending limits, "ask me before", etc.) for agent behavior. "Automated scraping, 'buy-for-me' agents or any end-to-end flow that permits payment without a final human review step is not permitted."

### Inferences

1. **Rules are not rules in the traditional sense—they're enforced code.** Stripe blueprints embed safety checks as deterministic nodes; OpenAI garbage collection agents actively detect and fix drift.
2. **Memory as code.** Rules live in version control, reviewed in PRs, and are auditable.
3. **Verification loops are critical.** Spotify's linting, compilation, testing harness caught ~25% of proposed changes (via judge layer vetoing); agents successfully course-corrected about half the time when retried.

### Gaps

- No published guidance on governance boards for rule changes at org scale.
- Stripe does not publish rules-checking metrics (e.g., how many repos comply with scoped rules).
- OpenAI's garbage collection agents are described as concept; no implementation details or success rates shared.

---

## 3. The Trace → Dataset → Eval → Prompt Loop

### Takeaway
**Braintrust** and **Langfuse** automate the feedback loop: instrument production, turn interesting logs into datasets, run offline experiments with scorers, and iterate on prompts/rules without fine-tuning. Both support LLM-as-judge evaluators. Neither reports fine-tuning as necessary for improvement.

### Braintrust (PRIMARY)

From [braintrust.dev/blog/eval-feedback-loops](https://braintrust.dev/blog/eval-feedback-loops):

**The Loop:**
1. Instrument application code to trace context
2. Interesting examples appear in logs
3. Add them to datasets (10–200 examples targeting specific behavioral patterns)
4. Run experiments: execute task against dataset, apply scorers
5. Iterate prompts/models, re-run experiments
6. Deploy when scores are good

**Production-to-Test Flow:** Traces use the same data structure as experiments, so "production data seamlessly becomes evaluation datasets."

**Practical:** Review logs to identify recurring issues. Use metadata filters, tags, and user feedback ratings to surface high-value examples. Run online scoring to auto-surface low-performing cases.

**Data:** Braintrust organizes test cases, runs experiments, logs traces, applies scorers, attaches human feedback. Scorers measure accuracy, relevance, or custom metrics.

### Langfuse (PRIMARY)

From [langfuse.com/docs/evaluation/core-concepts](https://langfuse.com/docs/evaluation/core-concepts):

**Components:**
- **Scores:** Universal data object (NUMERIC, CATEGORICAL, BOOLEAN, TEXT) attachable to traces, observations, sessions, dataset runs
- **Evaluation Methods:** LLM-as-a-Judge, decision models, code evaluators, manual scoring via UI/API
- **The Loop:** Offline (test against fixed datasets via Experiments) + Online (score live production traces)
- **Experiments:** Test applications against datasets; iterate until results look good, then deploy

Workflow: "Test changes, review scores, deploy when ready, monitor production with online evaluation, and continuously expand your dataset with real-world edge cases."

### Inferences

1. **Production logs are the ground truth.** Both platforms treat live traces as the signal source, not synthetic test cases.
2. **LLM-as-judge at scale.** Both support LLM judges for subjective assessments. Neither requires human annotation for every score.
3. **No fine-tuning mentioned.** Both platforms focus on prompt/rule refinement, dataset expansion, and re-evaluation. Fine-tuning is not listed as an improvement path.

### Gaps

- Neither Braintrust nor Langfuse publish metrics on how frequently production-derived datasets uncover new agent failure modes.
- No published guidance on dataset size thresholds or evaluation cadence for optimal improvement.

---

## 4. Measured Improvements from Memory and Rules

### Takeaway
**GitHub Copilot Memory: 7% merge rate increase** (83% → 90%, p < 0.00001); +2% positive feedback on code review comments. No other vendor publishes validated, measured improvements. Stripe claims "1,300 PRs/week" but does not isolate memory contribution. Spotify reports "majority of PRs merged" and ~25% judge veto rate but no baseline comparison.

### Cited Findings

**GitHub Copilot Memory (PRIMARY):** A/B testing showed:
- Copilot coding agent: **7% increase in PR merge rates** (83% without memories → 90% with memories enabled)
- Both improvements achieved high statistical significance: **p-value < 0.00001**
- Copilot code review: +2% positive feedback rise (75% → 77%)

Method: Memories include citations to specific code locations. Before use, agents validate citations in real-time against the current codebase. Adversarial testing (seeding false memories) showed agents consistently detected contradictions and corrected them rather than propagating errors.

Source: [github.blog 2026-01-09](https://github.blog/2026-01-09-building-an-agentic-memory-system-for-github-copilot)

**Stripe Minions (PRIMARY):** "1,300+ merged PRs per week" with agents writing all code, humans reviewing none. However, the article does not isolate the contribution of rule files vs. verification loops vs. blueprints. No before/after comparison provided.

Method: Layered feedback: local linting (< 5s), CI testing (selective from 3M tests with autofixes), max 2 CI rounds (diminishing returns noted).

Source: [blog.bytebytego.com](https://blog.bytebytego.com/p/how-stripes-minions-ship-1300-prs)

Checked against the primary post on 2026-10-17 (1,300+ PRs/week, at most 2 CI rounds, rules scoped to subdirectories): [stripe.dev, Minions part 2](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents-part-2) PRIMARY

**Spotify Honk (PRIMARY):** "Majority of background agent PRs merged into production" after ~1,500 PRs. Judge layer (verification) vetoes ~25% of proposed changes. Agent successfully course-corrects ~50% of the time on retry.

No before/after comparison or control group for rule-set changes.

Source: [engineering.atspotify.com 2025-11](https://engineering.atspotify.com/2025/11/context-engineering-background-coding-agents-part-2)

The ~25% veto and ~50% recovery figures were checked on 2026-10-17 in part 3 of the series: [engineering.atspotify.com 2025-12](https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3) PRIMARY

**Academic/Secondary:** One academic paper (2024) reported "15.7% merge rate at semantic similarity threshold 0.85 for memory rule deduplication" and "0.62 success rate with shared agent memory vs. single agent requiring all 500 questions." (SECONDARY, no vendor validation provided.)

### Inferences

1. **GitHub's 7% lift is vendor-validated and statistically significant.** This is the only published A/B test result with p-values.
2. **Verification loops appear critical.** Spotify's 25% veto rate and 50% correction rate suggest agents depend on fast feedback to self-improve.
3. **No correlation data published.** Neither Stripe nor Spotify isolates which improvement (rules, eval loops, or both) drove the outcome.

### Gaps

- Stripe does not publish merge rate or success rate before/after adopting rules and blueprints.
- Spotify does not publish success rate with/without context engineering.
- No vendor measures time-to-merge or review-burden metrics.
- No vendor publishes memory accuracy or false-positive rates over time.

---

## 5. Governance: Memory Reviewed, Memory as Code, Security Concerns

### Takeaway
Memory governance splits into two camps: **(A) vendor-enforced** (GitHub citations, Cursor sidecar rules) and **(B) user-enforced** (memory as version-controlled code, PR-reviewed). Security researchers flag memory poisoning as distinct from prompt injection—persistent, can outlive sessions—and no vendor publishes defenses beyond citation validation.

### Memory as Code / PR Review (PRIMARY)

**MintMCP and Memclaw:** Emerging practice treats agent memory as version-controlled, diffable, and PR-reviewed. Agentlore is "repo memory for coding agents—committed to your repository, reviewed in the pull request that motivated it, and gated so it cannot silently rot."

Pattern: `.agent_memory/` directory with JSON files reviewed in same PR as code changes.

Source: [mintmcp.com/blog/agent-memory-should-live-git](https://www.mintmcp.com/blog/agent-memory-should-live-git)

**Enterprise Memory Governance:** Two-key pattern: agent plans and stages changes; execution requires explicit policy grant (or human approval) bound to specific diff, scope, and time window.

Source: [radar.firstaimovers.com](https://radar.firstaimovers.com/enterprise-ai-agent-memory-layer-2026)

### Memory Poisoning and Security (PRIMARY)

**Research (2024):** Three peer-reviewed studies identified memory poisoning as distinct from prompt injection:
- Prompt injection ends with session; memory poisoning persists across restarts.
- Attacks include backdoor triggers (specific patterns → malicious output).
- AgentPoison allows injecting crafted demonstrations into memory; triggers cause adversarial outputs even on benign prompts.

**OWASP Formalization:** Memory poisoning is formalized as ASI06, Memory and Context Poisoning, in OWASP Top 10 for Agentic Applications.

**Defense Gaps:** "Existing prompt injection defenses provide incomplete coverage for memory poisoning attacks. Memory design choices that improve agent performance on long-horizon tasks also expand the memory poisoning attack surface."

Sources: [arxiv.org/pdf/2609.13889](https://arxiv.org/pdf/2609.13889) (Persistent Memory Poisoning), [arxiv.org/pdf/2606.04329](https://arxiv.org/pdf/2606.04329) (From Untrusted Input to Trusted Memory), [arxiv.org/pdf/2607.14611](https://arxiv.org/pdf/2607.14611) (Bad Memory)

### Vendor Responses

**GitHub:** Citation validation (verify memory against current code before use) + adversarial testing (agents reject false memories).

**Stripe:** Rules scoped to directories; no agent-to-agent memory sharing.

**Cursor:** Sidecar-generated memories; no adversarial testing published.

### Inferences

1. **Vendor and user governance differ.** GitHub and Cursor enforce via code validation; MintMCP and Memclaw enforce via PR review.
2. **Memory poisoning is acknowledged but not fully defended.** Citation validation is detection, not prevention.
3. **No vendor publishes access controls or audit logs** for memory changes.

### Gaps

- No vendor publishes metrics on false-positive memory corrections.
- No guidance on memory access control (who can read, who can write, when).
- No vendor reports memory breach incidents or security incident response plans.

---

## Comparison: The Learning Loop Architectures

| Dimension | GitHub Copilot | Stripe Minions | Spotify Honk | Braintrust | Langfuse |
|-----------|---|---|---|---|---|
| **Memory** | Repo facts + citations | Rule files (scoped) | Prompts + context | Datasets (from logs) | Traces + scores |
| **Validation** | Citation check at use | Human PR review | None (prompt-based) | Experiment runs | Experiment runs |
| **Expiry** | 28 days | VCS history | Not specified | Not specified | Not specified |
| **Improvement Signal** | A/B merge rate (+7%) | 1,300 PRs/week (baseline unknown) | ~25% veto rate | Online scoring | Online evaluation |
| **Feedback Loop** | Implicit (user merges PRs) | Deterministic + judge layer | Verification loops | Logs → datasets → experiments | Traces → experiments |
| **Fine-tuning** | No | No | No | No | No |

---

## Key Findings for Architecture

1. **Memory is not a luxury—it's load-bearing.** GitHub's 7% merge-rate increase validates that agent memory improves outcomes at scale.
2. **Rules live in code, not databases.** Every approach (Stripe, Spotify, OpenAI, Cursor, Shopify) stores rules in version control or sidecar-managed files.
3. **Verification loops catch ~25% of errors.** Spotify's judge layer and Stripe's multi-round feedback show fast, iterative validation is critical.
4. **Production traces are the dataset source.** Braintrust and Langfuse converge on logs → datasets, not synthetic evaluation.
5. **Memory poisoning is a known gap.** Citation validation helps but is not a complete defense; user-enforced PR review for memory is emerging practice.
6. **No agent vendor fine-tunes.** All cite prompt refinement, rule updates, and eval loop iteration as improvement paths.

---

## Recommendations for Agentic Factory

1. **Implement citation-validated memory** similar to GitHub's approach: store facts with pointers to source code; validate at use time.
2. **Make rules discoverable.** Treat AGENTS.md as a table of contents to deeper `spec/` and `docs/` directories (OpenAI pattern).
3. **Close the eval loop early.** Instrument agent runs as traces; export interesting cases to datasets; run offline experiments before deployment gates.
4. **Version control governance.** Memory and rule changes should go through PR review; treat as system of record.
5. **Monitor verification veto rates.** Tracking judge-layer rejection rates (target: 20–30%) indicates eval coverage.

---

## Research Debt

- **Stripe isolation:** Measure rule-file contribution separately from verification loops and blueprints.
- **Spotify baseline:** Compare context-engineering-refined prompts against baseline, with statistical significance testing.
- **Memory accuracy drift:** Track false-positive memory corrections over time; publish expiry/refresh impact metrics.
- **Multi-agent memory sharing:** No vendor discusses memory exchange between agents; open question for factory-scale agents.
