# Vendor gap-fill: Devin, Jules, Antigravity, Kiro, Amp, Replit Agent, OpenHands Cloud, Factory Droids

Access date for every URL: 2026-10-13. Covers only platforms missing from `02_vendor_architectures.md`. PRIMARY = vendor docs or announcement. SECONDARY = third-party write-up. Anything not confirmed in a fetched page is UNVERIFIED or "Not found." Several search results were third-party pages whose titles tried to steer the description; they were ignored. Several vendor pages redirected or were index-only; those gaps are listed at the end.

## Key question 1: control plane, where code runs, triggers

### Takeaway
Most platforms run each task in a cloud machine or sandbox of their own. Antigravity's primary doc describes only local or git-worktree runs. Triggers are mostly chat or a web UI, with schedule and GitHub-event triggers in Factory and OpenHands.

### Cited Findings
- **Devin (PRIMARY index only):** the docs index lists pages for Automations, Slack, Linear, Jira and GitHub integrations, environment setup, "Outposts" (self-hosted), "Subagents (CLI)" and "Dynamic Workflows." Page bodies were not fetched. [Devin docs index](https://docs.devin.ai/llms.txt)
- **Devin (SECONDARY):** each session gets a fresh VM, and files outside version control are lost when the session ends. [Fast.io summary](https://www.fast.io/resources/devin-software-engineer.md) (SECONDARY, a vendor selling workspace products).
- **Jules (PRIMARY):** "Jules runs in a virtual machine where it clones your code, installs dependencies, and modifies files." Jules makes a plan you can approve before any change, notifies you on completion or when it needs input, and reads `AGENTS.md`. [Jules getting started](https://jules.google/docs/)
- **Jules (conflict):** a secondary guide says a GitHub issue labeled `jules` starts a task. The primary page does not say this. UNVERIFIED. No URL was fetched for the guide.
- **Jules limits (SECONDARY):** 15 tasks per 24 hours and 3 concurrent tasks on the free tier. [Morph comparison](https://www.morphllm.com/comparisons/jules-google-coding-agent). Not checked against Jules' primary limits page, which was not fetched.
- **Antigravity (PRIMARY):** Agent Manager runs one agent per task. Local mode: "The agent operates directly in your active folders." Worktree mode: "The agent operates in an isolated Git worktree." No cloud execution is described. [Antigravity getting started](https://antigravity.google/docs/getting-started)
- **Antigravity (conflict):** secondary sources describe a cloud side. UNVERIFIED against the primary page. The `/docs` path redirected, so the Agent Manager page itself was not fetched.
- **Kiro (PRIMARY):** Kiro web is a "Browser-based agent for multi-repo tasks that plans, implements, and opens PRs," in "zero-setup sandboxed sessions." [Kiro docs](https://kiro.dev/docs/)
- **Kiro autonomous agent (PRIMARY, AWS announcement, preview):** it "connects to your team's repos, pipelines, and tools, like Jira, GitHub, and Slack," tasks can be assigned "directly from GitHub," output is "proposed edits and pull requests," and it "maintains persistent context across sessions." The runtime provider is not named. [Amazon announcement](https://aboutamazon.com/news/aws/amazon-ai-frontier-agents-autonomous-kiro)
- **Amp (PRIMARY):** Amp runs in the browser or the CLI on your machine. In the cloud, each thread gets an "orb," described as "a machine it creates for that thread." The same threads appear across web, CLI and Mac/iOS apps. [Amp manual](https://ampcode.com/manual); [Amp docs](https://ampcode.com/docs)
- **Amp (SECONDARY):** the CLI "Thread Map" links threads, continuations and handoffs. [HackerNoon](https://hackernoon.com/sourcegraph-spinoff-amp-rolls-out-thread-map-to-manage-agent-workflows?source=rss)
- **Replit Agent (PRIMARY):** Agent works in the Project Editor and "creates checkpoints as it works, so you can roll back to any previous state." Triggers are chat and connected services. [Replit Agent docs](https://docs.replit.com/core-concepts/agent)
- **OpenHands Cloud (PRIMARY):** "the environment where OpenHands runs commands, edits files, and starts servers." Sandbox types are Docker (recommended, isolated container), process (no isolation) and remote (used by managed deployments such as OpenHands Cloud). [OpenHands sandboxes overview](https://docs.openhands.dev/openhands/usage/sandboxes/overview.md)
- **OpenHands integrations (PRIMARY index only):** GitHub, GitLab, Bitbucket, Slack and Jira Cloud, event-based automations, a PR review agent, and a "Warm Sandbox Pool" cookbook. Bodies not fetched. [OpenHands docs index](https://docs.openhands.dev/llms.txt)
- **Factory Droids (PRIMARY):** automation triggers are schedule (cron, UTC), Slack message, GitHub events (PR opened, comment added, new push, label change, checks completed), and webhook (Private Preview). Run target is a Droid Computer, the user's own machine via the desktop app, or GitHub Actions. "Webhook automations can't run on your own machine." [Factory automations](https://docs.factory.com/software-factory/automations) (the `docs.factory.ai` address redirects here)

### Inferences
- Antigravity's local worktree model and Factory's GitHub Actions option are the two run locations most like the factory's current model.
- Triggers are split: chat for interactive work, GitHub events for maintenance work. The factory already uses PR comments as its trigger.

### Gaps
- Devin sandbox model, Outposts orchestration and Subagents bodies: not fetched.
- Antigravity cloud execution: UNVERIFIED.
- Kiro runtime provider: not found.
- Amp permission and approval points: not found.

## Key question 2: context, HITL and output unit

### Takeaway
Every platform ends at a reviewable unit: a PR, a diff, or a set of artifacts. Plan approval before code changes is the common human gate (Jules, Replit, Antigravity). Factory adds a setup-PR gate and a pause-until-resumed rule.

### Cited Findings
- **Jules:** plan review before changes; notification on completion or input request. [Jules getting started](https://jules.google/docs/)
- **Replit:** Plan mode produces an ordered task list, and "Agent begins building only after you approve the plan." Paid actions "need confirmation before a paid action starts." Background tasks are capped at 1 on Core and 10 on Pro. [Replit Agent docs](https://docs.replit.com/core-concepts/agent)
- **Antigravity:** Artifacts include an implementation plan, a walkthrough and screenshots. `/grill-me` asks clarifying questions before implementation. [Antigravity getting started](https://antigravity.google/docs/getting-started)
- **Factory:** GitHub automations need the setup PR merged first, or runs "fail to post or push." Automations that cannot run reliably pause until an owner resumes them. Deleting one or running as a service account needs approval. [Factory automations](https://docs.factory.com/software-factory/automations)
- **Factory outputs:** Code Health opens "one small maintenance PR per run"; Error Triage opens a fix PR when safe; PR Reviewer posts review comments. [Factory automations](https://docs.factory.com/software-factory/automations)
- **Kiro:** proposed edits and PRs, with persistent context across sessions. [Amazon announcement](https://aboutamazon.com/news/aws/amazon-ai-frontier-agents-autonomous-kiro)
- **Replit outputs:** apps, dashboards, slides and documents that "All artifacts publish together." [Replit Agent docs](https://docs.replit.com/core-concepts/agent)

### Inferences
- A plan-approval step before code is cheap and already common. It matches the factory's spec-first flow.
- Factory's setup-PR gate shows a real failure mode: automations stop silently until a human merges. The factory should expect the same and alert on it.

### Gaps
- Devin PR creation and review flow: not found.
- Jules and Antigravity: no primary detail on how output is reviewed.

## Pricing

Only Replit and Factory describe tiers in primary text. No platform's amounts were verified.
- Devin: ACU billing; amounts not fetched. [Devin docs index](https://docs.devin.ai/llms.txt)
- Jules: free and paid tiers; secondary only. [Morph](https://www.morphllm.com/comparisons/jules-google-coding-agent)
- Antigravity, Kiro, Amp, OpenHands: credit or budget pages linked; no figures. Not found.
- Replit: Free, Auto, Power and Max modes; amounts not fetched. [Replit Agent docs](https://docs.replit.com/core-concepts/agent)
- Factory: not found.

## Comparison table

| Platform | Control plane | Where code runs | Triggers | HITL points | Output unit | Parallelism | Credentials | Pricing |
|---|---|---|---|---|---|---|---|---|
| Devin | Cognition cloud | Cloud VM; Outposts self-hosted (index only) | Web, API, CLI, Slack, Linear, Jira | Not found | Not found | Subagents page (not fetched) | Not found | ACU, amounts not found |
| Jules | Google | Google cloud VM | Web app (primary); issue label UNVERIFIED | Plan approval | Not found | Limits not fetched | Not found | Tiers, secondary only |
| Antigravity | Agent Manager | Local folder or git worktree; cloud UNVERIFIED | UI, slash commands | Plan review, `/grill-me` | Artifacts | One agent per task | Not found | Credits, no figures |
| Kiro | AWS / Kiro web | Sandboxed session; runtime not named | GitHub assignment, hooks | Review of edits and PRs | PRs, proposed edits (multi-repo) | Not found | Not found | Add-on credits, no figures |
| Amp | Sourcegraph | Cloud orb per thread, or local CLI | Web, CLI, mobile | Not found | Thread output | Multiple threads | Not found | Not found |
| Replit Agent | Replit | Replit project environment | Chat, connected services | Plan approval, paid-action confirm | Apps, documents, dashboards | 1 (Core) or 10 (Pro) background tasks | Replit account | Tiers, amounts not fetched |
| OpenHands Cloud | OpenHands | Managed remote sandbox; Docker or process for self-host | GitHub, GitLab, Bitbucket, Slack, Jira, event automations | Not found | PRs (PR review agent) | Warm sandbox pool (cookbook) | Not found | Budgets, no list price |
| Factory Droids | Factory | Droid Computer, user machine, or GitHub Actions | Cron, Slack, GitHub events, webhook (preview) | Setup-PR merge; pause/resume; approval for delete | PRs, commits, comments | Not found | Service account option | Not found |

## Implications for factory architecture

- **Devin:** Outposts is a self-hosted execution plane under a cloud control plane. That is close to the factory's E2B sandbox split. Read the Outposts page before copying it.
- **Jules:** Gate Build on an approved plan. The factory's spec-first flow already has that step.
- **Antigravity:** Worktree-per-agent matches the factory's one-branch-per-run rule. Do not design around the unverified cloud claim.
- **Kiro:** Persistent context plus PR output fits the factory's PR-comment feedback loop. Keep human review on every PR, because stored context can carry bad habits.
- **Amp:** One machine per thread matches one sandbox per run. Its thread handoff is a reference for the seat handoff, but it is secondary-sourced.
- **Replit:** Checkpoints and per-tier concurrency caps are useful limits. The factory should cap concurrent runs per repo.
- **OpenHands Cloud:** Warm sandbox pools cut start time. Measure whether start time matters before building one.
- **Factory:** Its setup-PR gate and pause-until-resumed rule are the most concrete HITL design found. Copy the pause rule for GitHub-triggered Build runs. The GitHub Actions run target matches the factory's reusable workflow.

## Platforms not fully covered (open work)

- Devin: the sandbox, Outposts orchestration and Subagents pages were not fetched. Next: `docs.devin.ai/cloud/outposts/overview.md`, then the orchestration page.
- Jules: the usage-limits and CLI pages were not fetched.
- Antigravity: the Agent Manager and Artifacts pages were not reached (redirect). Cloud execution UNVERIFIED.
- Kiro: the autonomous-mode page was not fetched.
- Amp: the orbs and tools pages were not fetched. Pricing and permissions not found.
- Replit: billing amounts not fetched.
- OpenHands Cloud: cloud and automation pages were listed in the index only.
- Factory: Droid Computer and concurrency limits not found.
- Pricing: no per-platform amount verified for any of the eight.
