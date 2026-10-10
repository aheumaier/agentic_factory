# Spike prompt — six Teams platform checks that gate spec 009

> **How to use this file.** Give everything below the line to a Claude Code
> session that runs alongside a human. The human has a Microsoft 365 dev
> tenant and the Teams desktop, web and mobile clients. Steps marked
> **HUMAN** need a person clicking in Teams. Every other step the agent does
> itself. Results go to `docs/research/teams-spikes-results.md`, and are then
> folded into `docs/80-teams-workspace-design.md` the same way the research
> was.
>
> Written 2026-10-09.

---

## 0. Your task

`docs/80-teams-workspace-design.md` designs a Microsoft Teams workspace for a
human + agent software team. Research
(`docs/research/teams-workspace-research-findings.md`) confirmed most of the
design. **Six questions can only be answered by trying them in a real
tenant.** They are listed in docs/80 §17.2 as the spikes "before 009" (009 is the Teams adapter; 008, the decision core, needs no tenant). Run
all six, record what actually happens, and say which docs/80 sections change
as a result.

These spikes produce **evidence, not product code.**

- **Where the code goes.** The harness lives in `spikes/teams/`, as
  throwaway code. Don't import it from, or add it to, `orchestration/`,
  `harness/` or `registry/`. Per `CLAUDE.md`, product code needs a
  `specs/NNN-slug/` behind it, and spec 009 doesn't exist yet.
- **No secrets in git.** Credentials live in `spikes/teams/.env.spike`,
  which is gitignored. Never put them in the repo-root `.env`. The SDK
  auto-loads a `.env` it finds from the working directory, so run the
  harness with `spikes/teams/` as the working directory, and pass every
  credential explicitly (docs/80 §15, "Credential hygiene").
- **Time-box each spike to about two hours.** If a spike can't be settled
  in that time, record what you saw and mark it **inconclusive**. Don't
  re-design anything to get around it.

## 1. Read first

1. `docs/80-teams-workspace-design.md`:
   - §2 (six apps; Factory owns every gate card);
   - §7.1–§7.5 (adapter, conversation, artifact service, notifier);
   - §10 (correlation and the persisted row);
   - §12–§14 (decisions, identity, cards);
   - §17.2 (the spike table).
2. `docs/research/teams-workspace-research-findings.md`:
   - the executive summary, including the "Conflicts" list;
   - §4.2 **End-to-end sketch**, which is the starting point for the harness;
   - entries B.1, D.1–D.4, E.2–E.6, F.7, H.1–H.2, J.7 and K.6.
3. `orchestration/webhook_bridge/server.py`. It shows how the existing
   aiohttp app is built, which is the shape the harness should mirror.

## 2. Prerequisites (HUMAN, once)

- [ ] **A dev tenant** where you are a Teams admin, with custom app upload
      allowed.
- [ ] **A team with a standard channel** named `factory-spike`. Not shared,
      not private: bots aren't supported in shared channels, and agents
      can't post in private ones.
- [ ] **A Dev Tunnel** with a stable public HTTPS URL
      (`devtunnel host -p 3978 --allow-anonymous`).
- [ ] **Three bot registrations in the Teams Developer Portal**
      ("Teams-managed", no Azure), each single-tenant and each with a client
      secret:
  - `SpikeFactory`
  - `SpikeArchitect`
  - `SpikeDesigner`

  The messaging endpoints are `<tunnel>/api/teams/factory/messages`,
  `…/architect/messages` and `…/designer/messages`.
- [ ] **One Azure Bot resource for S-H2**, in a subscription you can use
      (no compute needed). It has a **GitHub OAuth connection** backed by a
      GitHub OAuth App you create, with callback
      `https://token.botframework.com/.auth/web/redirect`.
- [ ] **A disposable GitHub repo** that you have `write` on, plus a second
      GitHub account with only `read`.
- [ ] **Three app packages (one per bot), uploaded to the team:**
  - **`SpikeFactory`'s package also carries:**
    - a static tab: `staticTabs`, `scopes: ["team"]`,
      `context: ["channelTab"]`, `contentUrl` = `<tunnel>/tab/`;
    - `webApplicationInfo` for tab SSO;
    - RSC `ChannelMessage.Read.Group` and `TeamMember.Read.Group`.
  - **`validDomains`:** the tunnel host and `token.botframework.com`.

The agent writes the three manifests, zips them, and checks them against
the current manifest schema before the human uploads them.

## 3. Shared harness (agent)

Build `spikes/teams/harness.py`: one aiohttp process hosting three `App`
instances (`microsoft-teams-apps==2.1.0`, Python ≥3.11). Start from the
findings doc's §4.2 sketch.

