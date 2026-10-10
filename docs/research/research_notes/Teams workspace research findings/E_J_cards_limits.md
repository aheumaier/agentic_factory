# Adaptive Cards in Teams and Teams bot operational limits (E.1–E.6, J.1–J.3, K.4)

Researched 2026-10-09. Format follows research prompt §4.1. Every source carries two dates where Learn gives them:
`updated_at` (last publish) and `ms.date` (last content review). A source whose `ms.date` is before 2026-05 is marked
**PRE-GA**, with a note on whether it still applies. Labels: **DOC** (a primary doc says it), **CODE** (read in SDK
source or samples), **INFER** (my reasoning).

Pinned versions:
- **SDK:** `microsoft-teams-apps` **2.1.0**, PyPI upload 2026-09-16, git tag `v2.1.0` dated 2026-09-15. I read
  `github.com/microsoft/teams.py` at `main` (commit `8539006`, 2026-10-07). Each API cited below was diffed against
  `v2.1.0` and is the same there.
- **Adaptive Card schema:** **1.6** is the ceiling for Teams. The SDK's `AdaptiveCard.version` defaults to `"1.5"`.

Caveat on the "SDK name" in docs. learn.microsoft.com Teams pages (2026) now call bots "agents" and show
Teams SDK (`microsoft_teams.*`) Python samples. Code below uses those packages, not `botbuilder-*`.

---

### E.1 Adaptive Card schema version and mobile support

**Answer:**
- **Version ceiling:** Teams supports Adaptive Card features up to **v1.6**. This applies to bot-sent cards,
  action-based message extensions, and also to user-sent cards (search message extensions, link unfurling) and
  dialogs. The Teams **mobile** app also supports up to **1.6**. Cards with a later schema version "might not render
  correctly or might have limited or inconsistent functionality on mobile".
- **Universal Actions** (`Action.Execute`, `refresh`) need `version: "1.5"` or higher. Below 1.5 the card "stops
  working" on Teams. Microsoft advises an `Action.Submit` fallback for older clients.
- **Teams-wide restrictions (all clients), DOC:**
  - positive/destructive action styling is unsupported;
  - Adaptive Cards in Teams do not support file or image uploads;
  - `isEnabled` on `Action.Submit` is unsupported.
- **Mobile-specific:** no element-by-element "unsupported on mobile" list exists in current primary docs. What is
  documented:
  - People Picker, Typeahead (dynamic search) and People icon are supported on mobile and desktop.
  - On mobile, manual refresh of a user-specific view is a long-press context menu item, not the "…" menu.
  - Full-width cards must be tested at narrow widths because content can be truncated.
- **Mobile limits on related features (see E.6):** `shareDeepLink` doesn't work on mobile. A deep link to an app
  works on mobile only after the app is approved for the Teams mobile client.

**Evidence:**
- https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/cards/cards-reference
  (updated_at 2026-08-19; ms.date 2024-09-16 → PRE-GA; DOC). "Support for Adaptive Cards" notes give v1.6 for bots
  and mobile, plus the styling/upload/`isEnabled` restrictions. The page labels itself **"legacy"** and points to the
  Adaptive Cards documentation hub. Its 1.6 statements were re-published 2026-08 and nothing contradicts them, so
  **they still apply**.
- https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/cards/universal-actions-for-adaptive-cards/work-with-universal-actions-for-adaptive-cards
  (updated_at 2026-07-27; ms.date 2022-12-20 → PRE-GA, still applies; DOC). Covers the 1.5 minimum and the fallback
  advice.
- https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/what-are-cards
  (updated_at 2026-06-30; ms.date 2023-01-08 → PRE-GA, still applies; DOC). Covers People Picker, Typeahead and
  People icon on mobile.
- teams.py `packages/cards/src/microsoft_teams/cards/core.py`, `class AdaptiveCard`: `version: Optional[Version] = "1.5"`
  (CODE, v2.1.0).

**Confidence:** high for the 1.6 ceiling and the 1.5 Universal Actions minimum. Low for a complete list of what is
unsupported on mobile, because none is published.

**Gap:** the Adaptive Cards hub (adaptivecards.microsoft.com) is a JS single-page app and couldn't be fetched as text.
Its per-host version matrix is unverified.

**Implication for docs/80:** §14 cards & UX. Author all cards at **`version: "1.5"`** (the SDK default; 1.6 at most).
Use only TextBlock, FactSet, ColumnSet, Container, Image, ActionSet, `Action.Execute` and `Action.OpenUrl`.
Confirms the working assumption. **New risk (detail):** test the team-board card at mobile width.

---

### E.2 `Action.Execute` vs `Action.Submit`, how the SDK surfaces each, user-specific views in channels

**Answer:**
- **`Action.Execute` (Universal Actions)** sends an `invoke` activity named `adaptiveCard/action`.
  - The SDK surfaces it as `AdaptiveCardInvokeActivity`.
  - `@app.on_card_action` catches every `adaptiveCard/action` invoke.
  - `@app.on_card_action_execute` (global) or `@app.on_card_action_execute("<id>")` (routed) checks that
    `value.action.type == "Action.Execute"`.
