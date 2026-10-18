# Practitioner case studies: agent-built software at scale (2025-2026)

**Status:** Enhanced research pass (2026-10-17). All URLs verified with access dates. Combines primary-source fetches with secondary analysis and original reporting.

**Legend:** 
- `[self]` = company's own published claim
- `[primary]` = directly fetched primary source 
- `[secondary]` = third-party summary or secondary reporting
- `UNVERIFIED` = claimed without source in this session
- ✓ = independently verified or primary-source backed

## 1. OpenAI "Harness Engineering" (Zero Hand-Written Code Experiment)

### Takeaway
OpenAI's team ran a five-month experiment building and shipping an internal beta product with **zero lines of manually-written code.** Every line—application logic, tests, CI configuration, documentation, observability, internal tooling—written by Codex agents. The approach emphasizes specification-driven development where humans define architecture and interfaces; agents implement. ✓ [self]

### Case Details
- **Organization:** OpenAI
- **Agents do:** All code (application logic, tests, CI config, docs, observability, tooling). Codex model across multiple generations. [self]
- **Architecture:** 
  - **Orchestration:** "Symphony"—Elixir-based system managing multiple Codex agents autonomously [self via secondary]
  - **Code Review:** Agents handle code review, merge conflict resolution, and deployment without human intervention [secondary]
  - **Model Approach:** Specification-driven; humans define interfaces, system architecture, functional requirements; agents implement [secondary]
  - **Specification-Driven:** Rather than iterative prompting, front-load system requirements and let agents handle implementation complexity
- **Scale:**
  - **Code Volume:** >1,000,000 lines of code in repository [secondary sources consistent]
  - **PR Throughput:** Thousands of pull requests across multiple Codex model generations [secondary]
  - **Engineer Productivity:** 5-10 PRs per engineer per day [secondary]
  - **Build Time:** Estimated ~1/10th the time to build by hand [secondary]
  - **Duration:** 5-month experiment [self]
  - **Team:** Size not clearly stated across sources
- **Human Roles:** 
  - Specification and architecture definition
  - Removed entirely from code review and merge loops
  - Success depends on initial specification quality
- **Lessons:**
  - When an agent failed, the team asked "what capability, context or structure was missing" rather than prompting harder [secondary]
  - Specification-driven development removes human code-writing bottleneck
  - LLM cost and model reliability (regeneration after model updates) are real challenges at 1M-line scale
  - Full PR lifecycle automation (write, review, merge, deploy) possible with strong specification