- **Mounting.** Each `App` is mounted through an `HttpServerAdapter` on its
  own `messaging_endpoint`. Run `await app.initialize()` for all three
  **before** `AppRunner.setup()`.
- **Raw logging.** Append every inbound activity, with the bot that
  received it, its route, `conversation.id`, `from.id`,
  `from.aadObjectId`, `channelData`, `serviceUrl` and `id`, to
  `spikes/teams/out/inbound.jsonl`. Raw JSON is the evidence for most
  spikes.
- **Persisted rows.** Write the docs/80 §10.4 row (`teams_thread_id`,
  `bot_app_id`, `service_url`, `tenant_id`, `team_id`, `channel_id`,
  `root_activity_id`, `board_activity_id`) to a SQLite file.
  `spikes/teams/send.py` (proactive sends, runnable as a separate process)
  reads it.
- **Tab.** Serve `spikes/teams/tab/` at `/tab/`, a single static page that
  does three things:
  - calls `app.initialize()` and then `getAuthToken()`;
  - shows `app.getContext()` (including `page.subPageId`);
  - calls `/api/whoami` with the token and shows the result.
- **Logging.** Log to the console with the bot name prefixed, so you can
  watch it live.

## 4. The spikes

For each spike, record:

- **Result:** pass, fail or inconclusive;
- **Evidence:** raw JSON excerpts from `inbound.jsonl`, return values,
  HTTP status codes, and screenshots under `spikes/teams/out/`;
- **Clients tested;**
- **docs/80 change:** the exact sections to edit, and what to write there.

### S-D4: one thread id for all bots?

**Why:** docs/80 §10 tags every run with a single `TeamsThreadId`. A
Microsoft doc says "the conversation ID is unique for each agent within a
specific channel".

1. Agent: `send.py`, running as `SpikeFactory`, calls
   `app.send(<bare channel id>, <card>)`. Record the returned
   `SentActivity.id` and whether a new thread root appears.
2. Agent: `send.py`, running as `SpikeArchitect`, calls
   `app.reply(<channel id>, <root id from step 1>, "architect reply")`.
   Does it land **inside** Factory's thread?
3. **HUMAN:** in that thread, post a reply that @mentions SpikeFactory, then
   another that @mentions SpikeArchitect.
4. Agent: compare the inbound `conversation.id` that each bot logged for the
   same thread. Repeat step 3 in a second thread.

**Pass:**

- step 1 creates a root and returns its id;
- step 2 replies into that thread;
- both bots log byte-identical `conversation.id` values for the same thread.

**If it fails:** docs/80 keeps per-bot rows keyed by
`(teams_thread_id, bot_app_id)`, and `TeamsThreadId` holds Factory's id.
Record which part failed.

### S-H2: GitHub sign-in inside a channel

**Why:** Learn says users must sign in from a personal chat before using
OAuth in a channel. The SDK 2.1 code sends a *targeted* OAuthCard in the
channel instead.

1. Agent: point `SpikeFactory` at the Azure Bot resource's app id instead,
   or register a fourth app on it, whichever the docs require. Add
   `app.add_oauth_flow("<connection>")`, an `@flow.on_signin` handler that
   calls GitHub `GET /user`, and an `@SpikeFactory link-github` command
   that calls `.sign_in(ctx)`.
2. **HUMAN:** in the channel, send `@SpikeFactory link-github` as the user
   who has `write`. Note who sees the card, and whether completing it works
   on desktop, web and mobile.
3. If step 2 fails: **HUMAN** signs in from a 1:1 chat with SpikeFactory,
   then retries in the channel.
4. Agent: log the GitHub login and `aadObjectId`. Then run the existing
   permission check, `orchestration/webhook_bridge/auth.py:24-35`
   `is_authorized`, against the disposable repo for both GitHub accounts.
   Import the function; don't copy it.

**Pass:** sign-in completes in the channel with only the requesting user
seeing the card, and the permission check returns `write` and `read`
correctly.

**Partial:** it works only after a personal-chat sign-in. docs/80 §13's
sign-in card then opens a 1:1 chat.

### S-B1: what a Teams-managed registration can do

**Why:** docs/80 §15 assumes the five non-OAuth bots need no Azure. That is
INFER only.

Using `SpikeArchitect` and `SpikeDesigner` (both Teams-managed), confirm
each of these and record the HTTP status of every call:

- a proactive channel post (from S-D4);
- an `Action.Execute` invoke reaching the handler (set up in S-E3x);
- an `update_activity` on the bot's own message;
- RSC delivery of a non-mentioned channel message to `SpikeFactory`. Post
  without any @mention and check `inbound.jsonl`.

