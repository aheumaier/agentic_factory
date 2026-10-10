# Research prompt — Microsoft Teams as the workspace of a human + agent software team

> **How to use this file.** Hand everything below the line to a deep-research
> agent as-is. It is self-contained: it restates the stack, the decisions
> already made, and the exact output format. Findings get folded back into
> [`docs/80-teams-workspace-design.md`](../80-teams-workspace-design.md),
> whose §17 open questions cross-reference the question letters (A–L) used
> here. Keep the letters stable; reorder nothing.
>
> Written 2026-10-09.

---

## 0. Your task

You are researching how to build a **Microsoft Teams workspace for a mixed
human + AI-agent software team**, on top of an existing Python/Temporal
pipeline. Your output is evidence, not a design: answer each lettered
question below from primary sources, and say how confident you are and what
it means for the design. A separate design doc
(`docs/80-teams-workspace-design.md`) already exists and is waiting on your
answers. Where it states something as a working assumption, your job is to
confirm or refute it.

## 1. Context

### 1.1 The stack you are designing against

- **Orchestration: Temporal (self-hosted, Python SDK `temporalio`).** One
  workflow, `AgentPipelineWorkflow`, runs on the task queue
  `agent-factory-pipeline`. Today it sequences:
  `ensure_target_pr` → architect stage (N candidate plans, judged and
  synthesized) → **human plan gate** (`plan_approved` / `plan_rejected(feedback)`
  signals + `workflow.wait_condition`) → Build (coding agent in an E2B
  sandbox) → Eval-Gate → Register. The workflow has no `@workflow.query`
  methods yet. Planned extensions (spec 005) add a `mode` parameter, PM and
  security gate signals, and an `escalation_resume` / `escalation_abandon(reason)`
  pair on retry-budget exhaustion. Each gate has a per-attempt "decision
  window", and a stale decision must never release a later window.
- **Agents: Claude Agent SDK (Python).** Each agent is a registry entry
  (`registry/agents/<name>/`: `manifest.yaml` + `SKILL.md`):
  - `pm-agent` shapes issues and reviews specs.
  - `architect-agent` does plan fan-out/judge.
  - `swe-agent` implements an already-planned Spec Kit feature, then opens a PR.
- **Model routing: LiteLLM proxy (self-hosted).** All model calls from the
  orchestration host go through it.
- **Inbound surface today: a GitHub App.** `orchestration/webhook_bridge/`
  is an **aiohttp** server. It does the following:
  - verifies GitHub `issue_comment` webhooks (HMAC), relayed locally via smee;
  - authorizes the author by GitHub repo permission (`write`/`admin`);
  - de-duplicates by delivery ID;
  - parses an exact comment grammar (`@pipeline-agent run mode=… agent=… version=…`, `plan_approved`, `plan_rejected: <feedback>`, …);
  - calls `start_workflow` / `signal`, finding the target run through the
    custom search attributes `TargetRepo` and `PRNumber`;
  - reacts on the comment (🚀 / 👀 / 😕).
- **Process: GitHub Spec Kit.** Every feature is
  `specs/NNN-slug/{spec,plan,tasks}.md` on a feature branch. The steps are
  specify → clarify → plan → tasks → implement. Tasks marked `[P]` "can run
  in parallel (different files, no dependencies)".
- **Git is the source of truth** for specs, plans, diagrams, mocks, code and PRs.

### 1.2 The mental model (the user's words)

> "The mental model is a real software team… we're just extending a current
> small team, one product engineer and one architect, with a fleet of
> agents." Work happens in a Teams chat, and the team must see real
> artifacts there: "Do we have a visualization of the architecture? Where
> can I see the mock?"

### 1.3 Decisions already made (do not re-open; do flag if evidence makes one impossible)

1. **The humans are the leads.** A product engineer (PE) and an architect
   direct the work, decide, and approve at every Spec Kit checkpoint.
2. **Each agent role is a teammate with its own Teams bot identity:**
   Coordinator ("Factory"), Product, Designer, Architect, Coder, Reviewer.
   There is one bot per *role*. Several coder instances share one bot and
   are labelled (e.g. "Coder #2 · T005–T007").
3. **Temporal enforces the Spec Kit process.** Concurrency follows what a
   real team would do within that process.
4. **Agents coordinate through workflow events and git artifacts, not by
   chatting.** The Teams thread is the human-visible projection: a live
   team-board card plus handoffs, questions-to-leads and presentations.
5. **A Teams channel tab renders artifacts from git** (spec, plan,
   diagrams, mocks).
6. **GitHub stays as a secondary command surface.** When a decision arrives
   from both Teams and GitHub, the first valid one wins.