- **Routing key, a trap.** The routed form matches `ctx.activity.value.action.data["action"]`. It does **not** match
  the Universal Actions `verb`, which is what the learn.microsoft.com Universal Actions pages route on. Put a
  discriminator such as `"action": "plan_approve"` in `data` if you use routed handlers. Otherwise use the global
  handler and switch on `value.action.verb` yourself.
- **What the handler must return:** an `AdaptiveCardInvokeResponse`, which is a union of these types:
  - `AdaptiveCardActionCardResponse(value=AdaptiveCard)`: status 200, type `application/vnd.microsoft.card.adaptive`.
    The client **replaces the card** for the user who acted.
  - `AdaptiveCardActionMessageResponse(value=str)`: status 200, type `application/vnd.microsoft.activity.message`.
    The client shows a transient message.
  - `AdaptiveCardActionErrorResponse`: status 400/500, type `application/vnd.microsoft.error`.
  - `...LoginResponse` (401), `...IncorrectAuthCodeResponse` (401) and `...PreconditionFailedResponse` (412) for the
    auth flows.
  - If a handler returns something that is not an `InvokeResponse`, the SDK wraps it as
    `InvokeResponse(status=200, body=result)`.
- **Card-replacement scope (INFER, from the user-specific-views doc):** an `AdaptiveCardActionCardResponse` updates
  the view of the user who invoked it. To change the card for **everyone** (for example "Approved by X"), the bot must
  also edit the message (E.3). The "Up to date cards" pattern is: invoke response + bot message edit, and the edit
  triggers an auto-refresh for the users in `userIds`.
- **`Action.Submit`** is "Legacy. Prefer `Action.Execute`" in both the Teams SDK docs and Learn.
  - The SDK docstring says "Action.Submit and other action types do not trigger AdaptiveCardInvokeActivity in modern
    Teams clients".
  - The last primary description of how it arrives is PRE-GA: "Teams sends a **message activity** to the bot". An
    object `data` "populates the activity's `value` property while the `text` property is empty". A string `data`
    posts a visible user message.
  - In the SDK this would reach `@app.on_message`, with `MessageActivity.value: Optional[Any]` (CODE).
  - No handler return value applies to `Action.Submit`; it is a plain message turn.
  - The current (2026-06) Learn card-actions page no longer documents `Action.Submit`'s delivery shape at all.
- **User-specific views and `refresh.userIds` in channels: yes, they work in chats and channels.**
  - At most **60** users can be listed in `refresh.userIds`, and "maximum 60 different users can see a different
    version of the card".
  - `userIds: []` turns off automatic refresh. Users get a manual "Refresh card" menu item ("…" on desktop/web,
    long-press on mobile).
  - Omitting `userIds` auto-refreshes for **all** members only when the chat or channel has **≤60** members.
  - `userIds` holds user MRIs (`29:…`, i.e. `activity.from.id`), not AAD object ids.
  - Each auto-refresh is an `adaptiveCard/action` invoke with `"trigger": "automatic"`, which costs one call to the
    bot per listed user per refresh.
  - The SDK `RefreshDefinition.user_ids` docstring states the same 60-user rule (CODE).

**Evidence:**
- teams.py `packages/apps/src/microsoft_teams/apps/routing/activity_handlers.py`, `on_card_action_execute`. The
  selector checks `ctx.value.action.type != "Action.Execute"` and `data.get("action") == action_or_handler`. Last
  changed 2026-04-01 (PR #222); present in v2.1.0 (CODE).
- teams.py `packages/apps/src/microsoft_teams/apps/routing/activity_route_configs.py:607`: `on_card_action` matches
  `activity.name == "adaptiveCard/action"` (CODE).
- teams.py `packages/api/src/microsoft_teams/api/models/adaptive_card/adaptive_card_action_response.py` (the six
  response classes) and `models/invoke_response.py:75` (`AdaptiveCardInvokeResponse = AdaptiveCardActionResponse`)
  (CODE).
- teams.py `packages/apps/src/microsoft_teams/apps/app_process.py`: non-`InvokeResponse` results are wrapped as
  status 200 (CODE).
- teams.py `examples/cards/src/main.py:347-430`: `@app.on_card_action_execute` handlers return
  `AdaptiveCardActionMessageResponse` (CODE, 2026).
- https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/cards/cards-actions
  (updated_at 2026-08-03; ms.date 2026-06-10; DOC). Action table marks `Action.Submit` "Legacy"; Universal Action
  submissions are "surfaced to your app as card.action activities"; there is a Python `@app.on_card_action` sample.
- https://microsoft.github.io/teams-sdk/python/in-depth-guides/adaptive-cards/executing-actions (accessed 2026-10-09,
  no date shown; DOC). Says `Action.Submit` is legacy and handlers return `AdaptiveCardInvokeResponse`.
- PRE-GA `Action.Submit` behaviour: MicrosoftDocs/msteams-docs `cards-actions.md` at commit `7e4ea66` (2026-01-22;
  ms.date 2024-11-07 → PRE-GA; DOC). Lines 437–444 cover the message activity with `value`. The same paragraph also
  says that without `msteams` in `data` it "works like a regular Bot Framework invoke action", so the old doc
  contradicts itself. Treat it as **partly applicable, unverified on current clients**.
