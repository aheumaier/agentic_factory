# Identity linking, multi-bot packaging, manifest, distribution and testing (H.2, H.3, J.4, J.5, J.6, K.1, K.5, K.7)

Researcher notes for `docs/research/teams-workspace-research-prompt.md`, folded into
`docs/80-teams-workspace-design.md` §2, §7, §13, §14, §15. Accessed 2026-10-09.

**How to read the labels.**
- **DOC**: a primary source says it.
- **CODE**: read in `microsoft/teams.py` at commit `8539006` (2026-10-07) or in the published manifest JSON schemas.
- **INFER**: my own reasoning.
- **PRE-GA**: the source's `ms.date` is before 2026-05. Each one is followed by a note on whether it still applies.

**Version pins.**
- `microsoft-teams-apps` **2.1.0**, published to PyPI 2026-09-16. Earlier releases: 2.0.16 on 2026-08-19, 2.0.14 on 2026-07-08 (CODE: PyPI JSON).
- Teams app manifest schema: **v1.30** is the newest published. `https://developer.microsoft.com/json-schemas/teams/v1.31/MicrosoftTeams.schema.json` returns 404 (probed 2026-10-09).

The answers below are in letter order (H, J, K), using the §4.1 format. Each entry also has a **Gaps** line.

---

### H.2 Linking a Teams user to a GitHub login (Bot Service OAuth connection / token store)

**Answer:**

*Mechanism*
- It works through an **OAuth connection setting on each Azure Bot resource**.
- The Bot Framework Token Service runs the OAuth dance and stores the user token.
- The bot asks for the token by connection name. If none is stored, it sends an OAuthCard sign-in card.

*How the Python SDK exposes it (2.1)*
- Register the connection with `app.add_oauth_flow(connection_name, oauth_card_text=…, sign_in_button_text=…)`.
- Start sign-in with `await flow.sign_in(ctx)`. It returns the token if one is cached. Otherwise it sends the card and returns `None`.
- Completion arrives in `@flow.on_signin`, with the token at `event.token_response.token`. Failures arrive in `@flow.on_signin_failure`.
- Also available: `flow.get_token(ctx)` and `flow.sign_out(ctx)`.
- `ctx.sign_in()` / `default_connection_name` are the deprecated 2.0 style.

*GitHub as the provider*
- Microsoft docs name GitHub as a supported third-party provider for this mechanism.
- If no named provider fits, the generic **"Oauth 2 Generic Provider"** lets you template the authorize, token and refresh URLs and bodies.

*Teams SSO does not help*
- Bot SSO exists only for Microsoft Entra ID.
- It is "not supported in channel scope".
- So GitHub always needs a **separate OAuthCard sign-in**.

*What the SDK does in a channel*
- It deliberately leaves out the SSO `tokenExchangeResource`.
- It sends the OAuthCard as a **targeted message**, visible only to the requesting user.

*Token refresh*
- The only primary guidance found is "if the bot has an expired user token… log the user out [and] initiate the sign-in flow again".
- The generic-provider form has Refresh URL and body templates, so the Token Service can call a refresh endpoint. I could not confirm when it actually refreshes.

*Design consequence: sign-in is per bot*
- The Token Service stores tokens "for a particular bot, channel, conversation, and user".
- The SDK looks the token up by `from.id` + `channel_id` + connection name.
- With one bot per role (K.1: one bot per app), a lead could be asked to sign in to GitHub once **per bot**, unless gate decisions go through a single bot.

**Evidence:**
- https://microsoft.github.io/teams-sdk/python/in-depth-guides/user-authentication (no date shown; accessed 2026-10-09; DOC)
  - Documents `add_oauth_flow`, `sign_in`, `on_signin`, `on_signin_failure`, `sign_out` and `get_graph_client(token)`.
  - Quote: "it is possible to authenticate the user into other auth providers like Facebook, Github, Google, Dropbox".
  - Regional token endpoints are set through `OAUTH_URL`, e.g. `https://europe.token.botframework.com/.auth/web/redirect`.
  - It does not cover token refresh.
- `packages/apps/src/microsoft_teams/apps/oauth_flow.py` (CODE)
  - `OAuthFlow.sign_in`, `sign_out`, `get_token`, `on_signin` and `on_signin_failure` exist.
  - `connection_name` is normalized per flow.
