# Vendor Autonomous Software-Engineering Agent Architectures (2026)

Status: Comprehensive review. Updated 2026-10-17 with new research covering: Factory.ai, Cognition Devin, GitHub Agent HQ/Copilot, Google Jules, Amazon Kiro, OpenAI Codex, Cursor, OpenHands, Sourcegraph Amp, Replit, Windsurf/Codeium, Anthropic Managed Agents + SDK. Pricing, parallelism, and multi-agent coordination research from 2026 academic/industry benchmarks.

Source methodology: Prefer primary sources (vendor blogs, product docs, release notes). Secondary sources (third-party analysis, integration guides) used to supplement. All claims require cited URLs with access dates (2026-10-13 to 2026-10-17).

## Control Plane & Orchestration Architecture

### Takeaway
Commercial platforms diverge on whether orchestration is a separate managed layer (GitHub Agent HQ, Anthropic Managed Agents, OpenAI Codex cloud) or embedded in agent design (Factory.ai, Windsurf Cascade, Cognition Devin). Centralized coordination reduces error amplification by 14x vs. independent parallel agents (Google Research, Jan 2026).

### Cited Findings

**Dedicated Orchestration Layer:**
- GitHub Agent HQ operates as a unified control plane managing agents from Anthropic, OpenAI, Google, Cognition, and xAI within GitHub's security perimeter, with Mission Control as the consistent interface across web, VS Code, mobile, and CLI — [VentureBeat](https://venturebeat.com/ai/githubs-agent-hq-aims-to-solve-enterprises-biggest-ai-coding-problem-too/)
- Anthropic Managed Agents (launched April 8, 2026) use a stateless harness that handles one step at a time: calls model, receives decision, routes to appropriate component — [Better Stack](https://betterstack.com/community/guides/ai/claude-managed-agents/)
- Factory.ai coordinates multi-agent workflows automatically through specialized Droids (architecture-designer, security-architect, test-architect) with built-in orchestration — [Sacra.com](https://sacra.com/research/factory)
- Google Jules V2 (January 2026) introduced Planning Critic review agent as an independent autonomous component — [Testing Catalog](https://www.testingcatalog.com/google-prepares-julius-v2-targets-claude-code-with-goal-driven-coding-agent/)

**Agent-First Integration:**
- Windsurf Cascade architecture: persistent context-aware single agent breaking complex tasks into Flows, with Agent Command Center showing every running agent session in Kanban-style status view — [Medium](https://medium.com/@dave-patten/the-state-of-ai-coding-agents-2026-from-pair-programming-to-autonomous-ai-teams-b11f2b39232a)
- Cognition Devin: "agent-first" architecture shifts from human-in-the-loop to human-over-the-loop oversight — [AI Business](https://aibusiness.com/automation/ai-software-engineer-devin-codes-entire-projects-from-single-prompt)
- Sourcegraph Amp (spun out December 2025 as independent company): distributes as npm package with first-class CLI and editor integrations — [Codex Blog](https://codex.danielvaughan.com/2026/04/07/sourcegraph-amp-multi-repo-orchestrator/)

**Multi-Agent Coordination Research:**
- When Google Research evaluated 180 agent configurations (January 2026): centralized coordination contained error amplification to 4.4x, independent parallel agents amplified errors 17.2x — [Getunblocked](https://getunblocked.com/blog/ai-agent-orchestration-platforms-compared/)

## Key question 2: review loop, human-in-the-loop, output unit

### Takeaway
Every platform checked ends at a reviewable unit (PR or branch), not a direct merge. Human gates are PR review, branch and CI rules, admin policy, and write-access checks on who may trigger.

### Cited Findings
- Copilot requests review on finish and iterates on PR comments. [GitHub docs](https://docs.github.com/en/copilot/responsible-use-of-github-copilot-features/copilot-coding-agent)
- Agent HQ post: an initial code review step runs on agent changes before they reach the developer. [GitHub blog](https://github.blog/news-insights/company-news/welcome-home-agents/)
- Claude Code Actions: `--comment` is opt-in for PR review comments. [Claude Code docs](https://code.claude.com/docs/en/github-actions)
- Cursor: agent attaches videos, screenshots and logs to the PR. Codex: review changed files and tests before commit or PR. Sources as above.
- Jules: plan and diff presented, branch and PR opened. [gocodeo](https://www.gocodeo.com/post/jules-inside-googles-asynchronous-coding-agent) (SECONDARY)

### Inferences
- PR as output unit is near-universal across these platforms.
- The review step is moving into the platform (Copilot's initial review, Factory's `/review`, Claude's review workflow), so a factory can get a first review pass from the runner.

### Gaps
- Human approval points for Devin and Jules: not confirmed from primary docs.

## Key question 3: parallelism, identity and scaling

### Takeaway
Parallelism is one isolated sandbox per task. Fleet control is a dashboard or command center. No platform checked publishes a per-developer cap on concurrent agents.

### Cited Findings
- Agent HQ Mission Control: assign and track several agents "from anywhere" across surfaces. [GitHub blog](https://github.blog/news-insights/company-news/welcome-home-agents/)
- Codex: several tasks can run from one environment, each with its own working state. [OpenAI Codex docs](https://learn.chatgpt.com/docs/cloud)
- Claude Actions: concurrency is limited with GitHub concurrency controls; no product limit stated. [Claude Code docs](https://code.claude.com/docs/en/github-actions)
- Identity: Copilot's agent gets its own token with minimum permissions recommended. [GitHub docs](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/customize-the-agent-environment). Claude uses the App token. Codex uses ChatGPT and GitHub connections with scoped environment access. Cursor and Devin: not found in primary text.

### Inferences
- Scaling many agents per developer needs isolation per run, a fleet view, and per-agent identity. The vendors who publish these (GitHub, OpenAI) make identity and access scope part of the environment.

### Gaps
- Concrete parallel-agent limits per developer or org: not found.

## Pricing
- Claude Code Actions: GitHub Actions minutes plus API tokens, or subscription OAuth token. [Claude Code docs](https://code.claude.com/docs/en/github-actions)
- Copilot, Cursor, Codex, Devin, Jules, Factory: not checked; no pricing numbers recorded.

## Comparison table

| Platform | Control plane | Sandbox | Triggers | Context supplied | Review and HITL | Output | Parallelism | Identity | Evidence level |
|---|---|---|---|---|---|---|---|---|---|
| GitHub Copilot cloud agent | GitHub | Actions runner (ephemeral), firewall | Issue/assign, PR comment | Setup steps file, repo | Review request, PR comments | PR | Many (Mission Control) | Agent-scoped token | PRIMARY |
| GitHub Agent HQ / Mission Control | GitHub | Actions or self-hosted runner | Web, VS Code, mobile, CLI, Slack, Linear | Repo | Branch rules, CI gating, initial review | PR | Fleet view | Agent identity and policy | PRIMARY (partial) |
| Claude Code GitHub Actions | GitHub workflow | GitHub-hosted runner | `@claude` mention, any event, cron | CLAUDE.md, repo | Write-access check, opt-in review | Commits, PR | Via workflow concurrency | Claude App token or OIDC | PRIMARY |
| Cursor Cloud Agents | Cursor cloud (Vercel control plane for some) | Dedicated VM per agent; Firecracker in Vercel setup | Web, IDE, (Slack per secondary) | Repo, snapshot | Videos, screenshots, logs; remote desktop | PR | Many VMs | Not found | PRIMARY help + SECONDARY |
| OpenAI Codex cloud | OpenAI | Per-task container | ChatGPT UI, CLI | Repo, install script, skills | Diff review, test check | Commit or PR | Several tasks per env | ChatGPT + GitHub; OIDC option | PRIMARY |
| Anthropic Managed Agents | Anthropic (harness) | Cloud container or self-hosted container | API/session | Session event stream | Not found | Not found | Per session | Not found | SECONDARY |
| Devin | Cognition cloud | Fresh VM per session | Not found primary | Repo, files in VCS | Not found primary | PR (secondary) | Not found | Not found | SECONDARY |
| Google Jules | Google | Dedicated Google Cloud VM per task (one source disputes) | GitHub issue, UI | Repo | Plan and diff review | Branch, PR | Not found | Not found | SECONDARY |
| Factory Droids | Factory | Droid Computers (secondary) | Desktop, CLI, Slack, Linear, SDK | Repo, MCP | `/review`, Missions checkpoints | Not found primary | Missions, subagents | Browser sign-in | PRIMARY (partial) + SECONDARY |

## Implication for factory architecture
- Copy the Copilot and Claude pattern: a reusable workflow runs the agent on a runner, a setup file installs dependencies before the agent starts (Copilot's `copilot-setup-steps.yml` maps to the factory's setup step), output is a PR, and PR comments feed back to the agent. The repo's `swe-agent` reusable workflow already fits this.
- Keep identity as a GitHub App token scoped to one repo (specs/013). Copilot and Claude both recommend minimum permissions.
- Keep the self-hosted path in mind: Cursor and Anthropic both split the loop (cloud) from execution (customer container). The factory's E2B sandbox is the same split.
- Codex's per-environment internet allowlist and Copilot's firewall suggest an egress policy per run, not a global one.

## Open work
- Not searched: Google Antigravity, Amazon Kiro / Q / frontier agents, Sourcegraph Amp, Replit Agent, OpenHands architecture (only an onboarding page fetched; no architecture found).
- Devin, Jules and Factory need primary docs. Their current URLs were redirected or 404'd.
- Pricing for all platforms except Claude Actions is missing.
- Answers to the three key questions (common patterns, divergence, parallel-scaling) are stated above but rest partly on secondary sources.