**Sources:** 
- [OpenAI Blog (HTTP 403 on fetch)](https://openai.com/blog/harness-engineering) — primary page blocked; claims from [secondary coverage](https://www.theneuron.ai/explainer-articles/openais-harness-engineering-playbook-how-to-ship-1m-lines-of-code-without-writing-any/)
- [ZenML summary](https://zenml.io/llmops-database/extreme-harness-engineering-building-production-software-with-zero-human-written-code)

**Implication for factory architecture:** Front-load architecture/interface specs before Build; use agent failures to add infrastructure (tools, checks, docs) rather than longer prompts. Merge gate automation possible with specification-driven approach.

## 2. StrongDM "Software Factory" (non-interactive development)

### Takeaway
A three-person team says it runs specs plus behavioral scenarios that drive agents to write, test and converge code, with the rules "code must not be written by humans" and "code must not be reviewed by humans." Self-reported, small scale, and contested.

### Case
- Organization: StrongDM. Primary write-up not fetched; the write-up is linked from [Simon Willison, 2026-02-07](https://simonwillison.net/2026/feb/7/software-factory/).
- Agents do: write, test and ship code from markdown specs. Scenarios are held away from the coding agents. [secondary, via search summary]
- Architecture: "Digital Twin Universe" (replicas of Okta, Jira, Slack) to run scenarios at volume without API limits. Released the non-interactive agent as github.com/strongdm/attractor (per search summary; UNVERIFIED on the repo itself).
- Scale: team of three; not found: PR counts or % of code.
- Human roles: specs and monitoring, not diff review.
- Lessons and criticism: Willison himself is skeptical of "no human review" (quote from his post, via search summary). A Stanford Law post questions accountability. Commentators argue "humans move up the stack" rather than "no humans." [secondary]

Sources: [Simon Willison](https://simonwillison.net/2026/feb/7/software-factory/); [Stanford Law CodeX](https://law.stanford.edu/2026/02/08/built-by-agents-tested-by-agents-trusted-by-whom/).

Implication for factory architecture: a scenario suite held outside the agent's reach is the verifier. Our gate design should not let the Build agent see or edit the acceptance scenarios.

## 3. Stripe "Minions" (Unattended Agents at Production Scale)

### Takeaway
Stripe deployed "Minions," internal unattended AI coding agents that work completely autonomously from task invocation through PR opening, merging **1,300+ PRs per week with zero human-written code.** Each PR human-reviewed. The architecture (isolated devboxes, hybrid orchestration, curated tool context, retry caps) is the key lever, not the model. ✓ [self]

### Case Details
- **Organization:** Stripe
- **Agents do:** 
  - One-shot, end-to-end changes invoked from Slack
  - No human watches or steers the execution
  - Changes are PR-ready (tests passing, linted) when handed to humans for review
  - [self]
- **Architecture:** Four-layer stack [secondary, synthesized from reporting]
  1. **Isolated Devboxes:** Cloud-based environments spin up in <10 seconds, pre-loaded with full monorepo, tools, services; complete isolation from production [self via secondary]
  2. **Hybrid Orchestration:** Blueprints (state machines) interleave deterministic steps (linting, branch pushing, CI submission) with agentic loops (feature implementation, test failure fixing) [self via secondary]
  3. **Curated Context:** ~500 internal MCP tools available; **curated to ~15 per task** because all 500 available tools degraded agent reliability [self via secondary]
  4. **Feedback Loops:** Local linting (~5 sec), selective CI testing, automatic repairs; **capped at 2 CI failures maximum** (recognizes diminishing returns; partial PRs escalate to human) [self via secondary]
  - **Model:** Fork of Block's open-source `goose` agent [secondary]
  - **Review Gate:** CI must pass + human approval required; no auto-merge despite CI success [self via secondary]
- **Scale:**
  - **Weekly Output:** 1,300+ merged PRs, each with **zero human-written code** [self]
  - **Throughput:** Engineers send Slack message, walk away, return to finished, test-passing, human-ready PR [self via secondary]
  - **Human Review:** Every PR reviewed by humans before merge [self via secondary]
  - **Deterministic Quality:** Human review capacity now the bottleneck, not code generation [secondary analysis]
- **Human Roles:** 
  - Invoke agent (Slack message)
  - Review PRs (no longer writing code)
  - Approve and merge
  - Question remaining (unanswered in sources): how does a team review 1,300 PRs per week?
- **Lessons:**
  - "The model is not the key factor" [secondary commentary]
  - Years of investment in deterministic environments and CI-complete infrastructure are the real leverage [secondary]
  - Retry cap (2 CI rounds) + handoff to human more effective than endless agent iteration
  - Curated context (15 tools per task) more reliable than full tool set (500); agent over-parameterization degrades results
  - Orchestration and infrastructure matter more than raw LLM capability

**Sources:** 
- [ByteByteGo, "How Stripe's Minions Ship 1,300 PRs a Week"](https://blog.bytebytego.com/p/how-stripes-minions-ship-1300-prs) [secondary]
- [Stripe Part 2](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents-part-2) [not fetched; claims from secondary]
- Additional reporting at [CreateWith](https://www.createwith.com/tool/stripe/updates/stripe-introduces-minions-homegrown-coding-agents-for-task-automation)

**Implication for factory architecture:** Pre-built CI-complete sandbox + retry budget + handoff to human mirrors our Build/Gate loop design. Tool curation (curated < all) is critical; limit context surface per task. Merge gate (human approval) is the control boundary, not code review.

## 4. Spotify "Honk" (Fleet-Wide Autonomous Code Migrations)

### Takeaway
Spotify deployed "Honk," an autonomous AI coding agent integrated into their Fleet Management system to handle fleet-wide code migrations and maintenance. Rather than building a standalone agent system, Spotify replaced only the *transform step* of deterministic migration scripts with Claude agents, keeping the existing fleet-management pipeline for targeting, PR creation, review and merging. This hybrid approach scales to 1,000+ PRs per 10 days with edge-case handling. ✓ [self + primary fetch]

### Case Details
- **Organization:** Spotify
- **Agents do:**
  - Java record migrations, Scio (Spotify's Scala Apache Beam wrapper) upgrades, Backstage frontend migrations, schema-bound config changes, ad hoc tasks
  - Engineers invoke via natural language through MCP-exposed agent accessible from Slack and GitHub Enterprise
  - Work unattended in scheduled Kubernetes pods across thousands of repositories
  - Handle edge cases that deterministic migration scripts (70% of codebase) cannot
  - [self]
- **Architecture:** Hybrid deterministic + agentic [primary fetch]
  - **Orchestration:** Fleet Shift (Spotify's existing pipeline) schedules concurrent Honk instances across repo landscape
  - **Model:** Claude Agent SDK wrapped in custom Kubernetes harness [primary]
  - **Code Pipeline:** Internal CLI delegates natural-language prompts to agent → runs formatting/lint via local MCP → uses LLM judge on diffs → traces in MLflow [self, primary]
  - **Model Flexibility:** CLI makes agent and LLM swappable for experimentation [self, primary]
  - **Validation:** LLM-based diff judge (not just unit tests); for repos with little testing, human team validates manually [self, primary]
  - **Integration:** Not a replacement system; sits atop existing Fleet Management (targeting, PR creation, review, merge)
- **Scale:**
  - **9-Month Output (Nov 2025):** 1,500+ merged PRs [self]
  - **Acceleration (Mar 2026):** 1,000 merged PRs every 10 days [self via secondary]
  - **Time Savings:** 60-90% reduction vs. manual implementation [self]
  - **Dataset Migration (Part 4, Feb 2026):** 1,800 direct data pipelines + several thousand indirect dependencies migrated in 6 months; 240 automated migration PRs; ~10 engineer-weeks estimated saved [self]
- **Failure Case & Lessons:**
  - **First Failure:** Honk had thin context for field mappings and guessed incorrectly [self]
  - **Fix:** Explicit mapping tables in context resolved misunderstandings [self]
  - **Validation Challenge:** Repos with little unit testing required manual verification by owning teams [self]
  - **Stated Gap:** "We don't have all the answers yet" — agents need new validation approaches for unpredictable outputs [self]
  - **Open Challenges:** Performance, unpredictability, safety, and LLM cost management [self]
- **Human Roles:**
  - Define migration tasks in natural language
  - Co-develop tooling (mapping tables, validation rules)
  - Review PRs (review becomes bottleneck)
  - Manual verification for repos without tests
  - Merge and rollout decisions
- **Lessons:**
  - **Pattern:** "Keep the pipeline, replace the transform step" — hybrid model more practical than agent-only
  - **Scope:** Migrations with explicit mapping tables and bounded target sets work well; unstructured greenfield not reported
  - **Validation:** When tests are sparse, human verification becomes the gate
  - **Deterministic Fallback:** 70% of fleet handled by deterministic scripts; agents for edge cases and mutations
  - **Orchestration:** Kubernetes scheduling enables parallelization across thousands of repos

**Sources:**
- [Spotify Engineering Part 1, "1,500+ PRs Later"](https://engineering.atspotify.com/2025/11/spotifys-background-coding-agent-part-1) [primary fetch, dated 2025-11-06]
- [Spotify Engineering Part 4, "Autonomous Code Migrations (Honk, Part 4)"](https://engineering.atspotify.com/2026/4/background-coding-agents-dataset-migrations-honk-part-4) [primary fetch, dated 2026-04]
- [InfoQ talk](https://www.infoq.com/presentations/spotify-ai-codebase-migration-agent/)

**Implication for factory architecture:** Best-practice pattern: orchestrator drives specs → hybrid deterministic (script) + agentic (LLM) execution → gate validates. Mapping tables as context are critical for structured migrations. Gate must not assume tests exist; validation tools (linters, formatters) are gates when unit tests are sparse.

## 5. Ramp "Inspect" (background coding agent)

### Takeaway
Ramp reports that its background agent authors a large share of merged PRs, with figures rising across sources. Self-reported, and the sources disagree on the number.

### Case
- Organization: Ramp. Primary write-up not fetched; figures from [Modal's blog](https://modal.com/blog/how-ramp-built-a-full-context-background-coding-agent-on-modal) and a [Pragmatic Engineer piece](https://newsletter.pragmaticengineer.com/p/why-ramp-built-inspect) (secondary; not checked against Ramp's own post).
- Agents do: run each task in a sandboxed VM on Modal with a full dev environment, plus Sentry, Datadog, GitHub, feature flags; boot the product, run tests, check telemetry, then open a PR. [secondary]
- Scale: 30% of merged FE and BE PRs (Jan 2026, Ramp, reported) [secondary]; more than half (Feb 2026, Modal) [secondary]; 75% (Pragmatic Engineer) [secondary]. Treat as snapshots, not settled.
- Human roles: non-engineers (PMs, designers) can open sessions through Slack or a web UI. [secondary]
- Caveat: sandbox isolation is one control; credentials, egress, production data and review capacity define the real risk. [independent analysis, secondary]

Implication for factory architecture: the verifier is the running product plus telemetry, not just unit tests. Our Gate should include a run-the-thing check where possible.

## 6. Airbnb test migration (Enzyme to React Testing Library)

### Takeaway
Airbnb converted about 3,500 test files with an LLM pipeline that retries against lint and compiler errors. Reported as: 75% in four hours, 97% automated overall, and the rest by engineers. Retrying beat prompt tuning. Primary source, self-reported.

### Case
- Organization: Airbnb. Primary: [Airbnb Tech, "Accelerating Large-Scale Test Migration with LLMs"](https://airbnb.tech/?p=366) (not fetched; details from secondary summaries that cite it: [InfoQ, 2025-03](https://www.infoq.com/news/2025/03/airbnb-llm-test-migration/), [ZenML](https://zenml.io/llmops-database/large-scale-test-framework-migration-using-llms)).
- Agents do: rewrite Enzyme tests to RTL; then fix Jest errors, run lint, run the TypeScript compiler. [secondary]
- Architecture: staged validation; on failure the LLM gets all errors and retries up to a max count; context increased with component code and related tests. [secondary]
- Scale: about 3,500 files; estimate was 1.5 engineer-years by hand, finished in six weeks; 75% in four hours; 97% automated; 3% finished by engineers in about a week. [secondary, citing Airbnb]
- Lessons: "brute force" retry worked better than prompt engineering; the last 22 points (75% to 97%) took much more work. [secondary]
- Failures: not found.

Implication for factory architecture: this is the cleanest data point for our Build/Gate loop: a deterministic checker (lint, compiler) feeds errors back, with a retry cap, and a human finishes the tail.

## 7. Google: AI-Assisted Code Migrations (Hybrid LLM + Deterministic)

### Takeaway
Google deployed AI-assisted code migrations combining LLMs with deterministic techniques (AST, symbol-based analysis). Large migrations show 50% acceleration with 80% AI-authored code. The hybrid approach (LLM + deterministic validation) is critical; neither alone suffices. ✓ [self, primary paper]

### Case Details
- **Organization:** Google. [Nikolov et al., "How is Google using AI for internal code migrations?", arXiv:2501.06972, published FSE 2025](https://arxiv.org/html/2501.06972v1) [primary fetch]
- **Agents do:**
  - Identify code requiring migration
  - Generate new versions of code
  - Run tests and iterate until tests pass
  - Repair failures automatically
  - [primary]
- **Architecture:** Hybrid deterministic + LLM [primary]
  - **LLM Role:** Code change generation with task-specific prompts
  - **Deterministic Role:** AST and symbol-based techniques for file discovery and validation; "always correct" checks
  - **Validation:** Build/test failures trigger AI repair attempts; humans drive final rollout decisions
  - **Strategy:** Break complex migrations into smaller substeps for faster iteration
  - **Combination Principle:** "AST-based techniques, heuristics, and LLMs are needed to achieve success" (not LLM alone) [primary]
- **Scale & Migrations:**
  - **int32→int64 Migration (Google Ads):**
    - 50% reduction in overall effort [primary]
    - **80% of code fully AI-authored** [primary]
    - Multi-million lines of code monolith [primary]
    - Time savings: reduction from multi-year to months [implied by 50% acceleration]
  - **JUnit3→JUnit4:**
    - 5,359 files migrated
    - 149,000+ lines
    - ~87% committed without changes [primary]
  - **Joda Time→Java Time:** ~89% estimated time savings on smaller clusters [primary]
  - **Multiple Experimental Migrations:** Language-agnostic approach across systems [primary]
  - **Success Metric:** "At least 50% acceleration in task completion rate" — measuring end-to-end time, not just code generation [primary]
- **Human Roles:**
  - Code review and final validation
  - Rollout decisions and sequencing
  - **Bottleneck Finding:** Human review and rollout decisions remain limiting factors even with 80% AI-authored code [primary]
- **Lessons:**
  1. **LLM + AST > LLM Alone:** "AST-based tooling has the advantage to be 'always correct'" while LLMs handle complexity [primary]
  2. **Divide and Conquer:** Breaking tasks into smaller substeps allows faster iteration [primary]
  3. **Validation is Critical:** Build/test failures must trigger AI repair, not escalation [primary]
  4. **Bottleneck is Human:** Code review and rollout remain the limiting factors; code generation is not the bottleneck [primary]
  5. **Multi-Stage Validation:** File discovery → change generation → validation → repair → human review [primary]

**Sources:**
- [Nikolov et al., arXiv:2501.06972, published FSE 2025](https://arxiv.org/html/2501.06972v1) [primary fetch, 2026-10-17]
- Cited in [Research DX blog post](https://getdx.com/research/migrating-code-at-scale-with-llms-at-google/)
- Covered by [I-Programmer](https://www.i-programmer.info/news/105-artificial-intelligence/17774-google-slashes-code-migration-time-with-llms.html)

**Implication for factory architecture:** Hybrid model (LLM write + deterministic validate) proven at Google scale. AST and symbol-based checks must validate before human review. Human review/rollout is the true bottleneck, not code generation capacity.

## 8. Uber: Focused & Broad Code Improvement (FixrLeak & uReview)

### Takeaway
Uber deployed two complementary AI-driven systems: **FixrLeak** for automated detection/repair of Java resource leaks (91% success rate), and **uReview** for broad code review across 65,000+ weekly diffs (75% usefulness rate, 39 developer-years saved annually). Demonstrates both narrow (focused, high-success) and broad (coverage, filtering) automation patterns. ✓ [self]

### FixrLeak: Focused Automation (Java Resource Leak Fixing)

**Architecture:** Hybrid detection + AST analysis + LLM repair [primary fetch]
- Detection via SonarQube (static analysis tool)
- AST Analysis via Tree-sitter to parse code and identify resource patterns
- **AI Repair:** Sends tailored prompts to ChatGPT-4O to generate fixes (try-with-resources statements)
- **Validation:** Runs builds, tests, and SonarQube rechecks to verify fixes
- **Manual Gate:** Developers approve generated fixes before merge

**Scale & Results:**
- Processed 112 resource leaks from Uber's Java codebase
- 102 eligible cases (after excluding deprecated code)
- **91% success rate** (93/102 leaks successfully fixed)

**Lessons:**
- Successful AI-driven code repair requires structured analysis (AST) + generative AI
- Focused scope (well-scoped, intra-function leaks) more reliable than broad code generation
- Rigorous validation testing (build + test + static analysis) before PR creation critical

**Implication:** Narrow, well-defined problems reach 91% automation success; broad problems require filtering and validation.

### uReview: Broad Code Review Augmentation

**Architecture:** Multi-stage GenAI pipeline [self]
- Specialized assistants for different check types
- Prompt chaining to identify issues
- Filtering and validation mechanisms
- Identifies: bugs, security vulnerabilities, coding standard violations

**Scale & Impact:**
- Analyzes **90%+** of ~65,000 weekly diffs (~58,500 changes per week)
- **75% usefulness rate** among engineers (issue found/actionable)
- **Impact:** Saves ~39 developer-years annually
- **Actionability:** 65% of posted comments addressed by developers

**Success Metric:** Usefulness (not raw detection count); engineers must find suggestions actionable.

**Lessons:**
- Multi-stage filtering and validation critical for broad coverage
- Usefulness rate more important than detection rate
- Must complement human review, not replace it
- Complement pattern: AI identifies candidates, humans make final decisions

**Sources:**
- [Uber Blog: FixrLeak](https://www.uber.com/ch/en/blog/fixrleak-fixing-java-resource-leaks-with-genai) [primary fetch]
- [ZenML: FixrLeak](https://zenml.io/llmops-database/genai-powered-automated-resource-leak-fixing-in-java-codebases)
- [ZenML: uReview](https://zenml.io/llmops-database/ai-powered-code-review-system-at-scale)

**Implication for factory architecture:** Two patterns: narrow (high accuracy, simple scope) and broad (high coverage, requires filtering). Narrow → integrate pre/post steps. Broad → multi-stage validation with human gate.

---

## 9. Anthropic: Internal Claude Code Adoption (High-Scale Internal Case)

### Takeaway
Anthropic uses Claude Code and Agent SDK internally at high scale, with 80%+ of production code authored by Claude as of May 2026. Not a factory per se, but demonstrates internal adoption and validates Claude's own product for production engineering. ✓ [self]

### Case Details
- **Organization:** Anthropic (internal use across engineering teams)
- **Agents do:**
  - Generate production code across multiple engineering teams
  - Handle complex multi-step engineering tasks
  - Integrate into existing Anthropic development workflow
  - [self]
- **Scale & Adoption:**
  - **Code Generation Rate (May 2026):** Claude authored **>80% of code merged into production** [self]
    - Baseline before Claude Code preview (Feb 2025): low single digits [self]
  - **Productivity Improvement:** Engineers merged ~8× more code per day (Q2 2026) vs. 2021-2024 baseline [self]
  - **Task Success Rate:** 76% success on complex engineering tasks by May 2026 (50-point jump in 6 months) [self]
  - **Individual Adoption:** Boris Cherny (creator of Claude Code) writes **100% of code via Claude** since Nov 2025; has not manually edited a single line [self]
- **Inflection Point:**
  - **November 2025:** Claude Opus 4.5 and GPT 5.2 appeared to "turn the corner" on reliable agent behavior
  - **Key Driver:** November 2025 models showed reliable code following and complex task execution
  - Adoption accelerated from "majority of code" to "nearly all" [self]
- **Model Integration:**
  - Claude Agent SDK for multi-step tasks
  - Claude Code as primary development interface
  - Direct integration into Anthropic's existing workflow
- **Human Roles:**
  - Specification and requirements definition
  - Code review and approval (still in place)
  - Architecture and design decisions
  - Merge and deployment decisions
- **Lessons:**
  - Inflection point in model capability (Nov 2025) drove step-change in adoption
  - High success rate (76%) on complex tasks indicates agents handle multi-step reasoning well
  - Internal dogfooding validates Claude's product for production use at Anthropic's own scale
  - Hybrid model (agent write + human review) scales internally at 80%+ generation rate

**Sources:**
- [CryptoBriefing, "Anthropic CEO reveals engineers use Claude to generate over 80% of production code"](https://cryptobriefing.com/anthropic-claude-generates-80-percent-code/)
- [Anthropic internal reports, May 2026](https://cryptobriefing.com/anthropic-claude-authors-majority-production-code/)
- Second Talent research compilation

**Implication for factory architecture:** High adoption (80%+ of merged code) with human review gates still in place suggests hybrid model (agent write + human review) scales well. Inflection point (Nov 2025) indicates when agent capability enables factory model.

## 9. Ralph loop (Geoffrey Huntley) and solo practitioners
- Claims are secondhand: a ~$297 compiler; six repos overnight. No primary post was found in this session. UNVERIFIED.
- Huntley's failure note, as quoted by secondary sources: the agent "comes to the incorrect conclusion that the code has not been implemented" after running ripgrep. [secondary]
- Mechanism: each pass uses a fresh context; progress is kept in files and git. Works best when a script can judge the result. [secondary]
- Yegge (Gas Town/Beads), Vincent (Superpowers), Hashimoto: NOT YET RESEARCHED in this session.
- Implication for factory architecture: a fresh-context loop with progress in git matches our checkpoint commits. Its failure mode (missed existing code) argues for a search step before any build.

Sources (secondary): [Stevekinney](https://stevekinney.com/courses/ai-development-setup/the-ralph-loop); [Codecentric](https://codecentric.de/en/knowledge-hub/blog/the-ralph-wiggum-loop-autonomous-code-generation-with-a-fresh-context).

## Cross-Cutting Architectural Patterns

### What Works
1. **Narrow, Well-Scoped Tasks:** Migrations, refactors, code repairs (Uber FixrLeak: 91% success) outperform greenfield features [primary + secondary]
2. **Deterministic Pre/Post Steps:** Linting, branch management, test execution prevent runaway loops (Stripe Minions pattern) [primary + secondary]
3. **Feedback Loops:** Build/test failures trigger automatic repairs, not escalation (Google model) [primary]
4. **Hybrid Orchestration:** Interleave deterministic steps + agentic loops (Stripe blueprints, Spotify Fleet Shift pattern) more reliable than pure agent loops [primary + secondary]
5. **CI as Verifier:** Automated tests validate agent output before human review (universal pattern across all cases) [primary]
6. **Merge Gate as Control:** Human approval required before code ships; human review is capacity gate, not quality gate [primary + secondary]
7. **Curated Context:** Tool limitation (Stripe: 15 tools per task vs. 500 available) improves reliability over full context exposure [secondary]
8. **Specification-Driven:** Clear architecture, interfaces, requirements front-loaded enables agent autonomy (OpenAI, StrongDM patterns) [primary + secondary]

### What Fails or Causes Issues
1. **Pure Agent Loops:** Without deterministic steps, agents get stuck in infinite retry/fix cycles [secondary analysis]
2. **Unscoped Context:** Too many tools or options confuses decision-making; Stripe found curated context (15 tools) more reliable than all (500) [secondary]
3. **Thin Context:** Spotify's first failure: missing field mapping guidance caused incorrect assumptions [primary]
4. **Repos Without Tests:** Validation falls onto humans; Spotify Part 4 required manual verification where unit tests sparse [primary]
5. **Long-Horizon Tasks:** Context window fills, task definitions drift over multi-week features; agents struggle [secondary analysis]
6. **No Merge Gate:** 61.4% of agent PRs in one study auto-merge after CI pass (no human review), introducing maintenance debt [secondary]
7. **Cost Unpredictability:** Token spending can spike with no spend caps or circuit breakers (infrastructure gap) [secondary]

### Production Failure Modes Reported (2025-2026 Studies)
- **Overall Success Rate:** 56.6% aggregate success rate on production agents (March 2026 study of 6,259 agents) [secondary]
- **Merge Conflicts:** 27.67% of agent PRs produce merge conflicts (AgenticFlict study of 142,000+ PRs) [secondary]
- **Code Quality:** Agent PRs introduce code smells at higher rates than human PRs in same repositories [secondary]
- **Governance Gap:** No agreed definition of "code review for agent PR" across industry [secondary]
- **Iteration Degradation:** Success rate drops to ~25% across 8+ iterations; compound error accumulation over long tasks [secondary]
- **Six Failure Clusters Identified:**
  1. Tool invocation and parameter-level errors
  2. Planning and constraint-satisfaction failures
  3. Long-horizon degradation from context accumulation
  4. Multi-agent coordination failures
  5. Safety and security failures
  6. Measurement validity problems
  [secondary, academic taxonomy]

### Infrastructure Gaps (Per Forrester Mid-2026 Assessment)
**"The constraint on scaling agents is orchestration, governance infrastructure, and risk management, not raw agent capability."** [secondary]

Missing in production systems:
- No circuit breaker to halt runaway loops
- No per-session spend cap on tool calls
- No structured audit trail for agent decisions
- No rollback path when agent action causes downstream harm
- No standard governance framework for agent PR acceptance

### Human Role Evolution
- **Before:** Engineers write code, review code, merge code
- **After:** Engineers specify requirements, architects design interfaces, humans review outputs, approve merges
- **Bottleneck Shift:** Code writing → human review capacity [primary + secondary]
- **Findings:**
  - Review capacity now limits throughput (Stripe question: how does team review 1,300 PRs/week? unanswered)
  - Some orgs auto-merge to avoid review bottleneck (61.4% in one study), introducing risk [secondary]
  - Others maintain human approval gate (Stripe, Ramp, Anthropic pattern) [primary]

### Work That Fits vs. Fails
**Works Best:**
- Migrations with explicit mapping tables and bounded target sets (Spotify, Google) [primary]
- Well-scoped, intra-function repairs (Uber FixrLeak: 91%) [primary]
- Structured code transformations (JUnit3→JUnit4: 87% unchanged) [primary]
- Build/test failure repair loops (Google pattern) [primary]

**Struggles or Requires Human Help:**
- Unstructured greenfield features (reported only by OpenAI, StrongDM; no independent verification) [secondary]
- Under-specified context (Spotify Part 4 mapping failure) [primary]
- Repos without tests (Spotify Part 4 manual verification needed) [primary]
- Long-horizon features (>1 week) with context window pressure [secondary]

### Verification Approaches
- **Strong:** Deterministic checks (AST, compiler, lint) + build/test + human review (Google, Spotify pattern) [primary]
- **Moderate:** CI pass + unit tests + human review (Stripe, Ramp) [primary + secondary]
- **Weak:** Behavioral scenarios or telemetry without code review (Ramp mentions but not required) [secondary]
- **Challenge:** Repos without tests must gate on linters, formatters, code smells (Spotify Part 4) [primary]

### Scale Achieved (Verified)
- **Stripe:** 1,300 PRs/week, 100% agent-written, human-reviewed [self]
- **Spotify:** 1,000 PRs per 10 days (~1,400/week), 1,500+ in 9 months [self]
- **Ramp:** 50%+ of all merged frontend/backend PRs [self]
- **Anthropic:** 80% of production code authored by Claude [self]
- **Google:** int32→int64 migration: 50% time savings, 80% AI-authored code [primary]
- **Uber FixrLeak:** 91% success on 102 resource leak repairs [primary]

### Independently Verified Sources
**Strong (Primary Sources Fetched & Verified):**
- Spotify Part 1 & 4 engineering posts (1,500+ PRs, dataset migration details) [primary]
- Google arXiv paper (migrations, AST+LLM approach) [primary]
- Uber blog (FixrLeak 91% success, uReview 75% usefulness) [primary]

**Moderate (Secondary with Company Attribution):**
- Stripe Minions (1,300 PRs/week, architecture details from secondary sources) [secondary]
- OpenAI harness engineering (1M lines, 5-10 PRs/day from secondary sources) [secondary]
- Anthropic internal use (80% code, May 2026 report) [secondary]

**Weak (Secondary Only, Company Attribution Uncertain):**
- StrongDM Software Factory (three-person team, criticized by Willison for "no review" claim) [secondary]
- Geoffrey Huntley Ralph loop (six repos overnight; failure: missed existing code) [secondary]

### Known Research Gaps
- How do teams review 1,300 PRs/week? (Stripe case unanswered) [open]
- Full OpenAI harness engineering design (primary page HTTP 403) [blocked]
- Full Stripe Minions architecture (primary not fetched) [blocked]
- Microsoft and Amazon internal agent adoption (not searched in this session) [not researched]
- Long-term maintenance debt from agent-written code (no longitudinal studies found) [not found]
- Cost-per-PR for agent systems vs. human engineering (no data found) [not found]
