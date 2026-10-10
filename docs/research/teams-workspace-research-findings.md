# Teams research confirms the six-bot workspace

The Teams workspace in `docs/80-teams-workspace-design.md` can be built as designed, on `microsoft-teams-apps==2.1.0`, self-hosted next to Temporal with no Azure compute. But 36 findings change docs/80 before spec 008 is written, and six spikes have to run first. The core holds. One bot per role is feasible because each role must be its own Teams app anyway (the manifest allows one bot per app). All six `App` instances can mount into the existing aiohttp `webhook_bridge` through the SDK's `HttpServerAdapter` protocol. Proactive sends and in-place card updates work from a Temporal activity using only stored scalars. Static channel tabs handle SSO and client-side mermaid. The changes cluster in five places:

- **Identity.** GitHub sign-in needs an Azure Bot resource and a per-bot token store. The researchers disagree on whether sign-in works in a channel at all.
- **Cards.** Routing keys off `data.action`, not `verb`. Images cannot sit behind SSO. The hard size limit is 80 KB measured in UTF-16. A card action's invoke response only changes the clicking user's view, so the message must also be edited.
- **Tab.** Static tabs only, using the `getAuthToken()` token directly with no OBO exchange. Mocks need signed URLs, and the nested-iframe question is unresolved.
- **Producers.** Mermaid C4 cannot be validated by parsing, and there is no Python parser at all.
- **Orchestration.** Use an Update plus validator for decisions. Lanes must survive continue-as-new. Lanes split per user story, not per `[P]` run.

Three questions are genuinely contested in the notes and are presented as such below: whether channel sign-in needs a personal chat first, whether a thread's conversation id is per bot, and whether Teams-managed (non-Azure) bot registrations support proactive messaging and card actions.

## Executive summary

**Verdict.** Every decision in prompt §1.3 survives. None is made impossible by the evidence.

- **Decision 2 (one bot per role)** is forced into "six separate Teams apps", because the manifest caps `bots` at one. That is still feasible.
- **Decision 5 (tab renders git)** is confirmed. Mocks are the one exception, pending a spike.
- **Decision 7 (Teams SDK for Python, TeamsJS, Adaptive Cards)** is confirmed. GA was 2026-05-01 and the current release is 2.1.0 (2026-09-16).

### Findings that change docs/80

| # | docs/80 § | Change | Source entry |
|---|---|---|---|
| 1 | §2, §7.1 | Six role bots means **six Teams apps**: 6 manifests, 6 Entra apps, 6 bot registrations, 6 installs. There is no bundle concept. Close the K.1 open question. | K.1, K.5 |
| 2 | §2 | **No per-message sender override exists.** "Coder #2 · T005–T007" must be card or text content. Do not use `onBehalfOf`, which attributes the message to a human. | K.7 |
| 3 | §5 | A parent continue-as-new **terminates running lanes** under the default `ParentClosePolicy.TERMINATE`. Start lanes with `ABANDON` and deterministic ids, or never continue-as-new while lanes run. Lanes report upward by signal. | L.1 |
| 4 | §5.1 inv. 1 | Settle L.4: **one sub-branch per lane** (worktrees add nothing across E2B sandboxes). The code-side merge activity pre-checks with `git merge-tree --write-tree`; exit 1 is a lane failure. | L.4 |
| 5 | §5.1 inv. 4 | Upstream Spec Kit's parallel unit is the **user story**. Barriers apply only at Setup, Foundational and Polish. Default to one Coder lane per user-story phase, optionally split by disjoint-path `[P]` runs. The dependency check is ours, because there is no machine-readable notation. | L.3 |
| 6 | §6.4, §14 | **Streaming is unavailable in channels**, and typing indicators in channels are unconfirmed. Status lives on the board. The AI label, citations and feedback buttons do work in channels. | C.4 |
| 7 | §7.3 | Thread context: the activity stream carries no history. Prefer **our own thread log**, fed by giving Factory the RSC permission `ChannelMessage.Read.Group`. Graph `/replies` remains a backfill path whose protected-API status is unknown. Strip **only the bot's own** mention; the Python SDK strips all mentions by default and has no mention route. | C.2, C.5 |
| 8 | §7.1, §15 | The Teams adapter mounts in the existing aiohttp process through a ~25-line `HttpServerAdapter`. FastAPI and uvicorn are still hard dependencies. Run `await app.initialize()` **before** `AppRunner.setup()`. | B.6, K.3 |
| 9 | §7.4 | The tab sends the **`getAuthToken()` access token itself**. It is not "SSO-exchanged"; OBO is needed only for Graph. The API validates `aud` = client id GUID, `iss`/`tid` = our tenant, `scp` = `access_as_user`, and identity from `oid`. | F.2 |
| 10 | §7.4, §14.4 | The mock origin can never take part in SSO. Serve mocks on **signed, expiring URLs**. Ship **"open mock in browser" first**; the nested sandboxed iframe waits on a spike. Add `connect-src 'none'`, `form-action 'none'`, `img-src data:` and `frame-ancestors <tab host>` to the mock CSP. | F.5, I.3, G |
| 11 | §7.5, §10.4 | Persist **scalars, not a conversation-reference blob**: threaded conversation id, `service_url` (refreshed on every inbound activity), tenant, team/channel ids, root/card activity ids, bot id. Key rows by `(teams_thread_id, bot_app_id)` until the per-bot-id spike resolves. | D.1, D.4 |
| 12 | §8.2, §15 | Use **`staticTabs`** (manifest ≥1.16, `scopes:["team"]`, `context:["channelTab"]`). Configurable tabs are kept only for backward compatibility. Only one tab can be pinned per app, so the six views are routes inside one tab. The channel↔repo link cannot come from a config page. | F.1 |
| 13 | §9.1 | "Validation by parse, in Python" cannot be done: **no Python mermaid parser exists**. For mermaid C4, parsing accepts malformed input, and `mmdc` can exit 0 with a wrong PNG. Choose Structurizr DSL (`validate` as the gate, `export` to mermaid/PNG) or mermaid `flowchart` plus our own structural check. | I.1 |
| 14 | §9.1, §14 | **Card images must be PNG/JPEG/GIF, ≤1024×1024, with no SVG and no redirects.** | E.4 |
| 15 | §9.2 | Mocks use **compiled Tailwind** (standalone binary, inlined). The Play CDN is forbidden. Screenshots come from Playwright with `offline=True`. Figma is not viable as the primary output, since it needs a Full-seat human MCP session. | I.2 |
| 16 | §12.1 | Use **Update + validator** for Teams decisions, with set-if-unset handlers as defence in depth. GitHub stays on signals that apply to the open window, or the bridge queries the open attempt and sends an Update. The bridge must use `start_update(wait_for_stage=ACCEPTED, rpc_timeout=…)`, because **Updates need a live worker** and signals do not. | L.1 |
| 17 | §12.5, N2 | `status()` must be a **Query**, not an Update. It is advisory (TOCTOU), and it fails when the worker is down. The board aggregates in the parent, because a query cannot fan out. | L.2 |
| 18 | §13, §15 | **GitHub linking through a Bot Service OAuth connection needs an Azure Bot resource** (a subscription, not compute) on whichever bot runs sign-in. Teams SSO cannot replace it: bot SSO is Entra-only and not supported in channels. | B.1, H.2 |
| 19 | §13 | Tokens are stored **per bot**, so sign-in would be repeated for each bot. Make linking a one-time act on Factory: persist `aadObjectId → github_login` and keep authorizing each decision with the GitHub App installation token, as today. | H.2 |
| 20 | §13 | Authorize on `(tenant_id, from.aadObjectId)`, never on `from.id` (it differs per bot). **Add a tenant allow-list middleware.** The SDK does none, and its Entra-issuer inbound path accepts any tenant whose token has our audience. | H.1, J.7 |
| 21 | §13 | Do **not** assume `ChannelMember.Read.Group` (the docs contradict each other). For "any channel member", use the zero-consent bot roster API or RSC `TeamMember.Read.Group`. | H.3 |
| 22 | §14 | Use **`Action.Execute` only**. Every action's `data` carries an `action` routing key, because SDK routed handlers match `data.action`, not `verb`. §14.1 `board.refresh` and §14.3 `gate.decide` route on `verb` today. Gate data also carries `attempt`. | E.2 |
| 23 | §14.3, §12.3 | To show "resolved by X" to everyone, return `AdaptiveCardActionCardResponse` **and** edit the message. The invoke response alone changes only the clicking user's view. | E.2, E.3 |
| 24 | §14.1 | **Factory is the sole editor of the board.** Send cards as attachment-only activities (text plus attachment splits the message and loses the id). Debounce and coalesce updates. | E.3 |
| 25 | §14.3 | The gate card's image URL **cannot be the SSO-protected artifact service**. Use an unguessable, no-redirect URL or an inline `data:image/png;base64` thumbnail. | E.4 |
| 26 | §14.7 | Confirmed that cards never carry artifact bodies. Add a hard check: `len(json.dumps(activity).encode("utf-16-le")) < 80_000`. A 60k-char plan is ≥120 KB in UTF-16 and can never fit. Do not attach files in channels: that is Graph-only and would copy git into SharePoint. | E.5, J.2 |
| 27 | §14.4 | Whether a card can carry actions bound to another bot is **unresolved**. Keep the fallback: Factory posts the gate buttons. | E.3, H.2 gap |
| 28 | §15 | **Use a standard channel.** Shared channels do not support bots, and agents cannot post in private channels. | C.1 |
| 29 | §15 | Azure footprint: 6 Entra apps + 6 bot registrations, of which 5 are Teams-managed (if the B.1 inference holds) and Factory's is an Azure Bot for OAuth. Alternatively all 6 start Teams-managed and Factory is migrated later with `teams app bot migrate`, which keeps its ids. The SDK has **no built-in certificate credential**, so `_CERT_PATH` needs a custom `TokenCredentials` provider. Managed identity and FIC do not work off-Azure. | B.1, B.2, B.5 |
| 30 | §15 | **Never set generic `CLIENT_ID`, `CLIENT_SECRET` or `TENANT_ID` env vars or a reachable `.env`.** `App` silently falls back to them, and `load_dotenv` runs at import. Pass every credential kwarg explicitly. | K.3 |
| 31 | §15 | Put **one shared outbound rate limiter per channel** in the notifier. All bots together get 14 sends/s and 16 per 2 s per thread. Retry 429/412/502/504 with jittered exponential backoff. | J.1, K.4 |
| 32 | §15, §16 | Dev loop: **Agents Playground** plus `dangerously_allow_unauthenticated_requests=True`, guarded so it cannot be enabled in prod. DevTools are removed from Python. Dev Tunnel serves real-client tests. | B.4, J.6 |
| 33 | §15 | Compose runs the **deprecated `temporalio/auto-setup:latest`** (server 1.29.3, unpinned). Move to a pinned `temporalio/server` plus `admin-tools`. | L.1 |
| 34 | §15 | Budget for **one Chromium-bearing renderer image**, shared by diagrams (mmdc/puppeteer, or the 4.03 GB Structurizr playwright image) and mock screenshots. | I.1, I.2 |
| 35 | §15 | The tab's CSP needs `style-src 'unsafe-inline'` because mermaid injects `<style>` without a nonce. Pin mermaid ≥11.16.1 (CVE-2026-50159), use the same version server- and client-side, and give each diagram a sibling-free container. | F.4, I.3 |
| 36 | §16 | Pin `microsoft-teams-apps==2.1.0` and Python ≥3.11. There is **no published support horizon**, and the 2.x line has had about 10 releases with in-line deprecations. Decide whether to bump Spec Kit from 0.13.0 to 1.1.2. | A.2, L.3 |

### Spikes before spec 008

1. **S-D4: per-bot conversation id and cross-bot threading.**
   - Confirm that `app.send(<bare channel id>, card)` creates a thread root and returns its id.
   - Confirm that a *second* bot can `app.reply(channel_id, root_id, …)` into it.
   - Compare the inbound `conversation.id` each bot sees for the same thread.

   If any of these fails, `TeamsThreadId` becomes per-bot.
2. **S-H2: GitHub sign-in in a channel.** Does the SDK's targeted OAuthCard complete sign-in inside a channel, or must the lead first sign in from a personal chat, as Learn says? Also run it on an Azure Bot registration.
3. **S-B1: Teams-managed registration capabilities.** Positively confirm proactive channel posts, `Action.Execute` invokes and RSC on a Teams-managed (non-Azure) bot.
4. **S-F7: deep link into a static channel tab.** Does `…/l/entity/<appId>/<entityId>?context={"subEntityId":…,"channelId":…}` land on a static tab pinned in a given channel, on desktop, web and mobile?
5. **S-E3x: cross-bot card actions.** If the Designer posts a card, where does an `Action.Execute` on it go? Can only the posting bot update it? This decides §14.4.
6. **S-J7: inbound tenant isolation.** Add and test the tenant allow-list middleware, including the Entra-issuer path.

Spikes that can run in parallel with 008 but must finish before the spec named:

- **F.5 nested sandboxed iframe** on web, desktop, iOS and Android (before 011).
- **C.2 Graph `/replies`** protected-API status (only if the own-log design is rejected).
- **K.2 bot-to-bot delivery** (detail; the self-filter already covers it).
- **L.1 two-decisions-in-one-task** `WorkflowEnvironment` test (in 008).
- **I.1 LLM diagram-generation pass-rate** eval (before 010).
- **J.3 inbound duplicate delivery** (in 008).
- **F.3 strict `connect-src`** versus the TeamsJS valid-origins CDN (in 008).
- **E.2B Playground fidelity** for channel threads and `Action.Execute` (in 008).

### Conflicts between researchers or sources (not silently resolved)

- **Channel sign-in.**
  - Learn's add-authentication page (updated 2026-06-30) says OAuth "isn't supported in the group chat or channel scopes directly… they must authenticate in their personal scopes" first.
  - SDK 2.1 code sends a *targeted* OAuthCard in the channel.
  - Unresolved. See H.2 and spike S-H2.
- **Per-bot conversation id.**
  - The proactive-messaging page says "the conversation ID is unique for each agent within a specific channel".
  - It also says "the `channelId` is global". The observed threaded format is built from global ids.
  - Unresolved. See D.4 and spike S-D4.
- **Teams-managed bots and proactive messaging.**
  - The A/B researcher *infers* that Teams-managed suffices for proactive sends and card actions, because the only documented gap is OAuth/SSO. No positive statement exists.
  - The H/K researcher describes each role as needing "its own Azure Bot resource", citing an Azure-oriented auth page.
  - The reconciled position in B.1/K.1 is: Teams-managed for all six, plus Azure only where OAuth is needed. That position is INFER until spike S-B1.
- **RSC consent.** The RSC page says "only resource owners can grant application RSC permissions", and its own SDK table says "a team owner or member".
- **`ChannelMember.Read.Group`.** The Graph channel-members page lists it as least-privileged Application. The RSC table lists it as NA/NA.
- **Teams AI v1 status.** The repo says maintenance, PyPI says "7 – Inactive", and a Learn search snippet says "deprecated" (not found on the fetched page).
- **Agents Playground and auth.** The 2026-06-04 blog says unauthenticated requests are accepted when no credentials are set. Current docs and code return 401 unless the flag is set. The blog is stale.
- **Mention route.** Learn (S1) says the Teams SDK has a "dedicated `mention` activity route". The Python SDK has none (CODE).
- **Deep-link `channelId`.**
  - The deep-link page says `channelId` is "only in configurable tabs with a scope of team".
  - The tabs pages say only static tabs can now be pinned.
  - The deep-link wording is likely stale but unverified.
- **Mermaid version.**
  - The F/G researcher saw 12.x GitHub release tags with dates that contradicted the 2026 advisories.
  - The L/I researcher pinned mermaid 12.1.0 (npm, 2026-10-02) and ran it.
  - Neither confirms that 12.x carries the CVE-2026-50159 fix. The sketch pins 11.16.1.
- **Single-tenant and Dev Tunnels.** A PRE-GA Bot Service page says single-tenant and UAMI bots are not supported in Dev Tunnels. The Teams SDK docs (2026-10-08) recommend Dev Tunnels with single-tenant bots. The Teams SDK docs are treated as current.

---

## 4.1 Per-question answers

Label key, used throughout:

- **DOC**: a primary source says it.
- **CODE**: read in SDK source, samples, schemas, or verified by running pinned tools.
- **INFER**: reasoning by the researchers or this synthesis.
- **PRE-GA**: the source's content date (`ms.date`) is before the 2026-05 Teams SDK for Python GA. Each such source is followed by whether it still applies.

Sources:

- `teams.py` was read at `main@8539006` (2026-10-07), with APIs checked against tag `v2.1.0`.
- `teams-sdk` docs were read from GitHub source at `0187ab0` (2026-10-08).

### A.1 SDK lineage and support status
**Answer:** There are four SDKs.

- **Teams SDK v2** (renamed from "Teams AI Library v2") is the current, actively developed Teams-first SDK. It has separate repos per language: `teams.ts`, `teams.net` and `teams.py`.
- **Teams AI Library v1** is maintenance-only, on a `release/v1` branch with "critical bug fixes and security patches". Its PyPI package `teams-ai` 1.8.2 (2026-06-17) is classified "7 - Inactive". A Learn search snippet calls it "deprecated", but that sentence was not on the fetched page.
- **Bot Framework SDK** (`botbuilder-python`) is end of support. Tickets stopped 2025-12-31, the repo was archived 2026-01-05, and the last release was `botbuilder-core` 4.17.1 (2026-01-05).
- **Microsoft 365 Agents SDK** is the other supported, "first-class" SDK. It is multi-channel and Azure Bot Service-based, while Teams SDK talks to "Teams Bot Service" and covers Teams-native depth. The Agents SDK is also the named Bot Framework migration target. Its Python packages are at 1.8.0 (2026-10-01).

Teams SDK's AI layer (ChatPrompt, OpenAI, MCP, A2A) is deprecated in TS/.NET and **already removed in Python**.

**Evidence:**
- https://github.com/microsoft/botbuilder-python (archive banner and README; accessed 2026-10-09; DOC).
- https://github.com/microsoft/teams-ai README (accessed 2026-10-09; DOC).
- https://pypi.org/project/teams-ai/ (1.8.2, 2026-06-17, "7 - Inactive"; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/platform/teams-sdk/ (ms.date 2026-02-25, PRE-GA, updated 2026-07-28; the "deprecated" wording is search-snippet only; DOC, medium).
- https://github.com/microsoft/teams-sdk/blob/main/teams.md/docs/main/teams/choosing-an-sdk.md (2026-10-08; DOC): "Microsoft positions both as first-class".
- https://github.com/microsoft/teams-sdk/blob/main/teams.md/blog/2026-06-16-ai-libs-to-agent-frameworks/index.md (2026-06-16; DOC): "already removed in Python".
- https://github.com/microsoft/teams.py/releases/tag/v2.0.0 (2026-05-06; DOC): PRs #406 and #413.
- PyPI `microsoft-agents-hosting-aiohttp` 1.8.0 (2026-10-01; DOC).
- The Python compat package `microsoft-teams-botbuilder` depends on archived `botbuilder-*` (CODE `packages/botbuilder/pyproject.toml`). That makes it an EOL dependency (INFER).

**Confidence:** high for Bot Framework end of support, the rename and the positioning. Medium for the formal status of Teams AI v1, because the three sources disagree.

**Implication for docs/80:** §7/§16 **confirm** Teams SDK v2 and drop botbuilder and teams-ai v1. §7 gets a note that Teams SDK is transport, cards and routing only, which fits Claude Agent SDK plus Temporal owning agent logic.

### A.2 Python packages, GA, version, horizon, parity
**Answer:**

*Packages.* `microsoft-teams-apps` (main), which pulls in `microsoft-teams-api` and `microsoft-teams-common`. The others are `-cards`, `-graph` (extra, wraps `msgraph-sdk>=1.30,<2`), `-botbuilder` and `-m365extensions`. All need Python `>=3.11,<4.0`.

