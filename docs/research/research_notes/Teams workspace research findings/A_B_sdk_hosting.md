# Teams SDK for Python: lineage, registration and self-hosting (A.1–A.4, B.1–B.6, J.7, K.3)

Researched 2026-10-09. Format: research prompt §4.1 (Answer / Evidence / Confidence / Implication), plus a **Gaps** line where something could not be confirmed.

**Source pinning used throughout**
- `microsoft/teams.py`: shallow clone of `main` at commit `8539006` (2026-10-07). File dates below are last-touch dates in that clone. A date of `≤2026-06-15` means the file has not changed since at least the shallow-clone boundary. All of these files are post-GA.
- `microsoft/teams-sdk` (the docs site source for microsoft.github.io/teams-sdk): clone of `main` at `0187ab0` (2026-10-08). Every docs page cited was last touched 2026-10-08, and I give that date as the page's "last updated". GitHub paths are given because the rendered site has no per-page dates.
- PyPI JSON API and GitHub Releases API, both queried 2026-10-09.
- Labels: **DOC** means a primary doc says it. **CODE** means I read it in SDK source or samples. **INFER** is my own reasoning.

---

## A. SDK lineage

### A.1 Relationship and support status of the four SDKs
**Answer:**
- **Teams SDK v2** (formerly "Teams AI Library v2", renamed "Teams SDK") is the current, actively developed Teams-first framework. It has separate repos per language: `teams.ts`, `teams.net`, `teams.py`.
- **Teams AI Library v1** is in maintenance. It lives on a `release/v1` branch that gets "critical bug fixes and security patches". Its PyPI package `teams-ai` is still published (1.8.2, 2026-06-17) but carries the classifier `Development Status :: 7 - Inactive`.
- **Bot Framework SDK** (`botbuilder-python`) is end-of-support. Support tickets stopped 2025-12-31 and the repo was archived (read-only) on 2026-01-05. Its last PyPI release is `botbuilder-core` 4.17.1 (2026-01-05).
- **Microsoft 365 Agents SDK** is the other supported SDK, positioned by Microsoft as "first-class" alongside Teams SDK:
  - The Agents SDK targets **breadth**: Azure Bot Service, multi-channel (Teams, M365 Copilot, Copilot Studio, WebChat).
  - Teams SDK targets **depth**: the "Teams Bot Service" plus Teams-native features such as mentions, threaded/quoted replies, channel events, targeted messages, citations, AI label, feedback, message extensions and dialogs.
  - The Agents SDK is also the official migration target named in the archived Bot Framework repo.
  - Its Python packages are current: `microsoft-agents-hosting-core` and `microsoft-agents-hosting-aiohttp` 1.8.0 (2026-10-01).
- Teams SDK's AI helper layer has been dropped. `ChatPrompt`, OpenAI model, MCP plugin and A2A plugin are deprecated in TS/.NET and **already removed in Python**. Microsoft now recommends pairing Teams SDK with an external agent framework.