- https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/cards/universal-actions-for-adaptive-cards/user-specific-views
  (updated_at 2026-10-09; ms.date 2026-10-01; DOC). Covers the 60-user maximum and the `trigger: automatic` invoke.
- work-with-universal-actions page (above; PRE-GA, still applies; DOC). Covers `userIds` semantics, `[]`, the ≤60
  auto-refresh rule and MRI format.
- https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/cards/universal-actions-for-adaptive-cards/overview
  (updated_at 2026-10-09; ms.date 2026-09-30; DOC). User-specific views and sequential workflows work "in the chat or
  channel".
- teams.py `cards/core.py`, `class RefreshDefinition`, `user_ids` docstring (CODE).

**Confidence:**
- High for `Action.Execute` handling and the return types (code and docs agree).
- High for the 60-user cap.
- Medium for how `Action.Submit` arrives on current clients (only PRE-GA docs plus a code docstring).

**Implication for docs/80:**
- §12 decisions across surfaces and §14 cards: **confirm `Action.Execute` only; drop `Action.Submit`.**
- Gate buttons (`plan_approved` / `plan_rejected`) should carry `data` with:
  - `action`, the routing key;
  - `workflow_id`, `gate`, and **`attempt` / decision-window id**, so a stale card can't release a later window
    (matches §1.1 of the prompt);
  - `verb` for readability.
- **Change:** the bot must return `AdaptiveCardActionCardResponse` **and** edit the message (E.3) to show "resolved by
  X" to everyone.
- **New risk (detail):** a user-specific "Approve/Reject only for leads" view is feasible (2 leads ≪ 60). Each lead's
  client calls the bot on every refresh, so the bot must answer within the invoke timeout (J.3).

---

### E.3 Updating a posted card in place (team board, "resolved by X via GitHub")

**Answer:**
- **API:** `PUT {serviceUrl}/v3/conversations/{conversationId}/activities/{activityId}` with a new Activity; the
  response is a `ResourceResponse`. You "must cache the activity ID returned by the original post call". The new
  message need not match the original's type.
