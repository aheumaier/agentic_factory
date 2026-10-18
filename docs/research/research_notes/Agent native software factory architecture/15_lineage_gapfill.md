# Lineage gap-fill: software factory, autonomy ladders, "agent-native"

Access date for all sources: 2026-10-13. "Primary" = fetched from the author's or publisher's own page. "Secondary" = search snippet or third-party summary. Gaps are listed, not guessed.

## 1. Greenfield & Short, "Software Factories" (2004)

### Takeaway
Greenfield's 2004 essay defines a software factory as a configured development environment for one application type. Neither the essay nor the book uses "agent" or "autonomous".

### Cited Findings
- Primary: "A Software Factory is a development environment configured to support the rapid development of a specific type of application." — [Greenfield, "The Case for Software Factories" (Microsoft Learn archive, 2004)](https://learn.microsoft.com/en-us/previous-versions/aa480032(v=msdn.10)?redirectedfrom=MSDN)
- Primary, same essay: the method is the Language-Framework pattern (reusable abstractions, then a framework, then a language and tools that generate the assembly). The factory analogy is economies of scope, not scale.
- Not verified: the list "product line + schemas + templates + guidance + DSLs" from the brief. The essay mentions product lines and DSL-like languages, but I did not confirm the list word for word.

### Implication for factory architecture
The 2004 sense is a reuse-and-generation line. Our layers map to "framework plus tools generate the assembly": the spec and templates are the product line, the agent is the assembler. Say so in the design docs, so readers do not confuse it with the 2026 "dark factory".

### Gaps
- Book chapters (schemas, templates, guidance): not fetched.

## 2. Dan Shapiro, "five levels" (2026)

### Takeaway
The post exists and its top rung is called the dark factory. The level names and count conflict across sources. I did not reach the original post, so the list is UNVERIFIED.

### Cited Findings
- Secondary (Simon Willison, 2026-01-28, fetched): six levels numbered 0-5: "Spicy autocomplete", "The coding intern", "The junior developer", "The developer", "The engineering team", "The dark software factory" — [Willison](https://simonwillison.net/2026/Jan/28/the-five-levels/)
- Conflict: a guessed danshapiro.com URL returned a different list with driving analogies ("lane-keeping", "Autopilot", "robotaxi") and an unnamed Level 5 "Dark Factory". The URL is not confirmed, so I do not rely on it — [danshapiro.com (unconfirmed)](https://danshapiro.com/blog/2026/01/the-five-levels-from-spicy-autocomplete-to-the-software-factory/)
- Conflict: a search summary attributes a different L0-L5 ladder to Shapiro ("By hand", "Assisted", "Paired", "Review manager", "Spec manager", "Dark factory") — [developertoolkit.ai](https://developertoolkit.ai/en/ladder/)
- Secondary: the "dark" name is credited to Simon Willison — [env.dev](https://env.dev/ai/agentic-coding-levels)

### Implication for factory architecture
Do not quote level names in the repo until the original post is read. `swe-agent` is supervised (`requires_human_supervision: true`), so it sits near the "developer / engineering team" rung in the Willison version. Name each pipeline stage's rung and gate, not one level for the whole factory.

### Gaps
- Original Shapiro post: not reached.

## 3. Andrej Karpathy: "Software 3.0", autonomy sliders, "agentic engineering"

### Takeaway
The autonomy slider comes from the June 2025 YC AI Startup School talk, as reported by secondary write-ups. "Agentic engineering" is a 2026 term with a definition given in a later talk and post. I did not fetch the talk or his own posts.

### Cited Findings
- Secondary: "partial autonomy apps" have an autonomy slider where the user sets how much control the LLM gets — [Latent Space write-up](https://www.latent.space/i/166191505/part-partial-autonomy). Paywalled in part.
- Secondary: "the hottest new programming language is English" and the 1.0/2.0/3.0 framing — [Gigazine](https://gigazine.net/gsc_news/en/20250620-andrej-karpathy-software-is-changing)
- Secondary: "agentic engineering" is described as orchestrating agents and acting as oversight. The "99% of the time" figure is unverified against his own post — [Taskade summary](https://www.taskade.com/blog/what-is-agentic-engineering)
- Secondary: at Sequoia AI Ascent (2026-04-30) he defines the discipline as "coordinating fallible agents while preserving correctness, security, taste, and maintainability" — [StartupHub](https://www.startuphub.ai/news/figure-andrej-karpathy-agentic-engineering-sequoia-2026-07-31). Quote is from a summary, not his post.

### Implication for factory architecture
The slider suits the gate. Each stage should have its own autonomy setting (agent proposes, human approves), not one global mode. The "fallible agents" framing supports a strong Gate layer.

### Gaps
- Primary talk transcript and Karpathy's own posts: not fetched.

## 4. Factory.ai: "agent-native" framing

### Takeaway
Factory calls itself an "agent-native software development platform". It frames agents as delegates with human approval checkpoints, not as fully dark.

### Cited Findings
- Primary: "agent-native software development platform" is the company's category description. Droids "delegate complete tasks" while keeping "human approval checkpoints" — [Factory](https://factory.com/) (the factory.ai URL redirects here).

### Implication for factory architecture
Factory keeps a human gate before completed work, the same position as our merged-PR output. Cite it as a counter-example to the no-review model.

### Gaps
- No Factory definition of "agent-native" beyond the category label was found.

## 5. Microsoft "Agent Factory" (Azure blog, 2025)

### Takeaway
The Azure series is product marketing. Its "agent factory" means a governed platform for building agents, not a software-production process.

### Cited Findings
- Primary: the blueprint post says the series "shares best practices, design patterns, and tools to help guide you through adopting and building agentic AI" — [Azure blog](https://azure.microsoft.com/en-us/blog/agent-factory-creating-a-blueprint-for-safe-and-secure-ai-agents/)
- Secondary: about seven posts from August to September 2025 — [Azure blog listing](https://azure.microsoft.com/nb-no/blog)

### Implication for factory architecture
Our "agent factory" name overlaps with Microsoft's product term. The README should say we mean the build-and-ship pipeline, not a hosting platform.

### Gaps
- Full text of the series posts other than the blueprint: not fetched.

## 6. BMAD method (bmad-code-org)

### Takeaway
The README describes "Agile Ai Driven Development" and "specialized perspectives" (product, architecture, UX, development, testing). It does not list named roles or artifacts in the fetched text. Named PRD/epics/stories roles are UNVERIFIED.

### Cited Findings
- Primary: "Bring in product, architecture, UX, development, and testing expertise when it helps" — [BMAD README](https://github.com/bmad-code-org/BMAD-METHOD) (fetch summary, not the raw file).
- Primary, same page: named modules are "BMad Builder" and "BMad Test Architect".
- Not verified: the roles Analyst, PM, Architect, Developer, QA, and the artifacts PRD, epics, stories. The docs site was not fetched.

### Implication for factory architecture
The role split (product, architecture, dev, test) matches our PM, architect and build agents. Confirm exact role names on the docs site before using them.

### Gaps
- BMAD role and artifact list: not verified.

## 7. "Agent-native": is there a software definition?

### Takeaway
No single definition was found. Sources use the term differently. For software development, the closest common meaning is "agents are the main authors of code; humans set direction and review".

### Cited Findings
- Secondary: agents as the primary operator, humans supervising — [Shiplight](https://www.shiplight.ai/blog/what-is-agent-native). Shiplight says at least six competing definitions exist.
- Secondary: applications designed with agents as first-class users — [CopilotKit](https://www.copilotkit.ai/learning/what-is-an-agent-native-application)
- Secondary: infrastructure for agent-generated code; CI/CD, databases and secrets are the blockers — [Northflank](https://northflank.com/blog/agent-native-software-development)
- Not found: a primary source defining "agent-native" for software development.

### Implication for factory architecture
Define the term in our README, in one sentence with its boundary: the agent writes and tests code; a human sets the spec and reviews at the gate.

## 8. SAE J3016 and coding-autonomy ladders

### Takeaway
SAE J3016 has six levels (0-5). The names are confirmed; the descriptions are UNVERIFIED. Shapiro's coding ladder is the best known, but its names vary. Swyx, GitHub and Google ladders were not found.

### Cited Findings
- SAE J3016 level names: No Driving Automation (0), Driver Assistance (1), Partial Driving Automation (2), Conditional (3), High (4), Full (5) — [SAE J3016 listing](https://connect.snv.ch/it/sae-j3016_202104). Level descriptions: UNVERIFIED.
- The level applies to the feature in use, not the vehicle — [SAE summary](https://saemobilus.sae.org/content/j3016_202104) (search snippet only).
- Oversight Ladder (Dominik): Level 1 suggests and the person writes every line; Level 5 runs unattended overnight. Higher means less oversight, not better work — [DEV Community](https://dev.to/dominik_ddd/the-oversight-ladder-the-five-levels-of-ai-coding-autonomy-1d94)
- Single-axis ladder (Steve Yegge), from no AI to building your own orchestrator — described in [Osmani, "Agentic Autonomy Levels"](https://addyosmani.com/blog/agentic-autonomy-levels/) (search result, not fetched).
- Swyx, GitHub and Google coding-autonomy ladders: not found.

### Implication for factory architecture
Use the J3016 idea (level per feature, not per tool) and the Oversight Ladder's point that less oversight is not better. Mark each pipeline stage with its gate type. Do not adopt one ladder's names without a primary source.

## Open items
- Shapiro original post: not reached; conflict unresolved.
- Karpathy talk and posts: not fetched; quotes are secondary.
- Factory.ai blog and BMAD docs site: not fetched.
- Azure Agent Factory posts other than the blueprint: not fetched.
- SAE J3016 level descriptions: UNVERIFIED.
- Swyx, GitHub and Google ladders: not found.