**Pass:** all four work. **Fail:** list which Azure resource each failing
item needs.

### S-F7: deep link into the static tab

**Why:** card buttons in docs/80 §8.2 deep-link to tab views. The deep-link
doc still says `channelId` only works for configurable tabs.

1. **HUMAN:** pin SpikeFactory's static tab in `factory-spike`.
2. Agent: post a card from SpikeFactory with three `Action.OpenUrl` buttons
   to `https://teams.microsoft.com/l/entity/<appId>/<entityId>?context=<URI-encoded JSON>`:
   - `{"subEntityId":"014-saved-carts/plan/2","channelId":"<channel id>"}`;
   - the same without `channelId`;
   - a link over 1,500 characters.
3. **HUMAN:** click each button on desktop, web, iOS and Android. Record:
   - whether the tab opens;
   - in which context (the channel's tab, or a personal-app view);
   - what `page.subPageId` the tab page shows.

**Pass:** the tab opens in the channel with the right `subPageId` on desktop
and web. Record mobile behaviour separately, whatever it is.

### S-E3x: card actions on another bot's card

**Why:** docs/80 §14.4 has Factory post every gate card, because nobody
knows where an `Action.Execute` on another bot's card goes.

1. Agent: `SpikeDesigner` posts a card with an `Action.Execute` whose `data`
   is `{"action": "gate.decide", "gate": "mock", "attempt": 1}`. Register a
   `gate.decide` handler on **all three** apps, each logging which bot
   received it. Routing is on `data.action`, not `verb`.
2. **HUMAN:** click it.
3. Agent: record which bot got the invoke. Then try `update_activity` on
   that card from SpikeFactory (a different bot) and from SpikeDesigner (the
   owner).
4. Agent: have the receiving handler return `AdaptiveCardActionCardResponse`.
   **HUMAN** confirms that only the clicker's view changed, until the
   owner's `update_activity` changes it for everyone.

**Record:**

- which bot received the invoke;
- whether a non-owner can update the card (expected: no);
- whether the invoke response is per-user.

### S-J7: tenant allow-list

**Why:** the SDK has no tenant allow-list. Its Entra-issuer inbound path
builds the issuer from the token's own `tid` (docs/80 §13).

1. Agent: add middleware to the harness that rejects any inbound activity
   where `channelData.tenant.id` (or `conversation.tenantId`) is not our
   tenant, and any tab/API token where `tid` is not our tenant. Log
   `tenant_not_allowed`.
2. Agent: unit-test it with recorded `inbound.jsonl` activities, rewriting
   the tenant id in each.
3. If a second tenant is available (**HUMAN**), sideload SpikeFactory there
   and message it. Confirm the activity is rejected before any handler runs.
   If no second tenant is available, say so and rely on step 2.
4. Agent: read the SDK's inbound validation path again at
   `microsoft-teams-apps==2.1.0`. Confirm which path a Teams channel
   activity actually takes: Bot Connector or Entra issuer. Record the
   `iss` claim from a real inbound request.

**Pass:**

- the middleware rejects foreign tenants on both the activity path and the
  tab path;
- the `iss` seen in real traffic is recorded.

### Optional, if time allows

These come from docs/80 §17.2 and are otherwise scheduled "in 009":

- **S-J3:** watch `inbound.jsonl` for duplicate `activity.id`s across a
  day.
- **S-B4:** run the harness against Agents Playground
  (`agentsplayground -e http://localhost:3978/api/teams/factory/messages -c msteams`)
  and check whether channel threads and `Action.Execute` behave as they do in
  Teams.
- **S-F3:** set a strict `connect-src` on the tab and check whether
  TeamsJS still initializes.

## 5. Output

Write `docs/research/teams-spikes-results.md`. Structure it as:

1. **Summary table:** spike, result (pass / fail / partial /
   inconclusive), one-line finding, docs/80 sections to change.
2. **One section per spike:** steps actually run, evidence (inline JSON
   excerpts; screenshots referenced under `spikes/teams/out/`), clients
   tested, and the proposed docs/80 edit text.
3. **Surprises:** anything that contradicts docs/80 or the findings doc,
   even if no spike asked about it.
4. **Teardown checklist:** the Azure Bot resource, the GitHub OAuth App,
   the uploaded apps and the Dev Tunnel. List them; leave the deleting to
   the human.

**Don't edit `docs/80` yourself.** The human reviews the results first. Then
a separate pass folds them into docs/80 §10, §13, §14.4 and §15 and updates
§17.2. After that comes `/speckit-specify` for 009.

Do not commit anything. Leave `spikes/teams/` and the results file
uncommitted for review.