*GA.* **Confirmed 2026-05-01**, with nuance:
- the 2.0.0 wheel was uploaded 2026-04-30T23:09Z;
- the GA blog is dated 2026-05-01;
- the GitHub release object is dated 2026-05-06.

*Current version.* **2.1.0** (2026-09-16). `main` is `2.2.0-dev`.

*Support horizon.* **Not published anywhere.**

*Parity.* The GA blog claims "same SDK surface". The researchers found these differences:
1. The browser tab library `@microsoft/teams.client` is TS-only.
2. Typed Graph endpoint packages are TS-only; Python wraps `msgraph-sdk`.
3. `@microsoft/teams.config` has no Python counterpart.
4. The AI/OpenAI/MCP/A2A helpers are removed from Python.
5. DevTools is removed from Python.
6. The docs-level tabs guide covers TS/C# only.
7. There is no Python OTel docs page.
8. The agentic-identity status is unclear.

Socket Mode (experimental) exists in all three languages.

**Evidence:**
- PyPI JSON for `microsoft-teams-apps` (accessed 2026-10-09; DOC). Every pre-May-2026 alpha is PRE-GA.
- https://github.com/microsoft/teams.py/releases (v2.0.0 2026-05-06, v2.1.0 2026-09-16; DOC).
- https://devblogs.microsoft.com/microsoft365dev/python-support-for-the-microsoft-teams-sdk-is-now-generally-available/ (2026-05-01; DOC): no version, LTS or horizon.
- `packages/*/pyproject.toml` (apps pyproject 2026-09-24; CODE).
- The `teams.ts/packages` listing (accessed 2026-10-09; CODE).
- Tabs guide front-matter `languages: ['typescript','csharp']` at https://github.com/microsoft/teams-sdk/blob/main/teams.md/src/pages/templates/in-depth-guides/tabs/README.mdx (2026-10-08; DOC).
- https://github.com/microsoft/teams-sdk/blob/main/teams.md/blog/2026-06-04-devtools-to-agents-playground/index.md (2026-06-04; DOC).

**Confidence:** high for names, versions and dates. Medium for the parity list, which comes from inventories rather than a symbol-level diff.

**Implication for docs/80:** §15/§16 **change**: pin `microsoft-teams-apps==2.1.0` and require Python ≥3.11. **New risk** for §16: no support horizon and high churn. There were about 10 releases in 5 months, including in-2.x deprecations: `default_connection_name` was deprecated in favour of `add_oauth_flow()`, and `skip_auth` was renamed to `dangerously_allow_unauthenticated_requests`.

### A.3 Python SDK and tabs
**Answer:** The Python SDK helps with tabs **server-side only**.

- `App.tab(name, path)` and `App.page(...)` serve a static bundle at `/tabs/<name>/`.
- `@app.func` registers `POST /api/functions/<name>`, authenticated by an Entra bearer token through `TokenValidator.for_entra(client_id, tenant_id, application_id_uri=…)`.
  - Accepted audiences: `client_id`, `api://client_id`, `api://botid-client_id`, plus `application_id_uri`.
  - Required claims: `oid`, `tid`, `name`.
  - Required headers: `X-Teams-App-Session-Id` and `X-Teams-Page-Id`.
- There is **no OBO helper**. The only `on_behalf_of` in the code is the Agent 365 flow.
- Everything client-side is TeamsJS or `@microsoft/teams.client` (TS). The Python tab sample uses a Vite/React frontend with `@microsoft/teams.client ^2.0.9`.
- Socket Mode disables tabs and functions.

**Evidence:**
- `packages/apps/src/microsoft_teams/apps/app.py` `page()`/`tab()`/`func()` (2026-09-29; CODE).
- `auth/remote_function_jwt_middleware.py` (≤2026-06-15; CODE).
- `auth/token_validator.py` `for_entra` (2026-08-03; CODE).
- `examples/tab` (CODE).
- https://github.com/microsoft/teams-sdk/blob/main/teams.md/src/components/include/in-depth-guides/tabs/typescript.incl.md (2026-10-08; DOC).

**Confidence:** high on what exists. Medium on fit, because the Python tab path is undocumented.

**Implication for docs/80:** §7.4/§8 **confirm** decision 7 ("TeamsJS for the tab"). The artifact service can reuse `TokenValidator.for_entra` inside our own aiohttp handlers. Prefer that over `@app.func`, whose route collides across Apps (K.3).

### A.4 SDK choice for a new Python bot in late 2026
**Answer:** Use **Teams SDK for Python, `microsoft-teams-apps==2.1.0`**.

- We need channel threads, mentions, card actions, proactive threaded replies and targeted messages. Microsoft's own decision guide assigns exactly those Teams-depth features to Teams SDK.
- Bot Framework is archived and Teams AI v1 is inactive.
- The **M365 Agents SDK** (`microsoft-agents-hosting-aiohttp` 1.8.0) is the credible fallback. It is natively aiohttp, but it covers only "cross-channel essentials" in Teams.

Teams SDK's downsides are its youth, the missing support horizon, hard FastAPI/uvicorn dependencies, and thinner Python docs.

**Evidence:** choosing-an-sdk.md (2026-10-08; DOC), plus the A.1 sources and `packages/apps/pyproject.toml` (CODE). The Agents SDK's own Teams-specific gaps were **not** read (gap).

**Confidence:** medium-high.

**Implication for docs/80:** §7/§15/§16 **confirm**. Record the Agents SDK as the fallback if FastAPI coupling or churn bites.

### B.1 Azure Bot resource vs Teams Developer Portal (Teams-managed) registration
**Answer:** There are two registration locations.

- **Teams-managed:** registered through the TDP API. It is the default for `teams app create`, and needs no Azure subscription.
- **Azure Bot:** a resource in your own subscription.

The Teams SDK docs say the **only** thing Teams-managed cannot do is OAuth connections and SSO: "Use Azure only when your bot needs OAuth or SSO — that's the one thing Teams-managed can't do". Teams-managed "works for production too".

**No doc positively states** that proactive messaging and `Action.Execute` work on Teams-managed. The A/B researcher infers they do, because they are ordinary Connector calls and activities (INFER, medium). **Conflict:** the H/K researcher's K.1 entry describes each role as needing "its own Azure Bot resource", citing the Azure-oriented add-authentication page. This synthesis reconciles the two as Teams-managed for every role, plus an Azure Bot only on the bot that runs GitHub OAuth (H.2). That reconciliation is INFER pending spike S-B1.

Switching later is possible: `teams app bot migrate` keeps the client id, secret, tenant and manifest bot id.

**Evidence:**
- https://github.com/microsoft/teams-sdk/blob/main/teams.md/docs/cli/concepts/bot-locations.md (2026-10-08; DOC).
- https://github.com/microsoft/teams-sdk/blob/main/teams.md/docs/cli/commands/app/bot-migrate.md (2026-10-08; DOC).
- https://github.com/microsoft/teams-sdk/blob/main/teams.md/docs/cli/concepts/tdp-portal.md (2026-10-08; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/authentication/add-authentication (ms.date 2026-04-14 PRE-GA, updated 2026-06-30, still applies; DOC).

**Confidence:** high that Teams-managed lacks only OAuth/SSO. Medium (INFER) that proactive sends, card actions and RSC work there.

**Implication for docs/80:** §15 **change**: Teams-managed is enough for Phase 1 except identity linking. §13/§16 **new dependency**: GitHub linking via Bot Service OAuth forces one Azure Bot (subscription) on the bot that runs sign-in. Make that Factory only. Spike S-B1.

### B.2 Entra tenancy and credential types; what works off-Azure
**Answer:**

*Tenancy.* Multi-tenant Azure Bot creation "will be deprecated after July 31, 2025". New bots must be single-tenant or user-assigned MI. There is a nuance in the Teams CLI/TDP path: it creates the Entra app as `AzureADMultipleOrgs` but registers the bot with `isSingleTenant: true`, and setting `AzureADMyOrg` "causes service principal creation to fail silently". The SDK treats a missing `TENANT_ID` as multi-tenant, so **always set `tenant_id`**.

*Credential classes in the SDK:*

| Class | What it is | Works self-hosted? |
|---|---|---|
| `ClientCredentials` | client secret via MSAL | yes |
| `TokenCredentials` | any callable returning a token | yes (this is where a certificate or a non-Azure federated credential must be built, INFER) |
| `ManagedIdentityCredentials` | user-assigned MI | no |
| `FederatedIdentityCredentials` | MI → FIC exchange | no |

There is **no built-in certificate credential**. MI and FIC need an Azure compute resource: "The identity you select here must also be assigned to the compute resource".

**Evidence:**
- https://learn.microsoft.com/en-us/azure/bot-service/bot-service-quickstart-registration (ms.date 2024-10-09 **PRE-GA**, updated 2026-09-01; DOC). It still applies, since the Teams SDK uses the same Bot Connector issuer and its 2026-10-08 docs also prescribe single-tenant. Its claim that single-tenant/UAMI are "not supported in … Dev Tunnels" conflicts with current Teams SDK docs and is treated as stale (INFER).
- https://github.com/microsoft/teams-sdk/blob/main/teams.md/docs/cli/concepts/aad-apps.md (2026-10-08; DOC).
- https://github.com/microsoft/teams-sdk/blob/main/teams.md/docs/main/teams/app-authentication/federated-identity-credentials.md (2026-10-08; DOC).
- https://github.com/microsoft/teams-sdk/blob/main/teams.md/docs/main/teams/app-authentication/README.mdx (2026-10-08; DOC).
- `packages/api/src/microsoft_teams/api/auth/credentials.py` (2026-08-03; CODE).
- `app.py::_init_credentials` (CODE).

**Confidence:** high on the deprecation and the classes. Medium on the certificate-via-`TokenCredentials` route, for which no sample exists.

**Implication for docs/80:** §15 **change**. Each role gets a single-tenant registration with a client secret, stored as a compose secret. The `TEAMS_BOT_<ROLE>_CERT_PATH` option needs a custom MSAL-based `TokenCredentials` provider (spike). **New risk:** rotating six secrets.

### B.3 Messaging endpoint requirements
**Answer:**

- **Endpoint.** It must be public HTTPS ("reachable on the public internet over HTTPS") with a publicly trusted server certificate. Client certificates are not used. The SDK registers only `POST <messaging_endpoint>` (default `/api/messages`).
- **IP allow-listing is not the documented control; JWT validation is.** The `AzureBotService` service tag exists, but no doc says Teams-managed traffic comes from those ranges, so an allow-list could break delivery.
- **Socket Mode** (dial-out) removes the ingress, but only on the Canary/Pilot1 rings: "the production default returns 503".

**Evidence:**
- https://github.com/microsoft/teams-sdk/blob/main/teams.md/docs/main/developer-tools/local-tunnels.md (2026-10-08; DOC).
- https://learn.microsoft.com/en-us/azure/bot-service/rest-api/bot-framework-rest-connector-authentication (ms.date 2024-10-09 **PRE-GA**, updated 2026-09-01; still the governing scheme the SDK implements; DOC).
- https://learn.microsoft.com/en-us/azure/virtual-network/service-tags-overview (ms.date 2026-09-16; DOC).
- `http/http_server.py` (2026-08-03; CODE).
- `examples/socket/README.md` (2026-10-07; DOC/CODE).

**Confidence:** high on HTTPS and reachability. Low on IP ranges.

**Implication for docs/80:** §15 **confirm**. Expose one POST path per bot through the reverse proxy with a public certificate, and no IP allow-list. Add Socket Mode to the §16 watch list.

### B.4 Local development loop
**Answer:** There are three loops.

1. **M365 Agents Playground.** Needs no Azure, no tenant and no credentials. Run `npm i -g @microsoft/m365agentsplayground`, then `agentsplayground -e http://localhost:3978/api/messages -c msteams`. It sends unauthenticated requests, which the SDK **rejects** unless `App(dangerously_allow_unauthenticated_requests=True)` is set. A 2026-06-04 blog claiming otherwise is contradicted by current docs and code (`401 "Authentication not configured"`).
2. **Real Teams client.** Needs a tenant with custom upload, a Teams-managed registration (`teams app create --endpoint https://<tunnel>/api/messages`) and a Dev Tunnel (`devtunnel create --allow-anonymous`, `port create -p 3978`, `host`).
3. **Socket Mode.** Canary rings only.

Teams SDK DevTools is **gone from Python**. Agents Toolkit support for Teams SDK Python projects was not confirmed. The **minimal no-Azure loop is 1, or 2 when the real client is needed.**

**Evidence:**
- https://github.com/microsoft/teams-sdk/blob/main/teams.md/docs/main/developer-tools/agents-playground/README.md (2026-10-08; DOC).
- The 2026-06-04 blog (DOC, partly stale).
- https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/test-with-toolkit-project (ms.date 2026-07-24; DOC).
- local-tunnels.md (2026-10-08; DOC).
- `http/http_server.py` (CODE).

**Confidence:** high.

**Implication for docs/80:** §15/§16 **change**. The dev loop is Playground plus the unauthenticated flag. Guard the flag so the process refuses to start if it is set while `ENV=prod`. Real-client tests use a Dev Tunnel per developer, which confirms §15's "Dev Tunnel replaces smee for Teams".

### B.5 Self-hosting with no Azure compute
**Answer:** **Yes.** The SDK is a plain Python HTTP handler. It calls `smba.trafficmanager.net/teams` and fetches keys from `login.botframework.com`.

Still mandatory:
1. One **Entra app registration** per bot (an identity object, not a subscription resource).
2. One **bot registration** per bot: Teams-managed (no subscription) or an Azure Bot. The Azure Bot is needed only for OAuth or SSO.
3. One **public HTTPS endpoint** per bot route.
4. **Egress** to `login.microsoftonline.com`, `login.botframework.com` and the activity's `serviceUrl`, plus Graph if used.

Credentials are a secret or a custom `TokenCredentials`.

**Evidence:**
- aad-apps.md and bot-locations.md (2026-10-08; DOC).
- `app.py` default `service_url`; `cloud_environment.py` `PUBLIC` (CODE).

**Confidence:** high that no compute is needed. Medium that Teams-managed is production-grade: the docs say so, but give no SLA.

**Implication for docs/80:** §15 **change**. Footprint: 6 Entra apps + 6 bot registrations, of which 5 are Teams-managed and Factory's is an Azure Bot (for OAuth). Alternatively all 6 start Teams-managed and Factory is migrated later with `teams app bot migrate`. The bot-registration part rests on the B.1 inference, which needs spike S-B1.

### B.6 Mounting `App` inside an existing aiohttp app
**Answer:** **Yes, through `App(http_server_adapter=…)`.**

- The adapter is any object with `register_route(method, path, handler)`. `serve_static`, `start` and `stop` are optional.
- `await app.initialize()` registers `POST messaging_endpoint → HttpServer.handle_request`. That handler does JWT validation and dispatch on a framework-neutral `{body, headers} → {status, body}`.
- The non-managed lifecycle ("initialize() + start server yourself") is officially supported, and `examples/http-adapters/src/starlette_adapter.py` is the template.
- No aiohttp adapter ships in the box. One is about 25 lines (see §4.2 item 1).

Caveats:
- FastAPI and uvicorn are **hard dependencies**, imported at module load.
- `HttpMethod = Literal["POST"]`.
- aiohttp freezes its router at `AppRunner.setup()`, so call `initialize()` first (INFER).
- Each App needs a distinct `messaging_endpoint`.

**Evidence:**
- `packages/apps/src/microsoft_teams/apps/http/adapter.py` (≤2026-06-15; CODE).
- `http/http_server.py` (2026-08-03; CODE).
- `app.py` around L126-129: `adapter = self._socket_mode or self.options.http_server_adapter or FastAPIAdapter()` (2026-09-29; CODE).
- `examples/http-adapters/README.md` and `starlette_adapter.py` (CODE).
- `packages/apps/pyproject.toml` (2026-09-24; CODE).

**Confidence:** high on the mechanism. Medium on our adapter, which has not been run.

**Implication for docs/80:** §7.1/§7.2 **confirm**: the Teams adapter lives inside `webhook_bridge`'s aiohttp process, with no second server. §15 should note the FastAPI/uvicorn transitive dependencies.

### C.1 Mention-only delivery and RSC `ChannelMessage.Read.Group`
**Answer:**

- **Default.** A bot gets a channel message **only when it is @mentioned**. It gets nothing for team or channel mentions, nor for replies to its own posts that don't mention it.
- **With RSC.** The application RSC permission `ChannelMessage.Read.Group` delivers **all** messages in every channel of each team where the app is installed.
- **Consent.** The app must be installed or upgraded in the team, and the team owner consents at install. Tenant-wide control sits with the Entra admin center RSC settings.
- **Graph too.** RSC also governs what the bot can read via Graph.
- **Which events.** No current doc says whether RSC also adds edit, delete or reaction events for unmentioned messages.
- **Private channels.** Agents cannot post messages or cards in private-channel conversations.
- **Shared channels.** "Bots, connectors, and message extensions aren't supported" in shared channels. So the workspace must be a **standard channel**. This is a side finding of the E/J researcher, sourced from https://learn.microsoft.com/en-us/microsoftteams/limits-specifications-teams (ms.date 2026-07-16, updated 2026-10-07; DOC, high confidence).
- **Consent conflict.** The RSC page says "Only resource owners can grant application RSC permissions", while its own SDK table says "a team owner or member".