- `packages/apps/src/microsoft_teams/apps/routing/activity_context.py`, lines 377–452 (CODE)
  - `ctx.sign_in` is marked deprecated in favor of `app.get_oauth_flow(name).sign_in(ctx, options)`.
  - It calls `api.users.get_token(GetUserTokenParams(channel_id, user_id=activity.from_.id, connection_name))`.
  - On 404 it fetches `api._bots.sign_in.get_resource(state)`.
  - Then `is_group → recipient.is_targeted = True`.
  - Then `token_exchange_resource = None if is_channel`.
  - Code comment: "Channels cannot perform the silent SSO token exchange, so the token exchange resource is omitted there to render the sign-in button (OAuth card flow)".
  - `examples/oauth/src/main.py` shows two named connections on one `App`.
- https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/authentication/bot-sso-overview (ms.date 2026-08-27; DOC)
  - The page is titled "Enable SSO with Microsoft Entra ID".
  - Quote: "SSO for a bot app in Teams is supported in one-on-one and group chat scope, and not supported in channel scope."
- https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/authentication/add-authentication (ms.date 2026-04-14, updated_at 2026-06-30; DOC; PRE-GA by ms.date but refreshed after GA, and its samples are Teams SDK `bot-auth-quickstart/python`, so it still applies)
  - OAuth Connection Settings live on the Azure Bot resource.
  - The manifest needs `validDomains: ["token.botframework.com"]`.
  - The redirect URI is `https://token.botframework.com/.auth/web/redirect`.
  - Quote: "OAuth isn't supported in the group chat or channel scopes directly. If you enable authentication and users install your bot in group chats or channels, they must authenticate in their personal scopes before they can use the bot in the group chat or channel."
  - Quote: "Only one messaging endpoint is allowed for a bot."
  - **This contradicts the SDK code above**, which sends a targeted OAuthCard inside the channel. I report both. The doc may predate targeted messages (manifest `supportsTargetedMessages` first appears in v1.29, see J.4). This needs a spike.
- https://learn.microsoft.com/en-us/azure/bot-service/bot-builder-concept-authentication (ms.date 2024-10-09, updated_at 2025-12-16; DOC; **PRE-GA**, Bot Framework-era)
  - Still applies: the Python SDK calls the same Token Service (`api.users.get_token`, `api._bots.sign_in.get_resource`).
  - It names "the Microsoft Graph, **GitHub**, or a company's REST service" as external services.
  - The Token Service is responsible for "Securely storing tokens for a particular bot, channel, conversation, and user".
  - Quote: "If the bot has an expired user token, the bot should: Log the user out; Initiate the sign-in flow again".
  - Quote: Teams can secure the sign-in URL "without the user noticing", so no magic code.
- https://learn.microsoft.com/en-us/azure/bot-service/bot-builder-concept-identity-providers (ms.date 2024-10-09, updated_at 2025-12-16; DOC; **PRE-GA**, still applies for the same reason)
  - The full provider list is only available via `az bot authsetting list-providers` or the portal.
  - "OAuth 2 Generic Provider" has Authorization/Token/Refresh URL templates and a Refresh Body Template (`grant_type=refresh_token`).
- INFER (recommended shape):
  1. **Linking is a one-time act.** On first gate use, the Coordinator bot runs the GitHub OAuthCard. With the user token, call GitHub `GET /user` once and persist `aadObjectId → github_login`.
  2. **Each decision is authorized with the existing GitHub App installation token** (collaborator-permission check for `github_login`), exactly as `webhook_bridge` does today.
  3. This keeps "gate decisions require GitHub write/admin" without depending on user-token lifetime or refresh.
  4. It avoids per-bot re-sign-in: either route all gate cards through the Coordinator, or rely on the stored mapping, which is shared across bots.

**Confidence:** medium.
- High: the mechanism, the SDK API, SSO being Entra-only and not available in channels, and per-bot token storage.
- Low: the channel-scope sign-in UX, because doc and code disagree.
- Low: GitHub refresh behavior.