7. **Candidate tech, to confirm or refute:**
   - Teams SDK for Python (PyPI `microsoft-teams-apps`, repo
     `microsoft/teams.py`), reported GA on 2026-05-01;
   - TeamsJS for the tab;
   - Adaptive Cards for interaction.
8. **Takeover of a stuck lane is tool-agnostic.** The card gives the
   branch, the PR and a clone command.

### 1.4 Goal

Produce the evidence that turns docs/80's working assumptions into
confirmed design, and surface anything that forces a design change.

## 2. Source rules

- **Primary sources only for factual claims:**
  - `microsoft.github.io/teams-sdk`
  - `github.com/microsoft/teams.py` (code, releases, issues)
  - the TeamsJS docs and `github.com/OfficeDev/microsoft-teams-library-js`
  - `learn.microsoft.com` (Teams platform, Bot Service, Graph, Adaptive Cards, Entra)
  - `adaptivecards.io` / `adaptivecards.microsoft.com`
  - `docs.temporal.io` and the `temporalio` Python SDK source
  - `github.com/github/spec-kit`

  Blogs, Stack Overflow and forum posts may *point* you to a primary
  source. They are never the evidence.
- **Date-stamp every claim** with the source's last-updated date (or your
  access date if it has none). **Pin versions:** package versions, manifest
  schema versions, Adaptive Card schema versions.
- **Flag staleness.** Mark any source dated before the 2026-05 GA of the
  Teams SDK for Python as `PRE-GA`, and say whether it still applies.
  Bot Framework-era docs are the usual trap.
- **Separate fact from inference.** Label every statement `DOC` (a source
  says it), `CODE` (you read it in SDK source or samples) or `INFER` (your
  reasoning). Never present an `INFER` as a `DOC`.
- If a question cannot be answered from primary sources, say so plainly.
  That gap is a finding.

## 3. Questions

### A. SDK lineage

1. Lay out the current relationship between these SDKs, and which are
   supported, in maintenance, or deprecated, with dates:
   - Teams SDK v2 (formerly "Teams AI Library v2");
   - Teams AI Library v1;
   - Bot Framework SDK (Python `botbuilder-*`);
   - Microsoft 365 Agents SDK.
2. Confirm the Python package name(s), the GA date, the current version, and the
   support horizon of the Teams SDK for Python. Is Python at parity with
   TypeScript/C#? List the features that are TS/C#-only.
3. Does the Python SDK cover anything for **tabs** (server-side helpers,
   SSO token exchange), or are tabs purely TeamsJS?
4. Which SDK should a new Python bot built in late 2026 use, and why?

### B. Registration & hosting

1. Compare Azure Bot resource registration with Teams Developer Portal bot
   registration. Which is required for channel bots with proactive
   messaging and Adaptive Card actions?
2. Entra app setup:
   - single-tenant vs. multi-tenant (note any multi-tenant deprecation for new bots);
   - client secret vs. certificate vs. managed identity / federated credentials.

   Which work when the bot is **not** hosted on Azure compute?
3. Messaging endpoint requirements: public HTTPS, certificate, any IP
   allow-listing.
4. Local development:
   - Dev Tunnels;
   - the Microsoft 365 Agents Toolkit (formerly Teams Toolkit);
   - the Teams SDK DevTools / playground.

   What is the minimal loop that needs no Azure subscription?
5. Can the bot be **self-hosted** on our own host (docker-compose next to
   Temporal) with no Azure compute at all? What Azure resources remain
   mandatory?
6. Can the Python SDK's `App` be **mounted inside an existing aiohttp
   application** (our `webhook_bridge`)? Or does it bring its own HTTP
   server (FastAPI/uvicorn?) that we must run alongside? Show the plugin or
   adapter mechanism.

### C. Conversational bots in channels

1. Does a bot in a channel receive only messages that @mention it? What
   exactly does RSC `ChannelMessage.Read.Group` change (all messages? which
   events?), and what consent does it need?
2. **Thread history for agent context.** Can the bot read prior replies in
   a channel thread through the activity stream, or only through Graph
   (`/teams/{id}/channels/{id}/messages/{id}/replies`)? Which permissions
   does each need (RSC vs. application), and what are the protected-API /
   metered-API constraints?
3. The conversation-id format for a channel root post vs. a reply in its
   thread. How does a bot reply *into* an existing thread?
4. In channels specifically, what is the support status of each of these?
   - streaming responses;
   - typing indicators;
   - the "AI generated" label;
   - citations;
   - feedback (👍/👎) buttons.
5. Mention handling: does the SDK strip the bot's own `<at>` mention from
   the text? How are other @mentions (users, other bots) represented?

### D. Proactive messaging