- **Python, v2.1.0:** `await app.api.conversations.update_activity(conversation_id, activity_id, MessageActivityInput().add_card(card))`.
  - Inside a handler, `ctx.api.conversations.update_activity(...)` does the same.
  - The form shown in the Learn page's Python sample, `ctx.api.conversations.activities(conversation_id).update(...)`,
    is marked **`@deprecated`** in v2.1.0 ("Use the flattened activity methods… This grouped accessor will be removed
    in a future release"). Don't copy the Learn sample verbatim.
- **Permissions:** no Graph/RSC permission is needed. The call uses the bot's own Bot Connector token, the same as
  sending.
- **Who may update:**
  - DOC: "An agent can't update or delete messages sent by the user".
  - That **only the posting bot** may update its own message is INFER. The PUT is bot-token-authenticated and scoped
    by activity id, but I found no doc sentence saying so for bot-to-bot.
  - Design for only the posting bot editing a card: the Coordinator bot owns the team-board card.
- **Rate limits:**
  - The rate-limit table has no separate "update" row.
  - "All requests are subject to the same rate limiting policy, including sending messages…", so updates count
    against the per-bot per-thread and all-bots per-thread budgets (J.1/K.4).
  - The doc recommends you "avoid issuing multiple requests to the same personal or channel conversation. Instead,
    create a batch".
- **From a proactive context: yes.**
  - The proactive-messaging doc says to update a proactive message with `UpdateAsync(conversationId, activityId, updatedActivity)`.
  - teams.py `examples/proactive-messaging` calls `app.initialize()` (no HTTP server), then `app.send(...)`, then
    `app.api.conversations.update_activity(conversation_id, activity_id, updated)`.
- **Message-splitting trap:** if one activity carries both text and an attachment, Teams splits it into two activities
  "and you do not receive the message ID in response", so you can't update it later. The SDK returns a placeholder id
  when no `id` comes back. **Send the board card as an attachment-only activity.**
- **Edit triggers refresh:** a bot message edit re-triggers an auto-refresh (an `adaptiveCard/action` invoke) for each
  user in the edited card's `refresh.userIds`.

**Evidence:**
- https://learn.microsoft.com/en-us/microsoftteams/platform/bots/build-conversational-capability#update-and-delete-messages-sent-from-bot
  (updated_at 2026-09-28; ms.date 2026-09-28; DOC). The old `.../bots/how-to/update-and-delete-bot-messages` URL
  301-redirects here. Covers:
  - the PUT endpoint;
  - "can't update or delete messages sent by the user";
  - the Python `update` sample using the deprecated accessor;
  - the "Update cards" example using `reply_to_id`;
  - the message-splitting note.
- https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/conversations/send-proactive-messages
  (updated_at 2026-09-25; ms.date 2026-06-30; DOC). Covers updating or deleting a proactive message and caching the
  activity ID.
- teams.py `packages/api/src/microsoft_teams/api/clients/conversation/client.py`: `@deprecated` on `activities()`;
  `update_activity()` at line 299 (present in v2.1.0) (CODE).
- teams.py `clients/conversation/activity.py:105` (`update` does the HTTP PUT) and `create()` (placeholder id when
  the response lacks one) (CODE).
- teams.py `examples/proactive-messaging/src/main.py:78-98` (CODE, last changed 2026-07-10).
- https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/cards/universal-actions-for-adaptive-cards/up-to-date-views
  (updated_at 2026-09-21; ms.date 2026-09-16; DOC). A bot message edit triggers auto-refresh for `userIds` users.
- https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/rate-limit (updated_at 2026-07-27; ms.date
  2025-02-06 → PRE-GA, still applies, no newer replacement; DOC). Source of "all requests are subject to the same rate
  limiting policy".

**Confidence:** high for the API, the proactive update and message splitting. Medium for "only the posting bot"
(INFER). High that no update-specific limit is published.

**Implication for docs/80:**
- §14 / §7 outbound notifier: **confirm** the live team-board card and "resolved by X via GitHub" (GitHub-path
  decisions edit the Teams card from the Temporal side).
- **New design rule:** persist `(service_url, conversation_id, activity_id)` per card in Temporal or the notifier
  store, and make each card update a debounced, coalesced activity (one PUT per board state change, not per event).
- **Change:** the board card has one owner bot, the Coordinator. Agent bots never edit it.

---

### E.4 Images in cards

**Answer:**
- **Formats:** PNG, JPEG or GIF. **SVG and animated GIF are not supported.** Max **1024×1024 px**.
  - Picture messages (images as message attachments) may be up to 1024×1024 and **1 MB**.
  - The "Inline card images" rules sit under "Common properties for all cards" on the legacy reference page. They are
    written for Bot Framework rich cards (hero/thumbnail) and may not map 1:1 onto the Adaptive Card `Image` element.
    Treat them as the safe envelope.
- **Hosted URL vs data URI:**
  - Teams recommends a "link to the publicly available image" over HTTPS, ideally on a CDN.
  - Redirecting image URLs are **not supported**.
  - The Adaptive Card schema allows **data URIs in `Image.url` from schema 1.2+**.
  - Teams' own size note says the 100 KB message limit "doesn't include base64 encoded images", which implies base64
    images are accepted.
  - In GCC High/DoD, images must be base64 because external links don't render.
- **Data URI size:** I found no documented cap specific to data URIs.
- **Auth on image URLs:** **not documented.** Every primary source says "publicly available" and that redirects aren't
  followed. So an image URL that needs a bearer token, or redirects to a sign-in page, will very likely fail (INFER).
  A short-lived pre-signed or capability URL with no redirect is the realistic option (INFER).

**Evidence:**
- cards-reference (updated_at 2026-08-19; ms.date 2024-09-16 → PRE-GA, legacy-labelled, still applies; DOC).
  Covers "Images must be at most 1024 × 1024 pixels and in PNG, JPEG, or GIF format. Animated GIF and SVG formats
  aren't supported." and "the redirect in image URL is not supported".
- build-conversational-capability (updated_at 2026-09-28; DOC). Covers pictures at 1024×1024 and 1 MB, and GCC
  High/DoD base64 embedding.
- https://adaptivecards.io/schemas/adaptive-card.json, `definitions.Image.properties.url.description`: "The URL to the
  image. Supports data URI in version 1.2+" (accessed 2026-10-09; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/limits-specifications-teams (updated_at 2026-10-07; ms.date
  2026-07-16; DOC). "100 KB size limitation doesn't include base64 encoded image."

**Confidence:**
- High: no SVG, 1024×1024, no redirects.
- Medium: data URIs work in Teams bot cards (schema supports them, size doc implies it, no explicit Teams statement).
- Low: auth on image URLs (undocumented).

**Implication for docs/80:**
- §9 producers and §14: **change.** Mermaid/C4 diagrams must be **rasterized to PNG** (≤1024 px on the long edge)
  for card thumbnails; SVG is out.
- Serve thumbnails from an unauthenticated, non-redirecting HTTPS URL with unguessable paths. Or, for small
  thumbnails, inline them as `data:image/png;base64,…`, which doesn't count toward the 100 KB limit per the docs.
  That avoids exposing an image host.
- Full-fidelity diagrams belong in the tab (SSO-protected), not the card.

---

### E.5 Card and message size limits; handling a ~60,000-character plan

**Answer:**
- **The "~28 KB" figure is not in any current primary source.**
- The current documented limit is **~100 KB per bot message**. It counts the text, image links, @mentions and
  reactions **encoded as UTF-16**, and excludes base64 images.
- Microsoft recommends keeping the message itself **within 80 KB** "to guarantee successful message delivery".
- An oversized message gets **HTTP 413 `RequestEntityTooLarge` / `MessageSizeTooBig`**.
- Channel posts and chat messages share the same ~100 KB limit. The 24 KB figure on the same limits page is for
  **email-to-channel**, not bots.
- **Arithmetic (INFER):** UTF-16 is ≥2 bytes per character.
  - 60,000 chars ≈ **≥120 KB**, over the hard limit before any card JSON overhead.
  - The 80 KB safe budget is ≈ **40,000 characters at most**, and less once Adaptive Card JSON, escaping and
    mentions are added.
  - **A 60k-character plan cannot be sent as one card or one message.**