**Implication for docs/80:**
- §13: **confirm** that GitHub-permission gating can stay.
- §13: **change**. The design needs an explicit linking step, an `aadObjectId → GitHub login` store, and a statement that Teams SSO cannot replace GitHub sign-in.
- **New risk:** the per-bot token store means N sign-ins unless one bot owns all gate interactions.
- §15: add the `token.botframework.com` valid domain and one OAuth connection on the Coordinator's Azure Bot resource.

**Gaps:**
- I could not confirm that "GitHub" appears as a named entry in the current provider list (it needs `az bot authsetting list-providers`).
- GitHub-side token expiry (OAuth App vs GitHub App user tokens) is outside this research's primary-source set.
- Whether a targeted OAuthCard in a channel really completes sign-in end-to-end in the current Teams clients is a spike.
- Whether card-action invokes always reach the bot that posted the card is INFER, not sourced here.

---

### H.3 Teams-native authorization alternatives (membership checks)

**Answer:** There are four options, cheapest consent first.

**(a) Bot roster API: no Graph at all.**
- The Python SDK exposes `api.conversations.get_members`, `get_member_by_id(conversation_id, member_id)` and `get_paged_members`.
- They return `TeamsChannelAccount` with `aad_object_id`, `user_principal_name`, `email`, `tenant_id` and `user_role`.
- It is one call with the bot's own credentials and needs no consent beyond installation.
- It does **not** give owner/member semantics: `user_role` is only documented in code as "Role of the user in the conversation", and its values are unconfirmed.

**(b) Graph team members with RSC `TeamMember.Read.Group`.**
- An Application RSC permission, consented per team at install.
- `GET /teams/{id}/members?$filter=(microsoft.graph.aadUserConversationMember/userId eq '<aadObjectId>')` is one call.
- It returns `roles: ["owner"]` for owners.

**(c) Graph channel members with `ChannelMember.Read.Group`.**
- **Conflicting docs.** The Graph API page lists it as the least-privileged Application permission. The RSC permission table lists it as **NA for both Delegated and Application**.
- Avoid it until a spike confirms it. Use (b) for standard channels.

**(d) Entra group membership via `POST /users/{id}/checkMemberGroups`.**
- One call, up to 20 group IDs, transitive.
- Application permission needed: `User.ReadBasic.All` and `GroupMember.Read.All`, which means **tenant-wide admin consent**.
- Hidden-membership groups also need `Member.Read.Hidden`.

**Cheapest per decision:**
- All four are a single HTTP call.
- On consent cost: (a) needs none, (b) needs a team owner at install, (d) needs a tenant admin.
- (a), (b) and (d) can all be cached per `aadObjectId` with a short TTL (INFER).
- None of them expresses GitHub repo permission. They replace the rule rather than implement it.

**Evidence:**
- `packages/api/src/microsoft_teams/api/clients/conversation/client.py`, lines 438–452, and `packages/api/src/microsoft_teams/api/models/account.py`, lines 96–150 (CODE). These are the member APIs and fields listed in (a).
- https://learn.microsoft.com/en-us/graph/api/team-list-members (ms.date 2024-04-18, updated_at 2026-03-07; DOC; **PRE-GA**, still applies because Graph v1.0 is unchanged)
  - Application least-privileged permission is `TeamMember.Read.Group`.
  - Quote: "The TeamMember.Read.Group permission uses resource-specific consent".
  - It supports `$filter` on `userId`, and the response includes `roles`.
- https://learn.microsoft.com/en-us/graph/api/channel-list-members (ms.date 2024-04-04, updated_at 2025-07-31; DOC; **PRE-GA**)
  - Application least-privileged permission is `ChannelMember.Read.Group`.
  - It covers standard, private and shared channels.
- https://learn.microsoft.com/en-us/microsoftteams/platform/graph-api/rsc/resource-specific-consent (ms.date 2025-02-20, updated_at 2026-05-29; DOC; **PRE-GA** by ms.date, refreshed after GA)
  - `TeamMember.Read.Group` is Application: Supported.
  - `ChannelMember.Read.Group` and `ChannelMember.ReadWrite.Group` are listed as "NA | NA".
  - Quote: "Only resource owners can grant application RSC permissions". The page's own SDK table also says team consent is by "A team owner or member", so the page is internally inconsistent.
  - Application RSC needs manifest ≥ v1.6. Delegated RSC needs ≥ v1.12.