1. To send from a **different process** (a Temporal activity on the
   worker host, not the bot's HTTP handler), what has to be persisted?
   (Conversation reference, service URL, tenant id, bot id, the channel
   thread's conversation id …?) How long is each value valid?
2. What install prerequisites apply (app installed in the team?) before a
   proactive post to a channel or thread works?
3. Show the minimal Python Teams SDK call that sends a new message, or a
   reply into a known thread, from a function holding only stored ids plus
   credentials.
4. Can a proactive send create a **new channel post** (thread root) as well
   as reply into an existing thread?

### E. Adaptive Cards

1. Which Adaptive Card schema version does Teams desktop/web/mobile support
   today? Which elements/actions are unsupported on mobile?
2. Compare `Action.Execute` (Universal Actions) with `Action.Submit`:
   - How does the Python SDK surface each invoke?
   - What must the handler return?
   - Do user-specific views and auto-refresh (`refresh.userIds`) work in channels?
3. **Updating a posted card in place.** We need this for a live "team
   board" and for "resolved by X via GitHub". Cover:
   - API and permissions;
   - who may update (only the posting bot?);
   - rate limits;
   - whether updating from a proactive context (see D) works.
4. Images:
   - PNG vs. SVG support;
   - data URIs vs. hosted URLs;
   - size limits;
   - auth on image URLs (can an image URL require a token?).
5. **Card and message size limits.** How should a ~60,000-character plan
   be handled? (Our current GitHub comment budget is 60k.) Truncate +
   link? Attach a file? Something else?
6. Deep links from a card button into a **channel tab with a sub-entity**
   (e.g. open the tab at `feature=008&view=plan`): link format, and
   desktop/mobile behaviour.

### F. Tabs (TeamsJS)

1. What is the current guidance for configurable channel tabs (config page,
   `contentUrl`, `websiteUrl`)? Are static tabs in channels now preferred?
2. **SSO in a tab:** `authentication.getAuthToken()` → on-behalf-of
   exchange → a token our own API accepts. Cover:
   - the Entra app setup;
   - `webApplicationInfo`;
   - which audience our API validates.
3. Explain `validDomains`, CSP and `frame-ancestors`: what the tab's host
   must send to be framed by Teams on all clients.
4. Can the tab render **mermaid client-side** (a JS library inside the tab)?
   Are there CSP or `eval` restrictions?
5. **Sandboxed nested iframes for agent-generated HTML mocks.** We want to
   render an untrusted, self-contained HTML prototype inside the tab. Cover:
   - whether a tab may embed a nested `<iframe sandbox="allow-scripts">`
     served from a **different, isolated origin**;
   - whether that origin must be in `validDomains`;
   - any Teams restriction on nested frames.
6. Mobile behaviour of tabs: what works, and what silently doesn't.
7. Sub-entity routing: how a tab reads the `subEntityId` from a deep link,
   and how it creates one.

### G. Artifact-viewing alternatives

Evaluate each option for viewing a feature's spec (markdown), architecture
diagrams (mermaid/PNG) and clickable mocks (HTML) inside Teams:

- Loop components;
- the channel Files tab (SharePoint), including whether sync from git is
  practical;
- link-unfurling message extensions (unfurl a GitHub/tab URL into a card);
- Adaptive Card image previews;
- a custom channel tab.

Rank them per artifact type, covering fidelity, mobile, auth, effort, and the
cost of keeping git as the source of truth.

### H. Identity & authorization

1. Which identity fields arrive on an inbound activity? Name each one:
   `from.id`, `from.aadObjectId`, the UPN/email (when present), tenant.
   Which of them are stable and safe to authorize on?
2. **Linking a Teams user to a GitHub login.** Cover:
   - the Bot Service OAuth connection / token store with GitHub as an OAuth2 provider;
   - the sign-in card flow;
   - token refresh;
   - whether it works with Teams SSO or needs a separate sign-in.

   Purpose: keep our existing rule that gate decisions require GitHub
   `write`/`admin` on the target repo.
3. Teams-native authorization alternatives:
   - channel membership checks via Graph (RSC `ChannelMember.Read.Group`?);
   - Entra group membership.

   What do they need, and which is cheapest per decision?

### I. Artifact generation

1. **Architecture diagrams from LLMs.** Compare C4 in mermaid
   (`C4Context`/`flowchart`) with Structurizr DSL:
   - generation reliability;
   - validation by parse;
   - server-side rendering to PNG (`@mermaid-js/mermaid-cli` / Structurizr
     CLI) in a headless container: dependencies and Chromium requirements.
2. **Clickable UI prototypes from LLMs.** Compare:
   - static HTML + Tailwind (CDN vs. compiled);
   - design-system components;
   - Storybook;
   - the Figma REST/plugin API.

   For each, what can an agent produce reliably, and how do we screenshot
   it for a card thumbnail?
3. What is safe to render inside Teams (tab, card) from agent-generated
   content? Look at XSS, external fetches and CSP.

### J. Ops & limits

1. Rate limits:
   - per bot, per conversation, per tenant;
   - for proactive sends and card updates;
   - the 429 retry guidance.
2. Message size limits (text, card payload) and attachment options.
3. Retries and idempotency. Do inbound activities carry a stable id usable
   for dedup? Are Teams retries at-least-once?
4. App manifest: the current schema version and the fields relevant to bots,
   tabs, RSC and `webApplicationInfo`.
5. Distribution: sideloading (custom app upload) vs. the org app catalog,
   and the admin approval steps.
6. Testing:
   - DevTools;
   - unit-testing handlers without Teams;
   - recording/replaying real activities.
7. **Inbound JWT validation:** what the SDK does automatically, and what we
   must configure when self-hosting.

### K. Multi-agent teams in Teams

1. **Can one app package hold multiple bots, or is it one bot per app?**
   If one per app, what do these look like?
   - N Entra registrations;
   - N manifests;
   - a bundled catalog entry (is there an app "bundle" concept?);
   - admin consent ×N.
2. **Do bots receive other bots' channel messages?** (With RSC
   `ChannelMessage.Read.Group`? Without?) This decides whether "agents
   don't chat with each other" is enforced by the platform or by us.
3. Can **one Python process host N `App` instances**, each with its own
   credentials and its own messaging route? Is there shared global state in
   the SDK that prevents this?
4. Per-bot rate limits when N bots post into the same channel or thread.
5. The UX of installing several apps into one channel: N installs or one,
   and admin vs. user.
6. How does @mentioning a specific bot route when several bots are
   installed in the channel? Does only the mentioned bot get the activity?
7. Per-bot avatars and display names: where are they set, and can a bot
   post "as" a sub-identity (e.g. "Coder #2")?

### L. Orchestration patterns

1. **Temporal entity-workflow patterns for a long-lived feature.** Cover:
   - a parent "feature" workflow with per-role child workflows ("lanes");
   - signals to a specific child;
   - signal-with-start and update-with-start;
   - `continue-as-new` for a workflow that lives days or weeks;
   - workflow-to-workflow signalling;
   - Updates (validated, acknowledged) vs. Signals for human decisions.

   Cite the Python SDK API for each.
2. A `@workflow.query` or Update for "status" while a workflow is blocked
   in `wait_condition`: any constraints?
3. **Spec Kit `[P]` semantics as a fan-out rule.** Use
   `.specify/templates/tasks-template.md` upstream in `github/spec-kit`.
   Does Spec Kit define how `[P]` tasks group, or any dependency notation
   beyond phase order?
4. **Git strategies for parallel agent lanes.** Compare sub-branches per
   lane merged into the feature branch with `git worktree` per lane:
   - conflict detection/resolution;
   - who merges;
   - how existing multi-agent coding tools handle it (cite primary docs).

## 4. Output format

Produce one markdown document with these sections.

### 4.1 Per-question answers

For **each** numbered sub-question, in letter order:

```
### <Letter>.<n> <short title>
**Answer:** …
**Evidence:** <URL> (last updated YYYY-MM-DD; DOC|CODE|INFER) …
**Confidence:** high | medium | low — <why>
**Implication for docs/80:** <which §, and confirm / change / new risk>
```

### 4.2 End-to-end sketch

Write minimal, runnable-in-principle Python (and one HTML/JS file)
showing all of the following, with each SDK call cited:

1. **Two `App` instances** (Coordinator plus one agent, e.g. Architect), each
   with its own credentials, served from **one aiohttp process**. If that is
   impossible, show the closest supported shape and say why.
2. Receiving an @mention in a channel thread and **replying in that
   thread**.
3. Posting an Adaptive Card and later **updating it in place**.
4. A **proactive send** from a separate function (standing in for a Temporal
   activity), using only persisted ids plus credentials.
5. A **TeamsJS channel tab** that does SSO, calls our API with the
   exchanged token, and renders a mermaid diagram client-side.

### 4.3 Risks and unknowns

List what could not be confirmed, what contradicts the decisions in §1.3,
and what needs a spike. Give each item a severity: blocks design, changes
design, or detail.

### 4.4 Question → docs/80 section map (for the folding pass)

| Letter | docs/80 sections it feeds |
|---|---|
| A | §7 system architecture, §15 hosting, §16 phasing |
| B | §7, §15 |
| C | §6 chat protocol, §7 conversation handling |
| D | §7 outbound notifier, §10 correlation |
| E | §12 decisions across surfaces, §14 cards & UX |
| F | §7 artifact service, §8 artifact model (tab) |
| G | §8 |
| H | §13 identity & authorization |
| I | §9 new producers |
| J | §14, §15 |
| K | §2 team roster, §7 |
| L | §4 concurrency, §5 lane model |