- **Options:**
  1. **Summary card + link (recommended).** A card with a title, a ≤2–4k-character executive summary, a FactSet of key
     decisions, and `Action.OpenUrl` buttons to the **channel tab deep link** (E.6, `subEntityId` =
     `feature=NNN&view=plan`) and to the GitHub `plan.md`.
  2. **File attachment in a channel: Graph only.**
     - The SDK file-consent API "only support[s] files in personal context", with `supportsFiles: true` in the
       manifest.
     - In channels you must upload to the channel's SharePoint folder through Graph (OAuth to the team's files), then
       post a card that references the file.
     - This copies git content into SharePoint, which conflicts with "git is the source of truth" (decision 5).
  3. **Splitting into N messages** works under the limit but floods the thread and uses the rate budget (J.1). Not
     recommended.

**Evidence:**
- build-conversational-capability, "Message size limits" (updated_at 2026-09-28; ms.date 2026-09-28; DOC): "The agent
  message size limit is 100 KB… encoded as UTF-16… ensure that the size of the message itself is within 80 KB… 413
  status code (RequestEntityTooLarge)… MessageSizeTooBig".
- limits-specifications-teams (updated_at 2026-10-07; ms.date 2026-07-16; DOC). Channel post and chat are both
  "Approximately 100 KB per post"; 80 KB recommended; 24 KB applies only to "Emailing a channel".
- https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/bots-filesv4 (updated_at 2026-08-20; ms.date
  2026-08-19; DOC). Graph works in all scopes; SDK file-consent APIs are personal only; `supportsFiles`.

**Confidence:** high for 100/80 KB and the 413. High that a 60k plan won't fit (arithmetic on a documented encoding).

**Implication for docs/80:**
- §14: **change the 60k comment budget assumption.** The Teams card budget is a summary of a few KB plus a deep link.
- Add a hard serialized-size check (`len(json.dumps(activity).encode('utf-16-le')) < 80_000`) in the notifier, with a
  degrade path to "summary + link".
- §8: the plan's full view lives in the tab.

---

### E.6 Deep link from a card button into a channel tab with a sub-entity

**Answer:**
- **Format for bot/card links:**
  `https://teams.microsoft.com/l/entity/<appId>/<entityId>?tenantId=<tenantId>&webUrl=<entityWebUrl>&label=<entityLabel>&context=<context>&openInMeeting=false`
- **The parts:**
  - `appId` is the Teams app ID, i.e. the manifest `id`, "from Microsoft Teams admin center".
  - `entityId` is the tab's entity ID set when the tab was configured (`page.id` in TeamsJS context).
  - `context` is URI-encoded JSON, for example `{"subEntityId":"feature=008&view=plan","channelId":"19:…@thread.skype"}`.
  - `subEntityId` surfaces in the tab as `page.subPageId`.
  - `channelId` is available "only in configurable tabs with a scope of team".
  - `webUrl` is the fallback URL "if the client doesn't support rendering the tab".
  - All query parameters must be URI-encoded, e.g. `encodeURIComponent(JSON.stringify({...}))`. Encoded deep links
    don't work in Outlook.
- **From inside a tab:** `pages.navigateToApp({appId, pageId, webUrl, subPageId, channelId})` (TeamsJS v2).
  `pages.shareDeepLink` / `shareDeepLink` "doesn't work on Teams mobile platforms".
- **Desktop/web behaviour:**
  - A deep link in an **`Action.OpenUrl`** opens the Teams tab in the current context.
  - The same link in a **TextBlock** opens a new browser tab "in Chrome and in the Teams desktop app when they're
    running on Linux".
  - Use `Action.OpenUrl` buttons, not markdown links.
- **Custom (sideloaded) apps:** deep links work, but if a Store app has the same app ID, the Store app opens.
- **Mobile:**
  - Deep links to an app work on mobile "after your app is approved for the Teams mobile client".
  - Teams iOS needs the Apple App Store Connect Team ID configured.
  - Nothing more specific is documented about channel-tab sub-entity routing on mobile.

**Evidence:**
- https://learn.microsoft.com/en-us/microsoftteams/platform/concepts/build-and-test/deep-link-application (updated_at
  2026-07-29; ms.date 2026-06-23; DOC). Covers:
  - the format and parameter table (`subEntityId` → `page.subPageId`; `channelId` team-scope only);
  - the encoding rule;
  - `Action.OpenUrl` vs TextBlock behaviour;
  - `navigateToApp`;
  - `shareDeepLink` not on mobile;
  - the mobile approval / App Store Connect Team ID note;
  - the custom-app vs Store ID collision.

**Confidence:** high for the format and desktop behaviour. Low for mobile behaviour of channel-tab sub-entity links
(undocumented; needs a device test).

**Implication for docs/80:**
- §14 / §8: **confirm** the deep-link design. The notifier needs the **app id, the tab's `entityId`, and the channel
  id** persisted when the tab is configured.
- Use `Action.OpenUrl`, and give a `webUrl` fallback to the tab's own web route, so mobile and unsupported clients
  still land on the artifact.
- **Spike:** test on iOS/Android with a custom (org-catalog) app.
- Cross-ref F.7 for reading `page.subPageId` in the tab.

---

### J.1 Rate limits (per bot, per conversation, per tenant; proactive sends and card updates; 429 guidance)