- https://learn.microsoft.com/en-us/graph/api/directoryobject-checkmembergroups (ms.date 2026-05-21; DOC)
  - Quote: "You can check up to a maximum of 20 groups per request".
  - Quote: "This function is transitive."
  - Application permission for other users is `User.ReadBasic.All and GroupMember.Read.All`.
  - Hidden-membership groups need `Member.Read.Hidden`.

**Confidence:**
- High for (b) and (d).
- Medium for (a): the API is certain, but the role semantics are not.
- Low for (c): contradictory docs.

**Implication for docs/80:**
- §13: **confirm** that GitHub permission stays the primary gate.
- Offer (b) or (d) as an *additional* "is a lead" check.
- (a) is a zero-consent sanity check that the decider is in the conversation.
- **New risk:** `ChannelMember.Read.Group` should not be assumed in the manifest.

**Gaps:**
- The possible values of the roster `userRole` field.
- Whether the roster for a channel conversation equals team membership or channel membership for private and shared channels.
- Graph throttling numbers for these endpoints were not fetched.

---

### J.4 App manifest: current schema version and the fields that matter

**Answer:**

*Version*
- The newest published schema is **v1.30**. v1.29 and v1.28 are also published; v1.31 returns 404.
- The Teams SDK auth sample still pins v1.22.

*Fields that matter*
- **`bots[]`**
  - `maxItems: 1` ("Currently only one bot per app is supported").
  - Each item has: `botId` (Entra/Azure Bot app ID); `scopes` from `team | personal | groupChat | copilot`; `supportsFiles`; `isNotificationOnly`; `supportsCalling`; `supportsVideo`; `commandLists` (max 3); `needsChannelSelector`; `configuration`; `requirementSet`; `registrationInfo` (system-generated).
  - `supportsTargetedMessages` is **new in v1.29** and relevant to H.2's targeted OAuthCard.
- **`staticTabs`**: max 16.
- **`configurableTabs`**: max 1.
- **`validDomains`**: max 100. Include `token.botframework.com` for bot OAuth.
- **`webApplicationInfo`**
  - `{id: GUID (required), resource: string ≤2048}`.
  - New `nestedAppAuthInfo[]` (≤5) for nested app auth prefetch in tabs.
  - The bot-auth sample uses `id = BOT_ID`, `resource = api://botid-{BOT_ID}`.
- **`authorization.permissions.resourceSpecific[]`**
  - At most 16 items, each `{name ≤128, type: "Application" | "Delegated"}`, unique.
- **`name.short`**: ≤30 characters. `name.full` is ≤100 characters.
- **`icons`**
  - `color` is 192×192 PNG, `outline` is 32×32 white-on-transparent PNG.
  - An optional `color32x32` is also allowed.
- **Other top-level keys present in v1.30:** `agenticUserTemplates` (maxItems 1), `copilotAgents`, `agentConnectors`, `agentSkills`, `supportedChannelTypes`, `defaultBlockUntilAdminAction`, `defaultInstallScope`, `defaultGroupCapability`.

**Evidence:**
- `https://developer.microsoft.com/json-schemas/teams/v1.30/MicrosoftTeams.schema.json` and the v1.28 and v1.29 schemas, probed and parsed 2026-10-09 (CODE/DOC: the schema itself). `manifestVersion.const = "1.30"`. Every constraint above was read directly from the published v1.30 JSON: `bots.maxItems 1`, `scopes` enum and max 4, `commandLists` max 3, `staticTabs` max 16, `configurableTabs` max 1, `validDomains` max 100 / item maxLength 2048, `name.short` 30 / `name.full` 100, `icons`, `webApplicationInfo` incl. `nestedAppAuthInfo`, and `authorization.permissions.resourceSpecific` max 16. They match the Learn reference page below.
- https://learn.microsoft.com/en-us/microsoft-365/extensibility/schema/root (updated 2026-10-01; DOC)
  - Same constraints: `bots.maxItems: 1`, `configurableTabs` max 1, RSC max 16, `validDomains` max 100.
  - The fetched rendering appeared to describe the devPreview/"m365-app-1.30" schema, so I take the version number from the published JSON instead.