**Evidence:**
- Bot Framework archival: https://github.com/microsoft/botbuilder-python (archive banner "archived by the owner on Jan 5, 2026"; README: "Support tickets for the Bot Framework SDK will no longer be serviced as of December 31, 2025"; points to the Agents SDK; accessed 2026-10-09; DOC).
- Teams AI v1 maintenance: https://github.com/microsoft/teams-ai README ("previous main branch (v1) has been moved to the release/v1 branch… We will continue to provide critical bug fixes and security patches for v1"; accessed 2026-10-09; DOC).
- PyPI `teams-ai` 1.8.2, uploaded 2026-06-17, classifier "7 - Inactive" (https://pypi.org/project/teams-ai/, accessed 2026-10-09; DOC).
- A Learn search snippet says "Teams AI library v1 is deprecated" (https://learn.microsoft.com/en-us/microsoftteams/platform/teams-sdk/). I did not see that sentence on the fetched landing page (ms.date 2026-02-25, updated_at 2026-07-28), so treat it as snippet-sourced and medium confidence.
- Rename: https://github.com/microsoft/teams-sdk/blob/main/README.md ("'Teams AI' is now officially 'Teams SDK'"; accessed 2026-10-09; DOC).
- Positioning of Teams SDK vs Agents SDK: https://github.com/microsoft/teams-sdk/blob/main/teams.md/docs/main/teams/choosing-an-sdk.md (rendered at microsoft.github.io/teams-sdk/teams/choosing-an-sdk; last updated 2026-10-08; DOC). Key passages:
  - "Microsoft offers two supported, actively-developed SDKs…"
  - "Microsoft positions both as first-class."
  - Rule of thumb: "if your bot uses most of the Teams-native set above, the Teams SDK is the right home."
  - Teams SDK talks to "Teams Bot Service"; Agents SDK talks to "Azure Bot Service".
  - Bot Framework migration: either migrate to Agents SDK, or "host legacy in Teams SDK" via a compat package. The Python compat package is `microsoft-teams-botbuilder`, which depends on `botbuilder-core>=4.14.0` and `botbuilder-integration-aiohttp>=4.17.0` (CODE: `packages/botbuilder/pyproject.toml`). Those packages are archived and end-of-support, so the compat path means taking on an EOL dependency (INFER).
- AI helpers removed: https://github.com/microsoft/teams-sdk/blob/main/teams.md/blog/2026-06-16-ai-libs-to-agent-frameworks/index.md (2026-06-16; DOC): "deprecated in TypeScript and .NET, and already removed in Python." This matches the v2.0.0 release notes: PR #406 "Deprecate ai, openai, mcpplugin, and a2a packages" and PR #413 "remove ai, openai, mcpplugin, a2a, and devtools packages" (https://github.com/microsoft/teams.py/releases/tag/v2.0.0, published 2026-05-06; DOC).
- Agents SDK Python versions: PyPI JSON for `microsoft-agents-hosting-aiohttp` 1.8.0, uploaded 2026-10-01 (accessed 2026-10-09; DOC).

**Confidence:** high for Bot Framework end-of-support, the rename, and the Teams SDK / Agents SDK positioning. Medium for the formal "deprecated" status of Teams AI v1: the repo says maintenance, PyPI says Inactive, and the Learn "deprecated" wording comes only from a search snippet.

**Implication for docs/80:**
- §7 and §16: confirm Teams SDK v2 as the base and drop any botbuilder or teams-ai v1 option.
- New note for §7: Teams SDK no longer ships an AI/agent layer in Python. That fits our design, because Claude Agent SDK and Temporal own agent logic and the Teams SDK is only transport, cards and routing.

**Gaps:** I found no published end-of-life date for Teams AI v1 and no LTS policy for Teams SDK v2 (see A.2).

### A.2 Python package names, GA date, current version, support horizon, parity
**Answer:**
- **Packages** (all require Python `>=3.11,<4.0`):
  - `microsoft-teams-apps` is the main one.
  - It pulls in `microsoft-teams-api` and `microsoft-teams-common`.
  - The others are `microsoft-teams-cards`, `microsoft-teams-graph` (optional extra `[graph]`, wraps `msgraph-sdk>=1.30,<2`), `microsoft-teams-botbuilder` (compat layer) and `microsoft-teams-m365extensions`.
- **GA date: confirmed as 2026-05-01, with nuance.**
  - The `2.0.0` wheel went to PyPI on 2026-04-30T23:09Z, which is still 2026-04-30 in US Pacific time.
  - The announcement blog is dated 2026-05-01.
  - The GitHub release object `v2.0.0` was published 2026-05-06.
- **Current version: 2.1.0** (PyPI and GitHub, 2026-09-16). `main` is versioned `2.2.0-dev.{height}`. Patch line: 2.0.11 (05-15), 2.0.12 (05-27), 2.0.13 (06-08), 2.0.14 (07-08), 2.0.15 (08-04), 2.0.16 (08-19). Preview releases `2.1.0a1` and `a2` came out in August.
- **Support horizon:** not published anywhere I looked (GA blog, repo README, RELEASE.md references, docs site).
- **Parity:** the GA blog claims "the same SDK surface… across our TypeScript and .NET stacks". The repo and docs show these differences:
  1. **Browser-side tab library `@microsoft/teams.client`** is TS-only. It is inherently JS, and the Python tab sample itself uses it.
  2. **Typed Graph packages:** `teams.ts` has `graph-endpoints`, `graph-endpoints-beta` and `graph-tools`. Python instead wraps Microsoft's `msgraph-sdk`.
  3. **`@microsoft/teams.config`:** a TS package with no Python counterpart.
  4. **AI, OpenAI, MCP and A2A helpers:** still shipped (deprecated) in TS/.NET, removed from Python.
  5. **DevTools:** marked obsolete in TS/.NET, already removed from Python and PyPI.
  6. **Docs-level gaps:**
     - The tabs guide (including "functions") declares `languages: ['typescript', 'csharp']`.
     - There is no Python include for `observability/opentelemetry`, even though Python ships a `diagnostics/` telemetry module (CODE).
     - `choosing-an-sdk.md` says agentic identity via Agent365 is "coming soon to Teams SDK", yet Python already exposes `AgenticIdentity` and `get_agentic_identity()` (CODE, `app.py`). The documented status is unclear.
- **Same in all three languages:** Socket Mode (experimental) exists in Python (`socket_mode/`, CODE) and also in teams.ts and teams.net (GitHub code search hits; teams.py commit #625 aligns with teams.net#693).

**Evidence:**
- Package list and Python requirement: `packages/*/pyproject.toml` in https://github.com/microsoft/teams.py/tree/8539006 (apps pyproject last touched 2026-09-24; CODE).
- PyPI release history for `microsoft-teams-apps` (https://pypi.org/pypi/microsoft-teams-apps/json, accessed 2026-10-09; DOC): 0.0.1a1 on 2025-08-21 → 2.0.0a1 on 2025-09-18 → … → 2.0.0a78 on 2026-04-25 → **2.0.0 on 2026-04-30T23:09:23Z** → … → **2.1.0 on 2026-09-16**. Every pre-May-2026 alpha is **PRE-GA**.
- GitHub releases: https://github.com/microsoft/teams.py/releases (v2.0.0 published 2026-05-06T18:39Z; v2.1.0 published 2026-09-16; DOC).
- GA blog: https://devblogs.microsoft.com/microsoft365dev/python-support-for-the-microsoft-teams-sdk-is-now-generally-available/ (2026-05-01; DOC). It says "generally available", names `microsoft-teams-apps` and claims "same SDK surface". It gives no version, LTS or support horizon.
- `version.json` on `main`: `"version": "2.2.0-dev.{height}"` (CODE).
- TS package directories via the GitHub API on `microsoft/teams.ts/packages` (accessed 2026-10-09; CODE): `ai api apps botbuilder cards client common config dev devtools graph-endpoints-beta graph-endpoints graph-tools graph m365extensions openai`.
- Tabs guide front-matter: https://github.com/microsoft/teams-sdk/blob/main/teams.md/src/pages/templates/in-depth-guides/tabs/README.mdx (`languages: ['typescript', 'csharp']`; 2026-10-08; DOC).
- DevTools removal: https://github.com/microsoft/teams-sdk/blob/main/teams.md/blog/2026-06-04-devtools-to-agents-playground/index.md (2026-06-04; DOC): "for Python the package has already been removed from PyPI".
- Leftover README text: the teams.py README still says "Agent 365 support is being developed on this integration branch" on `main` (CODE). This looks like stale text.

**Confidence:**
- High on package names, versions and dates.
- Medium on the parity list. It comes from package and docs inventories; I did not diff the APIs symbol by symbol, and the .NET repo layout could not be listed via the API.

**Implication for docs/80:**
- §15 and §16: pin `microsoft-teams-apps==2.1.*` and require Python ≥3.11.
- New risk for §16: there is no stated support horizon, and churn is high. In five months there were ~10 releases, including deprecations inside 2.x: `default_connection_name` was deprecated in 2.1 in favour of `add_oauth_flow()`, and `skip_auth` was renamed to `dangerously_allow_unauthenticated_requests`. Budget for upgrades.

**Gaps:** support/LTS policy; a symbol-level parity diff against .NET.

### A.3 Does the Python SDK do anything for tabs?
**Answer:** It does so **server-side only**:
1. **`App.tab(name, path)` / `App.page(name, dir_path, page_path)`** serve a static directory (for example a built SPA) at `/tabs/<name>/` through the HTTP adapter's `serve_static`.
2. **`@app.func`** registers `POST /api/functions/<name>` "remote functions" that a tab calls. Each request is authenticated with an **Entra ID bearer token**, validated by `TokenValidator.for_entra(client_id, tenant_id, application_id_uri=…)`:
   - accepted audiences: `client_id`, `api://client_id`, `api://botid-client_id`, plus the optional `application_id_uri`, which "matches webApplicationInfo.resource in the app manifest";
   - required token claims: `oid`, `tid`, `name`;
   - required headers: `X-Teams-App-Session-Id` and `X-Teams-Page-Id`.

   The handler gets a `FunctionContext` that can `send()` to the conversation.
3. **No OBO helper for tab SSO.** The only `on_behalf_of` in the Python source is the Agent 365 agentic-user FIC flow (`token_manager.py`), not a tab-token exchange. If our API needs to call Graph or GitHub as the user, the OBO exchange is ours to write (for example with MSAL).

Everything client-side (TeamsJS, MSAL/NAA, consent) is the **TS** `@microsoft/teams.client` package or plain TeamsJS. The Python tab sample uses a Vite/React frontend with `@microsoft/teams.client ^2.0.9`. Socket Mode disables all of this, because there is no HTTP listener.

**Evidence:**
- `packages/apps/src/microsoft_teams/apps/app.py`: `page()`, `tab()`, `func()` (2026-09-29; CODE).
- `packages/apps/src/microsoft_teams/apps/auth/remote_function_jwt_middleware.py` (≤2026-06-15; CODE).
- `packages/apps/src/microsoft_teams/apps/auth/token_validator.py`: `for_entra` (2026-08-03; CODE).
- `options.py`: `application_id_uri` docstring (2026-09-29; CODE).
- `examples/tab/src/main.py` and `examples/tab/Web/package.json` (CODE).
- Tabs docs scope TS/C# only: https://github.com/microsoft/teams-sdk/blob/main/teams.md/src/components/include/in-depth-guides/tabs/typescript.incl.md (2026-10-08; DOC).
- Socket Mode limitation: `options.py` docstring "HTTP-only features (`app.function()`, tabs, OAuth redirect routes) have no listener" (CODE).

**Confidence:** high on what exists. Medium on how well it fits our tab, since the Python tab path is not documented on the docs site.

**Implication for docs/80:**
- §7 artifact service and §8: we can serve the tab bundle and an authenticated API from the same Python process as the bot, using `app.tab()` + `@app.func`, or use our own aiohttp routes and reuse `TokenValidator.for_entra` to validate the SSO token. Feeds F.2.
- The client side stays TeamsJS (or `@microsoft/teams.client`).
- Confirms decision 7 ("TeamsJS for the tab").

### A.4 Which SDK for a new Python bot in late 2026
**Answer:** Use **Teams SDK for Python (`microsoft-teams-apps` 2.1.x)**.
- Our design needs the Teams-depth features that Microsoft's own decision guide assigns to Teams SDK: channel threads, @mentions, card actions, proactive threaded replies, and targeted messages.
- Bot Framework is archived, and Teams AI v1 is inactive or maintenance-only.
- The **M365 Agents SDK** (`microsoft-agents-hosting-aiohttp` 1.8.0) is the credible alternative. It is natively aiohttp, which suits `webhook_bridge`, and is multi-channel, but it covers only the "cross-channel essentials" in Teams.

Downsides of Teams SDK:
- It is young (GA 2026-05-01) with no published support horizon.
- It hard-depends on FastAPI and uvicorn even when unused (see B.6).
- Python is behind TS/.NET in docs coverage (tabs, OTel).

**Evidence:** choosing-an-sdk.md, Bot Framework archive, teams-ai PyPI classifier, PyPI Agents SDK (all in A.1); `packages/apps/pyproject.toml` deps (CODE).

**Confidence:** medium-high. The recommendation follows Microsoft's own rule of thumb applied to our feature list. The Agents SDK's Teams-specific gaps were not verified against its own docs.

**Implication for docs/80:**
- §7, §15, §16: confirm decision 7 (Teams SDK for Python).
- Record the Agents SDK as the fallback if Teams SDK's FastAPI coupling or churn becomes a problem.

**Gaps:** I did not read Agents SDK Python docs for threaded replies or targeted messages, so I can't say exactly what we would lose.

---

## B. Registration & hosting

### B.1 Azure Bot resource vs Teams Developer Portal (Teams-managed) registration
**Answer:**
- There are two bot-registration "locations":
  - **Teams-managed:** registered via the Teams Developer Portal (TDP) API. This is the default for `teams app create`.
  - **Azure Bot:** an Azure Bot Service resource in your own subscription.
- The Teams SDK docs state that **the only thing Teams-managed cannot do is OAuth connections and SSO** (the Bot Service token store). Otherwise Teams-managed is "No Azure subscription needed… Works for production too, as long as you don't need OAuth/SSO."
- Nothing in either doc says proactive messaging or Adaptive Card actions (`Action.Submit` / `Action.Execute` invokes) need Azure. Those are ordinary activities and Connector calls, so a **Teams-managed** bot should suffice for channel bots with proactive messaging and card actions (INFER).
- **But** H.2 (linking a Teams user to GitHub via a Bot Service OAuth connection) *does* need an Azure Bot. You can switch later with `teams app bot migrate`, which keeps the same `CLIENT_ID`, `CLIENT_SECRET`, `TENANT_ID` and manifest bot id. The M365 Extensions channel and calling endpoint must be re-set after migration.
- Both locations need an Entra app registration.
- The Teams SDK docs talk to "Teams Bot Service"; the Azure path is "Azure Bot Service" (A.1).

**Evidence:**
- https://github.com/microsoft/teams-sdk/blob/main/teams.md/docs/cli/concepts/bot-locations.md (rendered microsoft.github.io/teams-sdk/cli/concepts/bot-locations; 2026-10-08; DOC). Quote: "Use Azure only when your bot needs **OAuth or SSO** — that's the one thing Teams-managed can't do."
- https://github.com/microsoft/teams-sdk/blob/main/teams.md/docs/cli/commands/app/bot-migrate.md (2026-10-08; DOC).
- https://github.com/microsoft/teams-sdk/blob/main/teams.md/docs/cli/concepts/tdp-portal.md (2026-10-08; DOC): `app create` does "4. Registers the bot (via TDP or Azure)".
- Azure path: https://github.com/microsoft/teams-sdk/blob/main/teams.md/docs/main/teams/azure-configuration.mdx (2026-10-08; DOC).

**Confidence:**
- High that Teams-managed lacks only OAuth/SSO, per the docs.
- Medium that proactive messaging and card actions work there. This is inferred from the absence of any restriction; I found no positive statement.

**Implication for docs/80:**
- §15: Teams-managed registration needs no Azure subscription and is enough for Phase 1.
- New dependency for §13/§16: GitHub identity linking via Bot Service OAuth (H.2) forces an Azure Bot resource (a subscription, though not Azure compute) for every bot that does sign-in. Consider doing sign-in on only one bot (Coordinator) to limit this to one Azure Bot.

**Gaps:** I found no doc stating per-feature support (proactive, `Action.Execute`, RSC) for Teams-managed bots, and no SLA statement for Teams-managed in production.

### B.2 Entra app setup: tenancy and credential types; which work off-Azure
**Answer:**
- **Tenancy:**
  - Azure Bot Service: "**Multi-tenant bot creation will be deprecated after July 31, 2025**." Existing multi-tenant bots keep working; new bots must be **single-tenant** or **user-assigned managed identity**.
  - Teams SDK manual setup creates the Azure Bot with `--app-type SingleTenant`.
  - Nuance: the Teams CLI/TDP creates the *Entra app* with `signInAudience: AzureADMultipleOrgs` while registering the *bot* with `isSingleTenant: true`. The docs say `AzureADMyOrg` "causes service principal creation to fail silently" on that path.
  - The SDK treats a missing `TENANT_ID` as multi-tenant and logs "TENANT_ID is not set, assuming multi-tenant app". **Always set `tenant_id`.**
- **Credential types in the Python SDK** (CODE, `microsoft_teams.api.auth.credentials`):
  - `ClientCredentials`: client secret, through MSAL `ConfidentialClientApplication`.
  - `TokenCredentials`: any callable or `TokenProviderProtocol` that returns a token for `(scope, tenant_id)`.
  - `ManagedIdentityCredentials`: user-assigned MI, through MSAL `ManagedIdentityClient`.
  - `FederatedIdentityCredentials`: an MI assertion exchanged for the app's token (FIC), system- or user-assigned MI.
  - There is **no built-in certificate credential.**
- **Off Azure compute:**
  - Client secret works.
  - Certificate auth or federated credentials from a *non-Azure* IdP (Kubernetes or GitHub OIDC) work only through `TokenCredentials` wrapping your own MSAL `ConfidentialClientApplication(client_credential={"private_key":…, "thumbprint":…})` or a client-assertion callable (INFER; not documented by Teams SDK).
  - Managed identity and FIC as implemented need an Azure MI endpoint. The FIC doc lists "A compute resource where your bot will be hosted (App Service, Container App, VM, etc.)" and says "The identity you select here must also be assigned to the compute resource." So they **do not work self-hosted** (DOC + CODE).
- **Precedence in `App._init_credentials`:** secret → token → MI/FIC, and every field falls back to environment variables (see K.3).

**Evidence:**
- https://learn.microsoft.com/en-us/azure/bot-service/bot-service-quickstart-registration (ms.date 2024-10-09, updated_at 2026-09-01; DOC). By ms.date this is **PRE-GA** Bot Framework-era content, but it still applies: the Teams SDK targets the same Bot Connector token issuer and scopes (`api.botframework.com`) and the Teams SDK's own 2026-10-08 docs also prescribe single-tenant. The same page claims single-tenant/UAMI types are "not supported in … Dev Tunnels". That conflicts with the Teams SDK docs, which recommend Dev Tunnels with single-tenant bots; I treat it as stale Bot Framework-tooling text (INFER).
- https://github.com/microsoft/teams-sdk/blob/main/teams.md/docs/cli/concepts/aad-apps.md (2026-10-08; DOC): AzureADMultipleOrgs + `isSingleTenant: true`; "A service principal is required for single-tenant bot registration (SFI requirement)."
- https://github.com/microsoft/teams-sdk/blob/main/teams.md/docs/main/teams/app-authentication/federated-identity-credentials.md (2026-10-08; DOC).
- App-auth overview lists only secret, UAMI and FIC: https://github.com/microsoft/teams-sdk/blob/main/teams.md/docs/main/teams/app-authentication/README.mdx (2026-10-08; DOC).
- Code: `packages/api/src/microsoft_teams/api/auth/credentials.py` (2026-08-03), `packages/apps/src/microsoft_teams/apps/app.py::_init_credentials` (2026-09-29), `token_manager.py` (imports `ConfidentialClientApplication`, `ManagedIdentityClient`) (CODE).

**Confidence:**
- High on the multi-tenant deprecation and on the credential classes.
- Medium on the certificate-via-`TokenCredentials` route. It is plausible from the type signature but no sample exists.

**Implication for docs/80:**
- §15: each role bot gets a single-tenant registration with a client secret, stored as a docker-compose secret.
- New risk for §15: secret rotation ×6 bots, and no first-class certificate support.
- Spike: a `TokenCredentials` + MSAL certificate provider.

**Gaps:** I found no Teams SDK doc on certificate or workload-identity-federation credentials, and did not verify whether Entra FIC with a non-Azure issuer works for the `api.botframework.com` scope.

### B.3 Messaging endpoint requirements
**Answer:**
- **Public internet, HTTPS.** "Teams… deliver requests from their own servers… your endpoint must be reachable on the public internet over HTTPS."
- **TLS certificate:** the Connector expects X.509v3 TLS on all service-to-service hops, and "Client certificates are NOT used." A publicly trusted server certificate behind our reverse proxy is required (INFER from DOC).
- **Method and path:** the SDK registers only `POST <messaging_endpoint>` (default `/api/messages`, configurable).
- **IP allow-listing is not the documented control; JWT validation is (J.7).**
  - An Azure service tag `AzureBotService` exists ("Both" directions, usable inbound). Its CIDRs are published as a weekly JSON download for on-prem firewalls.
  - **No doc says Teams-managed ("Teams Bot Service") traffic originates from `AzureBotService` ranges**, so an IP allow-list could break delivery.
- **Socket Mode (experimental) removes the inbound endpoint entirely:** the bot dials out over WebSocket/SignalR. Today it works only on the Canary/Pilot1 rings: "the production default returns 503". It is classic-bot-identity only, and the HTTP features (tabs, functions, OAuth callbacks) are unavailable.

**Evidence:**
- https://github.com/microsoft/teams-sdk/blob/main/teams.md/docs/main/developer-tools/local-tunnels.md (2026-10-08; DOC).
- https://learn.microsoft.com/en-us/azure/bot-service/rest-api/bot-framework-rest-connector-authentication (ms.date 2024-10-09 **PRE-GA**, updated_at 2026-09-01; still applies because the SDK implements this exact scheme, see J.7; DOC).
- https://learn.microsoft.com/en-us/azure/virtual-network/service-tags-overview (ms.date 2026-09-16; DOC): row "AzureBotService | Azure Bot Service. | Both | No | Yes"; weekly JSON downloads.
- `http/http_server.py::initialize` (`register_route("POST", self._messaging_endpoint, …)`) (2026-08-03; CODE).
- Socket Mode: `options.py` docstring (CODE) and `examples/socket/README.md`, commit `8539006` (2026-10-07; DOC/CODE): "Socket Mode is currently available only on the Canary … and Pilot1 … rings; the production default returns 503."

**Confidence:** high on HTTPS and public reachability; low on IP allow-listing (no Teams-specific statement found).

**Implication for docs/80:**
- §15: expose exactly the per-bot `POST` paths through the reverse proxy with a public certificate. Do not rely on IP allow-lists. Keep JWT validation on.
- New watch item for §16: once Socket Mode reaches production it could remove the public ingress (but not for tabs).

**Gaps:** source IP ranges for Teams-managed bot traffic; Socket Mode production timeline.

### B.4 Local development loop
**Answer:** There are three loops, from lightest to heaviest:
1. **Microsoft 365 Agents Playground (no Azure, no tenant, no credentials).**
   - Install with `npm i -g @microsoft/m365agentsplayground`, then run `agentsplayground -e http://localhost:3978/api/messages -c msteams`. The UI is at `localhost:56150`. It can mock arbitrary activity types (installs, invokes, reactions).
   - It sends **unauthenticated** requests. The SDK **rejects** those by default, so set `App(dangerously_allow_unauthenticated_requests=True)` (or the env var `DANGEROUSLY_ALLOW_UNAUTHENTICATED_REQUESTS`) for local runs only.
   - The 2026-06-04 blog claims the SDK accepts unauthenticated requests automatically when no credentials are set. The current docs and current code (`http_server.py` returns `401 "Authentication not configured"`) **contradict** it, so the blog is stale.
2. **Real Teams client without an Azure subscription.**
   - Requires an M365 tenant that allows custom app upload, a Teams-managed registration (`teams app create --endpoint https://<tunnel>/api/messages --env .env` with the Teams Developer CLI `@microsoft/teams.cli@preview`), and a **Dev Tunnel** (`devtunnel create <id> --allow-anonymous`, `port create -p 3978`, `host`). The tunnel gives a persistent HTTPS hostname. ngrok and Cloudflare Tunnel are named as substitutes.
3. **Socket Mode (experimental):** no tunnel, but only on the canary/pilot1 rings.

Other tools:
- **Teams SDK DevTools:** *gone for Python*. The package was removed at 2.0.0 (PRs #381/#413) and from PyPI. The 2026-06-04 blog replaces it with Agents Playground. The Learn mirror of the Teams SDK docs still lists DevTools pages (updated_at 2026-07-28), so it lags.
- **M365 Agents Toolkit (formerly Teams Toolkit):** Learn presents it as the IDE path that "abstracts much of the manual setup of the Azure Bot Service and Azure App registrations". The Teams SDK docs now steer to the Teams CLI and the `teams-dev` agent skill instead. I did not confirm Toolkit templates for Teams SDK Python.

**Minimal loop needing no Azure subscription:** loop 1, or loop 2 if you need the real Teams client.

**Evidence:**
- https://github.com/microsoft/teams-sdk/blob/main/teams.md/docs/main/developer-tools/agents-playground/README.md (2026-10-08; DOC): "By default the SDK **rejects** unauthenticated requests…"
- https://github.com/microsoft/teams-sdk/blob/main/teams.md/blog/2026-06-04-devtools-to-agents-playground/index.md (2026-06-04; DOC, partly stale as noted).
- https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/test-with-toolkit-project (ms.date 2026-07-24, updated_at 2026-10-01; DOC): Playground "supports both anonymous and authenticated modes. For anonymous testing, no other configuration is required."
- local-tunnels.md (B.3).
- bot-locations.md (B.1).
- `http/http_server.py` (CODE).
- v2.0.0 release notes (A.1).

**Confidence:** high.

**Implication for docs/80:**
- §15 and §16: the Phase-1 dev loop is Playground plus `dangerously_allow_unauthenticated_requests=True`. Guard it so it can never be on in the deployed compose file, for example by refusing to start if set while `ENV=prod`.
- Integration tests in the real Teams client use a Teams-managed registration and a persistent dev tunnel per developer.

**Gaps:** Agents Toolkit support for Teams SDK Python projects; whether `devtunnel` login needs anything beyond an MSA, Entra or GitHub account (not fetched).

### B.5 Self-hosting with no Azure compute; what Azure remains mandatory
**Answer:** **Yes, the bot can be self-hosted**, for example in docker-compose next to Temporal. The SDK is a plain Python ASGI/HTTP handler: it calls the Bot Connector at `smba.trafficmanager.net/teams` and fetches keys from `login.botframework.com`. Nothing in it requires Azure compute.

What remains mandatory:
1. **An Entra ID app registration per bot**, in a Microsoft Entra tenant. This is an identity-platform object, not an Azure subscription resource. "Every Teams bot needs an Azure Active Directory (AAD) app registration."
2. **A bot registration per bot.** Either **Teams-managed** (no Azure subscription) or an **Azure Bot resource** (needs a subscription and resource group). The Azure Bot is required only for OAuth connections and SSO.
3. **A public HTTPS endpoint per bot route** (B.3), unless Socket Mode reaches production.
4. **Outbound egress** to `login.microsoftonline.com` (tokens), `login.botframework.com` (JWKS), and the activity's `serviceUrl` (for example `smba.trafficmanager.net`). Graph egress is needed if used.

Credentials must be a client secret (or a custom `TokenCredentials` provider); MI and FIC don't apply off-Azure (B.2).

**Evidence:**
- aad-apps.md and bot-locations.md (B.1/B.2).
- `app.py` default `service_url` `https://smba.trafficmanager.net/teams` (CODE).
- `cloud_environment.py` `PUBLIC` (`login_endpoint`, `openid_metadata_url=https://login.botframework.com/v1/.well-known/openidconfiguration`, `bot_scope=https://api.botframework.com/.default`) (CODE).

**Confidence:**
- High that no Azure compute is needed.
- High that Entra plus a bot registration are mandatory.
- Medium that Teams-managed is production-grade: the docs say so but give no SLA.

**Implication for docs/80:**
- §15: confirm self-hosting next to Temporal.
- The Azure footprint is 6 Entra apps + 6 Teams-managed bot registrations. Add +1 Azure Bot (subscription) only if we adopt Bot Service OAuth for GitHub linking (H.2).
- Changes §15's "what Azure is mandatory" list from "Azure Bot resource" to "Entra app (+ Azure Bot only for OAuth/SSO)".

### B.6 Mounting `App` inside an existing aiohttp app (webhook_bridge)
**Answer:** **Yes, through the `HttpServerAdapter` protocol. There is no aiohttp adapter in the box, but writing one is about 25 lines.**

How the HTTP layer works:
- `App(http_server_adapter=…)` accepts any object with `register_route(method, path, handler)`. `serve_static`, `start` and `stop` are optional.
- `HttpServer` (owned by `App`, "Not a plugin") calls `adapter.register_route("POST", messaging_endpoint, self.handle_request)` during `await app.initialize()`.
- The handler is framework-agnostic: `HttpRequest = {body: dict, headers: dict}` maps to `HttpResponse = {status: int, body: object}`.
- `handle_request` runs JWT validation (J.7), then the activity pipeline, and returns the invoke response, for example the card-action result.
- The **non-managed** pattern is officially supported: "`app.initialize()` + start server yourself". The adapter's `start()` default raises "This adapter does not support managed server lifecycle. Start the server yourself."
- The shipped example `examples/http-adapters/src/starlette_adapter.py` is the template to copy.

Caveats:
1. **FastAPI and uvicorn are hard dependencies** of `microsoft-teams-apps` (`fastapi>=0.115.13`, `uvicorn>=0.34.3`). `app.py` imports `FastAPIAdapter` at module import time, so they get installed and imported even when unused. If you don't pass an adapter, `App` silently creates its own `FastAPIAdapter()`, which is harmless if never started.
2. **`HttpMethod = Literal["POST"]`.** The SDK registers only POST routes. GET routes for the tab are added by `serve_static`.
3. **aiohttp freezes its router at `AppRunner.setup()`**, so `await app.initialize()` must run *before* the runner is set up, not in `on_startup` (INFER from aiohttp semantics).
4. Each `App` defaults to `/api/messages`. With several apps on one adapter, set distinct `messaging_endpoint` values (K.3).
5. The `aiohttp` package already appears in the teams.py lockfile (Dependabot bump in 2.1.0 notes). It most likely comes in via `microsoft-teams-botbuilder`'s `botbuilder-integration-aiohttp` dependency rather than `apps` (INFER).
6. Alternative: the M365 Agents SDK ships `microsoft-agents-hosting-aiohttp` natively (A.4).

**Evidence:**
- `packages/apps/src/microsoft_teams/apps/http/adapter.py` (≤2026-06-15; CODE). Protocol: `register_route` "Required"; `serve_static` "Optional — no-op by default"; `start` "Optional — raises if not implemented".
- `http/http_server.py` (2026-08-03; CODE).
- `http/fastapi_adapter.py` (≤2026-06-15; CODE).
- `app.py` lines ~126-129: `adapter = self._socket_mode or self.options.http_server_adapter or FastAPIAdapter()` (2026-09-29; CODE).
- `app.py::initialize` docstring: "allowing you to use app.send() for proactive messaging without running a server" (CODE).
- `examples/http-adapters/README.md` table "Managed vs Non-Managed", plus `starlette_adapter.py` and `fastapi_non_managed.py` (≤2026-06-15; CODE).
- `packages/apps/pyproject.toml` dependencies (2026-09-24; CODE).

**Confidence:** high on the mechanism (read in source, with an official non-FastAPI adapter example). Medium on the aiohttp adapter below, which is my code and has not been run.

**Implication for docs/80:**
- §7: confirm that the Teams bots can live inside `webhook_bridge`'s aiohttp process. No second server is needed.
- Note the FastAPI/uvicorn transitive dependencies in §15.
- Feeds §4.2 item 1 (snippet below).

---

## J.7 Inbound JWT validation: what is automatic, what we must configure

**Answer:** Validation is **automatic** once `client_id` is set and `dangerously_allow_unauthenticated_requests` is false. `HttpServer.handle_request` runs `InboundActivityTokenValidator`, and **it behaves differently by token issuer**.

**Bot Connector tokens** (classic bots; `TokenValidator.for_service`) are checked against the Learn Connector→Bot list:

| Learn requirement | SDK behaviour |
|---|---|
| (1) Bearer header | Checked. A missing or malformed header returns **401**. |
| (2) Well-formed JWT | Checked. |
| (3) `iss == https://api.botframework.com` | Checked. |
| (4) `aud` equals the app id | Checked. The SDK accepts `[app_id, api://app_id, api://botid-app_id]`. |
| (5) Validity period, 5-minute skew | Checked: `exp`/`iat` with `JWT_LEEWAY_SECONDS = 300`. |
| (6) Signature | Checked: RS256 against keys from `https://login.botframework.com/v1/.well-known/keys`. The keys URL is derived by regex from the OpenID metadata URL rather than read from the metadata document. |
| (7) `serviceurl` claim matches the activity body's `serviceUrl` | Checked, with trailing slashes normalised. |
| **Channel endorsements** (reject with 403 if the key lacks a `msteams` endorsement) | **Not implemented.** `grep -rn endorse` over the packages returns nothing (CODE). |

Further notes on the Connector path:
- The SDK returns **401** on any failure, where the Learn page says 403.
- Check (7) runs only when a service URL is available: `handle_request` passes `body.get("serviceUrl")`, and `_validate_service_url` is skipped when that and the `service_url` option are both empty. An activity with no `serviceUrl` therefore skips check (7) (CODE).
- Key caching is delegated to PyJWT's `PyJWKClient`, built with defaults. In PyJWT `master` (read 2026-10-09) the defaults are `cache_jwk_set=True, lifespan=300`, so the JWKS is re-fetched at most every 5 minutes. That satisfies Learn's "refresh … at least once every 24 hours".
- I read PyJWT `master`, not the exact installed `pyjwt>=2.12.0`, so those defaults are not verified for the pinned version.
- `PyJWKClient` fetches synchronously (urllib), so a cache-miss fetch blocks the event loop briefly (INFER).

**Entra-issued tokens** (Agent 365 / "Agent ID" activities; `iss` starts with `login.microsoftonline.com` or `sts.windows.net`):
- The validator **reads `tid` from the unverified token**, then builds `TokenValidator.for_entra(app_id, tid)`. It caches up to 100 tenants.
- The issuer check is therefore **tautological**: it accepts any tenant's issuer that matches the token's own `tid`.
- The audience must still be our app id.
- `serviceurl` is **not** checked. Source TODO: "Agent ID inbound Entra tokens currently do not include serviceurl".
- Risk (**INFER, needs a spike**). TDP-created Entra apps are `AzureADMultipleOrgs` (B.2). Any tenant that provisions a service principal for our app could therefore mint an app-only token with `aud=<our app id>` and pass this path. Mitigations:
  - add a tenant allow-list middleware that checks `activity.conversation.tenantId` / `channelData.tenant.id` against our tenant;
  - and/or make the Entra app single-org if the TDP path permits it.

**What we must configure when self-hosting:**
- **Credentials:** set `client_id` (+ secret or token provider) per App. Without it, every request is rejected with `401 "Authentication not configured"`.
- **`tenant_id`:** set it per App. Otherwise the app is treated as multi-tenant.
- **Cloud:** correct `cloud` (or `CLOUD` env), defaulting to Public.
- **Outbound egress** to `login.botframework.com`.
- **Never set `DANGEROUSLY_ALLOW_UNAUTHENTICATED_REQUESTS`** in prod.
- **Tenant and installation authorization** is ours. The SDK does no tenant or team allow-listing.
- **Remote functions / tab APIs:** these use a separate validator (`entra_token_validator`) that also needs `tenant_id`. With `tenant_id=None` it logs "Issuer validation will be skipped, accepting tokens from any tenant."

**Evidence:**
- `packages/apps/src/microsoft_teams/apps/auth/token_validator.py` (2026-08-03; CODE).
- `http/http_server.py` (2026-08-03; CODE).
- `api/auth/cloud_environment.py` `PUBLIC` (CODE).
- PyJWT `jwks_client.py` on master: https://github.com/jpadilla/pyjwt/blob/master/jwt/jwks_client.py (read 2026-10-09; CODE).
- https://learn.microsoft.com/en-us/azure/bot-service/rest-api/bot-framework-rest-connector-authentication (ms.date 2024-10-09, **PRE-GA** but still the governing spec; updated_at 2026-09-01; DOC).
- The v2.0.0 release notes show the hardening history: PR #370 "Security hardening: token validation and service URL improvements", PR #415 "Revert serviceUrl allowlist" (DOC).

**Confidence:**
- High on what the code does.
- Medium on the exploitability of the Entra-path observation (not tested).

**Implication for docs/80:**
- §13 and §15: keep SDK validation on.
- Add our own tenant allow-list middleware, via `app.use(...)` or an aiohttp middleware in front.
- Note the missing endorsement check, a minor gap since the audience is pinned.
- Add a spike on the Entra inbound path. Severity: changes design, as a small middleware addition.

---

## K.3 One Python process hosting N `App` instances

**Answer:** **Supported in practice. No blocking global state was found.** Everything that matters is per instance:
- router, event emitter, OAuth registry;
- `TokenManager`/`AppTokenProvider` (holding that App's credentials);
- `ApiClient`, `HttpServer` (with its own `InboundActivityTokenValidator` bound to that App's `client_id`);
- plugin processor and default `LocalStorage`;
- the dependency-injector `Container()` instance (set via `set_provider` on the instance).

The only module-level state is:
- immutable constants (`_CLOUD_ENVIRONMENTS`, the env-value sets in `options.py`);
- a `NullHandler` on the package logger;
- `load_dotenv(find_dotenv(usecwd=True))`, which runs **at import of `microsoft_teams.apps.app`**. It walks up from CWD and loads a `.env` into `os.environ`. This is a process-wide side effect on the webhook_bridge host. That it does not override existing variables is python-dotenv's default `override=False` (INFER; I did not read python-dotenv source).

The real hazards are **environment fallbacks**:
- `App._init_credentials` does `self.options.client_id or os.getenv("CLIENT_ID")`. The same pattern applies to `CLIENT_SECRET`, `TENANT_ID` and `MANAGED_IDENTITY_CLIENT_ID`.
- The constructor also reads `CLOUD` and `SERVICE_URL`, and `DANGEROUSLY_ALLOW_UNAUTHENTICATED_REQUESTS` is read in `options.py`.
- So two Apps built with a missing kwarg **silently share one identity or one tenant**. Pass every credential kwarg explicitly, and keep `CLIENT_ID`/`CLIENT_SECRET`/`TENANT_ID` *out* of the process environment and out of any `.env` reachable from the CWD.

Routing:
- All Apps default to `messaging_endpoint="/api/messages"`. Give each its own path.
- Each `HttpServer` registers only its own route, so sharing **one** adapter (one aiohttp `web.Application`) between Apps works when paths differ (CODE: `HttpServer(adapter, messaging_endpoint=…)` per App; `initialize()` guarded per HttpServer).
- `app.tab()`/`app.page()` paths (`/tabs/<name>/`) are global to the adapter, so tab names must not collide across Apps.
- **`@app.func` routes collide too.** `App.func` registers the fixed path `POST /api/functions/<name>` and ignores `messaging_endpoint` (CODE, `app.py`). If two Apps on one adapter both define a function with the same name, the path is registered twice. aiohttp's `add_post` does not reject the duplicate; the first route wins and the second is silently shadowed (INFER, not tested). Use unique function names per role, or serve tab APIs from our own aiohttp handlers that reuse `TokenValidator.for_entra` (see A.3).

Other notes:
- Socket Mode instances are per App, but Socket Mode excludes custom adapters.
- Each App does its own token acquisition and JWKS fetches, so N=6 means 6 token caches and 6 `PyJWKClient`s. That is fine at our scale (INFER).

**Evidence:**
- `app.py` `App.__init__`, `_init_credentials`, module-level `load_dotenv` (2026-09-29; CODE).
- `options.py` env helper (`os.getenv` in `_env_bool`-style helper, line ~31) (CODE).
- `container.py` (DeclarativeContainer instantiated per App) (CODE).
- `http/http_server.py` (CODE).
- grep across `apps/src`, `api/src`, `common/src` for `global`, module-level mutable `_x = {}/[]`, `lru_cache`, `ContextVar`, `_instance =`: no hits besides the constants (CODE, 2026-10-09).
- There is no official multi-App sample. `examples/http-adapters` shows a single App with a user-provided server (CODE).

**Confidence:**
- High that there is no shared global state.
- Medium overall, because I found no sample or test that runs two Apps in one process, and I have not executed the snippet.

**Implication for docs/80:**
- §2 and §7: confirm decision 2 (one bot per role) can be served from one aiohttp process. Each role gets its own route (`/api/teams/<role>/messages`) and that path is registered as its bot's messaging endpoint.
- New rule for §15: explicit credential kwargs only, and no generic `CLIENT_ID`-style env vars in the bridge environment.

---

## Code sketch: two `App`s in one aiohttp process (feeds §4.2 item 1)

Runnable in principle. It has not been executed. Each SDK API is cited.

```python
# teams_host.py  — mounts N Teams bots into the existing webhook_bridge aiohttp app.
import os
from aiohttp import web
from microsoft_teams.api import MessageActivity, MessageActivityInput          # api pkg
from microsoft_teams.apps import App, ActivityContext                            # apps/__init__
from microsoft_teams.apps.http.adapter import (                                  # http/adapter.py
    HttpMethod, HttpRequest, HttpResponse, HttpRouteHandler,
)

class AiohttpAdapter:
    """HttpServerAdapter (runtime_checkable Protocol, http/adapter.py) for an existing aiohttp app.
    Modelled on examples/http-adapters/src/starlette_adapter.py."""

    def __init__(self, web_app: web.Application) -> None:
        self._web_app = web_app

    def register_route(self, method: HttpMethod, path: str, handler: HttpRouteHandler) -> None:
        if method != "POST":                     # HttpMethod = Literal["POST"]
            raise ValueError(f"unsupported method {method}")

        async def _route(request: web.Request) -> web.StreamResponse:
            try:
                body = await request.json()
            except ValueError:
                return web.Response(status=400)
            # HttpServer.handle_request does JWT validation + dispatch (http/http_server.py)
            result: HttpResponse = await handler(HttpRequest(body=body, headers=dict(request.headers)))
            if result.get("body") is not None:
                return web.json_response(result["body"], status=result["status"])
            return web.Response(status=result["status"])

        self._web_app.router.add_post(path, _route)

    def serve_static(self, path: str, directory: str) -> None:   # used by App.tab()/App.page()
        self._web_app.router.add_static(path.rstrip("/"), directory)

    async def start(self, port: int) -> None:                    # non-managed: bridge owns lifecycle
        raise NotImplementedError("webhook_bridge runs the aiohttp server")

    async def stop(self) -> None:
        pass


def make_role_app(role: str, adapter: AiohttpAdapter) -> App:
    # Pass EVERY credential explicitly: App._init_credentials falls back to CLIENT_ID/CLIENT_SECRET/TENANT_ID env vars.
    return App(
        client_id=os.environ[f"TEAMS_{role.upper()}_CLIENT_ID"],
        client_secret=os.environ[f"TEAMS_{role.upper()}_CLIENT_SECRET"],   # -> ClientCredentials
        tenant_id=os.environ["TEAMS_TENANT_ID"],                          # single-tenant
        http_server_adapter=adapter,                                      # AppOptions.http_server_adapter
        messaging_endpoint=f"/api/teams/{role}/messages",                 # AppOptions.messaging_endpoint
    )


async def build(web_app: web.Application) -> dict[str, App]:
    adapter = AiohttpAdapter(web_app)
    apps = {r: make_role_app(r, adapter) for r in ("factory", "architect")}

    @apps["architect"].on_message                     # routing/generated_handlers.py
    async def on_architect_msg(ctx: ActivityContext[MessageActivity]) -> None:
        # ctx.send(): "In channels, sends to the current thread" (routing/activity_context.py)
        await ctx.send(f"Architect saw: {ctx.activity.text!r}")

    # Must run BEFORE aiohttp's AppRunner.setup() freezes the router.
    for a in apps.values():
        await a.initialize()       # registers POST route + JWT validator; no server started (app.py)
    return apps


async def main() -> None:
    web_app = web.Application()          # in reality: the existing webhook_bridge app with its GitHub routes
    apps = await build(web_app)
    runner = web.AppRunner(web_app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 8088).start()
    # ... run forever

# Proactive send from a Temporal activity (separate process): build an App with the same explicit
# kwargs, `await app.initialize()` (no server needed per its docstring), then:
#   await app.send(conversation_id, "text" | AdaptiveCard, service_url=stored_service_url)      # app.py
#   await app.reply(conversation_id, root_message_id, activity)  # threads via to_threaded_conversation_id
#   await app.api.conversations.update_activity(conversation_id, activity_id, MessageActivityInput(...))
#        (examples/proactive-messaging/src/main.py::send_and_update_proactive_message)
```

Notes on the sketch:
- Each bot's registration (TDP/Azure) must point its messaging endpoint at `https://<public-host>/api/teams/<role>/messages` (INFER).
- `App(...)` with no adapter would silently create an unused `FastAPIAdapter`. Passing ours avoids that, but FastAPI and uvicorn are still installed and imported (B.6).
- In the worker-side `App`, `initialize()` registers its route on a default `FastAPIAdapter` that never starts. That is harmless.
- If the two Apps use `@app.func`, give the functions distinct names: `/api/functions/<name>` is shared across Apps on one adapter (see K.3).

---

## Cross-cutting risks found (for §4.3)

| Risk | Severity | Source |
|---|---|---|
| GitHub identity linking via Bot Service OAuth needs an **Azure Bot resource** (subscription), not Teams-managed. | changes design (§13/§15) | bot-locations.md (DOC) |
| No published support horizon or LTS for Teams SDK Python; high release churn inside 2.x. | detail / watch | PyPI, releases (DOC) |
| `App` env-var fallbacks (`CLIENT_ID`, `TENANT_ID`, …) plus import-time `load_dotenv` can make N apps share an identity silently. | changes design (config rule) | app.py (CODE) |
| Entra-issuer inbound path accepts any tenant whose token has `aud=<our app>`; no tenant allow-list in the SDK; TDP apps are `AzureADMultipleOrgs`. | changes design (add middleware); needs spike | token_validator.py (CODE) + aad-apps.md (DOC) |
| No channel-endorsement check on Connector tokens. | detail | token_validator.py (CODE) vs Learn (DOC) |
| FastAPI and uvicorn are mandatory dependencies even when mounted in aiohttp. | detail | apps/pyproject.toml (CODE) |
| Docs drift: the Learn mirror of the Teams SDK still lists DevTools, A2A and MCP; the 2026-06-04 blog's "no credentials ⇒ accepted" claim contradicts current code. | detail (cite the GitHub docs source, not the Learn mirror) | (DOC/CODE) |
| Teams-managed traffic source IPs undocumented, so don't IP-allow-list. | detail | service-tags page (DOC), gap |
| Socket Mode (no public ingress) works only on canary/pilot1 rings; prod returns 503. | detail / future option | examples/socket README (DOC) |