**Answer:**
- **Policy:** "All requests are subject to the same rate limiting policy, including sending messages, channel
  enumerations, and roster fetches". Proactive sends and updates are not treated differently, and updates have no
  separate row (INFER from that sentence). Exact values "are subject to change"; the tables are "for estimation only".
- **Per bot per thread** (a thread is a 1:1, group chat, or **channel**):

  | Operation | Limit |
  |---|---|
  | Send to conversation | 7 per 1 s / 8 per 2 s / 60 per 30 s / 1,800 per 3,600 s |
  | Create conversation | same as Send |
  | Get conversation members | 14 per 1 s / 16 per 2 s / 120 per 30 s / 3,600 per 3,600 s |
  | Get conversations | same as Get conversation members |

- **Per thread, all bots combined:**

  | Operation | Limit |
  |---|---|
  | Send / Create conversation | 14 per 1 s / 16 per 2 s |
  | Get members / Get conversations | 28 per 1 s / 32 per 2 s |

- **Per app per tenant (global):** **50 RPS**.
- The page's note says "the thread limit of 3600 seconds and 1800 operations applies only if multiple agent messages
  are sent to a single user". The wording is ambiguous; treat 1,800/h per channel as a ceiling anyway.
- Service-side message splitting can raise effective RPS.
- **429 guidance:**
  - Expect HTTP 429 when over a limit.
  - Use **exponential backoff with random jitter**. The sample uses 3 retries, 2 s min, 20 s max, 1 s delta, ±20%
    randomization.
  - Also retry **412, 502 and 504**.
  - Batch requests rather than issuing many to one conversation.
- **Legacy member APIs:** the deprecated `TeamsInfo.getMembers` is throttled to 5 req/min (not relevant if you use
  paginated members).
- **Retry-After:** no mention of honouring a `Retry-After` header was found.

**Evidence:**
- https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/rate-limit (updated_at 2026-07-27; ms.date
  2025-02-06 → PRE-GA. It is the current canonical page and was re-published after GA with "agent" terminology, so it
  **still applies**. Its C# samples are Bot Framework-era (`HttpOperationException`, transient fault block), and the
  SDK-specific retry hooks are not documented there; DOC). All tables and quotes above come from this page.

**Confidence:** high that these are the published numbers. Medium on how they apply in practice (Microsoft says they
are estimates and may change).

**Gap:** I didn't verify whether `microsoft-teams-apps` 2.1.0 retries 429 automatically. The HTTP client wasn't
inspected for retry policy. Assume no, and wrap calls.

**Implication for docs/80:**
- §15 / §14: **new design constraint.** Put a per-conversation token bucket in the outbound notifier, sized to the
  **shared** all-bots budget (see K.4). Coalesce board updates, retry 429/412/502/504 with jittered exponential
  backoff as a Temporal activity retry policy, and make sends idempotent (J.3).

---

### J.2 Message size limits and attachment options

**Answer:**
- **Text or card message:** ~100 KB (UTF-16; includes mentions and reactions; excludes base64 images); 80 KB
  recommended; 413 `MessageSizeTooBig` beyond it (see E.5).
- **Images:** ≤1024×1024; picture attachments ≤1 MB; PNG/JPEG/GIF; no SVG or animated GIF.
- **Files from the bot:**
  - **Channels and group chats:** only via **Graph**. Upload to the team's channel files (SharePoint) or OneDrive,
    then post a card that references the file.
  - **Personal chat only:** the SDK **file-consent** flow (`FileConsentCard`, `file.consent.accept` / `decline`,
    manifest `bots[].supportsFiles: true`).
  - Bots can't send or receive files in GCC High, DoD or 21Vianet.
- **Adaptive Cards** cannot upload files or images.
- **Human file limits (for comparison):** chat allows 10 file attachments and 100 MB per file.

**Evidence:**
- build-conversational-capability (2026-09-28; DOC).
- limits-specifications-teams (updated_at 2026-10-07; DOC).
- bots-filesv4 (updated_at 2026-08-20; ms.date 2026-08-19; DOC): "Teams SDK file consent APIs work only in the personal
  context. They don't work in the channel or groupchat context."
- cards-reference (PRE-GA, legacy, still applies; DOC): "Adaptive Cards within Teams don't provide support for file or
  image uploads".

**Confidence:** high.

**Implication for docs/80:**
- §8 / §14: **confirm** "artifacts live in git and render in the tab". Don't plan on bot-attached files in channels;
  it would need Graph `Files.ReadWrite`-class permissions and a SharePoint copy of git content.

---

### J.3 Retries and idempotency of inbound activities

**Answer:**
- **Stable id:**
  - Every inbound activity has an `id`. For channel messages it is the Teams message id.
  - The activity samples show `messageUpdate` and `messageDelete` notifications carry the **same `id`** as the
    original message, so `activity.id` is the message's stable identity (DOC, sample payloads).
  - For card invokes, `activity.reply_to_id` is the id of the message holding the card (the docs use it to update the
    card).
  - A dedup key such as `(conversation.id, activity.id)` is therefore usable, but that is INFER: no doc calls it a
    dedup key.
