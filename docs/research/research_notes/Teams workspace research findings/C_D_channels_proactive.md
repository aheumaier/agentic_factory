# C / D / H.1 / K.2 / K.6: Channel bots, proactive messaging, inbound identity, bot-to-bot visibility

Research date: 2026-10-09. Scope: questions C.1–C.5, D.1–D.4, H.1, K.2 and K.6 from
`docs/research/teams-workspace-research-prompt.md`, plus code for §4.2 items 2 and 4.

Labels: **DOC** means a source says it. **CODE** means I read it in SDK source or samples. **INFER** is my own reasoning.
**PRE-GA** marks a source whose `ms.date` is before 2026-05.

## Sources used (with dates)

| Key | Source | ms.date (updated_at) | Status |
|---|---|---|---|
| S1 | [Channel and group conversations](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/conversations/channel-and-group-conversations) | 2026-06-23 (2026-09-28) | current, Teams SDK pivots |
| S2 | [Enable an agent to receive all chat messages](https://learn.microsoft.com/en-us/microsoftteams/platform/agents-in-teams/enable-receive-all-chat-messages) (both `.../channel-messages-with-rsc` and `.../channel-messages-for-bots-and-agents` redirect here) | 2026-09-28 | current |
| S3 | [Send proactive messages](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/conversations/send-proactive-messages) | 2026-06-30 (2026-09-25) | current |
| S4 | [Teams SDK: Proactive messaging](https://learn.microsoft.com/en-us/microsoftteams/platform/teams-sdk/essentials/sending-messages/proactive-messaging) | 2026-07-27 | current |
| S5 | [Teams SDK: Sending messages (threading, streaming)](https://learn.microsoft.com/en-us/microsoftteams/platform/teams-sdk/essentials/sending-messages/overview) | 2026-07-27 | current |
| S6 | [Stream agent messages](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/streaming-ux) | 2026-08-24 (2026-09-28) | current |
| S7 | [AI content labels](https://learn.microsoft.com/en-us/microsoftteams/platform/agents-in-teams/integrate-ai/ai-content-labels) | 2026-09-27 | current |
| S8 | [User feedback controls](https://learn.microsoft.com/en-us/microsoftteams/platform/agents-in-teams/integrate-ai/user-feedback-controls) | 2026-09-26 | current |
| S9 | [Graph: List channel message replies (v1.0)](https://learn.microsoft.com/en-us/graph/api/chatmessage-list-replies?view=graph-rest-1.0) | 2024-04-04 (2025-07-23) | **PRE-GA**. Graph API, not SDK-dependent, so it still applies. |
| S10 | [Resource-specific consent](https://learn.microsoft.com/en-us/microsoftteams/platform/graph-api/rsc/resource-specific-consent) | 2025-02-20 (2026-05-29) | **PRE-GA** by ms.date, refreshed after GA. Still applies. |
| S11 | [Conversations with an agent](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/build-conversational-capability) (`.../conversation-messages` redirects here) | 2026-09-28 | current |
| S12 | [Bot v3 archive: Proactive messages, "Creating a channel conversation"](https://learn.microsoft.com/en-us/previous-versions/microsoftteams/platform/resources/bot-v3/bot-conversations/bots-conv-proactive) | 2023-04-02 (2026-08-18) | **PRE-GA and ARCHIVED** (`is_archived: true`, NOINDEX, v3 Bot Framework banner). It contains a Teams SDK Python snippet, but nothing that rests on it alone is high confidence. |
| S13 | [Graph metered APIs list](https://learn.microsoft.com/en-us/graph/metered-api-list) | 2025-08-06 (2026-04-03) | **PRE-GA**. Still applies (the policy change is dated 2025-08-25). |
| CODE | [`microsoft/teams.py`](https://github.com/microsoft/teams.py) cloned at `main` @ `8539006` (2026-10-07). I checked that the same APIs (`App.send`, `App.reply`, `utils/thread.py`) are present in tag **`v2.1.0`**. PyPI `microsoft-teams-apps` latest is **2.1.0** (uploaded 2026-09-16). | — | current |

Line numbers below refer to `main@8539006` unless a line says otherwise.

---

### C.1 Mention-only delivery and RSC `ChannelMessage.Read.Group`

**Answer:**
- **Default delivery.** A bot installed in a team receives a channel message only when the bot is @mentioned. It does **not** receive:
  - a team or channel @mention;
  - a reply to the bot's own message that doesn't @mention the bot.
- **With RSC.** Adding the RSC application permission `ChannelMessage.Read.Group` to the manifest makes the bot receive **all** messages in the channels of every team where the app is installed, with no @mention needed.
- **Consent.** After the permission is added, the app must be installed or upgraded in the team, and the **team owner** consents at install time.
- **Admin controls.** RSC application permissions are governed tenant-wide by "Microsoft Entra admin center-based controls for Teams".
- **Graph access too.** S2 says the default limits both what agents "receive **or can access via Graph APIs**". So RSC also governs Graph read access, not only delivery.
- **Private and shared channels.** Private channels are limited: agents can't post messages or cards in private-channel conversations (S1). Shared and private channels have separate support rules, which I did not research further.

**Evidence:**
- S1 (2026-06-23; DOC): "By default, agents in group chats and channels only receive messages when they're directly @mentioned … your agent doesn't receive a message when the team or channel is mentioned, or when someone replies to a message from your agent without @mentioning it."
- S2 (2026-09-28; DOC): "`ChannelMessage.Read.Group`: Receive all messages in the channels of the team where the app is installed" and "install or upgrade the app … The team or chat owner must consent to the requested RSC permissions during installation." It also says: "By default, the only chat messages that agents receive or can access via Graph APIs are the ones where they're @mentioned."
- S10 (2025-02-20, PRE-GA, still applies; DOC):
  - "Only resource owners can grant application RSC permissions."
  - Tenant controls are "Microsoft Entra admin center-based controls for Teams".
  - The manifest must be ≥ v1.6.
- **Which events RSC adds.** S2 talks only about "messages". No current doc says whether RSC also adds edit, delete or reaction events for messages that don't mention the bot. That is a gap (the SDK has `on_message_update`, `on_message_delete` and `on_message_reaction` routes; CODE, `routing/generated_handlers.py`).

**Confidence:** High for mention-only delivery and RSC receive-all. Low for which non-message events RSC adds.

**Implication for docs/80:** §6.3 and §7.3 are confirmed. Two choices follow:
- **Without RSC**, every role bot sees only messages addressed to it. That matches §6.3 "Addressing an agent" exactly.
- **With RSC**, each bot sees every human message, which is useful for thread context (see C.2), but it must filter with `is_recipient_mentioned()`.

Each RSC-enabled bot means one more team-owner consent per bot app (feeds K.1 and K.5).

---

### C.2 Thread history for agent context (activity stream vs Graph)

**Answer:**
- **The activity stream carries no history.** Each inbound activity is a single message. No primary source describes a way to fetch prior replies through the Bot Connector, and the SDK's `ConversationClient` has no list-messages call (CODE: the `api/clients/conversation/client.py` methods are create, update, reply, delete, get_members and the targeted variants).
- **History comes from Graph:** `GET /teams/{team-id}/channels/{channel-id}/messages/{message-id}/replies`, plus `GET …/messages/{message-id}` for the root. Permissions:
  - **Least-privileged application permission:** `ChannelMessage.Read.Group`, which is the RSC permission, so it is scoped to teams where the app is installed and owner-consented.
  - **Broader application permissions:** `ChannelMessage.Read.All`, `Group.Read.All`, `Group.ReadWrite.All`.
  - **Delegated:** `ChannelMessage.Read.All`.
- **Paging:** `$top` maximum 50, and no other OData parameters.
- **Metered:** No. Teams Graph APIs are no longer metered since 2025-08-25.
- **Protected:** **Not confirmed.** The "protected APIs in Teams" page (`learn.microsoft.com/en-us/graph/teams-protected-apis`) returned 404 on 2026-10-09. S13 says only that "some … APIs … are protected and require additional validation". I found no current primary source that says whether the RSC `ChannelMessage.Read.Group` path to `/replies` needs the protected-API request form.

**Evidence:**
- S9 (2024-04-04, PRE-GA, Graph REST is unchanged so it still applies; DOC): permission table "Application | ChannelMessage.Read.Group | ChannelMessage.Read.All, Group.Read.All, Group.ReadWrite.All" and "The ChannelMessage.Read.Group permission uses resource-specific consent". The page also says "Maximum allowed `$top` value is 50", and the API "supports subscribing to changes … using change notifications".
- S2 (2026-09-28; DOC): RSC governs "receive **or** access via Graph APIs".
- S13 (2025-08-06, PRE-GA, still applies; DOC): "Starting August 25, 2025, the Teams APIs are no longer metered, and no billing configuration is required."
- CODE: `ActivityContext.app_graph` (`routing/activity_context.py` ~L210) gives an app-token Graph client inside a handler. Graph helpers come from the `microsoft-teams-graph` package (`packages/graph`).
- Gap: protected-API status for RSC-scoped `/replies`. Needs a spike (call it with an RSC-consented app and see whether you get 403 or 200).

**Confidence:** High for the endpoint, permissions and not-metered status. Low for protected-API status.

**Implication for docs/80:** §7.3 "Context" has two options:
- **(a) Graph `/replies` with RSC.** Needs a Graph token for each bot's Entra app and carries the unresolved protected-API risk.
- **(b) Our own thread log (INFER, recommended).** If Factory alone has RSC `ChannelMessage.Read.Group`, the bridge receives every human message in each feature thread in real time and can persist a thread transcript keyed by `TeamsThreadId` in the §10 Postgres table. Agents then read context from our store, which removes the Graph and protected-API dependency.

  Caveats:
  - The log misses messages from before the install and messages sent while the bridge was down.
  - Graph `/replies` stays the backfill path.
  - Bot-authored messages may not be delivered (see K.2). We already know our own posts, so we can log them at send time.

Add **new risk**: "Graph `/replies` protected-API status unconfirmed".

---

### C.3 Conversation-id format: root post vs thread reply, and replying into a thread

**Answer:**
- **Base channel id:** `19:<hex>@thread.tacv2`. Older examples show `@thread.skype`.
- **Inside a thread** the activity's `conversation.id` carries a thread suffix: `19:…@thread.skype;messageid=<root message id>`. The root message id is numeric (epoch milliseconds, for example `1481567603816`).
- **Reactive reply.** Inside a handler, the inbound `conversation_ref` already holds the threaded id. `ctx.send(x)` posts into the same thread with no quote, and `ctx.reply(x)` posts into the same thread with a visual quote of the inbound message.
- **Proactive reply.** Outside a handler:
  - `app.reply(conversation_id, root_message_id, x)` builds the threaded id for you;
  - or `to_threaded_conversation_id(conversation_id, root_message_id)` followed by `app.send(...)`.
- **Helper rules.** `to_threaded_conversation_id`:
  - strips any existing `;…` suffix and appends `;messageid=<id>`;
  - **rejects** a non-numeric or `"0"` message id.
- **How the root id is recovered.** The SDK sample takes the root id from the inbound conversation id (`split(";messageid=")`) and falls back to `activity.id` when the suffix is absent. A root post's own id is its message id.

**Evidence:**
- S1 (2026-06-23; DOC): sample payload `"conversation": {"id": "19:aebd0ad4d6ab42c8b9ed19c251c2fc37@thread.skype;messageid=1481567603816"}`, plus "When your agent receives a message in a thread, the conversation context already carries the thread ID. Use `send()` … without quoting, or `reply()` … with a visual quote".
- S4 (2026-07-27; DOC): "To proactively send a message as a reply to a thread, use `app.reply()` with the conversation ID and thread root message ID. The SDK constructs the threaded conversation ID for you", and "Threads are only rendered visibly in Teams channels."
- S9 (PRE-GA; DOC): Graph example channel id `19:4a95f7d8db4c4e7fae857bcebe0623e6@thread.tacv2`, message id `1616989510408`, and each reply's `replyToId` equals the root id.
- CODE: `packages/apps/src/microsoft_teams/apps/utils/thread.py` L7–27:
  ```python
  if not message_id or not message_id.isdigit() or message_id == "0":
      raise ValueError(...)
  base_id = conversation_id.split(";")[0]
  return f"{base_id};messageid={message_id}"
  ```
  The helper was added in commit `8e0cdfa` ("Add proactive threading support (#389)", 2026-04-20).
- CODE: `app.py` L353–391 `App.send` docstring: "For channel threads, the conversation ID must include `;messageid=`". `App.reply` (L443–480) has a 3-arg form that threads and a 2-arg form that sends as-is.
- CODE: `routing/activity_context.py` L241–301:
  - `send()` says "In channels, sends to the current thread";
  - `reply()` calls `quote(activity.id, …)`, which prepends a quote placeholder.
- CODE: `examples/interacting-with-messages/src/threading_handlers.py` `_thread_reference()`.

**Confidence:** High.

**Implication for docs/80:** §10 "`TeamsThreadId` (Keyword)" is confirmed. Store it as the full threaded id `19:…@thread.tacv2;messageid=<rootId>`, or store `(channel_conversation_id, root_message_id)` as two keywords. Either way it is a string that is stable for the thread. See D.4 for the risk that conversation ids are per-bot.

---

### C.4 Channels: streaming, typing, AI label, citations, feedback buttons

**Answer:**

| Feature | Channels? | Source |
|---|---|---|
| Streaming (`ctx.stream.emit/update`) | **No.** One-on-one chats only. | S6, S5 (DOC) |
| Typing indicator | **Unconfirmed in primary sources.** `TypingActivityInput` exists and the SDK sample sends it unconditionally, but no current Learn page states channel-scope support. | CODE only |
| AI-generated label (`add_ai_generated()`) | **Yes** | S7 (DOC) |
| Citations (`add_citation()`) | **Yes.** At most 20 per message. Citations that use Adaptive Cards are in public developer preview. | S7 (DOC) |
| Feedback 👍/👎 (`add_feedback()`, handled by `@app.on_message_submit_feedback`) | **Yes** | S8 (DOC) |

**Evidence:**
- S6 (2026-08-24; DOC): "Streaming agent messages are supported only in one-on-one chats. Teams supports only one concurrent streaming response per chat at a time." Also: "Attachment, AI-label, feedback button, and sensitivity labels are available only for the final streaming message", and streams have a 2-minute limit.
- S5 (2026-07-27; DOC): "Streaming is currently only supported in 1:1 conversations, not group chats or channels."
- CODE: `http_stream.py` has no scope guard, so the SDK will *try* to stream in a channel. INFER: expect `403 ContentStreamNotAllowed` ("The streaming API feature isn't allowed for the user or agent", S6 error table).
- S7 (2026-09-27; DOC): "AI content labels are available for agents in personal chats, group chats, and channels." "A maximum of 20 citations are displayed in a message." "Citations with Adaptive Cards are available in public developer preview."
- S8 (2026-09-26; DOC): "Feedback controls are available for agents in personal chats, group chats, and channels." `add_feedback(mode="custom")` triggers a `message/fetchTask` invoke.
- CODE: `examples/interacting-with-messages/src/main.py` L31 `await ctx.send(TypingActivityInput())`. `http_stream.py` L160 sends informative updates as `TypingActivityInput` with `stream_type="informative"`.
- Gap: typing indicator in channel scope. I found only forum and Q&A posts, which are not usable as evidence.

**Confidence:** High for streaming, AI label, citations and feedback. Low for typing.

**Implication for docs/80:** §14 and §6.4. Confirm "no progress chatter" for a second reason: streaming is unavailable in channels anyway. Presentations can carry `add_ai_generated()` + `add_feedback()` + `add_citation()` (for example, cite the git artifact). Don't design around a typing indicator in channels; the board card in §6.1 already covers "working" state.

---

### C.5 Mention handling and stripping (`microsoft-teams-apps`)

**Answer:**
- **No auto-strip in Python.** The Python SDK does **not** strip mentions automatically, and it has **no dedicated mention route**. You call `ctx.activity.strip_mentions_text(options)` yourself.
- **Default behaviour strips everything.** With no options it removes **every** mention entity's text, other users and bots included, then `.strip()`s.
- **Strip only your own mention** with `StripMentionsTextOptions(account_id=ctx.activity.recipient.id)`.
- **Keep the name** with `tag_only=True`, which keeps the inner name and drops the `<at>` tags.
- **Is the bot addressed?** `activity.is_recipient_mentioned()` checks whether any `MentionEntity.mentioned.id == recipient.id`.
- **Wire format of a mention.** Each @mention (user, bot or tag) appears twice:
  - in `text` as `<at>Name</at>`;
  - as an entity `{"type":"mention","mentioned":{"id":…,"name":…},"text":"<at>…</at>"}`.
  - A tag mention adds `"type":"tag"` inside `mentioned`.
- **Trust.** S1 warns not to parse user info from the text, because the sender can alter it. Use `entities`.
- **DOC vs CODE discrepancy.** S1 says "The Teams SDK provides a dedicated `mention` activity route". In the Python SDK (`v2.1.0` / `main`) `routing/generated_handlers.py` has no `on_mention` and nothing under `routing/` references mentions. The route is likely TS/C#-only. Treat it as **not available in Python**.

**Evidence:**
- S1 (2026-06-23; DOC):
  - "messages that @mention your agent include a mention entity … the message text contains mention markup such as `<at>@agentname</at>`"
  - "Preserve other mentions when they are part of the user's request."
  - "The TypeScript and Python versions for Teams SDK include built-in functions to remove @mention."
  - The Python sample calls `ctx.activity.strip_mentions_text().text`.
- CODE: `packages/api/src/microsoft_teams/api/activities/utils/strip_mentions_text.py`:
  - `StripMentionsTextOptions(account_id=None, tag_only=False)`; the docstring says "By default, all at-mentions listed in `entities` are removed";
  - the loop `continue`s when `options.account_id and mentioned_id != options.account_id`.
- CODE: `packages/api/src/microsoft_teams/api/activities/message/message.py` L88 `is_recipient_mentioned`, L105 `get_account_mention(account_id)`, L124 `strip_mentions_text()`, which mutates `self.text` and returns self.
- CODE: `grep -rni mention packages/apps/src/microsoft_teams/apps/routing/` finds nothing, so there is no mention route and no auto-strip in `App`.
- Import path (CODE, as in `packages/api/tests/unit/test_message_activities.py` L21): `from microsoft_teams.api.activities.utils import StripMentionsTextOptions`.

**Confidence:** High.

**Implication for docs/80:** §6.3 and §7.3. The conversational capability must:
- strip only its own bot's mention, so "@Architect ask @PE about X" keeps the lead mention;
- resolve other mentions through `entities`, never through the text;
- rely on `mentioned.id`: a lead appears as a `29:` id with a name, and another bot appears as a `28:<appId>` id (see K.2).

---

### D.1 What to persist for a proactive send from another process, and validity

**Answer:** To send into a known channel thread from a Temporal activity, persist the following per thread or channel.

| Field | Where it comes from | Required? |
|---|---|---|
| Thread conversation id `19:…@thread.tacv2;messageid=<root>` (or the base channel id + root message id) | `ctx.conversation_ref.conversation.id` | **yes** |
| `service_url` | inbound `activity.service_url`, also on `ctx.conversation_ref.service_url` | **strongly recommended** (see note below) |
| Tenant id | `ctx.activity.conversation.tenant_id` / `channel_data.tenant.id` | needed to create conversations, and for single-tenant token acquisition through `App(tenant_id=…)` |
| Bot id | config `CLIENT_ID`; the inbound `recipient.id` is `28:<appId>` | `App.send` sets `bot=Account(id=self.id)` from credentials, so this is config, not data |
| Team id / channel id | `channel_data.team.id` / `channel_data.channel.id` | for Graph (`/replies`) and new root posts |
| Root post's activity id | `SentActivity.id` returned by `app.send` | for in-place card updates (E.3) |

No conversation-reference blob is needed. `App.send` builds a `ConversationReference` from just the id, the `service_url` and the app's own id.

**Note on `service_url`.** Without a stored `service_url`, `App` falls back to `SERVICE_URL` (env) or `https://smba.trafficmanager.net/teams`. S3 says to avoid hardcoding the global URLs and to use the `serviceUrl` from the incoming activity or conversation reference. Sovereign clouds (GCC and others) need their own URL.

**Validity:**
- **Conversation id: no expiry documented.** S3 says to "Create the conversation only once, and store the resulting `conversationId`", and that "The `channelId` is global."
- **`serviceUrl`: no documented TTL.** I found no current primary source on how long a `serviceUrl` stays valid or whether it can change.
- **INFER mitigation:** refresh the stored `service_url` from every inbound activity in that team.
- Sends can still fail at any time: 403 `BotDisabledByAdmin` (S11), or 403 `MessageWritesBlocked` when the app is blocked or uninstalled (S3).

**Evidence:**
- S3 (2026-06-30; DOC):
  - "store the `tenantId` and then store either the `userId`, or `channelId` to create a new conversation";
  - "For `serviceUrl`, use the value from an incoming activity … Avoid hardcoding them";
  - "The conversation ID is unique for each agent within a specific channel";
  - "Use either the `conversationReference` object or `conversationId` and `tenantId` to send the message."
- S4 (2026-07-27; DOC): "you need to have the `conversation_id` of the chat or channel … store this value somewhere from an activity handler".
- CODE: `app.py` L117–119 is the `service_url` fallback, and L353–391 has `App.send(conversation_id, activity, *, service_url=None, agentic_identity=None)`, which builds `ConversationReference(channel_id="msteams", service_url=service_url or self.api.service_url, bot=Account(id=self.id), conversation=ConversationAccount(id=conversation_id))`.
- CODE: `activity_send.py` L31–37 clones the API client when `ref.service_url` differs.
- CODE: `app_process.py` L121–130 sets the inbound `conversation_ref.service_url = activity.service_url or token.service_url`.
- S11 (2026-09-28; DOC): `channelData.tenant.id` is "passed in all contexts". The same page says `channelData` "isn't included in messages in personal conversations", so for channels it is present, and the bridge should fall back to `conversation.tenantId` elsewhere. The request headers `x-ms-conversation-id` / `x-ms-tenant-id` are present.
- Gap: TTLs for `serviceUrl` and the conversation id.

**Confidence:** High for the field list. Low for validity periods, because none are documented.

**Implication for docs/80:** §7.5 and §10 item 4 are confirmed. The Postgres row keyed by `TeamsThreadId` holds `(conversation_id, service_url, tenant_id, team_id, channel_id, root_activity_id, bot_app_id)`. Refresh `service_url` on each inbound activity. **Change:** "conversation reference" can be reduced to these scalars, so no serialized blob is needed. **Per-bot caveat:** see D.4 / K.

---

### D.2 Install prerequisites for proactive channel posts

**Answer:**
- **Install first.** The app (each role bot's app) must be **installed in the team** before it can post proactively to any of its channels. Installing it is enough to get the conversation id: the bot receives an install / `conversationUpdate` event (SDK `@app.on_install_add`) that carries `conversation.id`, so it can be stored.
- **Proactive install.** Graph or a custom app policy can install the app; only apps in the org catalog or the Store can be installed that way.
- **RSC is not needed to post.** Plain proactive posting needs only team installation. `ChannelMessage.Send.Group` exists as an RSC permission, but that is for Graph sends (S10).
- **Private channels:** agents can't post in them (S1).

**Evidence:**
- S3 (2026-06-30; DOC): "For a group chat or team, the app that contains your agent must be first installed in that location." "Ensure that the agent is installed in the team before you can send a proactive message to a channel." "You can only install apps that are in your organizational app catalog or the Microsoft Teams Store."
- S1 (2026-06-23; DOC): "You can also store the `conversationId` during installation to enable proactive messaging later". The page also has the `@app.on_install_add` sample and the private-channel limitation.

**Confidence:** High.

**Implication for docs/80:** §15 and §7.5. Factory and every role bot that posts must be installed in each linked team. Use the install event as the `@Factory link` bootstrap moment to capture `service_url`, tenant and team/channel ids.

---

### D.3 Minimal Python call: proactive send or thread reply from stored ids + credentials

**Answer:** Build an `App` with credentials, call `await app.initialize()` (this starts no HTTP server), then:
- `await app.send(conversation_id, text_or_card, service_url=…)` for a new message in a known conversation;
- `await app.reply(channel_conversation_id, root_message_id, text_or_card, service_url=…)` to reply into a thread.

Both return a `SentActivity` whose `.id` is the new message id.

To update the message in place later:
```python
await app.api.conversations.update_activity(conversation_id, activity_id, MessageActivityInput(...))
```
or `app.send()` with an activity whose `id` is set. `send_or_update_activity` routes to update when `activity.id` is set (CODE `activity_send.py` L38–50).

**Evidence:**
- S4 (2026-07-27; DOC): `await app.reply(conversation_id, message_id, "Thread update!")` and `await app.send(thread_id, "Sent via helper")`.
- CODE: `examples/proactive-messaging/src/main.py`: "Uses app.initialize() instead of app.start() (no HTTP server)", `await app.send(conversation_id, card)`, `await app.api.conversations.update_activity(conversation_id, activity_id, updated)`.
- CODE: `app.py` L250 `async def initialize(self)`; L353 `send`; L443 `reply`; `send` raises `ValueError("app not initialized …")` if `initialize()` hasn't run.
- CODE: `options.py` L63–81: `client_id`, `client_secret` and `tenant_id` are all supported, and so are managed identity and federated identity credentials (`managed_identity_client_id`).

Minimal snippet for §4.2 item 4 (all SDK calls cited above):

```python
# notify.py — stands in for a Temporal activity on the worker host.
# Requires: pip install microsoft-teams-apps==2.1.0
import os
from microsoft_teams.apps import App                      # CODE apps/__init__.py
from microsoft_teams.api import MessageActivityInput      # CODE api/activities/message

_app: App | None = None

async def _get_app() -> App:
    global _app
    if _app is None:
        _app = App(                                       # CODE options.py L63-67
            client_id=os.environ["FACTORY_CLIENT_ID"],
            client_secret=os.environ["FACTORY_CLIENT_SECRET"],
            tenant_id=os.environ["TEAMS_TENANT_ID"],      # single-tenant app
        )
        await _app.initialize()                           # CODE app.py L250; no HTTP server
    return _app

async def notify_activity(row: dict, text: str) -> str:
    """row = persisted ids (D.1), same schema as save_thread_row() in the §4.2-item-2 sketch:
    teams_thread_id, channel_conversation_id, root_message_id, service_url, tenant_id, bot_app_id."""
    app = await _get_app()
    sent = await app.reply(                               # CODE app.py L443-480 (3-arg form)
        row["channel_conversation_id"],                   # e.g. "19:abc@thread.tacv2" (any ;messageid= suffix is stripped)
        row["root_message_id"],                           # numeric string, else ValueError (thread.py L22)
        MessageActivityInput(text=text).add_ai_generated(),   # S7
        service_url=row["service_url"],                   # CODE app.py L449 kwarg; else env/global fallback
    )
    return sent.id                                        # store for later update_activity (E.3)

async def update_board(row: dict, activity_id: str, card_activity: MessageActivityInput) -> None:
    app = await _get_app()
    # CODE examples/proactive-messaging/src/main.py L95. Same conversation id the card was posted to.
    await app.api.conversations.update_activity(row["teams_thread_id"], activity_id, card_activity)
```

Caveat (INFER): `app.api` is bound to the default `service_url`. `App.send` / `reply` honour `service_url=`, but a direct `app.api.conversations.update_activity` call uses the app-level URL. For a non-default `service_url`, set `App(service_url=…)` or `SERVICE_URL`, or route the update through `app.send(conversation_id, <activity whose .id = activity_id>, service_url=…)`. `send_or_update_activity` routes to update when `activity.id` is set. I did not verify the exact `MessageActivityInput` constructor field for `id`.

**Confidence:** High for `send` / `reply` / `initialize` (CODE + DOC). Medium for the update caveat, which is INFER from code paths.

**Implication for docs/80:** §7.5 `notify_activity(event)` is confirmed feasible with **no inbound request**: credentials + persisted scalars are enough. One `App` per bot identity is needed (K.3 is out of my scope). The activity should catch 403 (`MessageWritesBlocked`, `BotDisabledByAdmin`) and 429 and map them to Temporal retry or non-retry.

---

### D.4 Can a proactive send create a new channel post (thread root)?

**Answer:**
- **Yes, per the docs.** S3 lists "a new conversation thread in a channel" as something proactive messaging can create, but says "You can't create a new group chat or a new channel".
- **In the Python SDK**, the typed path is `app.send(<base channel conversation id without ;messageid=>, activity)`. INFER/CODE: this posts a new top-level message. The returned `SentActivity.id` is the new root message id, so the thread id is `f"{channel_id};messageid={sent.id}"`.
- **The raw `POST /v3/conversations` path** (`isGroup: true`, `channelData.channel.id`) is documented only in the **archived** v3 page (S12). It returns `{"id": conversationId, "activityId": …}`.
- **SDK gap:** the Python `CreateConversationParams` has **no `is_group` or `bot` field** (CODE). Using `app.api.conversations.create()` for a channel post would therefore rely on extra fields passing through, which is unverified.

**Evidence:**
- S3 (2026-06-30; DOC): "The SDK creates the conversation automatically when you call app.Send() … For example, a new one-on-one chat or a new conversation thread in a channel. You can't create a new group chat or a new channel in a team with proactive messaging." The page also says "You can also use the `teamId` to create a new conversation thread in the general or default channel".
- S12 (2023-04-02, **PRE-GA, archived**; DOC): "Your team-added bot can post into a channel to create a new reply chain". Its HTTP sample is `POST /v3/conversations` with `"isGroup": true` and `channelData.channel.id`, and its Teams SDK Python tab shows `conversation_id = "19:channelId@thread.tacv2"; await app.send(conversation_id=conversation_id, activity=activity)`.
- CODE: `app.py` L362–365 docstring: "For channel threads, the conversation ID must include `;messageid=`". INFER: without the suffix the post is top-level.
- CODE: `api/clients/conversation/params.py` `CreateConversationParams` fields are `members`, `tenant_id`, `activity`, `channel_data`; `ConversationResource` has `id`, `activity_id`, `service_url`.

**Per-bot id risk (needs a spike).** S3 says "The conversation ID is unique for each agent within a specific channel" and also "The `channelId` is global". This conflicts with docs/80's single shared `TeamsThreadId`.
- If the Bot Connector's thread conversation id differs per bot, then the Architect bot replying into Factory's thread needs its *own* id for that thread, and one shared `TeamsThreadId` would break.
- The observed format `19:<channel>@thread.tacv2;messageid=<root>` is built from global ids, which suggests it is the same for every bot. That is INFER and unverified.

**Confidence:** Medium. The capability is DOC'd, but the exact Python path rests on an archived page plus a docstring inference, and the per-bot id question is unresolved.

**Implication for docs/80:**
- §6.1 and §10. Factory creates the thread root (the board card) with `app.send(channel_id, card)` and stores `sent.id` as the root id.
- **Spike S-D4:**
  - (1) Confirm that `app.send(bare_channel_id)` creates a top-level post and returns the root id.
  - (2) Confirm that a *second* bot can `app.reply(channel_id, root_id, …)` into Factory's thread using the same ids.
  - (3) Compare the `conversation.id` each bot receives inbound for the same thread.

  If (2) or (3) fails, `TeamsThreadId` must become per-bot (a `(bot_app_id, conversation_id)` map). Severity: **changes design** if it fails.

---

### H.1 Inbound identity fields and which are safe to authorize on

**Answer:** Fields on an inbound channel message activity:

| Field | Example / format | Stability | Use |
|---|---|---|---|
| `from.id` | `29:1XJK…` (opaque) | **Unique per (bot, user)**: the same human has a *different* `from.id` for each bot | Bot Connector addressing only; never cross-bot correlation |
| `from.aadObjectId` (`from_.aad_object_id`) | Entra object id GUID | stable, unique per user in the tenant, same for every bot | **authorize on this** (+ tenant) |
| `from.name` | display name | mutable | display only |
| `from.email` (Python `Account.email`) | — | the SDK docstring says "when provided by the channel"; no current doc says Teams populates it inbound | don't rely on it |
| UPN | — | **not on the inbound `Account`**. It is on `TeamsChannelAccount.user_principal_name`, returned by the members/roster API | display / lookup only, never a key |
| `from.userRole` (`user_role`) | e.g. user/guest | as provided | can filter guests (INFER) |
| Tenant | `channelData.tenant.id` (channel and group contexts; S11 says `channelData` is absent in personal chats), `conversation.tenantId`, and the HTTP header `x-ms-tenant-id` | stable | **must check** against our tenant |
| `recipient.id` | `28:<bot app id>` | stable per bot | tells which bot was addressed |
| `channelData.team.id`, `channelData.channel.id` | `19:…@thread.tacv2` | stable ("definitive source for team and channel IDs") | channel ↔ repo map |

**Why the fields can be trusted (INFER).** The SDK validates the inbound Bot Service JWT (J.7, not my scope), so `from` and `channelData` are asserted by the service. The *message text* is not authoritative: S1 warns "It's possible for the person sending the message to alter it."

**Evidence:**
- S3 (2026-06-30; DOC): "The `aadObjectId` is unique to the user … The `userId` is unique to your agent ID and a particular user. You can't reuse the `userId` between agents. The `channelId` is global." "Teams doesn't support sending proactive messages using email or User Principal Name (UPN)."
- S11 (2026-09-28; DOC):
  - sample `from: {id: "29:…", name, aadObjectId}` and `recipient.id: "28:c9e8c047-…"`;
  - "`channelData` … is a definitive source for team and channel IDs";
  - "`tenant.id`: Microsoft Entra tenant ID passed in all contexts";
  - `channelData.teamsTeamId` / `teamsChannelId` are "Deprecated";
  - the headers `x-ms-conversation-id` / `x-ms-tenant-id` are present.
- CODE: `packages/api/src/microsoft_teams/api/models/account.py`:
  - `Account` has `id`, `aad_object_id`, `name`, `email` ("Email address for the account, when provided by the channel"), `user_role`, `role`, `tenant_id` (agentic);
  - `TeamsChannelAccount` (L96+) has `user_principal_name` ("Unique User Principal Name (UPN) for the user in AAD"), `email`, `given_name`, `surname`, `tenant_id`.

**Confidence:** High for `from.id` being per-bot, `aadObjectId` being stable, and tenant handling. Medium for whether email or UPN ever appear inbound: the docs are silent and the CODE says "when provided".

**Implication for docs/80:** §13 is confirmed and strengthened.
- Key leads on `(tenant_id, aad_object_id)`, never on `from.id`. With six role bots, `from.id` differs per bot for the same lead, so a `from.id` key would need six entries per person.
- Reject any activity whose `channelData.tenant.id` isn't ours.
- Use `channelData.channel.id` for the channel ↔ repo map.
- For the GitHub link (H.2), key the token store on `aad_object_id`.

---

### K.2 Do bots receive other bots' channel messages?

**Answer:** **Can't be confirmed from primary sources.**
- No current Learn page or SDK doc states whether a message posted by bot A is delivered to bot B, either when A @mentions B or when B has RSC `ChannelMessage.Read.Group`.
- S1 and S2 describe delivery only in terms of "messages" and "@mentioned". S1's mention guidance is about users and tags ("Your agent can mention other users"; `@everyone` is unsupported) and doesn't address bots mentioning bots.
- What we can rely on (DOC): a bot's id has the `28:` prefix (S11 example `recipient.id`), and user ids are `29:`.

**Evidence:**
- S1, S2, S11: none of them address bot-authored messages (absence checked 2026-10-09).
- Searches on learn.microsoft.com turned up only Q&A and forum threads, which are not evidence.
- INFER: a self-filter can key on our known bot app ids (`from_.id == f"28:{app_id}"` for each of our apps) and/or on `from_.id.startswith("28:")`, which drops all bots, including third-party ones.

**Confidence:** Low. This is an explicit gap.

**Implication for docs/80:** §6.5 is **confirmed as the right design**: "enforced by us either way, and the platform is not relied on". Add the concrete filter rule: drop an inbound activity if `from_.id` is in `{28:<appId> for each role bot}`. Optionally also drop `aad_object_id` values that belong to our bots' service principals.
- **Spike S-K2:** post from bot A with and without an `<at>` mention of bot B. Do it once with B lacking RSC and once with B holding RSC, and observe B's endpoint. Severity: **detail**, because the design already self-filters.

---

### K.6 With several bots in one channel, does only the @mentioned bot get the activity?

**Answer:** INFER from DOC (S1/S2):
- **Without RSC:** yes. Each bot receives only the messages that @mention *it*. A message mentioning two bots is delivered to both, as two separate activities, each with its own `recipient.id`.
- **With RSC** `ChannelMessage.Read.Group` on a bot: that bot receives **every** message in the team's channels, whether or not it is mentioned. It must filter with `activity.is_recipient_mentioned()` (SDK) or with the entity check in S2.
- **Delivery is per bot.** Each delivery goes to that bot's own messaging endpoint, signed for that bot's app id (INFER).
- **Mention picker:** I found no primary source on how the Teams client's @mention picker disambiguates several bots. It lists the installed apps by name (UX).

**Evidence:**
- S1 (2026-06-23; DOC): default "only receive messages when they're directly @mentioned".
- S2 (2026-09-28; DOC): "When ChannelMessage.Read.Group … RSC is in the app manifest, this method is called even when agent is not @mentioned", with a filter on `entity.mentioned.id == ctx.activity.recipient.id`.
- CODE: `message.py` L88 `is_recipient_mentioned()` compares mention ids with `self.recipient.id`.
- Gap: no doc explicitly covers delivery when several bots are installed or mentioned together.

**Confidence:** Medium. It is a direct consequence of documented per-bot rules, but there is no explicit multi-bot statement.

**Implication for docs/80:** §2 and §6.3 are confirmed. "@Architect Agent make it event-driven" reaches the Architect bot only, as long as the Architect bot lacks RSC. **Recommendation (INFER):**
- give RSC `ChannelMessage.Read.Group` to **Factory only** (for the C.2 thread log);
- keep the role bots mention-only.

This minimises owner-consent prompts and ensures routing comes from Teams' own mention delivery. If role bots do get RSC, every handler must start with an `is_recipient_mentioned()` guard.

---

## Code sketch for §4.2 item 2: receive an @mention in a channel thread and reply in that thread

```python
# architect_bot.py — Teams SDK for Python 2.1.0 (microsoft-teams-apps)
from microsoft_teams.api import MessageActivity, MessageActivityInput
from microsoft_teams.api.activities.utils import StripMentionsTextOptions   # CODE tests/unit/test_message_activities.py L21
from microsoft_teams.apps import ActivityContext, App

app = App(client_id=..., client_secret=..., tenant_id=...)                   # CODE options.py L63-67
OUR_BOT_IDS: set[str] = {...}   # {"28:<factory-app-id>", "28:<architect-app-id>", ...}  (K.2 self-filter)
OUR_TENANT = "..."

@app.on_message                                                              # CODE routing/generated_handlers.py L105
async def on_message(ctx: ActivityContext[MessageActivity]) -> None:
    act = ctx.activity
    if act.from_.id in OUR_BOT_IDS:                                          # docs/80 §6.5, enforced by us
        return
    cd_tenant = act.channel_data.tenant.id if act.channel_data and act.channel_data.tenant else None
    tenant = cd_tenant or act.conversation.tenant_id                         # S11: channelData.tenant.id "passed in all contexts"
    if tenant != OUR_TENANT:                                                 # H.1 tenant check
        return
    if not act.is_recipient_mentioned():                                     # CODE message.py L88; needed if this bot has RSC (K.6)
        return
    # Strip only OUR mention; keep @lead / @other mentions (S1 "Preserve other mentions")
    act.strip_mentions_text(StripMentionsTextOptions(account_id=act.recipient.id))   # CODE strip_mentions_text.py
    prompt = act.text or ""

    # Persist proactive-send scalars (D.1) — refresh service_url on every inbound activity
    thread_conv_id = ctx.conversation_ref.conversation.id                    # "19:…@thread.tacv2;messageid=<root>" (C.3)
    base, _, root = thread_conv_id.partition(";messageid=")
    await save_thread_row(
        teams_thread_id=thread_conv_id,
        channel_conversation_id=base,
        root_message_id=root or act.id,                                      # root post: its own id (CODE threading_handlers.py)
        service_url=ctx.conversation_ref.service_url,                        # CODE app_process.py L121-130
        tenant_id=tenant,
        bot_app_id=act.recipient.id,                                         # "28:<appId>"
        lead_aad_object_id=act.from_.aad_object_id,                          # H.1 — authorize on this, never from_.id
    )

    answer = await answer_question(prompt, thread_conv_id)                   # our LiteLLM-routed capability (§7.3)
    # In a channel, ctx.send posts into the CURRENT thread, no quote (CODE activity_context.py L241; S5)
    await ctx.send(MessageActivityInput(text=answer).add_ai_generated())     # S7: AI label works in channels
    # or: await ctx.reply(answer)  -> same thread, with a visual quote of the inbound message (L276)
```

Not covered here, because they are out of my scope: mounting this `App` inside aiohttp (B.6) and hosting N `App`s in one process (K.3). By default `app.start()` brings FastAPI/uvicorn (`pyproject.toml` deps; `options.py` "Defaults to FastAPIAdapter"), and `http_server_adapter` is the plug point.

## Cross-cutting risks surfaced (for §4.3)

| Item | Severity |
|---|---|
| D.4: conversation id "unique for each agent within a specific channel" (S3) vs a single shared `TeamsThreadId` across 6 bots. Spike S-D4. | **changes design** if per-bot |
| C.2: protected-API status of Graph `/replies` via RSC unconfirmed (protected-APIs page 404). Prefer our own RSC-fed thread log. | changes design (context source) |
| K.2: bot-to-bot delivery undocumented. §6.5 self-filter already covers it. Spike S-K2. | detail |
| C.4: streaming unavailable in channels (DOC). Typing in channels unconfirmed. | detail (confirms §6.4) |
| C.5: Learn claims a "dedicated mention route", but Python has none (CODE). The default `strip_mentions_text()` strips all mentions. | detail |
| D.1: no documented TTL for `serviceUrl`; refresh on every inbound activity. | detail |
| D.4: Python `CreateConversationParams` lacks `is_group`/`bot`; the new-root path rests on `app.send(bare_channel_id)` plus an archived doc. | detail, spike |