- https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/authentication/add-authentication (ms.date 2026-04-14; DOC; PRE-GA by ms.date, refreshed 2026-06-30): the full v1.22 sample manifest with `webApplicationInfo` and `validDomains`.
- RSC page (above): app RSC needs manifest ≥ v1.6, delegated ≥ v1.12.

**Confidence:**
- High for the field constraints.
- Medium that v1.30 is "current GA" rather than merely newest published: the Learn page also references devPreview.

**Implication for docs/80:**
- §15 and §7: **confirm** one manifest per role bot.
- Target `manifestVersion` 1.29 or later if targeted sign-in cards are used.
- Only one configurable tab is allowed per app, so the artifact tab lives in exactly one app (INFER: the Coordinator's).

**Gaps:**
- Whether `webApplicationInfo` is still required alongside `authorization.permissions.resourceSpecific` for RSC. Older guidance required it; the current schema doesn't say.
- No "GA vs preview" label per schema version was found.

---

### J.5 Distribution: sideloading (custom app upload) vs. the org app catalog

**Answer:** There are four routes.

1. **Custom app upload by a user** (sideload)
   - In the client: Apps → Manage your apps → Upload an app → Upload a custom app.
   - It can target personal use, a team/channel, a chat or a meeting.
   - It needs **no admin approval**, but three settings must all be on:
     - the org-wide setting **"Let users interact with custom apps in preview"**;
     - the app setup policy setting **"Upload custom apps"** for that user;
     - the per-team setting **"Allow members to upload custom apps"**. If it is off, only team owners who have the policy can upload.
2. **Submission by a user for approval**
   - Via the client or the Teams App Submission Graph API (`teamsApp` publish with review).
   - The app shows in the Teams admin center as Publishing status **Submitted** / Status **Blocked**.
   - An admin selects **Publish**, which changes it to Published / Allowed.
   - Updates arrive as "Update submitted" and need re-approval.
   - While a submission is pending, only the original submitter can update it.
3. **Upload by an admin** (Teams admin center → Teams apps → Manage apps → Upload new app)
   - Available to the whole org with no approval.
   - "available to the org users after a few hours".
4. **Access control after publishing**
   - App permission policies restrict who can use the app.
   - App setup policies pin it.

*Other notes*
- Custom app upload is not possible in GCC High, DoD or 21Vianet.
- For a pure code change, nothing needs re-uploading. Any manifest or config change needs a reinstall or update.
- An update consented in one context updates every context where the app is installed.

**Evidence:**
- https://learn.microsoft.com/en-us/microsoftteams/teams-custom-app-policies-and-settings (ms.date 2026-04-14; DOC; PRE-GA by two weeks; admin docs are independent of the SDK, so it applies)
  - The four-method table.
  - The team / app-setup-policy / org-wide interplay tables.
  - Quote: "If an admin uploads a custom app, it's available in the organization's catalog in the store without requiring any approval."
- https://learn.microsoft.com/en-us/microsoftteams/submit-approve-custom-apps (ms.date 2026-06-01; DOC): the Submitted/Blocked → Publish → Published/Allowed flow, update rules and notification rules.
- https://learn.microsoft.com/en-us/microsoftteams/platform/concepts/deploy-and-publish/apps-upload (ms.date 2025-01-23, updated_at 2026-04-01; DOC; **PRE-GA**, client UI steps still current per its refresh)
  - The upload steps.
  - The GCC High/DoD/21Vianet limitation.
  - The reinstall rule.
  - Quote: "When a Teams app receives an update, the user must consent to update the app in any one context, and the app is automatically updated in all the related contexts".

**Confidence:** high.

**Implication for docs/80:**
- §15, **confirm and detail**:
  - Dev: sideload N apps into a test team, which needs the upload policy for the PE and architect.
  - Prod: an admin uploads N packages, one admin action per app, then installs them into the team (K.5).
- **New ops item:** every manifest change across six apps means six updates. Script the packaging.

**Gaps:**
- Admin consent for Graph application permissions (Entra) is a separate step from catalog publishing. That step was not documented in these pages; it is standard Entra admin consent per app registration (INFER).

---

### J.6 Testing: DevTools, unit-testing handlers, record/replay

**Answer:**

*DevTools*
- Teams SDK **DevTools is deprecated** ("will be removed in a later version").
- No devtools package remains in `teams.py` (the grep found none).
- Its replacement is the **Microsoft 365 Agents Playground**:
  - Install: `npm install -g @microsoft/m365agentsplayground`.
  - Run: `agentsplayground -e http://localhost:3978/api/messages -c msteams`.
  - The Python app must set `App(dangerously_allow_unauthenticated_requests=True)` (or the env var `DANGEROUSLY_ALLOW_UNAUTHENTICATED_REQUESTS`). `skip_auth` is the deprecated alias.
  - Features: chat, a "Mock an Activity" menu (membership changes, invokes, reactions), and a request/response log panel.
  - It needs no Azure.

*Unit testing without Teams*
- The SDK's own tests drive handlers by constructing `App(...)`.
- They mock the transport: `app.server.adapter.start/stop = AsyncMock()`.
- They mock outbound calls: `app.api.conversations.create_activity`, `update_activity` and `create_targeted_activity` as `AsyncMock`.
- They inject an activity with `await app.event_manager.on_activity(ActivityEvent(body=<core activity>, token=FakeToken()))`.
- There is no published "test adapter" helper. This is a test-suite pattern, not a documented API.

*Record and replay*
- No feature was found in the Teams SDK docs, the Playground docs or the repo.
- INFER: log the inbound JSON bodies at the HTTP layer, with tokens redacted. Replay them through the same `on_activity` path in pytest, or paste them into the Playground's custom-activity mock.

**Evidence:**
- https://microsoft.github.io/teams-sdk/developer-tools/devtools/ (no date; accessed 2026-10-09; DOC)
  - Quote: "DevTools is deprecated and will be removed in a later version."
  - It points to the Agents Playground.
- https://microsoft.github.io/teams-sdk/developer-tools/agents-playground/ (no date; accessed 2026-10-09; DOC): the install, launch and flag details and the features listed above.
- `packages/apps/tests/test_app.py`, lines 83–142, 245 and 286 (CODE): the mocking and `on_activity` pattern.
- `packages/apps/src/microsoft_teams/apps/options.py`, lines 100–125 (CODE)
  - `dangerously_allow_unauthenticated_requests` defaults from the env var, else False.
  - `http_server_adapter` defaults to `FastAPIAdapter`.
  - Experimental `socket_mode`: "The bot dials the Teams service, so no public endpoint or dev tunnel is needed". It is relevant to B.4/B.5 for the other researcher.
- https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/authentication/add-authentication (DOC, see H.2): Microsoft's OAuth testing guide also points to the Agents Playground for local testing.

**Confidence:**
- High for the DevTools deprecation and the Playground.
- Medium for the unit-test pattern: it relies on internals (`event_manager`, `FakeToken`) that can change between minor versions.
- High that no record/replay feature exists in what I checked.

**Implication for docs/80:**
- §15 and §16: **change**. Drop any "DevTools" mention in favor of the Agents Playground.
- **New requirement:** the unauthenticated flag must be impossible to enable in prod (config guard).
- Add a pytest harness around `on_activity` with recorded fixtures, and pin `microsoft-teams-apps==2.1.*` because the harness uses internals.

**Gaps:**
- Whether the Playground supports channel-thread conversation shapes and Adaptive Card `Action.Execute` round-trips well enough to test gate cards. Not documented in what I fetched.

---

### K.1 One app package, multiple bots? (N apps, N Entra registrations, bundle, consent ×N)

**Answer:**

*One bot per app*
- The manifest schema caps `bots` at **`maxItems: 1`** in v1.28 through v1.30: "Currently only one bot per app is supported".
- So six role bots means **six Teams apps**.

*Each role then has its own set of pieces*
- Its own manifest `id` and package zip, with its own `name.short` and icons.
- Its own `botId`.
- Its own **Azure Bot resource**, with exactly one messaging endpoint ("Only one messaging endpoint is allowed for a bot"). The endpoints can be different paths on one host (INFER).
- Its own **Entra app registration**, single-tenant or user-assigned managed identity. "The Multi Tenant bot type in Azure Bot Service is deprecated… All new bot registrations must either use the Single Tenant bot type or the User-Assigned Managed Identity type".
- Its own client secret or credential.
- Its own OAuth connection, if it needs user sign-in (see H.2 for why only the Coordinator should).

*Consent multiplies too*
- **RSC consent is per app per team**, granted at install.
- **Entra admin consent** is needed only for Graph *application* permissions (e.g. option (d) in H.3), and is given per Entra app.
- If only the Coordinator holds Graph permissions, that is one admin consent, not six (INFER).

*No bundle*
- I found **no app-bundle concept**: no bundle or group key in the v1.30 top-level schema keys, and none in the admin docs fetched (custom app policies, submit/approve, upload).

*One tab only*
- `configurableTabs.maxItems: 1` per app.

**Evidence:**
- v1.28, v1.29 and v1.30 schema JSON (CODE/DOC, probed 2026-10-09): `bots.maxItems = 1` and the description string above. The top-level key list is in J.4 and has no bundle construct.
- https://learn.microsoft.com/en-us/microsoft-365/extensibility/schema/root (updated 2026-10-01; DOC): the same `maxItems: 1` statement.
- https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/authentication/add-authentication (ms.date 2026-04-14, updated 2026-06-30; DOC): the multi-tenant bot type deprecation and the one-endpoint-per-bot statement quoted above.
- RSC page (H.3; DOC, PRE-GA): consent is granted per resource (team) instance at install.

**Confidence:**
- High for one bot per app and for the per-app Azure Bot and endpoint.
- Medium for "no bundle": absence of evidence across the fetched docs and schema.

**Implication for docs/80:**
- §2 and §7: **confirm** decision 2 is feasible, at a cost of 6 apps × (Azure Bot + Entra app + manifest + catalog entry + team install).
- **New risk:** six credentials to rotate and six admin uploads. Recommend scripted packaging and keeping Graph and RSC permissions on the Coordinator only.

**Gaps:**
- Whether one Entra app registration can back more than one Azure Bot resource or `botId`. Not confirmed; INFER is one-to-one.
- No Microsoft-stated per-tenant limit on custom apps was found.

---

### K.5 UX of installing several apps into one channel

**Answer:**
- **Installation is per app and per team.** Each app is added separately through Upload a custom app (or the store's "Built for your org") → Add → pick the team/channel → Go. I found no multi-app install UI.
- Who may add an app depends on the custom-app policy matrix from J.5:
  - With the org setting and the user's app setup policy on, and the team setting "Allow members to upload custom apps" on, **anybody** in the team can upload.
  - With the team setting off, **only team owners** with the policy can.
- For catalog (admin-published) apps, availability is then governed by app permission policies.
- Application RSC permissions are granted at install. Per the RSC page this is "only resource owners", while its own table says team owner or member. The docs conflict.

*Scripted path*
- Graph `POST /teams/{team-id}/installedApps` with `teamsApp@odata.bind` pointing at the **catalog** app ID. **One app per call**, so N calls.
- Apps that request RSC must be installed with `TeamsAppInstallation.ReadWriteAndConsentForTeam(.All)` (or `...AndConsentSelfForTeam`) **and** a matching `consentedPermissionSet`.
- The plain `ReadWriteForTeam` permissions "cannot be used to install apps that require consent to resource-specific consent permissions".
- INFER: a bot installed into a team is reachable from every channel in that team. Only the archived bot-v3 page states "A bot can be mentioned… in a channel if it has been added to the team".

**Evidence:**
- https://learn.microsoft.com/en-us/microsoftteams/platform/concepts/deploy-and-publish/apps-upload (ms.date 2025-01-23, updated 2026-04-01; DOC; **PRE-GA**, UI still current): the per-app upload → Add → scope/channel → Go flow.
- https://learn.microsoft.com/en-us/microsoftteams/teams-custom-app-policies-and-settings (ms.date 2026-04-14; DOC): the interplay table (Off/Off → no user, Off/On → only team owners, On/On → anybody).
- https://learn.microsoft.com/en-us/graph/api/team-post-installedapps (ms.date 2024-10-17, updated_at 2025-07-23; DOC; **PRE-GA**, Graph v1.0 still applies): the permission table, its footnote ¹, and the `consentedPermissionSet` example.
- RSC page (H.3; DOC): who can consent.

**Confidence:**
- High: per-app install, the Graph API and the RSC install permission.
- Medium: no multi-install UI (absence of evidence).

**Implication for docs/80:**
- §2 and §15: **confirm**, adding a "workspace bootstrap" script that installs six apps via Graph with consent.
- Manual setup is six installs, done by a team owner.
- **New risk:** the RSC "who can consent" ambiguity. Have a team owner (the PE or architect) do the installs.

**Gaps:**
- The Teams-client team setting that governs adding *catalog* (non-custom) apps to a team was not fetched.
- Whether an admin can push team-scope installs from the Teams admin center UI (as opposed to Graph) was not confirmed.

---

### K.7 Per-bot avatars and display names; posting as a sub-identity ("Coder #2")

**Answer:**
- A bot's visible **name and avatar come from its app**:
  - `name.short` (≤30 chars) and `name.full` (≤100 chars);
  - `icons.color` (192×192 PNG) and `icons.outline` (32×32);
  - plus the icons on the Azure Bot Service registration.
- Each role therefore gets its own name and avatar only because it is its own app (see K.1).
- There is **no per-message sender override** (display name or avatar) in the current docs or in the Python SDK models.
- The nearest feature is Bot Framework's `channelData.onBehalfOf`. It is **not a sub-identity**:
  - It takes `{itemId: 0, mentionType: "person", mri, displayName}`, where `mri` is "the person on whose behalf the message is sent".
  - The sender renders as "[user] through [bot name]".
  - So it attributes a message to a real user. It cannot express "Coder #2".
- The Python Teams SDK's `ChannelData` model has **no `on_behalf_of` field**.
- The current Teams messaging page (2026-09-28) does not mention it.
- So "Coder #2 · T005–T007" must be **content**: message text, or a card header or badge.

**Evidence:**
- v1.30 schema (CODE/DOC): the `name` and `icons` definitions as quoted in J.4.
- https://learn.microsoft.com/en-us/microsoftteams/platform/concepts/build-and-test/apps-package (ms.date 2026-05-08; DOC)
  - Quote: "Your app package must include two .png versions of your app icon".
  - Quote: "If your app has a bot or message extension, your icons are included in your Microsoft Azure Bot Service registration."
- https://learn.microsoft.com/en-us/dotnet/api/microsoft.bot.schema.teams.onbehalfof?view=botbuilder-dotnet-stable (ms.date 2024-05-21; DOC; **PRE-GA**, Bot Framework-era .NET schema `Microsoft.Bot.Schema` 4.22.7)
  - Quote: "Specifies attribution for notifications."
  - `Mri`: "message resource identifier (MRI) of the person on whose behalf the message is sent. Message sender name would appear as '[user] through [bot name]'".
  - It still describes the wire format, but it is not surfaced in the Python Teams SDK.
- `packages/api/src/microsoft_teams/api/models/channel_data/channel_data.py`, lines 21–56 (CODE). Fields: `channel`, `app`, `event_type`, `team`, `notification`, `tenant`, `meeting`, `settings`, `feedback_loop_enabled`, `feedback_loop`. There is no `on_behalf_of`.
- https://learn.microsoft.com/en-us/microsoftteams/platform/bots/build-conversational-capability (ms.date 2026-09-28; DOC): a grep of the fetched page found no onBehalfOf/attribution section (INFER from absence).

**Confidence:** high that there is no sub-identity override, and high that the avatar and name are per app.

**Implication for docs/80:**
- §2: **confirm** decision 2's "one bot per role; instances labelled in content".
- §14: the label belongs in the card header (e.g. a ColumnSet with a role glyph + "Coder #2 · T005–T007"), not in sender identity.
- Do not use `onBehalfOf`: it would falsely attribute agent output to a human lead.

**Gaps:**
- Whether name or avatar changes in a manifest update propagate to already-posted messages. Not checked.
- The v1.30 manifest adds `agenticUserTemplates` (maxItems 1), and `teams.py` has `examples/agent365` plus `test_agent_lifecycle_routes.py`. These suggest a newer "agentic user" identity model, possibly per-agent user-like identities. I did not research it. **Spike candidate** for §2 if per-instance identities are ever wanted.