- **Are retries at-least-once?** **Not documented** in any primary source I could find.
  - DOC: the Bot Service expects the bot to finish within **10–15 seconds** depending on the channel. If it doesn't,
    the service times out and returns **504 GatewayTimeout** to the client. That guidance page is ms.date 2024-10-09
    (PRE-GA, Bot Framework-era), but the timeout is a service property, so it **likely still applies**.
  - CODE: the Teams SDK itself dedups `signin/tokenExchange` invokes. Its comments say "duplicates arrive from several
    of the user's clients but always on the same conversation" and "a late duplicate from a second Teams endpoint can
    arrive after the original settles". So **Teams does deliver duplicate invokes in at least that case.**
  - INFER: the SDK has **no general inbound dedup**; the only dedup logic found in `apps/src` is for token exchange.
  - Search results claiming the connector resends up to 2 times came from non-primary sources and are **not** cited
    as evidence.
- **Conclusion:** treat inbound delivery as **possibly duplicated** (at-least-once-like) and make handlers idempotent
  on `activity.id`. Delivery guarantees are unconfirmed.

**Evidence:**
- build-conversational-capability (2026-09-28; DOC). Sample `messageUpdate` / `messageDelete` payloads with
  `"id":"1666977568748"`; the "Update cards" section uses `ReplyToId`.
- https://learn.microsoft.com/en-us/azure/bot-service/bot-builder-howto-long-operations-guidance (updated_at
  2025-12-16; PRE-GA; DOC): "If the bot doesn't complete the operation within 10 to 15 seconds, depending on the
  channel, the Azure AI Bot Service will time out and report back to the client a 504:GatewayTimeout".
- teams.py `packages/apps/src/microsoft_teams/apps/oauth_state.py` lines ~35–56 and ~312–322 (last changed
  2026-08-28; present in v2.1.0; CODE).

**Confidence:**
- Medium that `activity.id` is a usable dedup key.
- Low on the retry semantics (undocumented).
- High on the 10–15 s timeout.

**Implication for docs/80:**
- §12 / §15: **confirm** the existing webhook_bridge pattern (dedup by delivery id) and port it. Dedup Teams inbound
  on `(conversation.id, activity.id)` for messages and on `(reply_to_id, from.aadObjectId, data.attempt)` for card
  decisions.
- Handlers must **ack fast**: signal Temporal and return within a few seconds; never run agent work inline.
- Temporal's own "first valid decision wins per decision window" remains the real idempotency guarantee.
- **New risk (detail):** delivery semantics need an empirical spike.

---

### K.4 Rate limits when N bots post into the same channel or thread

**Answer:**
- Each bot has its own **per bot per thread** budget: Send 7/s, 8/2 s, 60/30 s, 1,800/h.
- **All bots together** share a **per thread** budget: Send 14/s, 16/2 s.
- A "thread" here means the conversation (the channel), not a reply chain. Whether a reply chain (`;messageid=`)
  counts as its own thread for limiting is not stated.
- **With six role bots:** 6 × 7/s = 42/s of individual headroom, but the channel caps all of them at **14/s and
  16 per 2 s**.
  - So the effective per-bot share under contention is ~2–3 msgs/s.
  - Only the per-bot table has a 30 s / 1 h row, so long-run budgets are per bot (60/30 s, 1,800/h each).
- **Per app per tenant:** 50 RPS. Six bots are six apps (see K.1), so each gets its own 50 RPS (INFER).
- Card updates and sends draw from the same budgets (J.1).

**Evidence:** https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/rate-limit (updated_at
2026-07-27; ms.date 2025-02-06 → PRE-GA, still applies; DOC). Sections "Per agent per thread limit" and "Per thread
limit for all agents".

**Confidence:** high for the published numbers. Medium on whether "thread" means the channel or a reply chain.

**Implication for docs/80:**
- §2 roster and §7: **confirm one-bot-per-role is feasible**, but add a **single shared outbound rate limiter per
  channel** across all role bots (≤~10 sends per 2 s with margin), owned by the notifier, not by each bot.
- This strengthens decision 4: agents emit workflow events, and one serialized notifier projects them into Teams.

---

### Snippet for §4.2 item 3: post a card, update it in place, handle `Action.Execute`

Pinned to `microsoft-teams-apps==2.1.0` (and the `microsoft-teams-api` / `microsoft-teams-cards` packages it depends
on). Every API used is present in tag `v2.1.0` and unchanged on `main` (2026-10-07). Runnable in principle; not
executed against a tenant.

