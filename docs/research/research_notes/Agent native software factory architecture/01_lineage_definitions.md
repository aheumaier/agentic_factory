# Agent-Native Software Factory Lineage and Definitions

## Historical Roots: 1960s–2004

### Takeaway
The "software factory" metaphor originates from Japanese manufacturing process control applied to code (1970s), was codified by Cusumano's ethnographic study (1991), and evolved into Microsoft's DSL-and-patterns-driven model-driven development approach (2004). Each iteration added layers of automation and standardization.

### Cited Findings
- **Hitachi/Toshiba/NEC/Fujitsu (late 1960s–1970s):** Japanese firms launched factory programs between the late 1960s and late 1970s to standardize processes and diffuse tools/techniques internally and across subsidiaries [MIT Dspace: System Development Corp paper](https://dspace.mit.edu/bitstream/handle/1721.1/49002/systemdevelopmen00cusu.pdf) (accessed 2026-10-13). These efforts responded to U.S. SDC Software Factory precedent but refined it by tightly integrating product objectives with production management (tools, techniques, controls, training, reusable components).
- **Michael A. Cusumano, "Japan's Software Factories" (1991):** The definitive book analyzed how Japanese firms (Hitachi, Toshiba, NEC, Fujitsu) adapted manufacturing principles: large teams develop software cooperatively, reusing previous code components, with emphasis on process repeatability and metrics [Bookshop: Japan's Software Factories](https://bookshop.org/p/books/japan-s-software-factories-a-challenge-to-u-s-management-michael-a-cusumano/11781684) (accessed 2026-10-13). Key definition: software factories produce software through standardized, managed processes with measurable output.
- **MITI-sponsored projects (1980s):** Sigma (Software Industrialized Generator and Maintenance Aids) attempted to commoditize factory tools and reuse concepts industry-wide [MIT Dspace: SWP-3087](https://dspace.mit.edu/bitstream/1721.1/2280/1/SWP-3087-24832363.pdf) (accessed 2026-10-13).
- **Greenfield & Short, "Software Factories" (2004):** Jack Greenfield (Microsoft) and Keith Short published "Software Factories: Assembling Applications with Patterns, Frameworks, Models & Tools" (Wiley), describing a model-driven approach using Domain-Specific Languages (DSLs), patterns, frameworks, and guidance via tools like Visual Studio Team System [eWeek: Microsoft Sharpens Its Software Factory Vision](https://www.eweek.com/development/microsoft-sharpens-its-software-factory-vision/) (accessed 2026-10-13). Redefined the factory as a configuration of tools and templates for rapid development of domain-specific application types.

### Inferences
- **1970s Japanese factories** emphasized human-mediated process standardization and reuse (manual assembly line, knowledge codification).
- **Cusumano's framework** (1991) moved the definition from "manufacturing metaphor" to "measurable process" with documented inputs/outputs/repeatability—applicable to humans.
- **2004 Microsoft model** shifted focus toward automation of transformation: code generation from models, DSL-driven templates, reducing hand-coding overhead. The "factory" became a *technology stack*, not just a process discipline.

### Gaps
- No detailed technical specifications recovered for 1970s Hitachi/Toshiba implementations (scope, tooling, automation level unclear).
- Cusumano's definition did not address agent involvement; it assumes human developers throughout.

---

## Current Definitions (2025–2026): The Agent-Native Turn

### Takeaway
In 2025–2026, "software factory" evolved into "agent-native software factory": humans specify intent and review, while AI agents (not humans) write code, run tests, and iterate. Competing definitions center on whether agents are merely *callable* (agent-native architecture) or *autonomous* (agentic behavior).

### Cited Findings

#### Factory.ai Definition
- **Core definition:** "A managed model for producing software with repeatable inputs, standardized tooling, and measurable output. In 2026, the model is increasingly agent-native, with software development agents (Droids) participating in the work itself, taking standardized inputs and producing validated changes across coding, review, testing, and deployment." [Factory.ai](https://factory.com/articles/what-is-a-software-factory) (accessed 2026-10-13).
- **Key architectural property:** Actions are callable through protocols (MCP, CLI); artifacts are files; state is readable; human oversight is explicit and late (at review, not during execution).

#### StrongDM "Dark Factory" (February 2026)
- **Definition:** Humans no longer write code or conduct reviews; specifications flow into agents, which iteratively generate code and tests until convergence [Stanford Law](https://law.stanford.edu/2026/02/08/built-by-agents-tested-by-agents-trusted-by-whom/) (accessed 2026-10-13).
- **Critical gap identified:** Circular validation—same systems that write code also test it—creates blind spots. Trust is engineered via Digital Twin Universe.

#### Andrej Karpathy "Software 3.0" (2025–2026)
- **Definition framework:** Three eras: Software 1.0 (human-written code), Software 2.0 (human-curated data, model-learned logic), Software 3.0 (human-written prompts, LLM knowledge executes) [Analytics Vidhya](https://www.analyticsvidhya.com/blog/2025/06/andrej-karpathy-on-the-rise-of-software-3-0/) (accessed 2026-10-13).
- **Implication:** Validates spec-to-agent-execution as natural paradigm; leaves verification open.

#### Addy Osmani (ex-Google, 2026) / Agentic Engineering
- **Definition:** Encoding workflows and quality gates that senior engineers use (spec before code, test before merge) into agent-executable form. Left Google in 2026 to create Agent Engineer course [Thulyo](https://thuliobittencourt.com/agent-skills-google-engineering-skills-ia-coding-agents/) (accessed 2026-10-13).
- **Key properties:** 19 engineering skills + 7 commands inspired by Google best practices.

#### Simon Willison (February–March 2026)
- **Definition:** Agentic engineering is writing software reliable when executed by LLM agents rather than humans. Identified November 2025 as inflection point when Claude Opus 4.5 and GPT-5.1 made AI agents reliable for daily use [Simon Willison](https://simonwillison.net/2026/jan/28/) (accessed 2026-10-13).
- **Core patterns:** red/green TDD, templates, hoarding (reusable components).

#### Microsoft Agentic Enterprise (Late 2025–2026)
- **Definition:** Cloud ecosystem reoriented toward autonomous agents executing complex multi-step workflows with minimal human intervention; Copilot Studio enables enterprise-ready agent governance [DevBlogs](https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-at-build-2026/) (accessed 2026-10-13).

---

## Competing Definitions: AI-Native vs. Agent-Native vs. Agentic

### Takeaway
Three distinct, independent definitions coexist; conflating them causes architectural mistakes.

### Cited Findings
- **AI-Native:** Model is load-bearing from architecture start; humans still operate the software [Shiplight](https://www.shiplight.ai/blog/agent-native-vs-agentic-vs-ai-native) (accessed 2026-10-13).
  
- **Agentic:** Describes *system behavior*: perceive, plan, act, observe, revise. Plans own steps, selects tools, evaluates output, retries [Shiplight](https://www.shiplight.ai/blog/agent-native-vs-agentic-vs-ai-native) (accessed 2026-10-13).

- **Agent-Native:** Describes *architectural design*. Software is agent-native when something other than human can operate it: (1) actions callable (MCP, CLI), (2) artifacts are files, (3) state readable, (4) human oversight explicit and late [Shiplight](https://www.shiplight.ai/blog/agent-native-vs-agentic-vs-ai-native) (accessed 2026-10-13).

- **AI-Augmented:** Humans operate; AI suggests, autocompletes, summarizes [Shiplight](https://www.shiplight.ai/blog/agent-native-vs-agentic-vs-ai-native) (accessed 2026-10-13).

- **Independence:** A product can be agentic but unreachable (LLM reasoning without API) or agent-native but deterministic (Git—fully operational by agents, zero autonomy) [Shiplight](https://www.shiplight.ai/blog/agent-native-vs-agentic-vs-ai-native) (accessed 2026-10-13).

### Inferences
- This repo implements **agent-native** (Claude SDK tools, Spec Kit CLI, git/gh callable) and **agentic** (agents plan, select tools, retry). The pair is intentional.
- "Agent-native software factory" is architecturally precise: agents as first-class operators on file-based, human-reviewable output.

### Gaps
- Industry consensus on "agent-native" is absent; Shiplight's 2026 definition is among clearest published.

---

## Autonomy-Level Taxonomies

### Takeaway
Dan Shapiro's 2026 five-level model (borrowing from NHTSA driving-automation taxonomy) is the first widely-cited hierarchy for AI-assisted coding. ~90% of self-described "AI-native" developers are stuck at Level 2.

### Cited Findings
- **Dan Shapiro, "The Five Levels: from Spicy Autocomplete to the Dark Factory"** (January 23, 2026):
  - Level 0: Spicy Autocomplete (model suggests snippets; human types rest)
  - Level 1: Coding Intern (AI writes boilerplate; full human review)
  - Level 2: Junior Developer (pair programming; review every line)
  - Level 3: Developer (AI generates majority; human full-time reviewer)
  - Level 4: Engineering Team (humans define spec/plan; agents execute; humans review design, not code)
  - Level 5: Dark Factory (fully autonomous; humans design architecture only; code never reviewed)
  [Simon Willison](https://simonwillison.net/2026/jan/28/) (accessed 2026-10-13).

### Inferences
- This repo's design occupies **hybrid** position: **agent execution at Level 4–5** (agents plan, build, test; humans review intent/trace, not line-by-line); **human authority at Level 3** (eval gate, quality gate, security gate require human signoff on spec coverage and risk).
- StrongDM's "dark factory" (Level 5) risk: removing all human review requires alternative trust channels (Digital Twin, red teams, traceability). This repo's multi-gate approach hedges that.

### Gaps
- No other published AI coding autonomy-level hierarchies found; Shapiro's is currently dominant.

---

## Implications for This Factory's Architecture

1. **Lineage:** Inherits factory concept from Cusumano (measurable process, reuse, standardization) through Greenfield/Short (DSL-driven templates, model-driven generation) into 2026 agent-native form (agents as executors, humans as specifiers and reviewers).

2. **Agent-Native vs. Agentic:** The 8-layer design is **agent-native** (Spec Kit CLI, Claude SDK tool bindings, file-based artifacts, human gates); agents within are **agentic** (plan, select tools, retry). Not "fully autonomous"—intentionally.

3. **Trust Model:** Unlike StrongDM's Digital Twin, this repo trusts through:
   - **Layered gates:** eval gate (coverage), quality gate (specs/006, not yet wired), security gate (specs/007, not yet wired).
   - **Diverse perspectives:** swe-agent writes code; architect-agent plans; pm-agent reviews spec. No single system validates and executes.
   - **Traceability:** Temporal workflow, spec ID, task checkpoints, seat logs.

4. **Autonomy Level:** Target is **between Level 3 and 4**—agents do the work, humans review plan/spec/risk, *not* every line of code. Requires robust gates.

5. **Open Gaps Ahead:** Specs/006–007 (quality, security gates) are required to reach stated target autonomy level without drifting toward StrongDM's Level-5 risk (circular validation, institutional knowledge loss).