**Evidence:**
- https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/conversations/channel-and-group-conversations (ms.date 2026-06-23, updated 2026-09-28; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/platform/agents-in-teams/enable-receive-all-chat-messages (2026-09-28; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/platform/graph-api/rsc/resource-specific-consent (ms.date 2025-02-20 **PRE-GA**, updated 2026-05-29, still applies; DOC). Manifest must be ≥1.6.

**Confidence:** high for delivery rules. Low for which non-message events RSC adds.

**Implication for docs/80:** §6.3/§7.3 **confirm**. Give RSC to **Factory only**, which feeds the thread log in C.2. Role bots stay mention-only, so routing comes from Teams' own mention delivery and there is one consent prompt instead of six. Any RSC bot must guard every handler with `is_recipient_mentioned()`. §15 **change**: the workspace must be a standard channel (no shared channels, since they don't support bots; no private channels, since agents can't post there).

### C.2 Thread history for agent context
**Answer:**

- **The activity stream carries no history.** The SDK `ConversationClient` has no list-messages call.
- **History comes from Graph**: `GET /teams/{id}/channels/{id}/messages/{id}/replies`, plus the root message.
  - Least-privileged application permission: RSC `ChannelMessage.Read.Group`.
  - Broader options: `ChannelMessage.Read.All`, `Group.Read.All` or `Group.ReadWrite.All`. Delegated: `ChannelMessage.Read.All`.
  - Paging: `$top` ≤ 50.
- **Not metered** since 2025-08-25.
- **Protected-API status is unconfirmed.** The "protected APIs in Teams" page returned 404 on 2026-10-09.
- **Alternative (INFER, recommended).** Factory holds RSC, receives every human message in real time, and the bridge persists a transcript keyed by `TeamsThreadId`.
  - It misses messages from before install and during downtime. Graph remains the backfill.
  - Bot posts are logged at send time.

**Evidence:**
- https://learn.microsoft.com/en-us/graph/api/chatmessage-list-replies?view=graph-rest-1.0 (ms.date 2024-04-04 **PRE-GA**, updated 2025-07-23; Graph REST unchanged, still applies; DOC).
- enable-receive-all-chat-messages (2026-09-28; DOC).
- https://learn.microsoft.com/en-us/graph/metered-api-list (ms.date 2025-08-06 **PRE-GA**, updated 2026-04-03, still applies; DOC).
- `api/clients/conversation/client.py` and `ActivityContext.app_graph` (CODE).

**Confidence:** high for the endpoint, permissions and metering. Low for protected-API status.

**Implication for docs/80:** §7.3 "Context" **change**: use our own RSC-fed thread log as the primary source and Graph `/replies` as backfill. **New risk:** Graph protected-API status is unknown, and only matters if we rely on Graph.

### C.3 Conversation-id format and replying into a thread
**Answer:**

- **Base channel id:** `19:<hex>@thread.tacv2` (older examples show `@thread.skype`).
- **Inside a thread:** `19:…@thread.tacv2;messageid=<root message id>`. The root id is numeric.
- **Reactive reply.** In a handler, `ctx.send(x)` posts into the current thread with no quote, and `ctx.reply(x)` posts with a quote.
- **Proactive reply.** Use `app.reply(conversation_id, root_message_id, x)`, or `to_threaded_conversation_id(...)` followed by `app.send(...)`.
- **Helper rules.** The helper strips any `;…` suffix and **rejects** non-numeric or `"0"` ids. A root post's own id is its message id.

**Evidence:**
- channel-and-group-conversations (2026-06-23; DOC): sample `"19:…@thread.skype;messageid=1481567603816"`.
- https://learn.microsoft.com/en-us/microsoftteams/platform/teams-sdk/essentials/sending-messages/proactive-messaging (2026-07-27; DOC): "use `app.reply()` with the conversation ID and thread root message ID".
- `packages/apps/src/microsoft_teams/apps/utils/thread.py` L7-27, added in commit `8e0cdfa` (2026-04-20) (CODE).
- `app.py` L353-391 and L443-480 (CODE).
- `routing/activity_context.py` L241-301 (CODE).

**Confidence:** high.

**Implication for docs/80:** §10 **confirm** `TeamsThreadId` as the full threaded id, also storing `(channel_conversation_id, root_message_id)` separately. Its per-bot validity is D.4's risk.

### C.4 Channels: streaming, typing, AI label, citations, feedback
**Answer:**

| Feature | In channels? |
|---|---|
| Streaming | **No.** 1:1 chats only. The SDK has no scope guard, so expect `403 ContentStreamNotAllowed` (INFER). |
| Typing indicator | **Unconfirmed.** It exists in SDK code only. |
| AI-generated label | **Yes** |
| Citations | **Yes.** At most 20 per message. Citations that use Adaptive Cards are in public developer preview. |
| Feedback 👍/👎 | **Yes** |

**Evidence:**
- https://learn.microsoft.com/en-us/microsoftteams/platform/bots/streaming-ux (ms.date 2026-08-24; DOC): "supported only in one-on-one chats".
- https://learn.microsoft.com/en-us/microsoftteams/platform/teams-sdk/essentials/sending-messages/overview (2026-07-27; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/platform/agents-in-teams/integrate-ai/ai-content-labels (2026-09-27; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/platform/agents-in-teams/integrate-ai/user-feedback-controls (2026-09-26; DOC).
- `http_stream.py` and `examples/interacting-with-messages/src/main.py` L31 (CODE).

**Confidence:** high, except low for typing.

**Implication for docs/80:** §6.4/§14 **confirm** "no progress chatter", now for a platform reason too. Presentations add `add_ai_generated()`, `add_feedback()` and `add_citation()`, with the git artifact as the citation. Don't design around typing indicators.

### C.5 Mention handling
**Answer:** The Python SDK does **not** strip mentions automatically and has **no mention route**. The Learn page claims a "dedicated `mention` activity route", but none exists in Python 2.1.0, so that route is probably TS/C#-only.

- `ctx.activity.strip_mentions_text()` with no options removes **every** mention, then trims.
- `StripMentionsTextOptions(account_id=ctx.activity.recipient.id)` strips only our own mention. `tag_only=True` keeps the names and drops the tags.
- `is_recipient_mentioned()` tests whether we were addressed.
- Every mention appears twice: as `<at>Name</at>` in `text`, and as an entity `{"type":"mention","mentioned":{"id","name"},"text"}`. Tag mentions add `"type":"tag"`.
- Users are `29:` ids and bots are `28:<appId>`.
- Don't parse identity from the text: "the person sending the message [can] alter it".

**Evidence:**
- channel-and-group-conversations (2026-06-23; DOC).
- `packages/api/src/microsoft_teams/api/activities/utils/strip_mentions_text.py` (CODE).
- `activities/message/message.py` L88/L105/L124 (CODE).
- `grep -rni mention packages/apps/src/microsoft_teams/apps/routing/` finds nothing (CODE).
- https://learn.microsoft.com/en-us/microsoftteams/platform/bots/build-conversational-capability (2026-09-28; DOC): `28:` example.

**Confidence:** high.

**Implication for docs/80:** §6.3/§7.3 **change (detail)**. Strip only the bot's own mention, so "@Architect ask @PE about X" keeps the lead mention, and resolve other mentions from `entities`.

### D.1 What to persist for a proactive send, and validity
**Answer:** Persist these **scalars**. No conversation-reference blob is needed, because `App.send` builds the reference from the id, the `service_url` and its own bot id.

| Field | Source | Needed for |
|---|---|---|
| threaded conversation id (or base channel id + root id) | `ctx.conversation_ref.conversation.id` | every send |
| `service_url` | inbound `activity.service_url` | strongly recommended; otherwise `SERVICE_URL` env or the global default is used |
| tenant id | `channelData.tenant.id` / `conversation.tenantId` | creating conversations; single-tenant token |
| team id, channel id | `channelData.team.id` / `.channel.id` | Graph and new root posts |
| activity id of each posted card | `SentActivity.id` | in-place updates |
| bot id | config (`28:<appId>` inbound) | — |

**Validity.** No TTL is documented for the conversation id ("create the conversation only once, and store the resulting conversationId") or for `serviceUrl` (gap). Sends can fail at any time with 403 `BotDisabledByAdmin` or `MessageWritesBlocked`.

**Evidence:**
- https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/conversations/send-proactive-messages (ms.date 2026-06-30, updated 2026-09-25; DOC): "For `serviceUrl`, use the value from an incoming activity … Avoid hardcoding".
- The Teams SDK proactive-messaging page (2026-07-27; DOC).
- `app.py` L117-119 and L353-391 (CODE).
- `app_process.py` L121-130 (CODE).
- `activity_send.py` L31-37 (CODE).
- build-conversational-capability (2026-09-28; DOC): `channelData.tenant.id` "passed in all contexts", but `channelData` is absent in personal chats.

**Confidence:** high for the field list. Low for validity periods, which are undocumented.

**Implication for docs/80:** §7.5 and §10 item 4 **change**. Store scalars rather than "conversation reference", refresh `service_url` on every inbound activity, and map 403s to non-retryable errors and 429s to retryable ones. The row schema is in §4.2.

### D.2 Install prerequisites for proactive channel posts
**Answer:**

- **Each posting bot's app must be installed in the team.** The install event (`@app.on_install_add`) carries the conversation id to store.
- Proactive installs (Graph or policy) work only for apps in the org catalog or Store.
- **RSC is not needed to post.** `ChannelMessage.Send.Group` is for Graph sends.
- Agents cannot post in private channels.

**Evidence:**
- send-proactive-messages (2026-06-30; DOC): "Ensure that the agent is installed in the team before you can send a proactive message to a channel".
- channel-and-group-conversations (2026-06-23; DOC).

**Confidence:** high.

**Implication for docs/80:** §7.5/§15 **confirm**. All six apps are installed in each linked team. Use Factory's install event, plus `@Factory link`, as the moment to capture `service_url`, tenant and ids.

### D.3 Minimal Python proactive call
**Answer:**

1. Build `App(client_id=…, client_secret=…, tenant_id=…)`.
2. `await app.initialize()`. This starts no server.
3. Send:
   - `await app.send(conversation_id, text_or_card, service_url=…)`; or
   - `await app.reply(channel_conversation_id, root_message_id, x, service_url=…)`.

   Both return `SentActivity` with `.id`.
4. Update later with `app.api.conversations.update_activity(conversation_id, activity_id, MessageActivityInput(...))`.

**Caveat (INFER):** direct `app.api.*` calls use the App-level service URL, not a per-call one. Either construct the worker-side `App` with the stored `service_url`, or route the update through `app.send` with an activity whose `id` is set. The exact `id` field of `MessageActivityInput` was not verified.

**Evidence:**
- Teams SDK proactive-messaging (2026-07-27; DOC).
- `examples/proactive-messaging/src/main.py`: "Uses app.initialize() instead of app.start() (no HTTP server)" (CODE).
- `app.py` L250/L353/L443 (CODE).
- `options.py` L63-81 (CODE).

**Confidence:** high for send, reply and initialize. Medium for the update service-URL caveat.

**Implication for docs/80:** §7.5 **confirm** that `notify_activity(event)` needs no inbound request. One `App` per bot identity lives on the worker host. Code is in §4.2 item 4.

### D.4 Proactive send creating a new thread root
**Answer:** **Yes, per the docs.** Proactive messaging can create "a new conversation thread in a channel" (but not a new channel or group chat).

- In Python the typed path is `app.send(<base channel id without ;messageid=>, activity)`. The returned id is the new root, so the thread id is `f"{channel_id};messageid={sent.id}"`. This is INFER from the docstring; the explicit raw `POST /v3/conversations` with `isGroup` is documented only in the **archived** v3 page.
- Python `CreateConversationParams` has no `is_group` or `bot` field (CODE).

**Unresolved conflict.** The same page says "The conversation ID is unique for each agent within a specific channel" and "The `channelId` is global". The observed threaded format is built from global ids, which suggests it is shared across bots (INFER). If ids are per bot, docs/80's single shared `TeamsThreadId` breaks for Architect replying into Factory's thread.

**Evidence:**
- send-proactive-messages (2026-06-30; DOC).
- https://learn.microsoft.com/en-us/previous-versions/microsoftteams/platform/resources/bot-v3/bot-conversations/bots-conv-proactive (ms.date 2023-04-02, **PRE-GA and ARCHIVED**; low weight; DOC).
- `app.py` L362-365 docstring (CODE).
- `api/clients/conversation/params.py` (CODE).

**Confidence:** medium.

**Implication for docs/80:** §6.1/§10 **new risk, changes design if it fails.** Factory creates the root (the board) with `app.send(channel_id, card)`. Run **spike S-D4**. Until it passes, key persisted rows by `(teams_thread_id, bot_app_id)`.

### E.1 Adaptive Card schema version and mobile
**Answer:**

- **Teams supports up to v1.6**, mobile included. Universal Actions need **≥1.5**. The SDK default is `"1.5"`.
- **Teams-wide restrictions:** no positive/destructive action styling, no file or image uploads, and no `isEnabled` on `Action.Submit`.
- **There is no published per-element "unsupported on mobile" list.** Documented: People Picker and Typeahead work on mobile; manual refresh on mobile is a long-press; test full-width cards at narrow widths.
- E.1's recommended element set (TextBlock, FactSet, ColumnSet, Container, Image, ActionSet, `Action.Execute`, `Action.OpenUrl`) **does not include `Table`**, which the §14.1 board JSON uses. No note confirms `Table` on Teams mobile (unconfirmed, not known to fail).

**Evidence:**
- https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/cards/cards-reference (ms.date 2024-09-16 **PRE-GA**, updated 2026-08-19; page self-labelled "legacy", 1.6 statements re-published and still apply; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/cards/universal-actions-for-adaptive-cards/work-with-universal-actions-for-adaptive-cards (ms.date 2022-12-20 **PRE-GA**, updated 2026-07-27, still applies; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/what-are-cards (ms.date 2023-01-08 **PRE-GA**, updated 2026-06-30, still applies; DOC).
- `packages/cards/src/microsoft_teams/cards/core.py` `AdaptiveCard.version = "1.5"` (CODE).
- The adaptivecards.microsoft.com host matrix could not be fetched (gap).

**Confidence:** high for 1.6 and 1.5. Low for a mobile element list.

**Implication for docs/80:** §14 **confirm** 1.5. **New risk (detail):** test the board at mobile width and verify `Table` there, or fall back to ColumnSet.

### E.2 `Action.Execute` vs `Action.Submit`; user-specific views in channels
**Answer:**

*How the SDK surfaces `Action.Execute`.* It arrives as invoke `adaptiveCard/action`, i.e. `AdaptiveCardInvokeActivity`.
- `@app.on_card_action` catches all of them.
- `@app.on_card_action_execute("<key>")` routes on **`value.action.data["action"]`, not on `verb`** (CODE). Learn's Universal Actions pages route on `verb`, so this is a trap.

*What the handler returns.* `AdaptiveCardInvokeResponse`:

| Response | Status | Effect |
|---|---|---|
| `AdaptiveCardActionCardResponse(value=card)` | 200 | replaces the card **for the acting user** |
| `AdaptiveCardActionMessageResponse(value=str)` | 200 | transient message |
| `AdaptiveCardActionErrorResponse` | 400/500 | error |
| Login / IncorrectAuthCode / PreconditionFailed | 401/401/412 | auth flows |

A non-`InvokeResponse` return is wrapped as 200.

*`Action.Submit`.* It is "Legacy. Prefer `Action.Execute`". The SDK docstring says it does not trigger `AdaptiveCardInvokeActivity`. The only description of its delivery shape (a message activity with `value`) is PRE-GA and self-contradictory.

*User-specific views and `refresh.userIds`.* They **work in chats and channels**.
- At most **60** user MRIs (`29:…`) can be listed.
- `[]` disables auto-refresh.
- Omitting `userIds` auto-refreshes for all users only when there are ≤60 members.
- Each auto-refresh is one invoke per listed user.

*Making an outcome visible to everyone (INFER).* Return the card response **and** edit the message (E.3).

**Evidence:**
- `packages/apps/src/microsoft_teams/apps/routing/activity_handlers.py` `on_card_action_execute` (2026-04-01, in v2.1.0; CODE).
- `routing/activity_route_configs.py:607` (CODE).
- `api/models/adaptive_card/adaptive_card_action_response.py` (CODE).
- `app_process.py` (CODE).
- `examples/cards/src/main.py:347-430` (CODE).
- https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/cards/cards-actions (ms.date 2026-06-10, updated 2026-08-03; DOC).
- https://microsoft.github.io/teams-sdk/python/in-depth-guides/adaptive-cards/executing-actions (accessed 2026-10-09; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/cards/universal-actions-for-adaptive-cards/user-specific-views (ms.date 2026-10-01; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/cards/universal-actions-for-adaptive-cards/overview (ms.date 2026-09-30; DOC).
- msteams-docs `cards-actions.md` @ `7e4ea66` (ms.date 2024-11-07 **PRE-GA**, partly applicable; DOC).

**Confidence:** high for Execute handling, return types and the 60-user cap. Medium for `Action.Submit` delivery.

**Implication for docs/80:** §12/§14 **change**:
- Use `Action.Execute` only.
- Every action's `data` carries `action` (the routing key), plus `gate`, `attempt` and `thread`. Keep `verb` for readability only.
- §14.1 `board.refresh` and §14.3 `gate.decide` must gain `data.action`.
- A lead-only user-specific Approve/Reject view is feasible (2 ≪ 60), but each refresh must be answered within the invoke timeout (J.3).

### E.3 Updating a posted card in place
**Answer:**

- **API.** `PUT {serviceUrl}/v3/conversations/{conversationId}/activities/{activityId}`. "Cache the activity ID returned by the original post call."
- **Python 2.1.0.** `app.api.conversations.update_activity(conversation_id, activity_id, MessageActivityInput().add_card(card))`. The Learn sample's `conversations.activities(id).update(...)` is **`@deprecated`** in 2.1.0.
- **Permissions.** No Graph or RSC; the bot's own Connector token is enough.
- **Who may update.**
  - DOC: a bot "can't update or delete messages sent by the user".
  - That *only the posting bot* can update its own message is INFER.
- **Rate limits.** There is no separate update limit; updates share the send budget (J.1/K.4).
- **Proactive context: works.** The `examples/proactive-messaging` sample does exactly `initialize → send → update_activity`.
- **Message-splitting trap.** Text plus an attachment in one activity is split, "and you do not receive the message ID", so the card becomes un-updatable. Send cards as attachment-only activities.
- **Refresh trigger.** A bot edit triggers auto-refresh for each user in `refresh.userIds`.
- **Which conversation id to update the root card with (INFER).** Use the conversation id the card was *posted to*, as the SDK example does. The notes disagree: one snippet uses the threaded id, another the posted-to id.

**Evidence:**
- https://learn.microsoft.com/en-us/microsoftteams/platform/bots/build-conversational-capability#update-and-delete-messages-sent-from-bot (ms.date 2026-09-28; DOC).
- send-proactive-messages (2026-06-30; DOC).
- `packages/api/src/microsoft_teams/api/clients/conversation/client.py` (`@deprecated activities()`, `update_activity()` L299) (CODE).
- `clients/conversation/activity.py:105` (CODE).
- `examples/proactive-messaging/src/main.py:78-98` (2026-07-10; CODE).
- https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/cards/universal-actions-for-adaptive-cards/up-to-date-views (ms.date 2026-09-16; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/rate-limit (ms.date 2025-02-06 **PRE-GA**, updated 2026-07-27, still applies; DOC).

**Confidence:** high for the API, proactive update and splitting. Medium for "only the posting bot".

**Implication for docs/80:** §6.1/§7.5/§14.1/§12.3 **confirm** the live board and "resolved by X via GitHub".

- **Change:** Factory is the sole board editor. Persist `(conversation_id, activity_id, service_url)` per card.
- **Change:** updates are debounced and coalesced, one PUT per board state change.
- **Unresolved (§14.4):** whether an invoke on a Designer-posted card reaches Factory, and whether Factory can edit it. Keep the "Factory posts gate buttons as a reply" fallback (spike S-E3x).

### E.4 Images in cards
**Answer:**

- **Formats and size.** PNG/JPEG/GIF only; **no SVG, no animated GIF**; at most **1024×1024**. Picture attachments may be up to 1 MB. The size rules come from a legacy page written for rich cards and are treated as the safe envelope.
- **Hosting.** Use a public HTTPS URL, ideally a CDN. **Redirects are not supported.**
- **Data URIs.** The schema allows them from 1.2. The Teams size note excludes base64 images from the 100 KB limit, implying they are accepted. GCC High/DoD *require* base64. No data-URI size cap is documented.
- **Auth on image URLs: undocumented.** Every source says "publicly available", so a token-gated or sign-in-redirecting URL will very likely fail (INFER).

**Evidence:**
- cards-reference (ms.date 2024-09-16 **PRE-GA**, updated 2026-08-19, still applies; DOC): "Animated GIF and SVG formats aren't supported", "the redirect in image URL is not supported".
- build-conversational-capability (2026-09-28; DOC).
- https://adaptivecards.io/schemas/adaptive-card.json `Image.url`: "Supports data URI in version 1.2+" (accessed 2026-10-09; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/limits-specifications-teams (ms.date 2026-07-16, updated 2026-10-07; DOC).

**Confidence:** high for formats, size and redirects. Medium for data URIs in Teams. Low for image auth.

**Implication for docs/80:** §9.1/§14.3 **change**. Rasterize diagrams to PNG at ≤1024 px. The gate card's `Image.url` cannot point at the SSO-protected artifact service. Use an unguessable, unauthenticated, no-redirect URL, or inline a small `data:image/png;base64` thumbnail. Full fidelity lives in the tab.

### E.5 Size limits and the 60,000-character plan
**Answer:**

- **Limits.** ~**100 KB per bot message**, counting text, image links, mentions and reactions **encoded as UTF-16**, and excluding base64 images. Keep messages "within 80 KB". Over the limit returns **413 `MessageSizeTooBig`**. Channel posts and chat share this limit; the 24 KB figure is for email-to-channel. The "~28 KB" folklore figure appears in no current primary source.
- **Arithmetic (INFER).** 60,000 chars ≥ 120 KB in UTF-16, so it can **never** fit. The 80 KB budget is at most ~40,000 characters before JSON overhead.
- **Options:**
  1. **Summary card plus a deep link to the tab** (recommended).
  2. A file in the channel via Graph only. The SDK file-consent flow is personal-scope only, and this copies git into SharePoint.
  3. Splitting into N messages, which floods the thread and the rate budget. Not recommended.

**Evidence:**
- build-conversational-capability "Message size limits" (ms.date 2026-09-28; DOC).
- limits-specifications-teams (ms.date 2026-07-16; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/bots-filesv4 (ms.date 2026-08-19; DOC).

**Confidence:** high.

**Implication for docs/80:** §14.7 **confirm** the policy (no artifact body, 600-char excerpt). **Change:** add a hard serialized-size check, `len(json.dumps(activity).encode("utf-16-le")) < 80_000`, with the §14.7 degrade order. §8: the full plan view lives in the tab.

### E.6 Deep link from a card button into a channel tab sub-entity
**Answer:**

- **Format:** `https://teams.microsoft.com/l/entity/<appId>/<entityId>?tenantId=…&webUrl=<enc>&label=<enc>&context=<enc JSON {"subEntityId":"…","channelId":"19:…"}>&openInMeeting=false`.
- **The parts:**
  - `appId` is the manifest id (or the org-catalog id once published).
  - `subEntityId` surfaces as `page.subPageId`.
  - `webUrl` is the fallback.
  - Everything must be URI-encoded. Encoded deep links don't work in Outlook.
- **Desktop/web.** In an **`Action.OpenUrl`** the link opens the tab in place. In a TextBlock it opens a new browser tab on Chrome/Linux desktop.
- **Store collision.** A Store app with the same id wins.
- **Mobile.** Deep links work "after your app is approved for the Teams mobile client", and iOS needs an App Store Connect Team ID. Both statements are Store-oriented. `shareDeepLink` doesn't work on mobile.
- **Gap (see F.7).** The page says `channelId` is "only in configurable tabs with a scope of team", which predates static channel tabs.

**Evidence:** https://learn.microsoft.com/en-us/microsoftteams/platform/concepts/build-and-test/deep-link-application (ms.date 2026-06-23, updated 2026-07-29; DOC).

**Confidence:** high for format and desktop. Low for mobile and for static-tab channel targeting.

**Implication for docs/80:** §8.2/§14 **confirm** the design, pending **spike S-F7**.
- Persist app id, tab `entityId` and channel id.
- Always use `Action.OpenUrl` with a `webUrl` fallback.
- Fallback if S-F7 fails: Stageview via `tab/tabInfoAction`, or `websiteUrl`.

### F.1 Configurable vs static channel tabs
**Answer:** **Static tabs are now the only option for new pins in channels.**

- Since manifest v1.16, `staticTabs` accepts `scopes:["team",…]` and `context:["channelTab",…]`, with no config dialog. `setConfig` can still change `contentUrl` after pinning.
- `configurableTabs` remains for backward compatibility of already-pinned tabs. If both are declared, "Teams pins the static tab by default". The migration guide says "you can only pin static tabs from now".
- "Only the first tab listed in the manifest appears" in channel scope, and "you can pin only one tab per app".
- `websiteUrl` is the browser fallback.

**Evidence:**
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/how-to/create-channel-group-tab (ms.date 2025-02-06 **PRE-GA**, updated 2026-04-01, still applies; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/what-are-tabs (ms.date 2026-08-27, updated 2026-09-08; DOC).

**Confidence:** high.

**Implication for docs/80:** §8.2 **confirm** one tab with in-app views (Spec, Architecture, Mock, Plan, Board, Review) behind a router. §7.4/§15 **change**:
- Use `staticTabs` (manifest ≥1.16).
- The channel↔repo link cannot come from a config page. Derive it server-side from the channel id, validated against the SSO token's tenant, or set it via `setConfig` on first open.
- The tab lives in exactly one app; Factory is the natural owner (INFER).

### F.2 Tab SSO end to end
**Answer:**

*Flow.* `app.initialize()` → `authentication.getAuthToken()`, which returns an Entra **access token for our own API**, cached by Teams → the tab sends it as a `Bearer` header. **No OBO exchange is needed for our own API.** OBO is needed only for Graph or downstream APIs, because `getAuthToken()` covers only `openid`, `email`, `profile` and `offline_access`.

*Entra setup:*
- Single-tenant, no redirect URI.
- `requestedAccessTokenVersion: 2`.
- Application ID URI `api://<fqdn>/<clientId>`, with a lowercase fqdn (uppercase breaks Android). If a bot shares the app: `api://<fqdn>/botid-<clientId>`.
- Scope `access_as_user`.
- Pre-authorize Teams desktop/mobile `1fec8e78-bce4-4aaf-ab1b-5451cc387264` and Teams web `5e3ce6c0-2b1f-4285-8d4b-75ee78787346`, plus the M365/Outlook clients if those hosts are used.

*Manifest (≥1.5).* `"webApplicationInfo": {"id": "<clientId>", "resource": "api://<fqdn>/<clientId>"}`, with the same fqdn in `contentUrl` and `validDomains`.

*What our API validates:*
- the signature against Entra JWKS;
- `aud` = **client-id GUID** (the doc sample shows a GUID; also accept the `api://` form defensively, INFER);
- `iss` = `https://login.microsoftonline.com/<tid>/v2.0`, with `tid` = ours;
- `scp` ∋ `access_as_user`;
- `exp` and `nbf`;
- identity from `oid` + `tid`.

Never trust `getContext()` data as identity.

*Limits:*
- "Multiple domains per app aren't supported".
- No SAML. No redirect login inside the iframe. Fails for anonymous users.
- Mobile minimums: Android 1416/1.0.0.2020073101+, iOS 2.0.18+.

**Evidence:**
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/how-to/authentication/tab-sso-overview (ms.date 2023-01-17 **PRE-GA**, updated 2026-07-22, still applies; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/how-to/authentication/tab-sso-register-aad (ms.date 2023-02-01 **PRE-GA**, updated 2026-04-01, still applies; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/how-to/authentication/tab-sso-code (ms.date 2026-03-16 **PRE-GA**, updated 2026-07-13, still applies; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/how-to/authentication/tab-sso-manifest (ms.date 2022-11-21 **PRE-GA**, updated 2026-04-01, still applies; DOC).
- https://learn.microsoft.com/en-us/microsoft-365/extensibility/schema/root (updated 2026-10-01; DOC).
- `TokenValidator.for_entra` (CODE, A.3).

**Confidence:** high for the flow and setup. Medium-high for aud = GUID.

**Implication for docs/80:** §7.4 **change**: replace "SSO-exchanged token" with "`getAuthToken()` access token, validated as above". OBO only if the artifact service later needs Graph (H.3). §15 **new constraints**:
- One Entra app ↔ one tab fqdn. `ARTIFACT_API_AUDIENCE` is the client-id GUID.
- The mock origin cannot do SSO.
- The `botid-` URI applies if the tab ships inside Factory's package.

### F.3 validDomains, CSP and frame-ancestors
**Answer:**

- **HTTPS** with a publicly trusted certificate; self-signed is not supported.
- **`Content-Security-Policy: frame-ancestors`** covering:
  - `https://teams.microsoft.com https://*.teams.microsoft.com https://*.cloud.microsoft`;
  - `https://*.microsoft365.com https://*.office.com`;
  - `https://outlook.office.com https://outlook.office365.com`.

  Keep the old hosts alongside `*.cloud.microsoft` during the migration. Send no `X-Frame-Options: DENY/SAMEORIGIN`.
- **TeamsJS ≥2.19.0**, calling `app.initialize()`. Otherwise "your page isn't displayed" on `*.cloud.microsoft`.
- **`validDomains`:** every domain the tab loads from or navigates to. At most 100 entries, wildcards allowed. Auth flows must start and end on a listed domain.
- **No login redirects** in the frame (blank tab), and **no third-party cookies** (iOS blocks them).
- **Gap.** TeamsJS 2.56+ appears to fetch its valid-origins list from a CDN at runtime (INFER from release notes), so a strict `connect-src` may break initialization (spike).

**Evidence:**
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/how-to/tab-requirements (ms.date 2025-02-06 **PRE-GA**, updated 2026-05-29, still applies; DOC).
- schema/root (2026-10-01; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/platform/resources/troubleshoot (ms.date 2026-07-10; DOC).
- https://github.com/OfficeDev/microsoft-teams-library-js/releases (v2.56.0 2026-09-02 … v2.58.0 2026-10-07; CODE).

**Confidence:** high, except medium for the `connect-src` question.

**Implication for docs/80:** §15 **confirm and detail**. The tab host gets a public CA certificate (Caddy/Let's Encrypt is fine), the frame-ancestors header above, and an entry in `validDomains`. Pin `@microsoft/teams-js` 2.58.0 (released 2026-10-07).

### F.4 Client-side mermaid in a tab
**Answer:** **Yes.** Teams only frames the page and doesn't restrict tab JS, so the constraints are our CSP and mermaid itself.

- **No `eval`** in mermaid's API module, so `'unsafe-eval'` is not needed. Bundled dependencies were not audited.
- **`style-src 'unsafe-inline'` is required.** Mermaid injects a `<style>` into each SVG via `innerHTML` with no nonce.
- Keep `securityLevel:'strict'` (the default): labels are HTML-encoded, `click` is disabled, and output goes through DOMPurify.
- `mermaid.parse(text)` validates without rendering. The render API is `initialize({startOnLoad:false})` then `await mermaid.render(id, text)`.
- **Security floor: pin ≥11.16.1 / 10.9.8.** GHSA-6x64-9x62-f2gx / CVE-2026-50159 (CSS injection through sibling combinators) affects up to 11.16.0. There were further 2026 advisories (GHSA-87f9-hvmw-gh4p, GHSA-ghcm-xqfw-q4vr, GHSA-xcj9-5m2h-648r). Workaround: one sibling-free container per diagram. Self-host mermaid.
- **Version conflict.** F/G saw 12.x tags with inconsistent dates; L/I ran mermaid 12.1.0 (npm, 2026-10-02). Whether 12.x includes the CVE fix is unconfirmed.

**Evidence:**
- https://raw.githubusercontent.com/mermaid-js/mermaid/develop/packages/mermaid/src/mermaidAPI.ts (accessed 2026-10-09; CODE).
- https://mermaid.js.org/config/usage.html (accessed 2026-10-09; DOC).
- https://github.com/mermaid-js/mermaid/security/advisories/GHSA-6x64-9x62-f2gx (published 2026-08-04; DOC).
- https://github.com/mermaid-js/mermaid/releases (accessed 2026-10-09; CODE; dates inconsistent).

**Confidence:** high on the CSP need and advisories. Medium on transitive dependencies.

**Implication for docs/80:** §8.1/§9.1 **confirm** client-side mermaid. §15 **detail**: tab CSP `script-src 'self'; style-src 'self' 'unsafe-inline'`. Pin the **same** mermaid version for the server-side validator and the tab. Parse-valid diagrams can still carry `classDef` CSS payloads, so the pin matters.

### F.5 Nested `<iframe sandbox="allow-scripts">` from a separate origin
**Answer:** **Undocumented on every client.**

What is documented (DOC):
- `validDomains` covers domains the tab "expect[s] to load any content" from. Adding the mock origin is cheap and conservative.
- Teams loads tabs in sandboxed iframes with undocumented flags.
- Nested frames are anticipated: a nested frame "can act as a proxy to Teams" if it runs TeamsJS, which the mock must **not** do.

What is inferred (INFER):
- On the web, the grandchild frame is governed by **our** tab's `frame-src` and by the mock origin's `frame-ancestors`, which must allow the tab host.
- Desktop (WebView2) and mobile webviews may intercept navigation to non-`validDomains` hosts. Nothing documents what happens to subframes.

Two consequences:
- The mock origin, which is an opaque origin under `allow-scripts` alone, combined with "multiple domains per app aren't supported", **can never hold a user token**. Mocks need **short-lived signed URLs** minted by the SSO-authenticated artifact API.
- A documented alternative is `tab/tabInfoAction` → Collaborative Stageview (`contentUrl` must be in `validDomains`; web supports Modal only). It still frames our tab page, not the mock directly.

**Evidence:**
- tab-requirements (updated 2026-05-29, **PRE-GA** content, still applies; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/how-to/create-tab-pages/content-page (ms.date 2022-11-23 **PRE-GA**, updated 2026-07-29, still applies; DOC).
- what-are-tabs (2026-09-08; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/open-content-in-stageview (ms.date 2026-09-16; DOC).

**Confidence:** low that it works everywhere.

**Implication for docs/80:** §7.4/§14.4/§16 (011) **changes design pending spike**:
- Ship **"open mock in browser"** (signed URL) as the v1 path.
- Keep the nested iframe behind the F.5 spike on web, new desktop (Windows/macOS), iOS and Android.
- Add the mock origin to `validDomains`.
- Mock CSP: `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; frame-ancestors https://<tab-host>`.

### F.6 Mobile tab behaviour
**Answer:**

*Works (DOC):*
- Custom and org-catalog apps behave like Store apps approved for mobile: channel tabs open `contentUrl` in an in-app webview.
- There is a native loading indicator, and tabs don't reload on switch.
- SSO works at the mobile versions above.

*Silently doesn't:*
- `shareDeepLink`.
- TeamsJS v2 URL placeholders. Mobile honours only v1 placeholders, so use `getContext()`.
- Cookie auth on iOS.
- Link unfurling for authenticated links.
- Adaptive Cards above 1.6.

*Unverified for custom apps:*
- Stageview on mobile opening in the browser.
- The mobile deep-link approval and iOS Team ID requirement, which is stated for Store apps.
- Nested sandboxed iframes (F.5).

**Evidence:**
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/design/tabs-mobile (ms.date 2022-11-02 **PRE-GA**, updated 2026-05-29, still applies; DOC).
- deep-link-application (2026-06-23; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/how-to/access-teams-context (ms.date 2026-03-02 **PRE-GA**, updated 2026-09-17, still applies; DOC).
- tab-sso-overview (PRE-GA; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/platform/messaging-extensions/how-to/link-unfurling (ms.date 2026-09-24; DOC).

**Confidence:** medium-high for documented items. Low for deep links and nested frames on mobile.

**Implication for docs/80:** §8.2/§14 **confirm** that the tab works on mobile. **Detail:** build deep links ourselves rather than with `shareDeepLink`, and add device tests for card→tab links.

### F.7 Sub-entity routing
**Answer:**

- **Read:** `const ctx = await app.getContext()`, then `ctx.page.subPageId` (the v1 name is `subEntityId`), `ctx.page.id` (= entityId), `ctx.channel.id` and `ctx.user.tenant.id`.
- **Create from a card:** the E.6 URL inside `Action.OpenUrl`.
- **Create from the tab:**
  - `pages.navigateToApp({appId, pageId, webUrl, subPageId, channelId})`;
  - `pages.currentApp.navigateTo({pageId, subPageId})`;
  - `pages.shareDeepLink`, which is not available on mobile.
- **Limits:**
  - Windows desktop fails on deep links over **2048 chars**.
  - "Deep links aren't supported in `contentUrl`".
  - A tab without an entityId receives no subEntityId.
- **Gap.** It is unverified whether the deep link lands on a **static** tab pinned in a given channel, and which `entityId` to use (`staticTabs[0].entityId` is the candidate). This blocks the card-button design until spike S-F7.

**Evidence:**
- deep-link-application (2026-06-23; DOC).
- access-teams-context (2026-09-17; DOC).
- open-content-in-stageview (2026-09-21; DOC).

**Confidence:** high for the mechanics. Low for static-tab channel targeting.

**Implication for docs/80:** §8.2 **confirm** `subEntityId = "{NNN-slug}/{view}[/{attempt}]"`. §14 **new risk, changes design if S-F7 fails.** Fallbacks: Stageview `tab/tabInfoAction` with `contentUrl=https://<tab-host>/?sub=<id>`, or `websiteUrl`.

### G. Artifact-viewing alternatives
**Answer:** The per-option facts are DOC. The ranking is entirely INFER.

- **Loop components.** The body is an Adaptive Card. A view-only card "doesn't change to a Loop component". There is no HTML, JS or mermaid. **Unsuitable** for viewing.
- **Channel Files tab (SharePoint).**
  - Graph `filesFolder` (application `Files.Read.All`, RSC `File.Read.Group`) plus `PUT …/content` (≤250 MB, `Files.ReadWrite.All`) make a git→SharePoint mirror feasible.
  - The costs are a tenant-wide write grant, a second editable copy (drift) and no per-SHA versioning.
  - Native `.md` viewing in SharePoint is **secondary-source only** (Message Center MC1261592 via a third-party mirror). Mermaid in it, and HTML rendering, are unknown.
- **Link-unfurling message extension.**
  - It uses AC ≤1.3, caches results for 30 min, and works on mobile only for unauthenticated links.
  - "Don't add domains that aren't in your control", which **rules out unfurling github.com**.
  - It can open Stageview via `tab/tabInfoAction`.
- **Adaptive Card image previews.** PNG/JPEG/GIF at ≤1024², public, no redirects (E.4).
- **Custom static channel tab.** Full HTML/JS, SSO, mermaid, renders any path at a SHA (F.1–F.7). It costs a web app, an Entra app and the nested-frame unknown.

| Artifact | Rank 1 | Rank 2 | Rank 3 | Not suitable |
|---|---|---|---|---|
| **Spec / plan (markdown, up to ~60k chars)** | **Custom tab.** Fidelity: full GFM (our sanitizer), per-SHA. Mobile: yes. Auth: SSO → our API. Effort: medium (shared). Git cost: none. | **Files tab `.md` mirror.** Fidelity: native view (secondary source), no mermaid, no SHA. Mobile: SharePoint viewer. Auth: M365, free. Effort: low-medium. Git cost: **high** (drift, `Files.ReadWrite.All`). | **Card excerpt + link.** Fidelity: low. Mobile: yes. Auth: n/a. Effort: low. Git cost: none. | Loop; github.com unfurl |
| **Architecture diagrams (.mmd + PNG)** | **Custom tab** (client-side mermaid, strict, pinned). Fidelity: vector, matches source at SHA. Mobile: yes (low-end performance untested). Auth: SSO. Effort: medium. Git cost: none. | **AC PNG thumbnail.** Fidelity: raster ≤1024². Mobile: yes. Auth: **public or signed no-redirect URL**. Effort: low. Git cost: low (derived). | **Unfurl of our own tab URL** → card + Stageview. Mobile: unauthenticated links only. Effort: medium. Git cost: none. | Loop; Files tab |
| **Clickable HTML mocks** | **Custom tab → sandboxed nested iframe** on a signed URL. Fidelity: full. Mobile: **unknown (F.5)**. Effort: medium-high. Git cost: none. | **"Open mock in browser"** on a signed URL. Fidelity: full. Mobile: yes. Effort: low. Git cost: none. **Ship first.** | **AC screenshots** (PNG per screen). Fidelity: static. Mobile: yes. Auth: public/signed URL. Effort: low. Git cost: low. | Files tab (HTML rendering unconfirmed); Loop |

**Evidence:**
- https://learn.microsoft.com/en-us/microsoftteams/platform/m365-apps/design-loop-components (ms.date 2024-10-11 **PRE-GA**, updated 2026-04-01, still applies; DOC).
- https://learn.microsoft.com/en-us/graph/api/channel-get-filesfolder (ms.date 2024-08-19 **PRE-GA**, updated 2026-03-07, still applies; DOC).
- https://learn.microsoft.com/en-us/graph/api/driveitem-put-content (ms.date 2017-09-10 **PRE-GA**, updated 2026-08-11, still applies; DOC).
- link-unfurling (ms.date 2026-09-24; DOC; its code samples are Bot Framework-era, but the manifest and invoke contract still apply).
- cards-reference (PRE-GA, still applies; DOC).
- open-content-in-stageview (2026-09-21; DOC).
- https://mc.merill.net/message/MC1261592 (**not primary**; accessed 2026-10-09).

**Confidence:** high on the per-option facts. Medium on the ranking. Low on SharePoint rendering.

**Implication for docs/80:** §8 **confirm** the custom tab as the primary viewer for all three artifact types. §14.4 **change**: ship "open in browser" first. §1.4/§8 **record the rejection** of Loop and the Files-tab mirror (drift plus a tenant-wide `Files.ReadWrite.All` grant against git as source of truth). An unfurl handler for our own tab URLs is optional later work.

### H.1 Inbound identity fields
**Answer:**

| Field | Format | Stability | Use |
|---|---|---|---|
| `from.id` | `29:…` | **unique per (bot, user)**: the same human has six different ids across six bots | Connector addressing only |
| `from.aadObjectId` | Entra GUID | stable, the same for every bot | **authorize on this, together with tenant** |
| `from.name` | display name | mutable | display only |
| `from.email` | — | the SDK says "when provided by the channel"; no doc says Teams populates it inbound | don't rely on it |
| UPN | — | not on the inbound `Account`; only on `TeamsChannelAccount.user_principal_name` from the roster API | lookup only |
| `from.userRole` | user/guest | as provided | guest filter (INFER) |
| Tenant | `channelData.tenant.id` (channels and groups), `conversation.tenantId`, header `x-ms-tenant-id` | stable | **must match ours** |
| `recipient.id` | `28:<appId>` | stable per bot | which bot was addressed |
| `channelData.team.id` / `.channel.id` | `19:…@thread.tacv2` | "definitive source" | channel↔repo map |

Fields are service-asserted once the JWT has been validated (J.7; INFER). The message text is not (DOC).

**Evidence:**
- send-proactive-messages (2026-06-30; DOC): "The `userId` is unique to your agent ID and a particular user… The `channelId` is global"; UPN/email are not usable for proactive sends.
- build-conversational-capability (2026-09-28; DOC).
- `packages/api/src/microsoft_teams/api/models/account.py` (CODE).

**Confidence:** high, except medium for whether email or UPN ever appear inbound.

**Implication for docs/80:** §13 **confirm and strengthen**. Key leads by `(tenant_id, aadObjectId)`. Reject activities whose tenant isn't ours. Key the GitHub link on `aadObjectId`.

### H.2 Linking a Teams user to a GitHub login
**Answer:**

*Mechanism.* An **OAuth connection on an Azure Bot resource**. The Bot Framework Token Service runs the dance and stores the token. GitHub is named as a supported external service, and the "OAuth 2 Generic Provider" can template any provider.

*SDK 2.1:*
- `app.add_oauth_flow(name, …)`;
- `await flow.sign_in(ctx)` returns the cached token or sends an OAuthCard;
- `@flow.on_signin` delivers `event.token_response.token`, with `on_signin_failure`, `get_token` and `sign_out` alongside.
- `ctx.sign_in` and `default_connection_name` are deprecated.

*Teams SSO does not help.* Bot SSO is Entra-only and "not supported in channel scope".

*Token refresh.* The only guidance is "log the user out [and] initiate the sign-in flow again". The generic provider has refresh templates, but when the service actually refreshes is unconfirmed.

*Tokens are per bot.* The Token Service stores tokens "for a particular bot, channel, conversation, and user", and the SDK looks them up by `from.id` (which is per bot) + channel + connection.

*Conflict, unresolved.*
- Learn add-authentication (updated 2026-06-30): "OAuth isn't supported in the group chat or channel scopes directly… they must authenticate in their personal scopes before they can use the bot in the group chat or channel."
- SDK 2.1 code (`activity_context.py` L377-452) **sends the OAuthCard in-channel as a targeted message** (visible only to the requester) and omits the SSO exchange resource "to render the sign-in button".
- The doc may predate targeted messages (manifest `supportsTargetedMessages` arrived in v1.29). Spike S-H2 decides.

*Recommended shape (INFER):*
1. One-time linking on Factory: OAuthCard → GitHub `GET /user` → persist `aadObjectId → github_login`.
2. Authorize each decision with the existing GitHub App installation token's collaborator-permission check (`is_authorized`).
3. This avoids user-token lifetime and refresh, and avoids per-bot re-sign-in.

**Evidence:**
- https://microsoft.github.io/teams-sdk/python/in-depth-guides/user-authentication (accessed 2026-10-09; DOC).
- `packages/apps/src/microsoft_teams/apps/oauth_flow.py` and `routing/activity_context.py` L377-452 (CODE).
- https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/authentication/bot-sso-overview (ms.date 2026-08-27; DOC).
- add-authentication (ms.date 2026-04-14 **PRE-GA**, updated 2026-06-30, uses Teams SDK samples, still applies; DOC). Manifest `validDomains: ["token.botframework.com"]`; redirect `https://token.botframework.com/.auth/web/redirect`.
- https://learn.microsoft.com/en-us/azure/bot-service/bot-builder-concept-authentication (ms.date 2024-10-09 **PRE-GA**, Bot Framework-era; same Token Service, still applies; DOC).
- https://learn.microsoft.com/en-us/azure/bot-service/bot-builder-concept-identity-providers (ms.date 2024-10-09 **PRE-GA**, still applies; DOC).

**Confidence:** medium overall. High for the mechanism, SSO limits and per-bot storage. Low for channel UX and refresh.

**Implication for docs/80:** §13 **change**:
- Add an explicit linking step and the `aadObjectId → github_login` store.
- State that Teams SSO cannot replace GitHub sign-in.
- Route all gate interactions through Factory so there is one sign-in.

§15 **change**: one OAuth connection on Factory's Azure Bot; `token.botframework.com` in Factory's `validDomains`; manifest ≥1.29 if targeted cards are used. **New risk:** whether channel sign-in works (S-H2).

### H.3 Teams-native authorization alternatives
**Answer:**

| Option | What it is | Consent | Notes |
|---|---|---|---|
| (a) Bot roster API | `api.conversations.get_member_by_id` / `get_members` / `get_paged_members` → `TeamsChannelAccount` with `aad_object_id`, `user_role` | none beyond install | `user_role` values are unconfirmed |
| (b) Graph team members | `GET /teams/{id}/members?$filter=(…/userId eq '<aadObjectId>')` with RSC `TeamMember.Read.Group` | team owner at install | returns `roles:["owner"]` |
| (c) Graph channel members | `ChannelMember.Read.Group` | **conflicting docs** | the Graph page says least-privileged Application; the RSC table says NA/NA |
| (d) Entra groups | `POST /users/{id}/checkMemberGroups` (≤20 groups, transitive) | **tenant admin** (`User.ReadBasic.All` + `GroupMember.Read.All`, plus `Member.Read.Hidden` for hidden groups) | — |

All four are one call per decision and cacheable by `aadObjectId` (INFER). None expresses GitHub repo permission; they would replace the rule rather than implement it.

**Evidence:**
- `packages/api/src/microsoft_teams/api/clients/conversation/client.py` L438-452 and `models/account.py` L96-150 (CODE).
- https://learn.microsoft.com/en-us/graph/api/team-list-members (ms.date 2024-04-18 **PRE-GA**, updated 2026-03-07, still applies; DOC).
- https://learn.microsoft.com/en-us/graph/api/channel-list-members (ms.date 2024-04-04 **PRE-GA**, updated 2025-07-31; DOC).
- RSC page (PRE-GA, refreshed 2026-05-29; DOC).
- https://learn.microsoft.com/en-us/graph/api/directoryobject-checkmembergroups (ms.date 2026-05-21; DOC).

**Confidence:** high for (b) and (d), medium for (a), low for (c).

**Implication for docs/80:** §13 **confirm** that GitHub permission stays the gate. For "any channel member" (conversation and tab viewing), use (a) at zero consent, or (b). **Change:** remove any assumption of `ChannelMember.Read.Group`.

### I.1 Architecture diagrams: mermaid C4 vs Structurizr DSL
**Answer:** For "validated in Python, not trusted from the model", **mermaid C4 is the weakest choice, Structurizr DSL the strongest, and mermaid `flowchart` sits between them.**

*Mermaid C4.* It is "an experimental diagram for now". It has no auto-layout, and `sprite`, `tags` and `link` are unsupported.

*Mermaid parsing.* There is **no Python-callable mermaid parser**. `@mermaid-js/parser` 2.0.1 covers neither C4 nor flowchart. `mermaid.parse` in Node needs a jsdom shim; without one it fails on valid input with `DOMPurify.addHook is not a function`.

*Measured with mermaid 12.1.0 / mmdc 12.0.0 (CODE):*

| Input | `mermaid.parse` | `mmdc` render |
|---|---|---|
| valid C4Container | OK | exit 0, correct PNG |
| C4 with missing `)` | **accepted** | **exit 0, wrong PNG** |
| C4 `Rel` to undefined alias | **accepted** | exit 1 |
| valid flowchart | OK | — |
| broken flowchart | **line-numbered error** | — |

*Structurizr DSL* (new `structurizr/structurizr` 2026.09.19; the old `structurizr/cli` is frozen).
- `validate` rejected all three faults with line numbers and exit 1.
- It has real model semantics.
- Structurizr's own AI page says LLM output needs "a little cleanup".
- `export -format mermaid|png|…` enables a hybrid: model in DSL, render as mermaid in the tab.

*Headless rendering.*
- `mmdc` needs Node ≥22.13 and a puppeteer ^25 peer, i.e. Chromium. As root it needs `--no-sandbox` via `-p`.
- Structurizr PNG/SVG export works **only** in the `-playwright` image (4.03 GB, versus 430 MB base; ~35 s cold).

*Gap.* No primary source measures LLM generation reliability for any of these formats.

**Evidence:**
- https://github.com/mermaid-js/mermaid/blob/develop/packages/mermaid/src/docs/syntax/c4.md (accessed 2026-10-09; DOC).
- https://github.com/mermaid-js/mermaid/blob/develop/packages/mermaid/src/docs/config/usage.md (accessed 2026-10-09; DOC).
- https://github.com/mermaid-js/mermaid/tree/develop/packages/parser/src/language (CODE).
- https://github.com/mermaid-js/mermaid-cli (accessed 2026-10-09; DOC); npm 12.0.0 (2026-09-24; CODE).
- https://docs.structurizr.com/commands, /export, /validate, /binaries, /ai/dsl-generation (accessed 2026-10-09; DOC).
- https://github.com/structurizr/cli README (DOC).
- Local runs of mermaid 12.1.0, mmdc 12.0.0 and `structurizr/structurizr:2026.09.19[-playwright]` (2026-10-09; CODE).

**Confidence:** high for tool behaviour. Medium for generalising from 3–5 cases.

**Implication for docs/80:** §9.1 **change**: "parse in Python" is impossible and ineffective for C4. Options:
- (a) **Structurizr DSL as source**, with `validate` as the gate and `export` to mermaid (tab) and PNG (card);
- (b) mermaid `flowchart` with C4-styled classes, gated by Node `mermaid.parse`, a render-must-exit-0 check and our own endpoint-declared check;
- (c) not mermaid C4.

§15: a Chromium renderer image. §17 Q9 resolves toward Structurizr or flowchart. Spike: an LLM pass-rate eval in 010.

### I.2 Clickable UI prototypes and thumbnails
**Answer:**

- **Static HTML + Tailwind is the most reliable agent target.**
  - The Play CDN is "for development purposes only" and breaks §9.2's no-network rule.
  - **Compiled Tailwind v4.3.3** ships standalone binaries (linux x64/arm64/musl), so no Node is needed. Inline the CSS.
- **Design-system components:** not researched (gap). They need a build step (INFER).
- **Storybook 10.6.1:** `build-storybook` produces a static app, with per-story iframes. Visual testing goes through the Chromatic cloud. Worth it only if the target repo already has a component library (INFER).
- **Figma:**
  - The REST API is read/extract-oriented.
  - Writing to the canvas goes through the **remote MCP `use_figma`**, which needs a **Full seat** and edit rights, has a 20 kb response cap and no images or custom fonts.
  - No headless or service-account path is documented, and nothing is said about prototype interactions.
  - Beta and pricing status are unconfirmed.
- **Thumbnails: Playwright for Python 1.63.0.**
  - `page.screenshot(full_page=True, animations="disabled")` or a locator screenshot.
  - Block the network with `new_context(offline=True, service_workers="block")` and/or `page.route("**/*", lambda r: r.abort())`.
  - Load via `file://` or `set_content`.

**Evidence:**
- https://tailwindcss.com/docs/installation/play-cdn and /tailwind-cli (accessed 2026-10-09; DOC).
- https://github.com/tailwindlabs/tailwindcss/releases/tag/v4.3.3 (2026-07-16; CODE).
- https://storybook.js.org/docs/sharing/publish-storybook and /writing-tests/visual-testing (accessed 2026-10-09; DOC).
- https://developers.figma.com/docs/rest-api/ and /figma-mcp-server/write-to-canvas (accessed 2026-10-09; DOC).
- https://playwright.dev/python/docs/screenshots, /api/class-page, /api/class-browser, /network (accessed 2026-10-09; DOC).

**Confidence:** high for Tailwind, Figma scope and Playwright. Medium for Figma headless use. Low for design systems.

**Implication for docs/80:** §9.2 **confirm and make concrete**: compiled Tailwind inlined, Play CDN forbidden, Playwright screenshots offline in E2B. Whether the E2B template has Chromium is a spike. Storybook only when the repo already has a component library. **Figma rejected** as primary output. §17: close "design-system vs Tailwind vs Figma" in favour of compiled Tailwind. §15: one shared Chromium renderer.

### I.3 Safe rendering of agent-generated content
**Answer:**

*Adaptive Cards* are JSON rendered natively, so script injection is not possible. The residual exposure:
- TextBlock markdown links can phish, so show or allow-list targets;
- image URLs must be ours;
- `Action.OpenUrl` targets must be built only by our code;
- size limits (E.5).

*Tab markdown.* Render with raw HTML **disabled**, sanitize (e.g. DOMPurify), allow-list links, and drop or proxy remote images.

*Tab mermaid.* Strict mode, never `loose`, pinned ≥11.16.1, a sibling-free container per diagram, and `parse` before `render`. Residual risk is injected CSS, because of `style-src 'unsafe-inline'`.

*Tab CSP:* `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' <TeamsJS origins CDN?>; frame-src https://<mock-origin>; frame-ancestors <F.3 list>`.

*Mocks:*
- Served from a **separate registrable origin** on signed, expiring URLs.
- `sandbox="allow-scripts"` only.
- CSP `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'; form-action 'none'; frame-ancestors https://<tab-host>`.
- No tokens, context, TeamsJS or sensitive `postMessage` into the frame.

No Microsoft primary source prescribes a sanitizer or mock CSP. Those parts are **general web-security practice (INFER)**.

**Evidence:**
- mermaidAPI.ts and the mermaid advisories (F.4; CODE/DOC).
- cards-reference (2026-08-19; DOC).
- tab-requirements (2026-05-29; DOC).
- access-teams-context (2026-09-17; DOC): context "must not [be used] as proof of identity".

**Confidence:** medium. The card and mermaid parts are high; the sanitizer and CSP recipe is not Teams-documented.

**Implication for docs/80:** §7.4 **change**: extend the mock CSP as above. §9.2 **change**: mocks must be fully self-contained. §9.1 **detail**: the same mermaid version on both sides. §14 **detail**: card URLs are built only by our code.

### J.1 Rate limits
**Answer:** "All requests are subject to the same rate limiting policy", whether sends, proactive sends or updates. The values are "for estimation only" and "subject to change".

**Per bot, per thread** (a thread is a 1:1, group chat or channel):

| Operation | Limit |
|---|---|
| Send / create conversation | 7/1 s, 8/2 s, 60/30 s, 1,800/3,600 s |
| Get members / conversations | 14/1 s, 16/2 s, 120/30 s, 3,600/3,600 s |

**Per thread, all bots combined:**

| Operation | Limit |
|---|---|
| Send / create | 14/1 s, 16/2 s |
| Get members / conversations | 28/1 s, 32/2 s |

**Per app per tenant:** 50 RPS.

The note "the thread limit of 3600 seconds and 1800 operations applies only if multiple agent messages are sent to a single user" is ambiguous; treat 1,800/h as a ceiling anyway.

**On 429**, back off exponentially with random jitter. The sample uses 3 retries, 2–20 s, ±20%. Also retry 412, 502 and 504, and batch rather than issuing many calls to one conversation. No `Retry-After` guidance exists. Whether SDK 2.1.0 retries automatically was not checked; assume it doesn't.

**Evidence:** https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/rate-limit (ms.date 2025-02-06 **PRE-GA**, updated 2026-07-27 with "agent" terminology, still applies; its C# samples are Bot Framework-era; DOC).

**Confidence:** high that these are the published numbers. Medium on how they apply in practice.

**Implication for docs/80:** §14/§15 **new design constraint**:
- A per-conversation token bucket in the notifier, sized to the all-bots budget.
- Coalesced board updates.
- A Temporal retry policy on 429/412/502/504 with jitter.
- Idempotent sends.

### J.2 Message size and attachments
**Answer:**

- **Text or card:** ~100 KB (UTF-16), with 80 KB recommended and 413 above (E.5).
- **Images:** ≤1024², picture attachments ≤1 MB, no SVG.
- **Files in channels and group chats: Graph only** (SharePoint or OneDrive upload, then a card linking to it). The SDK file-consent flow (`FileConsentCard`, `supportsFiles: true`) is **personal scope only**.
- Bots can't send or receive files in GCC High, DoD or 21Vianet.
- Adaptive Cards can't upload files.

**Evidence:**
- build-conversational-capability (2026-09-28; DOC).
- limits-specifications-teams (2026-10-07; DOC).
- bots-filesv4 (ms.date 2026-08-19; DOC): "file consent APIs work only in the personal context".
- cards-reference (PRE-GA, still applies; DOC).

**Confidence:** high.

**Implication for docs/80:** §8/§14 **confirm** that artifacts live in git and render in the tab. No bot-attached files in channels.

### J.3 Inbound retries and idempotency
**Answer:**

- **Every inbound activity has an `id`.** For channel messages it is the Teams message id, and `messageUpdate` / `messageDelete` reuse it. A card invoke's `reply_to_id` is the card message's id.
- `(conversation.id, activity.id)` is a usable dedup key (INFER; no doc calls it one).
- **At-least-once delivery is not documented.**
- The Bot Service times out at **10–15 s** with a 504 (PRE-GA Bot Framework guidance, but a service property, so it likely still applies).
- The SDK's own code dedups `signin/tokenExchange` because "duplicates arrive from several of the user's clients". So Teams **does** deliver duplicate invokes in at least that case (CODE).
- There is no general inbound dedup in the SDK (INFER).

**Evidence:**
- build-conversational-capability (2026-09-28; DOC).
- https://learn.microsoft.com/en-us/azure/bot-service/bot-builder-howto-long-operations-guidance (ms.date 2024-10-09 **PRE-GA**, updated 2025-12-16; DOC).
- `packages/apps/src/microsoft_teams/apps/oauth_state.py` (2026-08-28; CODE).

**Confidence:** medium for the dedup key. Low for retry semantics. High for the timeout.

**Implication for docs/80:** §7.2/§12/§15 **confirm** porting the bridge dedup with keys:
- `teams:{conversation.id}:{activity.id}` for messages;
- `teams:{reply_to_id}:{aadObjectId}:{attempt}` for card decisions.

Handlers ack fast (signal or `start_update` to ACCEPTED, then return) and never run agent work inline. The workflow's first-valid-wins remains the real guarantee. Spike the delivery semantics.

### J.4 App manifest
**Answer:**

*Version.* The newest published schema is **v1.30**; v1.31 returns 404. Whether v1.30 is "GA" rather than merely published is unlabelled.

*Fields that matter:*
- **`bots`: `maxItems: 1`**, "Currently only one bot per app is supported". Each bot has `botId`, `scopes` (team/personal/groupChat/copilot), `supportsFiles`, `isNotificationOnly`, `commandLists` (≤3), and so on.
- **`supportsTargetedMessages`** is new in **v1.29**.
- `staticTabs` ≤16; static tabs in channels need ≥1.16.
- `configurableTabs` ≤1.
- `validDomains` ≤100.
- `webApplicationInfo` `{id, resource ≤2048}`, plus the new `nestedAppAuthInfo` (≤5); needs ≥1.5.
- `authorization.permissions.resourceSpecific` ≤16, `{name, type: Application|Delegated}`. Application RSC needs ≥1.6, delegated RSC ≥1.12.
- `name.short` ≤30 characters.
- `icons`: color 192² PNG, outline 32².
- v1.30 also adds `agenticUserTemplates`, `copilotAgents`, `agentConnectors`, `agentSkills`, `supportedChannelTypes`, and others.

**Evidence:**
- https://developer.microsoft.com/json-schemas/teams/v1.30/MicrosoftTeams.schema.json (probed and parsed 2026-10-09; CODE/DOC).
- schema/root (updated 2026-10-01; DOC).
- add-authentication (PRE-GA, refreshed; DOC).
- RSC page (DOC).

**Confidence:** high for the constraints. Medium for "current GA".

**Implication for docs/80:** §7/§15 **confirm** one manifest per role bot. Target `manifestVersion` **1.29+** (1.30 if available to the tenant), since targeted sign-in cards and static channel tabs both need recent versions. Put the tab, `webApplicationInfo` and RSC on **Factory only**.

**Gap:** whether `webApplicationInfo` is still required alongside RSC.

### J.5 Distribution
**Answer:**

1. **User custom upload (sideload).** No admin approval, but three settings must all be on:
   - org-wide "Let users interact with custom apps in preview";
   - the user's setup policy "Upload custom apps";
   - the team's "Allow members to upload custom apps" (if it is off, only team owners with the policy can upload).
2. **User submission for approval.** The app shows as Submitted/Blocked; an admin selects Publish; updates need re-approval.
3. **Admin upload.** It goes to the org catalog with no approval and appears "after a few hours".
4. **Access afterwards** is controlled by permission and setup policies.

Not available in GCC High, DoD or 21Vianet. A code-only change needs no re-upload; any manifest change needs an update. An update consented in one context applies everywhere.

**Evidence:**
- https://learn.microsoft.com/en-us/microsoftteams/teams-custom-app-policies-and-settings (ms.date 2026-04-14 **PRE-GA** by two weeks; admin docs are SDK-independent, still applies; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/submit-approve-custom-apps (ms.date 2026-06-01; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/platform/concepts/deploy-and-publish/apps-upload (ms.date 2025-01-23 **PRE-GA**, updated 2026-04-01, still applies; DOC).

**Confidence:** high.

**Implication for docs/80:** §15 **confirm and detail**. Dev sideloads six apps into a test team. Prod is admin upload ×6, then team installs. **New ops item:** script the packaging, since every manifest change means six updates.

### J.6 Testing
**Answer:**

- **DevTools is deprecated** and absent from Python. Its replacement is the **Agents Playground** (B.4), which offers chat, "Mock an Activity" for invokes, membership and reactions, and a request/response log.
- **Unit tests without Teams** follow the SDK's own test pattern:
  - construct `App`;
  - `AsyncMock` the adapter's `start`/`stop` and `api.conversations.create_activity` / `update_activity`;
  - inject activities with `await app.event_manager.on_activity(ActivityEvent(body=…, token=FakeToken()))`.

  This uses internals and is not a documented API.
- **Record/replay** does not exist. Log redacted inbound JSON at the HTTP layer and replay it through `on_activity` (INFER).
- **Gap:** whether the Playground faithfully models channel threads and `Action.Execute` round-trips.

**Evidence:**
- https://microsoft.github.io/teams-sdk/developer-tools/devtools/ (accessed 2026-10-09; DOC): "DevTools is deprecated".
- https://microsoft.github.io/teams-sdk/developer-tools/agents-playground/ (accessed 2026-10-09; DOC).
- `packages/apps/tests/test_app.py` L83-142, L245, L286 (CODE).
- `options.py` L100-125 (CODE).

**Confidence:** high for DevTools and the Playground. Medium for the unit pattern.

**Implication for docs/80:** §15/§16 **change**: drop DevTools in favour of the Playground, with a prod guard on the unauthenticated flag. Add a pytest harness around `on_activity` with recorded fixtures. The pin to `==2.1.0` matters because the harness uses internals.

### J.7 Inbound JWT validation
**Answer:** Validation is **automatic** once `client_id` is set and the unauthenticated flag is off.

*Bot Connector tokens* are checked for:
- the Bearer header;
- a well-formed JWT;
- `iss = https://api.botframework.com`;
- `aud` ∈ `{app_id, api://app_id, api://botid-app_id}`;
- `exp`/`iat` with 300 s leeway;
- an RS256 signature against `login.botframework.com` keys (PyJWT `PyJWKClient`, 5-min cache on master; unverified for the pinned version);
- a `serviceurl` claim matching the body's `serviceUrl`, **skipped when the body has none**.

Failures return 401, where Learn says 403. The **channel-endorsement check is not implemented.**

*Entra-issued tokens* (the Agent 365 path):
- The validator reads `tid` from the *unverified* token and builds the issuer from it, so the **issuer check is tautological**.
- `aud` must still be ours.
- `serviceurl` is not checked.
- TDP apps are `AzureADMultipleOrgs`, so another tenant with a service principal for our app could plausibly pass (INFER, needs a spike).

*We must configure:* explicit `client_id`/secret and `tenant_id` per App, the cloud, egress to `login.botframework.com`, never the unauthenticated flag in prod, and **our own tenant/installation allow-list** (the SDK does none). The remote-function validator also needs `tenant_id`, or it "accept[s] tokens from any tenant".

**Evidence:**
- `packages/apps/src/microsoft_teams/apps/auth/token_validator.py` (2026-08-03; CODE).
- `http/http_server.py` (CODE).
- `api/auth/cloud_environment.py` (CODE).
- https://github.com/jpadilla/pyjwt/blob/master/jwt/jwks_client.py (read 2026-10-09; CODE).
- bot-framework-rest-connector-authentication (ms.date 2024-10-09 **PRE-GA**, still the governing spec; DOC).
- v2.0.0 release notes, PRs #370 and #415 (DOC).

**Confidence:** high on what the code does. Medium on whether the Entra path is exploitable.

**Implication for docs/80:** §13/§15 **change**: add tenant allow-list middleware, either `app.use(...)` or aiohttp middleware checking `channelData.tenant.id` / `conversation.tenantId`. Note the missing endorsement check (detail). Spike S-J7.

### K.1 One app package, multiple bots?
**Answer:** **No. One bot per app** (`bots.maxItems: 1`, v1.28–v1.30), so six role bots are **six Teams apps**. Each has:

- its own manifest id, zip, `name.short` and icons;
- its own `botId` and bot registration with exactly one messaging endpoint ("Only one messaging endpoint is allowed for a bot"). Different paths on one host are fine (INFER).
- its own **single-tenant** Entra app and credential (the multi-tenant bot type is deprecated);
- its own OAuth connection, only if it does sign-in.

**Registration-location conflict.** The H/K notes say each role has "its own Azure Bot resource", citing an Azure-oriented auth page. The A/B notes (bot-locations.md) say Teams-managed registration needs no Azure Bot except for OAuth/SSO. Reconciled position (INFER, spike S-B1): 6 bot registrations, of which 5 are Teams-managed and Factory's is an Azure Bot (needed for OAuth).

**Consent.** RSC consent is per app per team. Entra admin consent applies only to Graph application permissions, per Entra app; keeping those on Factory means one consent (INFER).

**No bundle concept** was found, in the schema keys or the admin docs. `configurableTabs ≤1` per app.

**Evidence:**
- v1.28/1.29/1.30 schema JSON (probed 2026-10-09; CODE/DOC).
- schema/root (2026-10-01; DOC).
- add-authentication (PRE-GA, refreshed 2026-06-30; DOC).
- RSC page (PRE-GA; DOC).
- bot-locations.md (2026-10-08; DOC).

**Confidence:** high for one bot per app. Medium for "no bundle" (absence of evidence).

**Implication for docs/80:** §2/§7.1 **change**: close K.1 as six apps, at a cost of 6 × (Entra app + bot registration + manifest + catalog entry + team install). **New risk:** six credentials and six admin uploads. Script the packaging and keep Graph, RSC and the tab on Factory. Gap: whether one Entra app can back more than one `botId` (INFER: one-to-one).

### K.2 Do bots receive other bots' channel messages?
**Answer:** **This cannot be confirmed from primary sources.** No current doc says whether bot A's post reaches bot B, with or without a mention, with or without RSC. What is DOC: bot ids are `28:` and users are `29:`.

**Evidence:**
- channel-and-group-conversations (2026-06-23), enable-receive-all-chat-messages (2026-09-28) and build-conversational-capability (2026-09-28): all silent (DOC, checked by absence).
- Only Q&A and forum posts discuss it, which are not evidence.

**Confidence:** low (an explicit gap).

**Implication for docs/80:** §6.5 **confirm**: enforce it ourselves. Concrete rule: drop any activity with `from_.id ∈ {28:<appId> of each role bot}`. Optionally drop all `28:` senders. Spike S-K2 (detail).

### K.3 One process hosting N `App` instances
**Answer:** **Supported in practice, with no blocking global state.**

- Per-instance: router, event emitter, OAuth registry, token manager, API client, `HttpServer` with its own validator bound to its `client_id`, plugins, storage, and the DI container.
- Module-level state: constants, a NullHandler, and **`load_dotenv(find_dotenv(usecwd=True))` at import**, which walks up from CWD.

The hazards:
- **Env fallbacks.** `client_id or os.getenv("CLIENT_ID")`, and the same for `CLIENT_SECRET`, `TENANT_ID`, `MANAGED_IDENTITY_CLIENT_ID`, `CLOUD`, `SERVICE_URL` and `DANGEROUSLY_ALLOW_UNAUTHENTICATED_REQUESTS`. Two Apps missing a kwarg silently share one identity.
- **Routes.** Every App defaults to `/api/messages`. `@app.func` registers the fixed `/api/functions/<name>` regardless of the App, so same-named functions collide; in aiohttp the first route wins and the second is shadowed (INFER, untested). `app.tab()` paths are adapter-global.

**Evidence:**
- `app.py` `__init__`, `_init_credentials` and module-level `load_dotenv` (2026-09-29; CODE).
- `options.py` (CODE).
- `container.py` (CODE).
- `http/http_server.py` (CODE).
- A grep for module-level mutable state found none (CODE).
- There is no official multi-App sample.

**Confidence:** high on there being no shared global state. Medium overall, because it has not been run.

**Implication for docs/80:** §7.1 **confirm** one process with N Apps on `/api/teams/<role>/messages`. §15 **change**:
- Explicit credential kwargs only.
- No generic `CLIENT_ID`-style env vars or reachable `.env` in the bridge environment.
- Unique function and tab names, or serve tab APIs from our own aiohttp handlers.

### K.4 Rate limits with N bots in one channel
**Answer:**

- Each bot gets 7/s, 8/2 s, 60/30 s and 1,800/h per thread.
- **All bots together are capped at 14/s and 16/2 s per thread.** Six bots therefore share roughly 2–3 msgs/s each under contention.
- Whether a reply chain (`;messageid=`) counts as its own "thread" is not stated.
- Six apps get six 50-RPS tenant budgets (INFER). Updates draw from the same budgets.

**Evidence:** rate-limit (ms.date 2025-02-06 **PRE-GA**, updated 2026-07-27, still applies; DOC), sections "Per agent per thread limit" and "Per thread limit for all agents".

**Confidence:** high for the numbers. Medium for the meaning of "thread".

**Implication for docs/80:** §2/§7 **confirm** that one bot per role is feasible. **Change:** a **single shared outbound limiter per channel** across all role bots (about 10 sends per 2 s with margin), owned by the notifier. This reinforces decision 4.

### K.5 Installing several apps into one channel
**Answer:**

- **Install is per app, per team.** There is no multi-app install UI. Who may add an app follows the J.5 policy matrix.
- **Scripted path:** Graph `POST /teams/{id}/installedApps`, one app per call. Apps with RSC need `TeamsAppInstallation.ReadWriteAndConsentForTeam(.All)` (or `…AndConsentSelfForTeam`) plus a `consentedPermissionSet`. Plain `ReadWriteForTeam` "cannot be used" for RSC apps.
- A team install makes the bot reachable from every channel (INFER; stated only in the archived v3 page).
- The RSC "who can consent" conflict applies (C.1).

**Evidence:**
- apps-upload (PRE-GA, refreshed 2026-04-01; DOC).
- teams-custom-app-policies-and-settings (2026-04-14; DOC).
- https://learn.microsoft.com/en-us/graph/api/team-post-installedapps (ms.date 2024-10-17 **PRE-GA**, updated 2025-07-23, still applies; DOC).

**Confidence:** high for per-app install and the Graph API. Medium for "no multi-install UI".

**Implication for docs/80:** §2/§15 **confirm**. Add a **workspace bootstrap script** (6 Graph installs with consent), and have a team owner (PE or architect) do any manual installs.

### K.6 @mention routing with several bots installed
**Answer (INFER from DOC):**

- **Without RSC:** only the mentioned bot gets the activity. A message mentioning two bots arrives at both, as two activities with their own `recipient.id`, each at that bot's endpoint signed for its app id.
- **With RSC:** the bot gets every message and must filter with `is_recipient_mentioned()`.
- **The mention picker's disambiguation UX** is undocumented.
- **docs/80 §14.4's question** (can one card carry another bot's actions?) is **not answered by K.6**. Card-invoke routing is separate and unresolved (E.3, H.2 gaps).

**Evidence:** channel-and-group-conversations (2026-06-23; DOC), enable-receive-all-chat-messages (2026-09-28; DOC), `message.py` L88 (CODE).

**Confidence:** medium.

**Implication for docs/80:** §2/§6.3 **confirm**: "@Architect Agent …" reaches only the Architect bot, provided it lacks RSC. §14.4's cross-bot question moves to spike S-E3x.

### K.7 Per-bot avatars and names; posting as a sub-identity
**Answer:**

- **Name and avatar come from each app:** `name.short` ≤30 characters, `name.full`, and `icons.color` 192² / `icons.outline` 32², which are also on the bot registration.
- **There is no per-message sender override.** The Bot Framework `channelData.onBehalfOf` renders "[user] through [bot name]" for a *real person's* MRI. It is not a sub-identity, and the Python `ChannelData` has no such field.
- So "Coder #2" must be **content**.
- The new v1.30 `agenticUserTemplates` and the `teams.py` `examples/agent365` hint at an "agentic user" identity model. That was not researched (spike candidate).

**Evidence:**
- v1.30 schema (CODE/DOC).
- https://learn.microsoft.com/en-us/microsoftteams/platform/concepts/build-and-test/apps-package (ms.date 2026-05-08; DOC).
- https://learn.microsoft.com/en-us/dotnet/api/microsoft.bot.schema.teams.onbehalfof?view=botbuilder-dotnet-stable (ms.date 2024-05-21 **PRE-GA**, Bot Framework-era; describes the wire format, not surfaced in Python; DOC).
- `packages/api/src/microsoft_teams/api/models/channel_data/channel_data.py` L21-56 (CODE).

**Confidence:** high.

**Implication for docs/80:** §2 **change**: resolve the "if it can, we use that" branch to "it can't". The label goes in the card header, e.g. a ColumnSet with a role glyph and "Coder #2 · T005–T007". Never use `onBehalfOf`, which would attribute agent output to a lead.

### L.1 Temporal entity-workflow patterns (`temporalio` 1.34.0; repo pins 1.32.0)
**Answer:** Everything §5 assumes exists.

1. **Child lanes.**
   - `workflow.start_child_workflow(LaneWf.run, args=…, id=…, parent_close_policy=…)` returns a `ChildWorkflowHandle`; `execute_child_workflow` starts and awaits.
   - **The default `parent_close_policy` is `TERMINATE`.**
   - The server allows 2,000 pending children.
2. **Signalling a child.**
   - `child_handle.signal(...)`, or `workflow.get_external_workflow_handle(id)` / `get_external_workflow_handle_for(LaneWf.run, id)` and then `.signal`.
   - **Workflow code cannot send an Update.** Child and external handles expose only signal and cancel. Updates come from a `Client` (the bridge or an activity).
   - Lane ids must be deterministic, e.g. `feature/{repo}/{NNN}/architect`.
3. **Upward signals.** Use `workflow.info().parent.workflow_id`, then an external-handle signal. Omitting `run_id` survives a parent continue-as-new.
4. **Signal-with-start and update-with-start.**
   - Signal-with-start: `client.start_workflow(..., start_signal="name", start_signal_args=[…])`.
   - Update-with-start: `WithStartWorkflowOperation(..., id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING)` plus `execute_update_with_start_workflow` or `start_update_with_start_workflow`.
   - Update-with-start is "_not_ atomic". The docs recommend server ≥1.28; ours is 1.29.3.
5. **Continue-as-new.**
   - `workflow.continue_as_new`, `info().is_continue_as_new_suggested()`; wait for `workflow.all_handlers_finished` first.
   - Suggested at 4,096 events / 4 MiB, or at 90% of `maxTotalUpdates=2000`. Hard limit 51,200 events / 50 MiB.
   - **Trap:** "Child Workflows do not carry over when the Parent uses Continue-As-New". The parent close policy applies, so the default `TERMINATE` **kills running lanes**. Use `ABANDON` and re-address lanes by id, or never continue-as-new while lanes run. Lanes report upward by signal.
   - Update-id dedup is per run, so dedup across continue-as-new in workflow code.
6. **Updates vs Signals.**
   - `@workflow.update` plus a sync `@x.validator` that reads state, must not mutate it, and raises to reject. **A rejected update leaves no history.**
   - The SDK runs validators read-only. A mutation raises `ReadOnlyContextError`, which **fails the workflow task**. Validators don't re-run on replay.
   - Each update runs in its own task with no yield between validate and handler start. So a sync handler, or one that sets state before its first `await`, serializes two same-task decisions correctly (INFER, test it).
   - Limits: 10 in-flight updates, 2,000 total. `frontend.enableUpdateWorkflowExecution` is true in both 1.29.3 and 1.32.1.
   - **`execute_update` blocks until a worker processes it.** Signals don't need a worker. The bridge should use `handle.start_update(…, wait_for_stage=WorkflowUpdateStage.ACCEPTED, rpc_timeout=…)` and map `WorkflowUpdateRPCTimeoutOrCancelledError` to "worker unavailable".
   - **The GitHub fork:** either keep GitHub on set-if-unset signals that apply to the open window, or have the bridge query the open attempt and then send an Update. That has a TOCTOU gap, which the validator closes.

**Evidence:**
- https://docs.temporal.io/develop/python/message-passing (accessed 2026-10-09; DOC).
- https://docs.temporal.io/develop/python/child-workflows (DOC).
- https://docs.temporal.io/child-workflows (DOC).
- https://docs.temporal.io/develop/python/continue-as-new (DOC).
- https://docs.temporal.io/sending-messages (DOC).
- https://docs.temporal.io/handling-messages (DOC).
- https://docs.temporal.io/encyclopedia/workflow-message-passing (DOC).
- https://docs.temporal.io/workflow-execution/limits (DOC; all accessed 2026-10-09).
- https://github.com/temporalio/sdk-python/blob/1.34.0/temporalio/workflow/_workflow_ops.py, `_handlers.py`, `_context.py`, `worker/_workflow_instance.py`, `client/_workflow.py` (tag 2026-09-30; CODE).
- https://github.com/temporalio/temporal/blob/v1.32.1/common/dynamicconfig/constants.go and `service/history/transfer_queue_active_task_executor.go` (2026-10-08; CODE).
- https://hub.docker.com/r/temporalio/auto-setup (accessed 2026-10-09; DOC): "DEPRECATED".

**Confidence:** high for APIs, defaults and limits. Medium for the same-task serialization (untested). High for continue-as-new terminating lanes.

**Implication for docs/80:**
- §5/§5.2 **confirm with three additions**: deterministic lane ids with `ABANDON`, or no continue-as-new while lanes run; upward signals; signal-with-start as the default lane start.
- §12.1 **change**: Update + validator for Teams, with set-if-unset handlers.
- §7.2 **new risk**: the bridge needs `start_update(ACCEPTED)` with a timeout.
- §15 **change**: replace the deprecated `temporalio/auto-setup:latest`.
- 008 must include a `WorkflowEnvironment` test for two decisions in one task.

### L.2 Status while blocked in `wait_condition`
**Answer:** **Use a Query.**

- Queries work while the workflow is blocked. They must be `def`, read-only and non-blocking (`wait_condition`, `start_activity` and `continue_as_new` all assert not-read-only).
- They need a polling worker, leave no history, and work on closed workflows within retention.
- History metrics inside a query "may not be up to date", so return the workflow's own fields.
- **An Update for status is wrong:** it writes two events per call, counts toward `maxTotalUpdates`, and occupies in-flight slots.
- Queries can't fan out to children, so the parent aggregates lane state that lanes push upward.

**Evidence:** message-passing docs (accessed 2026-10-09; DOC); `_workflow_instance.py` and `_context.py` at 1.34.0 (CODE); constants.go v1.32.1 (CODE).

**Confidence:** high.

**Implication for docs/80:** N2/§5/§12.5 **confirm** `status()` as a Query. **Change:** the pre-check is advisory only (the validator is authoritative), and a down worker renders as "pipeline unavailable".

### L.3 Spec Kit `[P]` as a fan-out rule
**Answer:** `[P]` is only a per-task flag: "different files, no dependencies on incomplete tasks". There is **no grouping rule and no machine-readable dependency notation**. Dependencies come from:
- phase order, with explicit barriers only at Setup → Foundational ("BLOCKS all user stories") and Polish;
- prose sections;
- a free-text example, "(depends on T012, T013)".

**Upstream's parallel team unit is the user story.** The template says "all user stories can start in parallel (if team capacity allows)", with "Developer A: User Story 1 / Developer B: User Story 2". `[P]` inside a story is intra-developer concurrency.

`/implement`'s rules:
- phase-by-phase execution;
- `[P]` can run together;
- same-file tasks run sequentially;
- a non-`[P]` failure halts;
- `[P]` failures are reported while the rest continue.

The phase-by-phase rule conflicts with the template's parallel stories. `/implement` is written for one agent, the template for humans (INFER).

The local `tasks-template.md` is byte-identical to v1.1.2 except for one placeholder line. The local CLI is 0.13.0.

**Evidence:**
- https://github.com/github/spec-kit/blob/v1.1.2/templates/tasks-template.md (file 2026-05-12, tag 2026-10-07; DOC).
- https://github.com/github/spec-kit/blob/v1.1.2/templates/commands/tasks.md (2026-09-09; DOC).
- https://github.com/github/spec-kit/blob/v1.1.2/templates/commands/implement.md (2026-09-09; DOC).
- A local diff (CODE).

**Confidence:** high.

**Implication for docs/80:** §5.1 invariant 4 **change**:
- Barriers only at Setup, Foundational and Polish.
- One Coder lane per user-story phase by default, optionally split by `[P]` runs with disjoint file paths (every task names a path).
- Our own best-effort parse of "(depends on …)", falling back to path overlap.
- Map `/implement`'s failure rule onto lane outcomes.

§16: decide on the Spec Kit 0.13.0 → 1.1.2 bump.

### L.4 Git strategies for parallel lanes
**Answer:** Sub-branches and worktrees are **not alternatives at the same layer.** A worktree is a local checkout and still needs its own branch: git refuses to check out a branch already checked out elsewhere without `--force`. Each lane here runs in its own E2B sandbox, so **worktrees add nothing across lanes** (INFER). At most they serve as a throwaway checkout on the merge host.

**Conflict detection without a working tree:** `git merge-tree --write-tree <feature> <lane>` (Git ≥2.38) exits 0 for a clean merge and 1 for conflicts; `--quiet` exits early.

**Prior art:**

| Tool | Approach |
|---|---|
| Copilot coding agent | one branch and one PR per task; cannot approve or merge; a human merges |
| Claude Code | `--worktree` and subagent `isolation: worktree`; no documented merge-back; "each teammate owns a different set of files" |
| Codex app | detached-HEAD worktrees with a manual handoff |
| Codex Cloud | the human commits or opens the PR |
| Devin | a coordinator "resolves conflicts" across isolated VMs (unspecified how) |

The common pattern is isolation per agent, human-merged PRs, and conflicts avoided by partitioning files.

**Evidence:**
- https://git-scm.com/docs/git-worktree and https://git-scm.com/docs/git-merge-tree (accessed 2026-10-09; DOC).
- https://docs.github.com/en/copilot/concepts/agents/coding-agent/risks-and-mitigations and /about-coding-agent (DOC).
- https://code.claude.com/docs/en/worktrees, /sub-agents, /agent-teams (DOC).
- https://developers.openai.com/codex/app/worktrees and /codex/cloud (DOC).
- https://docs.devin.ai/work-with-devin/advanced-capabilities (DOC; all accessed 2026-10-09).

**Confidence:** high for documented behaviour. Medium for "worktrees irrelevant across E2B".

**Implication for docs/80:** §5.1 invariant 1 **change (settles L.4)**:
- Sub-branch `lane/<NNN>/<role><n>` per lane.
- The `FeatureWorkflow` merge activity pre-checks with `merge-tree`; exit 1 is a lane failure charged to the budget, never auto-resolution.
- Partition lanes by disjoint paths.
- The final PR is human-merged.

§14.5 takeover **confirm**: a lane branch is a normal ref.

---

## 4.2 End-to-end sketch

This sketch is runnable in principle and **untested**: none of it was executed against a tenant. It is assembled from the researchers' snippets and reconciled to one set of conventions.

- **Package pin:** `microsoft-teams-apps==2.1.0`, which brings in `microsoft-teams-api` and `microsoft-teams-cards`. Python ≥3.11.
- **One persisted-row schema:** `ThreadRow` and `CardRef`, below. Items 2, 3 and 4 all use it.
- **Routing convention:** every `Action.Execute` carries `data.action`, and handlers use `@app.on_card_action_execute("<action>")`. SDK routed handlers match `data["action"]`, not `verb` (E.2). `verb` is kept for readability only.
- **Explicit credentials:** every `App(...)` passes `client_id`, `client_secret` and `tenant_id` explicitly. No `CLIENT_ID`-style env vars exist (K.3).

SDK citations refer to `microsoft/teams.py` at `v2.1.0`/`main@8539006` unless stated.

### Shared: persisted ids (D.1, D.4, E.3, E.6)

```python
# teams_store.py — one Postgres table pair on the orchestration host (docs/80 §10 item 4).
from typing import TypedDict

class ThreadRow(TypedDict):
    teams_thread_id: str          # "19:…@thread.tacv2;messageid=<root>"  (C.3) — the TeamsThreadId search attribute
    bot_app_id: str               # "28:<appId>" — part of the key until spike S-D4 shows ids are bot-independent (D.4)
    channel_conversation_id: str  # "19:…@thread.tacv2" (base, no ;messageid=)
    root_message_id: str          # numeric; == the board card's activity id, because the board IS the thread root (§6.1)
    service_url: str              # from the inbound activity; refreshed on every inbound activity (D.1)
    tenant_id: str                # channelData.tenant.id / conversation.tenantId (H.1)
    team_id: str                  # channelData.team.id  (Graph backfill, new roots)
    channel_id: str               # channelData.channel.id (channel↔repo map, deep links)

class CardRef(TypedDict):
    card_key: str                 # "board" | "gate:plan:2" | …
    teams_thread_id: str
    bot_app_id: str               # only the posting bot edits its card (E.3, INFER)
    conversation_id: str          # the id the card was POSTED TO (channel id for the root board, threaded id for replies) — INFER (E.3)
    activity_id: str              # SentActivity.id returned by send/reply
    service_url: str

# PRIMARY KEY (teams_thread_id, bot_app_id) on ThreadRow; (card_key, teams_thread_id, bot_app_id) on CardRef.
async def save_thread_row(row: ThreadRow) -> None: ...      # upsert; refresh service_url
async def load_thread_row(teams_thread_id: str, bot_app_id: str) -> ThreadRow: ...
async def save_card_ref(ref: CardRef) -> None: ...
async def load_card_ref(card_key: str, teams_thread_id: str, bot_app_id: str) -> CardRef: ...
```

### 1. Two `App` instances in one aiohttp process (B.6, K.3)

```python
# teams_host.py — mounts role bots into the existing webhook_bridge aiohttp app.
import os
from aiohttp import web
from temporalio.client import Client
from microsoft_teams.apps import App                                   # apps/__init__
from microsoft_teams.apps.http.adapter import (                        # http/adapter.py (HttpServerAdapter Protocol)
    HttpMethod, HttpRequest, HttpResponse, HttpRouteHandler,
)

class AiohttpAdapter:
    """Implements the HttpServerAdapter protocol; modelled on examples/http-adapters/src/starlette_adapter.py."""
    def __init__(self, web_app: web.Application) -> None:
        self._web_app = web_app

    def register_route(self, method: HttpMethod, path: str, handler: HttpRouteHandler) -> None:
        if method != "POST":                                           # HttpMethod = Literal["POST"]
            raise ValueError(f"unsupported method {method}")
        async def _route(request: web.Request) -> web.StreamResponse:
            try:
                body = await request.json()
            except ValueError:
                return web.Response(status=400)
            # HttpServer.handle_request = JWT validation (J.7) + activity pipeline (http/http_server.py)
            result: HttpResponse = await handler(HttpRequest(body=body, headers=dict(request.headers)))
            if result.get("body") is not None:
                return web.json_response(result["body"], status=result["status"])
            return web.Response(status=result["status"])
        self._web_app.router.add_post(path, _route)

    def serve_static(self, path: str, directory: str) -> None:        # optional; used by App.tab()/App.page()
        self._web_app.router.add_static(path.rstrip("/"), directory)

    async def start(self, port: int) -> None:                         # non-managed lifecycle: the bridge runs the server
        raise NotImplementedError("webhook_bridge owns the aiohttp server")

    async def stop(self) -> None:
        pass

TENANT_ID = os.environ["TEAMS_TENANT_ID"]

def make_role_app(role: str, adapter: AiohttpAdapter) -> App:
    # EVERY credential explicit: App._init_credentials falls back to CLIENT_ID/CLIENT_SECRET/TENANT_ID env (K.3).
    return App(
        client_id=os.environ[f"TEAMS_BOT_{role.upper()}_CLIENT_ID"],
        client_secret=os.environ[f"TEAMS_BOT_{role.upper()}_CLIENT_SECRET"],  # ClientCredentials (B.2)
        tenant_id=TENANT_ID,                                                 # single-tenant; never omit (B.2, J.7)
        http_server_adapter=adapter,                                         # AppOptions.http_server_adapter
        messaging_endpoint=f"/api/teams/{role}/messages",                    # distinct per App (K.3)
    )

async def build(web_app: web.Application, temporal: Client) -> dict[str, App]:
    adapter = AiohttpAdapter(web_app)
    apps = {r: make_role_app(r, adapter) for r in ("factory", "architect")}
    register_architect_handlers(apps["architect"])                       # item 2
    register_factory_handlers(apps["factory"], temporal)                 # item 3
    for a in apps.values():
        await a.initialize()       # registers POST route + validator; starts no server (app.py::initialize)
    return apps                    # must run BEFORE AppRunner.setup() freezes aiohttp's router (B.6, INFER)

async def main() -> None:
    web_app = web.Application(middlewares=[tenant_allow_list])          # J.7: our own tenant check (see below)
    # ... existing GitHub webhook routes are added here unchanged ...
    temporal = await Client.connect(os.environ.get("TEMPORAL_ADDRESS", "localhost:7233"))   # temporalio.client.Client
    await build(web_app, temporal)
    runner = web.AppRunner(web_app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.environ.get("TEAMS_ADAPTER_PORT", "3978"))).start()

@web.middleware
async def tenant_allow_list(request: web.Request, handler):
    # J.7: the SDK does no tenant allow-listing, and its Entra-issuer path's issuer check is tautological.
    # Body-level check (channelData.tenant.id / conversation.tenantId) is done again in handlers; this is the cheap
    # header gate (x-ms-tenant-id is present per build-conversational-capability, 2026-09-28). Spike S-J7.
    if request.path.startswith("/api/teams/") and request.headers.get("x-ms-tenant-id") not in (None, TENANT_ID):
        return web.Response(status=403)
    return await handler(request)
```

Each bot's registration (Teams-managed, or an Azure Bot for Factory) points its messaging endpoint at `https://<public-host>/api/teams/<role>/messages`. FastAPI and uvicorn are still installed and imported (B.6). Don't use `@app.func` on more than one App with the same name (K.3).

### 2. Receive an @mention in a channel thread and reply in that thread (C.3, C.5, H.1, K.2)

```python
# architect_handlers.py
from microsoft_teams.api import MessageActivity, MessageActivityInput
from microsoft_teams.api.activities.utils import StripMentionsTextOptions   # api tests test_message_activities.py L21
from microsoft_teams.apps import ActivityContext, App
from teams_store import ThreadRow, save_thread_row

OUR_BOT_IDS: set[str] = {"28:<factory-app-id>", "28:<architect-app-id>"}   # §6.5 self-filter (K.2)
OUR_TENANT = "<tenant-guid>"

def register_architect_handlers(app: App) -> None:
    @app.on_message                                                       # routing/generated_handlers.py
    async def on_message(ctx: ActivityContext[MessageActivity]) -> None:
        act = ctx.activity
        if act.from_.id in OUR_BOT_IDS:                                   # agents never read each other (§6.5)
            return
        cd = act.channel_data
        tenant = (cd.tenant.id if cd and cd.tenant else None) or act.conversation.tenant_id   # H.1
        if tenant != OUR_TENANT:
            return
        if not act.is_recipient_mentioned():                              # message.py L88; required if this bot has RSC (K.6)
            return
        act.strip_mentions_text(StripMentionsTextOptions(account_id=act.recipient.id))  # strip ONLY our mention (C.5)
        prompt = act.text or ""

        thread_id = ctx.conversation_ref.conversation.id                  # "19:…@thread.tacv2;messageid=<root>" (C.3)
        base, _, root = thread_id.partition(";messageid=")
        await save_thread_row(ThreadRow(
            teams_thread_id=thread_id,
            bot_app_id=act.recipient.id,                                  # "28:<appId>"
            channel_conversation_id=base,
            root_message_id=root or act.id,                               # root post: its own id (threading_handlers.py)
            service_url=ctx.conversation_ref.service_url,                 # app_process.py L121-130; refresh every time
            tenant_id=tenant,
            team_id=cd.team.id if cd and cd.team else "",                 # attribute names per channelData model (CODE; untested)
            channel_id=cd.channel.id if cd and cd.channel else "",
        ))
        # Identity for any follow-up authorization: (tenant, act.from_.aad_object_id) — never from_.id (H.1).
        answer = await answer_question(prompt, thread_id)                 # LiteLLM-routed conversational capability (§7.3)
        # In a channel, ctx.send posts into the CURRENT thread, no quote (activity_context.py L241; Teams SDK sending-messages)
        await ctx.send(MessageActivityInput(text=answer).add_ai_generated())   # AI label works in channels (C.4)
        # ctx.reply(answer) would post into the same thread with a visual quote (L276).
```

### 3. Post an Adaptive Card and update it in place, with gate decisions via `Action.Execute` (E.2, E.3, L.1)

```python
# factory_handlers.py — runs in the bridge (inbound invokes). Posting/updating from the worker is in item 4.
import json
from datetime import timedelta
from urllib.parse import quote
from microsoft_teams.api import (
    AdaptiveCardInvokeActivity, AdaptiveCardActionCardResponse, AdaptiveCardInvokeResponse, MessageActivityInput,
)                                                                          # api/models/adaptive_card/adaptive_card_action_response.py
from microsoft_teams.apps import ActivityContext, App
from microsoft_teams.cards import ActionSet, AdaptiveCard, ExecuteAction, Image, OpenUrlAction, TextBlock  # cards/core.py (Image kwargs untested)
from temporalio.client import Client, WorkflowUpdateFailedError, WorkflowUpdateRPCTimeoutOrCancelledError, WorkflowUpdateStage

TEAMS_APP_ID, TAB_ENTITY_ID, TENANT = "<factory manifest id>", "factory", "<tenant-guid>"

def tab_deep_link(sub_entity: str, channel_id: str) -> str:
    # E.6 format; static-tab channel targeting is UNVERIFIED (spike S-F7)
    ctx = quote(json.dumps({"subEntityId": sub_entity, "channelId": channel_id}))
    web = quote(f"https://tab.example.com/?sub={sub_entity}")
    return (f"https://teams.microsoft.com/l/entity/{TEAMS_APP_ID}/{TAB_ENTITY_ID}"
            f"?tenantId={TENANT}&webUrl={web}&label=Factory&context={ctx}")

def gate_card(feature: str, attempt: int, thread: str, channel_id: str, status: str | None = None,
              thumb_png_data_uri: str | None = None) -> AdaptiveCard:
    body = [TextBlock(text=f"Gate · Plan approval · {feature} · attempt {attempt}", weight="Bolder", wrap=True)]
    if thumb_png_data_uri:                    # E.4: PNG ≤1024², no SVG; data URI or unguessable no-redirect URL — not the SSO API
        body.append(Image(url=thumb_png_data_uri, alt_text="C4 container diagram"))
    actions = [OpenUrlAction(title="Open plan in tab", url=tab_deep_link(f"{feature}/plan/{attempt}", channel_id))]
    if status is None:
        data = {"gate": "plan", "feature": feature, "attempt": attempt, "thread": thread}
        actions = [
            ExecuteAction(title="Approve").with_verb("gate.decide")                      # verb: readability only
                .with_data({"action": "gate_decide", "decision": "approved", **data}),   # data.action: routing key (E.2)
            ExecuteAction(title="Request changes").with_verb("gate.decide")
                .with_data({"action": "gate_decide", "decision": "rejected", **data}),
            *actions,
        ]
    else:
        body.append(TextBlock(text=status, wrap=True))                                   # resolved: no decision buttons
    body.append(ActionSet(actions=actions))
    return AdaptiveCard(body=body)            # version defaults to "1.5" (cards/core.py) — Universal Actions minimum (E.1)

def register_factory_handlers(app: App, temporal: Client) -> None:
    @app.on_card_action_execute("gate_decide")                           # routing/activity_handlers.py — matches data["action"]
    async def on_gate(ctx: ActivityContext[AdaptiveCardInvokeActivity]) -> AdaptiveCardInvokeResponse:
        act = ctx.activity
        data = act.value.action.data                                       # {"action","decision","gate","attempt","thread"}
        actor = act.from_.aad_object_id                                    # H.1
        # Dedup key (J.3): teams:{reply_to_id}:{aadObjectId}:{attempt} -> bridge core DeliveryCache.reserve
        # Authorize (H.2/§13): aadObjectId -> linked github_login -> GitHub App collaborator permission (is_authorized)
        login = await linked_github_login(actor)                          # None -> return sign-in card instead
        wf_id = await resolve_gate_target(thread=data["thread"])           # TeamsThreadId = … AND ExecutionStatus='Running' (§10)
        try:
            # L.1: Update + validator rejects stale attempt / second decision; ACCEPTED keeps the invoke under 10–15 s (J.3).
            # Update name "plan_decide" is the proposed 008 handler (docs/80 §12.1); string-named update is INFER.
            await temporal.get_workflow_handle(wf_id).start_update(
                "plan_decide",
                {"decision": data["decision"], "attempt": data["attempt"],
                 "resolved_by": login, "via": "teams", "feedback": data.get("feedback")},  # Input.Text values merge into data
                wait_for_stage=WorkflowUpdateStage.ACCEPTED,
                rpc_timeout=timedelta(seconds=5),
            )
            status = f"✅ {data['decision']} by {login} via Teams"
        except WorkflowUpdateFailedError:                                   # validator rejected: stale/duplicate (L.1)
            status = "Already resolved or superseded"                       # real impl: query status() for "by X via Y"
        except WorkflowUpdateRPCTimeoutOrCancelledError:
            status = "Pipeline unavailable — try again"                     # worker down (L.1/L.2)
        resolved = gate_card(data["feature"], data["attempt"], data["thread"], act.channel_data.channel.id, status)
        # Everyone's view: edit the message holding the card (reply_to_id), inbound service_url bound to ctx.api (E.3)
        await ctx.api.conversations.update_activity(                        # conversation/client.py L299 (not deprecated accessor)
            act.conversation.id, act.reply_to_id, MessageActivityInput().add_card(resolved))
        # The actor's view: replace immediately via the invoke response (E.2)
        return AdaptiveCardActionCardResponse(value=resolved)

    @app.on_card_action_execute("board_refresh")                          # §14.1 board "Status"/refresh: data.action="board_refresh"
    async def on_board_refresh(ctx: ActivityContext[AdaptiveCardInvokeActivity]) -> AdaptiveCardInvokeResponse:
        board = await render_board_from_status_query(ctx.activity.value.action.data["thread"])   # @workflow.query status() (L.2)
        return AdaptiveCardActionCardResponse(value=board)
```

The edit-in-place half from the worker side (a "resolved by X via GitHub" decision, a board tick) is `update_card()` in item 4. The same `gate_card()` builder is used by the worker's `post_gate_card()` (item 4), so both surfaces render identical cards.

### 4. Proactive send from a separate function, standing in for a Temporal activity (D.1, D.3, D.4, E.3, J.1)

```python
# notify.py — worker host; only persisted ids + credentials. pip install microsoft-teams-apps==2.1.0
import os
from microsoft_teams.apps import App
from microsoft_teams.api import MessageActivityInput
from microsoft_teams.cards import AdaptiveCard
from teams_store import CardRef, ThreadRow, save_card_ref, save_thread_row

_apps: dict[tuple[str, str], App] = {}

async def _app_for(role: str, service_url: str) -> App:
    # One App per (bot, service_url): direct app.api.* calls use the App-level service URL (D.3 caveat, INFER).
    # The `service_url=` kwarg passed to update_activity in one researcher's snippet is UNVERIFIED, so it is not used here.
    key = (role, service_url)
    if key not in _apps:
        app = App(
            client_id=os.environ[f"TEAMS_BOT_{role.upper()}_CLIENT_ID"],
            client_secret=os.environ[f"TEAMS_BOT_{role.upper()}_CLIENT_SECRET"],
            tenant_id=os.environ["TEAMS_TENANT_ID"],
            service_url=service_url,                  # App-level service URL (app.py L117-119 fallback; kwarg per D.3 note)
        )
        await app.initialize()                        # no HTTP server (app.py::initialize; examples/proactive-messaging)
        _apps[key] = app
    return _apps[key]

async def create_board(row: ThreadRow, card: AdaptiveCard) -> ThreadRow:
    """New thread root (D.4): send to the BASE channel id. Untested — spike S-D4 (1)."""
    app = await _app_for("factory", row["service_url"])
    sent = await app.send(row["channel_conversation_id"],                 # app.py L353; no ;messageid= -> top-level post
                          MessageActivityInput().add_card(card),          # card-only: text+card splits, loses id (E.3)
                          service_url=row["service_url"])
    row = {**row, "root_message_id": sent.id,
           "teams_thread_id": f"{row['channel_conversation_id']};messageid={sent.id}"}
    await save_thread_row(row)
    await save_card_ref(CardRef(card_key="board", teams_thread_id=row["teams_thread_id"], bot_app_id=row["bot_app_id"],
                                conversation_id=row["channel_conversation_id"],   # posted-to id (INFER, E.3)
                                activity_id=sent.id, service_url=row["service_url"]))
    return row

async def notify_in_thread(role: str, row: ThreadRow, text: str) -> str:
    """Handoff / question-to-lead / presentation text into a known thread (D.3)."""
    app = await _app_for(role, row["service_url"])
    sent = await app.reply(row["channel_conversation_id"], row["root_message_id"],   # app.py L443-480, 3-arg form
                           MessageActivityInput(text=text).add_ai_generated(),       # C.4
                           service_url=row["service_url"])
    return sent.id

async def post_gate_card(row: ThreadRow, card: AdaptiveCard, card_key: str) -> None:
    app = await _app_for("factory", row["service_url"])
    sent = await app.reply(row["channel_conversation_id"], row["root_message_id"],
                           MessageActivityInput().add_card(card), service_url=row["service_url"])
    await save_card_ref(CardRef(card_key=card_key, teams_thread_id=row["teams_thread_id"], bot_app_id=row["bot_app_id"],
                                conversation_id=row["teams_thread_id"],   # reply was posted into the threaded id (INFER)
                                activity_id=sent.id, service_url=row["service_url"]))

async def update_card(ref: CardRef, card: AdaptiveCard) -> None:
    """Board tick or 'resolved by X via GitHub' (E.3). Only the posting bot (Factory) edits. Debounce + coalesce upstream."""
    app = await _app_for("factory", ref["service_url"])
    await app.api.conversations.update_activity(                          # PUT /v3/conversations/{id}/activities/{id}
        ref["conversation_id"], ref["activity_id"], MessageActivityInput().add_card(card))

# Wrap each call as a Temporal activity: retry 429/412/502/504 with jittered exponential backoff (J.1);
# 403 MessageWritesBlocked / BotDisabledByAdmin -> non-retryable (D.1); acquire the per-channel shared
# token bucket (≈10 sends / 2 s across ALL bots, K.4) before each send/update; assert the serialized activity
# is < 80 KB in UTF-16 (E.5) and degrade per §14.7.
```

### 5. TeamsJS static channel tab: SSO, our API, client-side mermaid (F.1–F.4, F.7, I.3)

```html
<!doctype html>
<!-- Served from https://tab.example.com/ (same fqdn as webApplicationInfo.resource and validDomains; F.2/F.3) with:
  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';
    img-src 'self' data:; connect-src 'self'; frame-src https://mocks.example-isolated.net;
    frame-ancestors https://teams.microsoft.com https://*.teams.microsoft.com https://*.cloud.microsoft
    https://*.microsoft365.com https://*.office.com https://outlook.office.com https://outlook.office365.com
  ('unsafe-inline' styles: mermaid injects <style> without nonce (F.4). connect-src may need the TeamsJS
   valid-origins CDN host — untested, spike (F.3).) -->
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Factory</title>
</head>
<body>
  <div id="status">Loading…</div>
  <div id="diagram"></div><!-- sibling-free container per diagram (CVE-2026-50159 workaround, F.4) -->
  <script type="module">
    // @microsoft/teams-js 2.58.0, self-hosted (F.3). APIs: app.initialize / app.getContext /
    // authentication.getAuthToken / app.notifySuccess (tab-sso-code, access-teams-context).
    import { app, authentication } from "/vendor/teams-js/2.58.0/MicrosoftTeams.esm.js";
    // mermaid pinned >= 11.16.1 (security floor; 12.x CVE status unconfirmed), SAME version as the server-side validator (F.4, I.1)
    import mermaid from "/vendor/mermaid/11.16.1/mermaid.esm.min.mjs";

    const status = (t) => { document.getElementById("status").textContent = t; };

    async function main() {
      await app.initialize();                      // TeamsJS >= 2.19 + initialize, else the page isn't displayed (F.3)
      const ctx = await app.getContext();          // NOT proof of identity (access-teams-context)
      const sub = ctx.page.subPageId || "";        // "{NNN-slug}/{view}[/{attempt}]" (docs/80 §8.2, F.7)
      const [feature, view = "architecture", attempt] = sub.split("/");

      // F.2: getAuthToken returns an access token for OUR API (aud = our client-id GUID). No OBO for our own API.
      const token = await authentication.getAuthToken();
      const qs = new URLSearchParams({ feature: feature || "", view, attempt: attempt || "",
                                       channel: ctx.channel?.id || "" });   // lookup hint only, never identity
      const res = await fetch(`/api/artifacts?${qs}`, { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) throw new Error(`artifact API ${res.status}`);
      const { mermaidSource, sha } = await res.json();  // .mmd read from git at a SHA (§7.4)

      mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });  // strict: DOMPurify, no click (F.4)
      await mermaid.parse(mermaidSource);               // throws on invalid input (flowchart; weak for C4 — I.1)
      const { svg } = await mermaid.render("arch-" + (sha || "x").slice(0, 7), mermaidSource);
      document.getElementById("diagram").innerHTML = svg;
      status(`${feature} · ${view} @ ${sha}`);
      app.notifySuccess();                              // only needed if showLoadingIndicator: true
    }

    main().catch((e) => {
      status("Could not load artifact: " + e);
      try { app.notifyFailure({ reason: app.FailedReason.Other, message: String(e) }); } catch {}
    });
  </script>
</body>
</html>
```

Server side of `/api/artifacts`, the validation contract from F.2 (INFER on library choice). This is an aiohttp handler in the bridge process.

```python
# artifact_api.py — validate the getAuthToken() access token (F.2), then serve git content at a SHA (§7.4).
import jwt  # PyJWT; TokenValidator.for_entra (A.3) could be reused instead — its call signature was not captured in the notes
from aiohttp import web

CLIENT_ID, TENANT = "<tab app client id>", "<tenant-guid>"
_jwks = jwt.PyJWKClient(f"https://login.microsoftonline.com/{TENANT}/discovery/v2.0/keys")   # Entra JWKS (INFER URL)

async def artifacts(request: web.Request) -> web.Response:
    raw = request.headers.get("Authorization", "").removeprefix("Bearer ")
    try:
        key = _jwks.get_signing_key_from_jwt(raw).key
        claims = jwt.decode(raw, key, algorithms=["RS256"],
                            audience=[CLIENT_ID, f"api://tab.example.com/{CLIENT_ID}"],   # GUID per sample; api:// defensively
                            issuer=f"https://login.microsoftonline.com/{TENANT}/v2.0")
    except jwt.PyJWTError:
        return web.Response(status=401)
    if "access_as_user" not in claims.get("scp", "").split():
        return web.Response(status=403)
    user = (claims["tid"], claims["oid"])          # identity from oid+tid, never preferred_username (F.2)
    # §13: channel membership — bot roster get_member_by_id (zero consent) or RSC TeamMember.Read.Group (H.3)
    # then read specs/NNN-slug/** at the SHA via the GitHub App installation token (§7.4)
    ...
```

Manifest fragment (Factory's app package; manifest ≥1.29 for targeted sign-in cards, ≥1.16 for static channel tabs):

```json
{
  "manifestVersion": "1.30",
  "bots": [{ "botId": "<factory-app-id>", "scopes": ["team", "personal"] }],
  "staticTabs": [{ "entityId": "factory", "name": "Factory", "contentUrl": "https://tab.example.com/",
                   "websiteUrl": "https://tab.example.com/", "scopes": ["team"], "context": ["channelTab"] }],
  "validDomains": ["tab.example.com", "mocks.example-isolated.net", "token.botframework.com"],
  "webApplicationInfo": { "id": "<factory-app-id>", "resource": "api://tab.example.com/botid-<factory-app-id>" },
  "authorization": { "permissions": { "resourceSpecific": [
    { "name": "ChannelMessage.Read.Group", "type": "Application" },
    { "name": "TeamMember.Read.Group", "type": "Application" } ] } }
}
```

Notes on the manifest:
- `"personal"` scope on Factory is included only in case spike S-H2 shows that GitHub sign-in must start in a personal chat (INFER).
- The `botid-` Application ID URI applies because the tab ships in the same package as the Factory bot (F.2).
- In that case the tab's `CLIENT_ID` above is Factory's bot app id. If the tab ships in its own app instead, use `api://tab.example.com/<clientId>` and that app's id.

---

## 4.3 Risks and unknowns

No finding **blocks** the design: every unknown below has a documented fallback. A finding is ranked **changes design** where the outcome alters a docs/80 section, and **detail** where it alters only implementation.

| # | Risk / unknown | Severity | Contradicts §1.3? | Proposed spike or action |
|---|---|---|---|---|
| R1 | The thread conversation id may be **per bot**. The doc says both "unique for each agent within a specific channel" and "channelId is global" (D.4). | changes design (§10 key becomes per-bot) | no | **S-D4**: bare-channel `send` returns root; a second bot `reply`s into it; compare inbound ids |
| R2 | Channel sign-in for GitHub linking: Learn says sign in via a personal chat first, while SDK 2.1 sends a targeted OAuthCard in-channel (H.2). | changes design (linking UX, Factory personal scope) | no | **S-H2** on an Azure Bot registration |
| R3 | No positive doc that Teams-managed bots support proactive sends, `Action.Execute` and RSC. The researchers disagree on whether each role needs an Azure Bot (B.1, K.1). | changes design (§15 footprint: up to 6 Azure Bots) | no | **S-B1** |
| R4 | Deep link into a **static** tab pinned in a channel is unverified; the docs say `channelId` is for configurable tabs (E.6, F.7). | changes design (card buttons → Stageview/`websiteUrl`) | no | **S-F7** on desktop, web, iOS, Android |
| R5 | Nested `sandbox="allow-scripts"` iframe from an isolated origin is undocumented on all clients (F.5). | changes design (mock viewing) | partly decision 5 (mocks) | **F.5 spike**; ship "open in browser" first |
| R6 | Cross-bot card actions: where an invoke on a Designer-posted card goes, and whether only the posting bot can edit it (E.3, K.6, H.2 gap). | changes design (§14.4) | no | **S-E3x**; fallback is Factory posting the gate buttons |
| R7 | The Entra-issuer inbound path accepts any tenant whose token carries our audience. TDP apps are `AzureADMultipleOrgs` and the SDK has no tenant allow-list (J.7). | changes design (middleware) | no | **S-J7** |
| R8 | Shared channels don't support bots, and agents can't post in private channels (C.1). | changes design (standard channel only) | no | config rule |
| R9 | Parent continue-as-new terminates lanes under the default `TERMINATE` policy (L.1). | changes design (§5) | no | `ABANDON` + deterministic ids; `WorkflowEnvironment` test |
| R10 | Updates need a live worker; signals don't (L.1). | changes design (bridge behaviour) | no | `start_update(ACCEPTED, rpc_timeout)`; queue/retry |
| R11 | Mermaid C4 cannot be validated by parse, and there is no Python parser (I.1). | changes design (§9.1) | no | Structurizr or flowchart; LLM pass-rate eval in 010 |
| R12 | Card images can't require auth or redirect (E.4). | changes design (§14.3 image source) | no | data URI or unguessable URL |
| R13 | Six apps mean six Entra apps, six registrations, six secrets to rotate, six admin uploads and installs, with no bundle (K.1, K.5, J.5). | changes design (ops) | no (decision 2 holds) | packaging and bootstrap scripts |
| R14 | `App` env fallbacks and import-time `load_dotenv` can silently merge identities (K.3). | changes design (config rule) | no | explicit kwargs; no generic env |
| R15 | Graph `/replies` protected-API status is unknown (C.2). | detail if the own thread log is used; changes design otherwise | no | call `/replies` with an RSC-consented app (403 vs 200) |
| R16 | Bot-to-bot delivery is undocumented (K.2). | detail | no | **S-K2** (with/without RSC, with/without mention) |
| R17 | Inbound duplicate delivery is undocumented; duplicates confirmed only for token exchange (J.3). | detail | no | record inbound ids under load |
| R18 | Same-task decision serialization through the validator is inferred from code (L.1). | detail | no | `WorkflowEnvironment` unit test in 008 |
| R19 | No support horizon for `microsoft-teams-apps`; high churn inside 2.x (A.2). | detail / watch | no | pin `==2.1.0`; budget upgrades |
| R20 | TeamsJS ≥2.56 may fetch valid-origins from a CDN, so a strict `connect-src` could break init (F.3). | detail | no | strict-CSP smoke test |
| R21 | Mermaid 12.x: release dates inconsistent, CVE-2026-50159 fix unconfirmed (F.4 vs I.1). | detail | no | check npm/advisory before moving off 11.16.1 |
| R22 | `Table` element on Teams mobile is unconfirmed (§14.1 uses it) (E.1). | detail | no | mobile render test; ColumnSet fallback |
| R23 | Typing indicator in channels unconfirmed (C.4). | detail | no | none needed |
| R24 | No documented TTL for `serviceUrl` or conversation id (D.1). | detail | no | refresh `service_url` on every inbound activity |
| R25 | Which events RSC adds beyond messages; RSC consent wording conflict (C.1, K.5). | detail | no | have a team owner install |
| R26 | `ChannelMember.Read.Group` documentation conflict (H.3). | detail | no | don't declare it; use roster or `TeamMember.Read.Group` |
| R27 | No built-in certificate credential; non-Azure FIC unverified (B.2). | detail | no | MSAL-certificate `TokenCredentials` spike |
| R28 | Agents Playground fidelity for channel threads and `Action.Execute` (J.6). | detail | no | try in 008 |
| R29 | Compose runs the deprecated, unpinned `temporalio/auto-setup:latest` (L.1). | detail (ops) | no | pinned `temporalio/server` + `admin-tools` |
| R30 | Chromium renderer cost (4.03 GB Structurizr image or puppeteer); whether the E2B template has Chromium (I.1, I.2). | detail | no | `playwright install --with-deps chromium` in the template |
| R31 | Mobile deep links for custom/org-catalog apps (docs cover Store apps) (E.6, F.6). | detail | no | device test |
| R32 | Rate-limit "thread": channel vs reply chain; 1,800/h note ambiguous; SDK auto-retry not checked (J.1, K.4). | detail | no | size the limiter to the channel |
| R33 | Missing channel-endorsement check on Connector tokens (J.7). | detail | no | none (audience pinned) |
| R34 | GitHub user-token refresh behaviour unknown (H.2). | detail (design avoids it) | no | — |
| R35 | Figma has no documented headless or service-account path (I.2). | detail (option rejected) | no | — |
| R36 | Socket Mode works only on canary rings (prod 503) (B.3). | detail / future | no | watch |
| R37 | Spec Kit local 0.13.0 vs upstream 1.1.2 (L.3). | detail | no | decide the bump before 012 |
| R38 | The "agentic user" identity model (`agenticUserTemplates`, Agent 365) is unexplored (K.7, A.2). | detail | no | optional spike if per-instance identities are ever wanted |
| R39 | Teams AI v1 formal status (maintenance vs inactive vs "deprecated") (A.1). | detail | no | none; not used |

On the §1.3 decisions: **none is made impossible.**
- Decision 2 is satisfiable only as six separate apps.
- Decision 5 holds for spec, plan and diagrams; mocks depend on R5.
- Decision 6 requires the workflow-side Update/validator change.
- Decision 7 is confirmed (GA 2026-05-01, 2.1.0 current).
- Decision 8 is confirmed (L.4).

---

## 4.4 Question → docs/80 section map

The first two columns are the prompt's map, unchanged. The third adds the sections these findings also touch, so the folding pass doesn't miss them.

| Letter | docs/80 sections it feeds | Also touched by these findings |
|---|---|---|
| A | §7 system architecture, §15 hosting, §16 phasing | §7.4 (tab helpers, `TokenValidator.for_entra`) |
| B | §7, §15 | §13 (Azure Bot for OAuth), §16 (Socket Mode watch, dev loop) |
| C | §6 chat protocol, §7 conversation handling | §10 (`TeamsThreadId` format), §14 (AI label, feedback, citations) |
| D | §7 outbound notifier, §10 correlation | §6.1 (board as thread root), §15 (install prerequisites) |
| E | §12 decisions across surfaces, §14 cards & UX | §6.1 (board updates), §8.2 (deep links), §9.1 (PNG only) |
| F | §7 artifact service, §8 artifact model (tab) | §15 (static tab, CSP, origins, SSO audience), §14.4 (Stageview) |
| G | §8 | §1.4 (record rejected options), §14.4 ("open in browser" first) |
| H | §13 identity & authorization | §11 N14, §15 (OAuth connection, `validDomains`) |
| I | §9 new producers | §15 (Chromium renderer), §17 Q9 |
| J | §14, §15 | §7.2 (dedup keys), §13 (tenant allow-list), §16 (Playground, pin) |
| K | §2 team roster, §7 | §6.3/§6.5 (routing, self-filter), §14 (instance label), §15 (6 apps, bootstrap) |
| L | §4 concurrency, §5 lane model | §12.1 (Update + validator), §12.5/N2 (Query), §14.5 (takeover), §15 (Temporal image), §16 (Spec Kit version) |