```python
# Sources (CODE, teams.py v2.1.0):
#   App.send / App.reply                        packages/apps/src/microsoft_teams/apps/app.py
#   app.initialize() w/o HTTP server             examples/proactive-messaging/src/main.py
#   conversations.update_activity(...)           packages/api/src/microsoft_teams/api/clients/conversation/client.py:299
#     (conversations.activities(id).update(...) is @deprecated in 2.1.0; Learn's sample still shows it)
#   on_card_action_execute / AdaptiveCardInvokeActivity   packages/apps/src/microsoft_teams/apps/routing/activity_handlers.py
#   AdaptiveCardAction*Response                  packages/api/src/microsoft_teams/api/models/adaptive_card/adaptive_card_action_response.py
#   AdaptiveCard, TextBlock, ActionSet, ExecuteAction, OpenUrlAction   packages/cards/src/microsoft_teams/cards/core.py
from microsoft_teams.api import (
    AdaptiveCardInvokeActivity,
    AdaptiveCardActionCardResponse,
    AdaptiveCardInvokeResponse,
    MessageActivityInput,
)
from microsoft_teams.apps import ActivityContext, App
from microsoft_teams.cards import ActionSet, AdaptiveCard, ExecuteAction, OpenUrlAction, TextBlock

app = App()  # CLIENT_ID / CLIENT_SECRET / TENANT_ID from env


def gate_card(feature: str, attempt: int, status: str, deep_link: str) -> AdaptiveCard:
    # version defaults to "1.5" (Universal Actions minimum, <= Teams' 1.6 ceiling)
    return AdaptiveCard(
        body=[
            TextBlock(text=f"Plan gate · {feature} · attempt {attempt}", weight="Bolder", wrap=True),
            TextBlock(text=status, wrap=True),
            ActionSet(actions=[
                # Routed handlers match data["action"], NOT the Universal Actions `verb`.
                ExecuteAction(title="Approve").with_verb("plan_approved")
                    .with_data({"action": "plan_gate", "decision": "approve",
                                "feature": feature, "attempt": attempt}),
                ExecuteAction(title="Reject").with_verb("plan_rejected")
                    .with_data({"action": "plan_gate", "decision": "reject",
                                "feature": feature, "attempt": attempt}),
                OpenUrlAction(title="Open plan", url=deep_link),  # E.6 deep link, Action.OpenUrl not markdown
            ]),
        ],
    )


# --- 1) Post (proactive, e.g. from a Temporal activity; no HTTP server needed) -----------
async def post_card(service_url: str, conversation_id: str, card: AdaptiveCard) -> str:
    await app.initialize()  # credentials + token manager, no server
    # Card-only activity: never mix text + attachment (Teams splits it and returns no id).
    sent = await app.send(conversation_id, card, service_url=service_url)  # pass the STORED serviceUrl;
    return sent.id  # persist (service_url, conversation_id, activity_id)   # default is smba.trafficmanager.net/teams


# --- 2) Update in place (same process or a different one) --------------------------------
async def update_card(service_url: str, conversation_id: str, activity_id: str, card: AdaptiveCard) -> None:
    await app.initialize()
    await app.api.conversations.update_activity(
        conversation_id, activity_id, MessageActivityInput().add_card(card), service_url=service_url
    )  # HTTP PUT /v3/conversations/{id}/activities/{activityId}; subject to J.1 rate limits -> retry 429/412/502/504


# --- 3) Handle Action.Execute (inside the bot's HTTP handler) ----------------------------
@app.on_card_action_execute("plan_gate")
async def on_plan_gate(ctx: ActivityContext[AdaptiveCardInvokeActivity]) -> AdaptiveCardInvokeResponse:
    data = ctx.activity.value.action.data              # {"action","decision","feature","attempt"}
    who = ctx.activity.from_.aad_object_id             # authorize per H.*, then signal Temporal (fast; <10-15 s)
    # await temporal_client.get_workflow_handle(...).signal("plan_approved" | "plan_rejected", ...)  # dedup on attempt
    resolved = gate_card(data["feature"], data["attempt"], f"Resolved: {data['decision']} by {ctx.activity.from_.name}",
                         deep_link="https://teams.microsoft.com/l/entity/...")
    # Make the outcome visible to everyone: edit the shared message (reply_to_id = id of the card's message)...
    await ctx.api.conversations.update_activity(
        ctx.activity.conversation.id, ctx.activity.reply_to_id, MessageActivityInput().add_card(resolved)
    )
    # ...and replace the actor's view immediately via the invoke response.
    return AdaptiveCardActionCardResponse(value=resolved)
    # (alternative: AdaptiveCardActionMessageResponse(value="Recorded") for a toast)
```

Notes on the snippet:
- **Attribute names checked.** `ctx.activity.from_` and `Account.aad_object_id` are confirmed in
  `api/models/activity.py:49` and `api/models/account.py:27`. `MessageActivityInput.add_card` is confirmed at
  `activities/message/message.py:248` (CODE).
- **Real gate cards** should drop the Approve/Reject buttons in the resolved card and, for a stale `attempt`, return
  an error or "superseded" card.
- **Builder helpers.** `with_verb` and `with_data` exist on `ExecuteAction` (`cards/core.py:468`, `:480`).
  `MessageActivityInput().add_card(card)` is the pattern used by `App.send` itself.

---

### Side finding outside the assigned letters (flag for C/K/§2)

- **Shared channels do not support bots.**
  - DOC: the "Limits for shared channels" section says: "Bots, connectors, and message extensions aren't supported."
  - Source: https://learn.microsoft.com/en-us/microsoftteams/limits-specifications-teams (updated_at 2026-10-07;
    ms.date 2026-07-16).
  - Confidence: high. This is admin-facing doc; the developer docs elsewhere mention Workflows posting in shared
    channels as a flow bot.
- **Implication:** the team workspace must be a **standard channel** (or a private channel, which needs its own
  verification). That's a **changes-design** risk if anyone planned a shared channel with an external architect.
