# F / G / I.3 — Teams tabs (TeamsJS), artifact-viewing alternatives, safe rendering

Research notes for `docs/research/teams-workspace-research-prompt.md` questions F.1–F.7, G, I.3, plus the
TeamsJS tab snippet for end-to-end sketch §4.2 item 5. Accessed 2026-10-09.

**Conventions used throughout.**

- Format: the prompt's §4.1 block per sub-question (Answer / Evidence / Confidence / Implication), plus a
  `Gaps:` line where something could not be confirmed.
- Dates: learn.microsoft.com pages carry two dates — `ms.date` (when content was authored/reviewed) and
  `updated_at` (last publish). "last updated" below = `updated_at`. A source is marked **PRE-GA** when its
  `ms.date` (content date) is before 2026-05. For every PRE-GA tab/TeamsJS/Entra source below, the
  staleness concern does not really apply: tabs, TeamsJS and Entra SSO are independent of the Teams SDK for
  Python GA, and each such page was republished after 2026-03 without contradicting newer pages — so
  "PRE-GA, still applies" unless stated otherwise.
- Labels: `DOC` = a primary source states it; `CODE` = read in source code/releases; `INFER` = my reasoning.
- Pinned versions seen: `@microsoft/teams-js` **v2.58.0** (released 2026-10-07); manifest `staticTabs` in
  channels needs manifest **v1.16+**; `webApplicationInfo` needs manifest **v1.5+**; Teams Adaptive Cards
  **≤ v1.6** (link unfurling **≤ v1.3**); mermaid **≥ 11.16.1 / 10.9.8** (security floor, see F.4).

---

### F.1 Configurable vs static channel tabs

**Answer:** Static tabs in channels are now the platform default, and in effect the only option for new
pins. Since manifest v1.16, `staticTabs` accepts `scopes: ["team","groupChat",...]` and
`context: ["channelTab",...]`. There is no config dialog: the user pins the tab straight away, and the app
can still change `contentUrl` after pinning through the `setConfig` APIs. The migration guide says
"As you can only pin static tabs from now". `configurableTabs` (`configurationUrl` → config page calls
`pages.config.setConfig({entityId, contentUrl, websiteUrl, suggestedDisplayName})` +
`saveEvent.notifySuccess()`) stays in the manifest **only for backward compatibility** of tabs that are
already pinned. If both are declared for a scope, "Teams pins the static tab by default". Two constraints
shape our design:

- "When you declare multiple static tabs in the manifest and add the app in the channel scope, **only the
  first tab listed in the manifest appears**".
- "Tabs in chats, channels, or meetings behave more like apps, as you can **pin only one tab per app**".

`websiteUrl` is the browser fallback, and it is required for mobile fallback on non-mobile-approved Store
apps (F.6). Up to 16 static tabs per app (personal scope).

**Evidence:**
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/how-to/create-channel-group-tab (last updated
  2026-04-01; ms.date 2025-02-06 → PRE-GA, still applies; DOC). This is the "Migrate your configurable tab to
  static tab" section, with the quotes on v1.16+, "only the first tab listed … appears" and "you can only pin
  static tabs from now".
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/what-are-tabs (last updated 2026-09-08;
  ms.date 2026-08-27; DOC). It has the static-vs-configurable scope table (static: personal/channel/group
  chat/meetings/calling; configurable: channel/group chat/meetings), "Teams pins the static tab by
  default", "pin only one tab per app", "up to 16 static tabs per app", and "Teams apps can't use native
  plugins because they run inside sandboxed iframes".

**Confidence:** high. Two current Microsoft pages agree.

**Implication for docs/80:**
- §8.2 is **confirmed**: the views Spec / Architecture / Mock / Plan / Board / Review must be in-app views
  (router) inside **one** static tab (`scopes:["team"]`, `context:["channelTab"]`), not separate manifest
  tabs.
- §7.4 / §15 **change**: use `staticTabs` (manifest ≥1.16), not `configurableTabs`. The repo↔channel link
  can't come from a config page. Derive it server-side from `channel.id` / `team.groupId` (validated
  against the SSO token's tenant), or let the tab set it on first open via `setConfig`.

---

### F.2 Tab SSO end to end (getAuthToken → [OBO] → our API)

**Answer:** The flow, end to end:

1. The tab calls `microsoftTeams.authentication.getAuthToken()` after `app.initialize()`.
2. The Teams client gets an Entra access token for **our app's own exposed API** and caches it (consent
   happens only cross-tenant or when an admin hasn't consented).
3. The tab sends the token as `Authorization: Bearer` to our API.

**No OBO exchange is needed to call our own API.** The `getAuthToken()` token is already an access token
whose audience is our app. OBO is only needed when our server wants to call **Graph or another downstream
API** as the user. The docs say `getAuthToken()` only covers `email`, `profile`, `offline_access`,
`openid`, and Graph scopes like `User.Read` need OBO.

**Entra setup** (docs):

- Register the app as single-tenant for our LOB case. No redirect URI is needed for tab SSO.
- Set `requestedAccessTokenVersion: 2` in the Entra app manifest.
- Expose an API with Application ID URI **`api://<fqdn>/<clientId>`**, lowercase fqdn (uppercase breaks
  Android). If the same app also has a bot, the format is **`api://<fqdn>/botid-<clientId>`**.
- Add a scope (conventionally `access_as_user`).
- Pre-authorize these client IDs:

  | Client | Client ID |
  |---|---|
  | Teams desktop/mobile | `1fec8e78-bce4-4aaf-ab1b-5451cc387264` |
  | Teams web | `5e3ce6c0-2b1f-4285-8d4b-75ee78787346` |
  | Microsoft 365 web (only if the tab runs in M365/Outlook hosts) | `4765445b-32c6-49b0-83e6-1d93765276ca` |
  | Microsoft 365 desktop | `0ec893e0-5785-4de6-99da-4ed124e5296c` |
  | Microsoft 365 mobile / Outlook desktop | `d3590ed6-52b3-4102-aeff-aad2292ab01c` |
  | Outlook web | `bc59ab01-8403-45c6-8796-ac3ef710b3e3` |
  | Outlook mobile | `27922004-5251-4030-b22d-91ecd9a37ea4` |

**Teams app manifest (v1.5+):**

```json
"webApplicationInfo": {
  "id": "<clientId>",
  "resource": "api://<fqdn>/<clientId>"
}
```

The same fqdn must appear in `contentUrl` and `validDomains`. The current schema also has optional
`nestedAppAuthInfo` (max 5) for prefetching NAA tokens.

**What our API validates:**

- Signature via Entra JWKS.
- `aud` = **our client ID GUID**. The doc's sample v2 token shows `aud: "2c3caa80-…"`, a bare GUID, not the
  `api://` URI.
- `iss` = `https://login.microsoftonline.com/<our-tenant-id>/v2.0`, and `tid` = our tenant
  (single-tenant).
- `scp` contains `access_as_user`.
- `exp` / `nbf`.
- Identity comes from `oid` (+ `tid`), never from `preferred_username`. The docs point to "Using claims to
  reliably identify a user".
- Do **not** trust the `tid` that the doc sample POSTs in the request body from `getContext()`. Context
  data "must not [be used] as proof of identity" (access-teams-context page).
- Don't cache the token client-side; Teams does.

**Known limits:**

- OAuth only, no SAML.
- **"Multiple domains per app aren't supported"**: the domain registered in Entra must equal the domain the
  tab is served from.
- Redirect-based login doesn't work in iframes.
- `getAuthToken` fails for anonymous users.
- Mobile SSO needs Android 1416/1.0.0.2020073101+ and iOS 2.0.18+.

**Evidence:**
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/how-to/authentication/tab-sso-overview
  (last updated 2026-07-22; ms.date 2023-01-17 → PRE-GA, still applies; DOC). Runtime flow table, the
  getAuthToken scope limit, "Multiple domains per app aren't supported", mobile versions, iOS
  third-party cookie note.
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/how-to/authentication/tab-sso-register-aad
  (last updated 2026-04-01; ms.date 2023-02-01 → PRE-GA, still applies; DOC). `api://fqdn/{AppID}` format,
  `botid-` variant, lowercase rule, `requestedAccessTokenVersion` = 2, pre-authorized client ID table.
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/how-to/authentication/tab-sso-code (last
  updated 2026-07-13; ms.date 2026-03-16 → PRE-GA, still applies; DOC). Client code, the "access token and
  an ID token" statement, sample decoded payload (`aud` GUID, `iss …/v2.0`, `scp: access_as_user`, `ver:
  2.0`), and the statement that OBO is needed only for Graph.
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/how-to/authentication/tab-sso-manifest
  (last updated 2026-04-01; ms.date 2022-11-21 → PRE-GA, still applies; DOC). `webApplicationInfo` shape,
  manifest ≥1.5.
- https://learn.microsoft.com/en-us/microsoft-365/extensibility/schema/root (last updated 2026-10-01; DOC).
  `webApplicationInfo.id` / `resource` / `nestedAppAuthInfo`.
- Audience = client-ID GUID is shown in the sample token (DOC). That it holds for every v2 token issued for
  an `api://` URI is general Entra behaviour I did not re-fetch → INFER, high.

**Confidence:** high for the flow and setup. Medium-high for "aud = GUID": the sample shows it, and the API
should also accept the `api://…` form defensively.

**Implication for docs/80:**
- §7.4 **change**: the text says "calls it with the SSO-exchanged token". It should say "calls it with the
  `getAuthToken()` access token, validated as above". OBO only enters if the artifact service later needs
  Graph (e.g. channel-membership checks under §13 → research H.3).
- §15 **new constraints**: (a) one Entra app ↔ one fqdn for the tab, so the tab/artifact API host is fixed
  and the isolated mock origin **cannot** take part in SSO (see F.5); (b) if the tab ships in the same app
  package as a bot (e.g. "Factory"), the Application ID URI uses `botid-<botClientId>`, so deciding which
  package owns the tab feeds research K.1.

---

### F.3 validDomains, CSP and frame-ancestors

**Answer:** The tab host must do all of the following:

- Serve over **HTTPS** with a publicly trusted certificate: "Microsoft Teams tab doesn't support the ability
  to load intranet websites that use self-signed certificates".
- Send `Content-Security-Policy: frame-ancestors` covering every host. Docs table:

  | Host | frame-ancestors |
  |---|---|
  | All hosts (new) | `https://*.cloud.microsoft` |
  | Teams | `teams.microsoft.com`, `*.teams.microsoft.com` |
  | Microsoft 365 app | `*.microsoft365.com`, `*.office.com` |
  | Outlook | `outlook.office.com`, `outlook.office365.com`, `outlook-sdf.office.com`, `outlook-sdf.office365.com` |

  The docs warn that web Teams/Outlook/M365 are migrating to `*.cloud.microsoft`, so keep the old values
  too. Not sending `X-Frame-Options: DENY/SAMEORIGIN` is implied. `X-Frame-Options: ALLOW-FROM
  https://teams.microsoft.com/` is only the deprecated IE11 fallback.
- Use **TeamsJS ≥ 2.19.0** and call `app.initialize()`, otherwise there's a warning on `*.cloud.microsoft`
  and "your page isn't displayed".
- List every domain the tab loads or navigates to in `validDomains`. Rules: wildcards allowed (`*.x.com`),
  max 100 entries, each ≤ 2048 chars. Schema text: "A list of valid domains from which the tabs expect to
  load any content… If your tab configuration or content UI needs to navigate to any other domain besides
  the one use for tab configuration, that domain must be specified here". `setConfig` URLs must be HTTPS and
  same-domain or in `validDomains`. Authentication flows must "start and end on your domain, which must be
  listed in the validDomains".
- Never redirect to a login page inside the frame. That gives a blank tab, because login pages refuse
  framing.
- Use token auth, not third-party cookies. iOS blocks them.

Minimal header for our tab host:

```http
Content-Security-Policy: frame-ancestors https://teams.microsoft.com https://*.teams.microsoft.com https://*.cloud.microsoft https://*.microsoft365.com https://*.office.com https://outlook.office.com https://outlook.office365.com
```

Add `https://outlook-sdf.office.com https://outlook-sdf.office365.com` only if Outlook-SDF hosting matters;
it doesn't for us.

**Evidence:**
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/how-to/tab-requirements (last updated
  2026-05-29; ms.date 2025-02-06 → PRE-GA content, republished post-GA; DOC). Host table, `*.cloud.microsoft`
  warning, TeamsJS ≥2.19.0, self-signed-cert rule, sign-in pages not rendering in iframes.
- https://learn.microsoft.com/en-us/microsoft-365/extensibility/schema/root (last updated 2026-10-01; DOC).
  `validDomains` text, maxItems 100.
- https://learn.microsoft.com/en-us/microsoftteams/platform/resources/troubleshoot (last updated
  2026-09-28; ms.date 2026-07-10; DOC). Blank tab is caused by a non-frameable page or a domain missing from
  validDomains; the auth-flow validDomains rule; `setSettings` URL rules.
- https://github.com/OfficeDev/microsoft-teams-library-js/releases (accessed 2026-10-09; CODE). v2.56.0
  (2026-09-02) "fixed origin validation to handle malformed valid-origins payload from the CDN"; v2.57.0 and
  v2.58.0 add origins to the "valid-origins artifact".

**Confidence:** high for frame-ancestors, HTTPS and validDomains. Medium on the `connect-src` question below.

**Gaps:** TeamsJS v2.56+ appears to **fetch its valid-origins list from a CDN at runtime** (INFER from the
release notes). If our tab sets a strict `connect-src`, it may need to allow that CDN host (likely
`res.cdn.office.net`). Unverified → spike: load the tab with `connect-src 'self'` and watch the console.

**Implication for docs/80:**
- §15 **confirm + detail**: the tab host behind our reverse proxy needs a public CA certificate (no
  self-signed, so Caddy/Let's Encrypt is fine) and the frame-ancestors header above. Put the tab/API host in
  `validDomains`.
- New **detail** risk: the tab's own CSP must allow the TeamsJS CDN script and possibly its origins fetch.

---

### F.4 Client-side mermaid in a tab: CSP / eval

**Answer:** Yes. Mermaid is ordinary client-side JS and nothing in the Teams tab docs restricts which JS
libraries a tab runs (Teams only frames the page). The CSP constraints come from **our own** CSP and from
mermaid itself:

- **No `eval` needed.** The mermaid API source contains no `eval` / `new Function`, so `'unsafe-eval'` is
  not required. Bundled dependencies weren't audited (INFER: low risk, verify with a strict-CSP smoke test).
- **`style-src 'unsafe-inline'` is required.** Mermaid writes each diagram's CSS into a `<style>` element
  inside the SVG via `document.createElement('style'); style1.innerHTML = rules;
  svg.insertBefore(style1, …)` and **sets no nonce**. With a nonce- or hash-only `style-src`, diagrams render
  unstyled. Keep `script-src` strict, without `'unsafe-inline'` or `'unsafe-eval'`.
- **Security level.** The default `securityLevel: 'strict'` encodes HTML tags in labels and disables
  `click` callbacks. Non-`loose`, non-sandbox modes run the diagram code through **DOMPurify**.
- **`sandbox` mode** renders into an `<iframe sandbox="">`, i.e. no scripts at all. I did not see how the
  frame content is loaded (srcdoc vs `data:`), so if we use it our `frame-src` must be checked → spike.
- **Validate before render.** `mermaid.parse(text)` "validates graph definitions without rendering".
- **API.** `mermaid.initialize({startOnLoad:false, securityLevel:'strict'})` then
  `await mermaid.render(id, text)` → `{svg}`.
- **Version pin (security).** Mermaid has had a run of 2026 sanitization advisories:
  - 2026-05-11: GHSA-87f9-hvmw-gh4p (CSS injection via config), GHSA-ghcm-xqfw-q4vr (HTML injection via
    state-diagram `classDef`), GHSA-xcj9-5m2h-648r (CSS injection via `classDefs`).
  - 2026-08-04: **GHSA-6x64-9x62-f2gx / CVE-2026-50159**, CSS injection into sibling DOM elements through
    the `~` / `+` combinators. Affects 11.0.0-alpha.1 through 11.16.0 and ≤10.9.7; **patched 11.16.1 /
    10.9.8**. Workarounds: wrap the SVG in a container with no siblings, `securityLevel: "sandbox"`, or the
    `secure` config option.
  - 2025-08-19: an earlier critical one, GHSA-8gwm-58g9-j8pw (architecture-diagram `iconText` XSS).

  Pin **≥ 11.16.1** (or a 12.x that includes the fix) and render each diagram into its own sibling-free
  container. Load mermaid **self-hosted** from our tab origin, not a CDN, so `script-src 'self'` holds.

**Evidence:**
- https://raw.githubusercontent.com/mermaid-js/mermaid/develop/packages/mermaid/src/mermaidAPI.ts
  (develop branch, accessed 2026-10-09; CODE). `<style>` creation via innerHTML with no nonce; `sandbox`
  iframe `.attr('sandbox','')`; DOMPurify call; no eval/new Function in this file.
- https://mermaid.js.org/config/usage.html (no date on page, accessed 2026-10-09; DOC). The four
  securityLevel values and their definitions, strict is the default, `run` / `render` / `parse` APIs.
- https://github.com/mermaid-js/mermaid/security/advisories (accessed 2026-10-09; DOC) and
  https://github.com/mermaid-js/mermaid/security/advisories/GHSA-6x64-9x62-f2gx (published 2026-08-04; DOC).
- https://github.com/mermaid-js/mermaid/releases (accessed 2026-10-09; CODE). Shows `mermaid@12.1.0` /
  `12.0.0` as the newest tags, but the dates reported to me (2024-10-02 / 2024-09-10) contradict the 2026
  advisories that still patch the 11.x line. **Treat "current latest" as unverified.** Whether 12.x carries
  the CVE-2026-50159 fix is unconfirmed, so pin by advisory.

**Confidence:** high on the `style-src 'unsafe-inline'` need and the no-eval finding in the API module
(CODE). Medium on the transitive dependencies. High on the advisories.

**Implication for docs/80:**
- §8.1 / §9.1 **confirm**: "tab: Architecture (client-side mermaid)" works.
- **Add detail**: the tab's CSP is `script-src 'self' <teamsjs-cdn>; style-src 'self' 'unsafe-inline'`.
  Mermaid stays on `securityLevel:'strict'`, is pinned ≥11.16.1, and gets one container per diagram. The
  Python-side "parse-validated" step (§9.1) and the tab should run the **same** mermaid version. A
  parse-valid diagram can still carry `classDef` / `style` CSS payloads, so the version pin matters even with
  validation.

---

### F.5 Nested `<iframe sandbox="allow-scripts">` from a separate origin

**Answer:** **Undocumented.** No Teams platform page I found addresses a tab that embeds a third-party or
different-origin child iframe. What can be said:

- **DOC:** `validDomains` is worded around domains the tab "expect[s] to load any content" from and
  "navigate[s] to". The content-page doc says "Ensure that all URL domains used in your tabs are included
  in the validDomains array". So the conservative move is to **list the mock origin in validDomains anyway**
  (cheap; wildcards allowed).
- **INFER:** In browsers, the Teams host's own CSP `frame-src` applies only to frames the Teams page embeds
  directly (our tab), not to grandchildren that our tab embeds. On web, a nested frame is governed by **our
  tab's** CSP (`frame-src <mock-origin>`) and **the mock origin's** `frame-ancestors` (which must allow
  **our tab origin**, not Teams'). Teams desktop (WebView2) and mobile webviews may intercept navigations to
  non-validDomains hosts. That is not documented for subframes; it is the main unknown.
- **DOC:** Teams itself loads tabs in sandboxed iframes ("Teams apps … run inside sandboxed iframes"). The
  exact sandbox flags Teams applies are not documented, and a nested frame cannot get more privileges than
  its parent has. `allow-scripts` without `allow-same-origin` is a restriction, so it should be compatible
  with any parent flags (INFER).
- **DOC (related):** for a nested frame that *we* control and that needs TeamsJS, "you can update its code
  to initialize the SDK by specifying your domain. This allows your nested frame to act as a proxy to
  Teams". That confirms nested frames are anticipated, but the mock must **not** run TeamsJS.
- **SSO consequence (from F.2, DOC + INFER):** an `allow-scripts`-only frame has an **opaque origin**.
  Separately, "multiple domains per app aren't supported" for SSO. So the mock origin can never get a
  user token. Mocks must be served via **short-lived signed URLs** minted by the artifact API, which
  authorizes the caller with the SSO token. Otherwise the mocks are world-readable.
- **Documented alternative (DOC):** an Adaptive Card button with `Action.Submit` +
  `msteams.type: "invoke"`, `value.type: "tab/tabInfoAction"`, `tabInfo: {contentUrl, websiteUrl, name,
  entityId}` opens `contentUrl` in **Collaborative Stageview** ("The content URL must be within the list of
  validDomains"). Stageview Modal is the only mode on Teams web. `stageView` / deep-link `openMode` can be
  `popoutWithChat` | `popout` | `modal`. This could open a mock view (our tab page, which then frames the
  sandboxed mock) straight from the mock-review card in §14.4. It doesn't remove the nested-frame question,
  but if the mock origin is used directly as `contentUrl` it must then itself call `app.initialize()`,
  which defeats isolation.

**Evidence:**
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/how-to/tab-requirements (last updated
  2026-05-29; PRE-GA content; DOC). Nested-frame proxy note.
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/how-to/create-tab-pages/content-page (last
  updated 2026-07-29; ms.date 2022-11-23 → PRE-GA, still applies; DOC). "all URL domains used in your tabs …
  validDomains".
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/what-are-tabs (last updated 2026-09-08;
  DOC). Tabs run in sandboxed iframes.
- https://learn.microsoft.com/en-us/microsoft-365/extensibility/schema/root (last updated 2026-10-01; DOC).
  validDomains wording.
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/open-content-in-stageview (last updated
  2026-09-21; ms.date 2026-09-16; DOC). `tab/tabInfoAction`, `openMode`, web = Modal only, validDomains
  requirement.

**Confidence:** **low** that it works on all clients. Nothing is documented either way, and desktop/mobile
webview behaviour for subframes is unknown.

**Gaps:** No primary source on (a) the Teams sandbox flags for tab iframes, (b) whether desktop/mobile
webviews block or externalize subframe loads to non-validDomains origins, (c) whether a `sandbox` without
`allow-same-origin` breaks anything in the Teams webviews. → **Spike** on web, new Teams desktop (Win/macOS),
iOS and Android with the mock origin both in and out of validDomains.

**Implication for docs/80:**
- §7.4 / §15: **changes design (pending spike)**. Keep the planned "open mock in browser" fallback as a
  first-class path, not an afterthought.
- Add **signed, expiring mock URLs** (the mock origin can't use SSO).
- Add the mock origin to `validDomains` defensively.
- Mock origin headers: `Content-Security-Policy: default-src 'none'; script-src 'unsafe-inline';
  style-src 'unsafe-inline'; img-src data:; connect-src 'none'; frame-ancestors https://<tab-host>`.
- Consider `tab/tabInfoAction` → Stageview for §14.4.

---

### F.6 Mobile tab behaviour

**Answer:**

**What works (DOC):**
- For **custom-uploaded or org-catalog apps** (our case), "tab behavior is the same as Teams Store apps
  approved by Microsoft for mobile": channel tabs open **in the Teams mobile client using `contentUrl`**,
  in an in-app webview, with no separate mobile approval.
- Mobile shows a native loading indicator by default.
- Tabs aren't reloaded when the user switches between tabs.
- SSO works on Android 1416/1.0.0.2020073101+ and iOS 2.0.18+. Mobile auth needs TeamsJS ≥ 1.4.1.

**What silently doesn't (DOC unless marked):**
- `pages.shareDeepLink()` **"doesn't work on Teams mobile platforms"**.
- Mobile clients "support only TeamsJS **v1.x.x** placeholders" in URLs (e.g. `{subEntityId}`, not
  `{page.subPageId}`). Read context via `app.getContext()` instead.
- iOS blocks third-party cookies, so cookie-based tab auth fails. Use tokens.
- Link unfurling on mobile works "only for links that don't require authentication".
- Adaptive Cards on mobile are reliable only up to v1.6.
- Stageview on mobile for apps "not optimized" opens in the default browser. This is stated for Store apps;
  for custom apps it's unverified.
- Deep links to apps on mobile are documented as needing the app "approved for the Teams mobile client"
  plus an Apple App Store Connect Team ID for iOS. That is Store-oriented, and whether it applies to
  custom/org-catalog apps is **not stated** → gap.
- Store-only fallback, for completeness: an unapproved Store app's channel tab opens `websiteUrl` in the
  external browser, or is unavailable on mobile if there is no `websiteUrl`.
- Nested sandboxed iframes in the mobile webview: unknown (F.5).
- The doc tells you to handle low bandwidth/timeouts with progress indicators. That matters for big plans
  and mermaid.

**Evidence:**
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/design/tabs-mobile (last updated
  2026-05-29; ms.date 2022-11-02 → PRE-GA, still applies; DOC). "Apps not on Teams Store", in-app webview,
  no reload on tab switch.
- https://learn.microsoft.com/en-us/microsoftteams/platform/concepts/build-and-test/deep-link-application
  (last updated 2026-07-29; ms.date 2026-06-23; DOC). shareDeepLink mobile limit, mobile deep-link
  approval and Team ID.
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/how-to/access-teams-context (last updated
  2026-09-17; ms.date 2026-03-02 → PRE-GA, still applies; DOC). v1-only placeholders on mobile.
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/how-to/authentication/tab-sso-overview
  (last updated 2026-07-22; PRE-GA; DOC). SSO mobile versions, iOS cookies.
- https://learn.microsoft.com/en-us/microsoftteams/platform/messaging-extensions/how-to/link-unfurling (last
  updated 2026-10-08; ms.date 2026-09-24; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/cards/cards-reference
  (last updated 2026-08-19; PRE-GA content; DOC). AC ≤1.6 on mobile.

**Confidence:** medium-high for the documented items. Low for deep links and nested frames on mobile for
custom apps.

**Implication for docs/80:**
- §8.2 / §14 **confirm** that the tab works on mobile for an org-catalog app.
- **Detail**: don't build a "copy link" button on `shareDeepLink`. Build the deep link string ourselves
  (F.7) and render it as a normal link.
- **New risk (detail)**: card → tab deep links on mobile for a custom app need a device test.

---

### F.7 subEntityId: reading and creating deep links

**Answer:**

**Read:** call `const ctx = await app.getContext();` and use `ctx.page.subPageId` (v1 name `subEntityId`).
`ctx.page.id` = `entityId`, `ctx.channel.id` = channelId, `ctx.user.tenant.id` = tid. You can also use the
URL placeholder `{page.subPageId}` in `contentUrl`, but mobile only honours v1 placeholders like
`{subEntityId}`, so prefer `getContext()`.

**Create (from a bot/card):**

```
https://teams.microsoft.com/l/entity/<appId>/<entityId>?webUrl=<enc>&label=<enc>&context=<enc JSON>
```

`context` = `{"subEntityId":"014-saved-carts/plan/2","channelId":"19:…@thread.skype"}`. Per the docs,
`context.channelId` is for configurable tabs with team scope (see the gap below).

- Everything must be URI-encoded: `encodeURIComponent(JSON.stringify({...}))`.
- Put the link in `Action.OpenUrl`. Then "the Teams tab opens in the current browser tab". A link inside a
  `TextBlock` opens a new browser tab on Chrome/Linux desktop.
- `appId` = **manifest ID** for a custom-uploaded app, and the **org-catalog ID** once published to the
  catalog. If a Store app shares the ID, the Store app wins.

**Create (from inside the tab):**
- `pages.navigateToApp({appId, pageId, webUrl, subPageId, channelId})`
- `pages.currentApp.navigateTo({pageId, subPageId})` for in-app navigation
- `pages.shareDeepLink({subPageId, subPageLabel, subPageWebUrl})` (not on mobile)

**Limits:**
- Windows desktop can't handle deep links over **2048 chars**. Keep `subEntityId` short and resolve details
  server-side.
- Encoded deep links aren't supported in Outlook.
- "Deep links aren't supported in `contentUrl`".
- A tab without an entityId can't receive the subEntityId.

**Evidence:**
- https://learn.microsoft.com/en-us/microsoftteams/platform/concepts/build-and-test/deep-link-application
  (last updated 2026-07-29; ms.date 2026-06-23; DOC). Format, the parameter table ("the context object
  refers to the subEntityId as page.subPageId"; "context.channelId … available only in configurable tabs
  with a scope of team. It isn't available in static tabs, which has a personal scope"), 2048 limit, app ID
  table, OpenUrl vs TextBlock.
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/how-to/access-teams-context (last updated
  2026-09-17; DOC). v1↔v2 mapping table.
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/open-content-in-stageview (last updated
  2026-09-21; DOC). "deep links aren't supported in contentUrl".

**Confidence:** high for read/create mechanics. **Low** for the static-tab-in-channel deep link (gap below).

**Gaps:** The deep-link page still says `channelId` "isn't available in static tabs, which has a personal
scope". That wording predates static tabs in channels (F.1), so it may be stale. It is **unverified** whether
`…/l/entity/<appId>/<entityId>?context={"subEntityId":…,"channelId":…}` lands on a **static** tab pinned in a
specific channel, and what `entityId` to use (the manifest `staticTabs[0].entityId` is the obvious
candidate). → **Spike**, and it blocks the E.6 card-button design until verified.

**Implication for docs/80:**
- §8.2 **confirm** `subEntityId = "{NNN-slug}/{view}[/{attempt}]"` (short, well under 2048).
- §14 / E.6 **new risk (changes design if it fails)**: the static-tab channel deep link needs a spike.
  Fallback: Stageview via `tab/tabInfoAction` with `contentUrl=https://<tab-host>/?sub=<id>` (F.5), or open
  in browser via `websiteUrl`.

---

### G. Artifact-viewing alternatives (Loop, Files/SharePoint, link unfurling, AC images, custom tab)

**Answer, per option (DOC facts; ranking = INFER):**

- **Loop components (Adaptive Card-based).**
  - DOC: the body is an Adaptive Card ("Contents fully controlled by you" within AC rendering).
  - DOC: Loop components need live and actionable Universal Actions behaviour, and the design guidance says
    an Adaptive Card "with view-only experience doesn't change to a Loop component".
  - DOC: they render in Teams chats/meetings, Outlook, Whiteboard and the Loop app.
  - INFER: no HTML, no client-side JS, no mermaid; markdown only as AC TextBlock subset; images only as
    PNG/JPEG/GIF.

  → Unsuitable for viewing specs, diagrams or mocks. It is a candidate only for an *actionable* gate or
  board card that should travel to Outlook.
- **Channel Files tab (SharePoint).**
  - DOC: Graph `GET /teams/{id}/channels/{id}/filesFolder` returns the channel's driveItem (application
    least-privileged `Files.Read.All`; RSC `File.Read.Group` listed). Graph
    `PUT /drives/{drive-id}/items/{parent-id}:/{filename}:/content` uploads ≤250 MB (application
    `Files.ReadWrite.All`; sensitivity-labelled files can't be replaced app-only).
  - INFER: one-way git→SharePoint mirroring is practical but means a broad tenant-wide application
    permission, a second copy that users will edit (drift), and no per-SHA versioning that maps to git.
  - SECONDARY ONLY (not primary; Message Center MC1261592 via third-party mirrors, e.g.
    https://mc.merill.net/message/MC1261592): OneDrive/SharePoint gained native in-browser `.md`
    view/edit, rolling out mid-April to late May 2026. Whether it renders mermaid fences: no source.
  - HTML files in SharePoint: no primary source on whether they're rendered or forced to download → gap.
- **Link-unfurling message extension.**
  - DOC: register `composeExtensions[].messageHandlers[{type:"link", value:{domains:[…]}}]`, then handle
    `composeExtension/queryLink` and return a card with a `preview`.
  - DOC: AC **≤ v1.3**; results cached 30 min (opt out with `setCachePolicy`).
  - DOC: zero-install unfurl via `supportsAnonymizedPayloads` + `composeExtensions/anonymousQueryLink`,
    which **cannot** return Universal Actions cards.
  - DOC: on mobile, only for unauthenticated links.
  - **DOC: "Ensure that you don't add domains that aren't in your control"**, so unfurling `github.com` URLs
    is out. Only our own tab/artifact-host URLs can be unfurled.
  - DOC: an unfurl card can carry `tab/tabInfoAction` to open the tab content in Collaborative Stageview.
- **Adaptive Card image previews.**
  - DOC: images ≤ **1024×1024**, **PNG/JPEG/GIF only — "Animated GIF and SVG formats aren't supported"**.
  - DOC: "a link to the publicly available image", and image-URL redirects aren't supported.
  - DOC: Teams AC ≤1.6 (mobile ≤1.6).

  → Fine for diagram thumbnails and mock screenshots, but the URL must be fetchable without a token and
  without redirects. INFER: that means public or **unguessable signed** URLs. Image-auth specifics are
  research E.4.
- **Custom channel tab (static, TeamsJS).** F.1–F.7: full HTML/JS, SSO to our API, mermaid client-side,
  renders any path at a SHA straight from git.
  - Costs: one more web app (HTTPS, public certificate, CSP), Entra app plus Teams manifest, and the mock
    nested-frame unknown (F.5).

**Ranking table (all cells INFER, derived from the DOC items above):**

| Artifact | Rank 1 | Rank 2 | Rank 3 | Not suitable |
|---|---|---|---|---|
| **Spec / plan (markdown, up to ~60k chars)** | **Custom tab**. Fidelity: full GFM render (our sanitizer), anchors, per-SHA. Mobile: yes (in-app webview). Auth: SSO token → our API, membership check. Effort: medium (shared with the other views). Git-as-truth cost: none (reads git at a SHA). | **Files tab (.md mirror)**. Fidelity: native .md view (secondary source), no mermaid, no SHA pinning. Mobile: SharePoint viewer. Auth: M365 permissions (team members) for free. Effort: low-medium (Graph upload activity). Git cost: **high**, two copies, drift, users edit the wrong one, `Files.ReadWrite.All`. | **Card excerpt + link** (AC TextBlock, truncated per E.5/§14.7). Fidelity: low. Mobile: yes. Auth: n/a. Effort: low. Git cost: none. | Loop (view-only must not be Loop); link unfurl of github.com (domain not ours) |
| **Architecture diagrams (mermaid .mmd + PNG)** | **Custom tab** (client-side mermaid, strict, pinned ≥11.16.1). Fidelity: vector, zoom, always matches `.mmd` at SHA. Mobile: yes (perf on low-end devices untested). Auth: SSO. Effort: medium. Git cost: none. | **AC image thumbnail (server-rendered PNG)**. Fidelity: ≤1024², raster, no SVG. Mobile: yes. Auth: **public or signed no-redirect URL required**. Effort: low (render step already planned in §8.1). Git cost: low (PNG is a derived artifact at a SHA). | **Unfurl of our own tab/artifact URL** → card with PNG + `tab/tabInfoAction` to Stageview. Fidelity: as card plus a full view on click. Mobile: no-auth links only. Effort: medium (message-extension handler plus manifest). Git cost: none. | Loop; Files tab (no mermaid render, drift) |
| **Clickable HTML mocks** | **Custom tab → sandboxed nested iframe** from the isolated origin (signed URL). Fidelity: full interactivity. Mobile: **unknown** (F.5 spike). Auth: signed URL (origin can't SSO). Effort: medium-high. Git cost: none. | **"Open mock in browser"** link (Action.OpenUrl to signed URL on the isolated origin). Fidelity: full. Mobile: yes (system browser). Auth: signed URL. Effort: low. Git cost: none. **Robust fallback, ship first.** | **AC screenshot(s)** (PNG per screen, §8.1). Fidelity: static only. Mobile: yes. Auth: public/signed URL. Effort: low. Git cost: low. | Files tab (HTML rendering in SharePoint unconfirmed; drift); Loop |

**Evidence:**
- https://learn.microsoft.com/en-us/microsoftteams/platform/m365-apps/design-loop-components (last updated
  2026-04-01; ms.date 2024-10-11 → PRE-GA, still applies; DOC).
- https://learn.microsoft.com/en-us/graph/api/channel-get-filesfolder (last updated 2026-03-07; ms.date
  2024-08-19 → PRE-GA, still applies; DOC).
- https://learn.microsoft.com/en-us/graph/api/driveitem-put-content (last updated 2026-08-11; ms.date
  2017-09-10 → PRE-GA, still applies; DOC).
- https://learn.microsoft.com/en-us/microsoftteams/platform/messaging-extensions/how-to/link-unfurling (last
  updated 2026-10-08; ms.date 2026-09-24; DOC). Note: its code samples are still "based on v4.6 and later
  versions of the Bot Framework SDK", which is Bot-Framework-era. The manifest and invoke contract is
  SDK-independent, but take the Python handler shape from the Teams SDK (research A).
- https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/cards/cards-reference
  (last updated 2026-08-19; ms.date 2024-09-16 → PRE-GA, still applies; DOC). Image formats and size, no
  SVG, no redirects, AC ≤1.6. The page itself calls its AC section "legacy" and defers to
  adaptivecards.microsoft.com.
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/open-content-in-stageview (last updated
  2026-09-21; DOC).
- Markdown in SharePoint: https://mc.merill.net/message/MC1261592 (Message Center mirror, **not primary**;
  accessed 2026-10-09).

**Confidence:** high on the per-option DOC facts. Medium on the ranking (INFER). Low on SharePoint
.md/.html rendering (secondary or none).

**Implication for docs/80:**
- §8 **confirm** the custom tab as the primary viewer for all three artifact types.
- §14.4 **change**: ship "open mock in browser" (signed URL) as the v1 path, with the nested iframe behind
  the F.5 spike.
- §8.1 **confirm**: PNG thumbnails for cards (not SVG, ≤1024², no-redirect URL).
- **Reject** Loop components and the Files-tab mirror. Record the reason in §1.4 / §8: drift plus a
  tenant-wide `Files.ReadWrite.All` grant versus git as the source of truth.
- Optional later: a link-unfurl handler for **our own** tab-host URLs only.

---

### I.3 What is safe to render from agent-generated content (tab, card)

**Answer:**

**Adaptive Cards.** A card is JSON rendered natively by Teams. Agent text can't inject script, so the
exposure is limited to:
- (a) markdown in TextBlock: links can phish, so render link targets as visible text or allow-list them;
- (b) image URLs, which must be ours (≤1024², PNG/JPEG/GIF, no redirect);
- (c) `Action.OpenUrl` targets, which should be built only by our code, never copied from agent output;
- (d) size limits (E.5). INFER, consistent with the card docs.

**Custom tab, markdown (spec/plan/ADR).** Treat agent markdown as untrusted HTML input:
- render it with a markdown library with raw HTML **disabled**;
- sanitize the output (e.g. DOMPurify);
- rewrite or allow-list link targets;
- drop remote images, or proxy them through our host.

INFER: I found **no Teams or Microsoft primary source** that prescribes a markdown sanitizer. This is
general web-security practice, so mark it as such.

**Custom tab, mermaid (CODE/DOC, F.4):**
- keep `securityLevel:'strict'` (HTML in labels is encoded, `click` is disabled, DOMPurify runs);
- never use `loose`;
- pin ≥11.16.1 because of the 2026 CSS/HTML-injection advisories;
- render one diagram per sibling-free container (the CVE-2026-50159 workaround);
- run `mermaid.parse` both server-side (§9.1) and client-side before `render`;
- accept that the tab CSP needs `style-src 'unsafe-inline'`. Injected CSS is therefore the residual risk,
  contained by the version pin and container isolation. No `unsafe-eval` is needed.

**Custom tab, the tab's own CSP (INFER):**
```
default-src 'self'; script-src 'self' <teamsjs-cdn-or-self-hosted>; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' <possibly TeamsJS origins CDN, F.3>; frame-src https://<mock-origin>; frame-ancestors <F.3 list>
```
Self-host TeamsJS, or pin it with SRI, so `script-src` stays tight.

**HTML mocks (INFER + F.5):**
- serve them only from a **separate registrable origin**;
- frame them with `sandbox="allow-scripts"` only: no `allow-same-origin`, `allow-top-navigation`,
  `allow-popups` or `allow-forms`;
- the mock origin's CSP is `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline';
  img-src data:; font-src data:; connect-src 'none'; form-action 'none'; frame-ancestors https://<tab-host>`.
  `connect-src 'none'` kills external fetches and beacons; `img-src data:` stops pixel exfiltration;
- the producer (§9.2) must inline all assets, which means compiled Tailwind, not the CDN;
- signed, expiring URLs per mock at a SHA.

Never pass SSO tokens, `getContext()` data or TeamsJS into the mock frame. Don't `postMessage` anything
sensitive to it.

**Evidence:**
- mermaidAPI.ts (CODE, accessed 2026-10-09) and mermaid usage/advisories (DOC), as in F.4.
- cards-reference (last updated 2026-08-19; DOC) for image constraints.
- tab-requirements (last updated 2026-05-29; DOC) for frame-ancestors.
- access-teams-context (last updated 2026-09-17; DOC): "you must not use it as proof of identity".
- Everything about sanitizer choice and mock CSP is INFER (standard web security; no Teams primary source).

**Confidence:** medium. The mermaid and card constraints are high. The sanitization and CSP recipe is sound
practice but not Teams-documented.

**Implication for docs/80:**
- §7.4 **confirm and extend** the mock CSP (add `connect-src 'none'`, `form-action 'none'`, `img-src data:`,
  and `frame-ancestors` = tab host).
- §9.2 **new constraint**: mocks must be fully self-contained (no CDN Tailwind).
- §9.1 **detail**: pin the same mermaid version server- and client-side.
- §14 **detail**: card URLs are built only by our code.

---

### Snippet — minimal TeamsJS static channel tab (for end-to-end sketch §4.2 item 5)

The tab does `app.initialize` → `getContext` (`page.subPageId`) → `getAuthToken` → calls our API with
`Bearer` → `mermaid.parse` + `render` (strict). The bundling assumption is ES modules served from our own
origin (`/vendor/…`), so `script-src 'self'`. The versions are the ones seen above: `@microsoft/teams-js`
2.58.0 and mermaid ≥ 11.16.1. Don't copy the docs' `res.cdn.office.net/teams-js/2.2.0` URL; the docs
themselves warn it's not current.

```html
<!doctype html>
<!-- Served from https://tab.example.com/ with headers:
  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';
    img-src 'self' data:; connect-src 'self'; frame-src https://mocks.example-isolated.net;
    frame-ancestors https://teams.microsoft.com https://*.teams.microsoft.com https://*.cloud.microsoft
    https://*.microsoft365.com https://*.office.com https://outlook.office.com https://outlook.office365.com
  (F.3/F.4; connect-src may need the TeamsJS valid-origins CDN host — spike) -->
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Factory</title>
</head>
<body>
  <div id="status">Loading…</div>
  <div id="diagram"></div><!-- sibling-free container per diagram (CVE-2026-50159 workaround) -->
  <script type="module">
    // @microsoft/teams-js 2.58.0 (npm), self-hosted. API: app.initialize / app.getContext /
    // authentication.getAuthToken / app.notifySuccess — learn.microsoft.com tab-sso-code, access-teams-context,
    // content-page (see F.2, F.7).
    import { app, authentication } from "/vendor/teams-js/2.58.0/MicrosoftTeams.esm.js";
    // mermaid >= 11.16.1, self-hosted. API: initialize / parse / render — mermaid.js.org/config/usage.html (F.4).
    import mermaid from "/vendor/mermaid/11.16.1/mermaid.esm.min.mjs";

    const status = (t) => { document.getElementById("status").textContent = t; };

    async function main() {
      await app.initialize();                       // required, else the page isn't displayed (tab-requirements)
      const ctx = await app.getContext();           // context is NOT proof of identity (access-teams-context)
      // subEntityId from a deep link, e.g. "014-saved-carts/architecture/2" (F.7). Default view if absent.
      const sub = ctx.page.subPageId || "";
      const [feature, view = "architecture", attempt] = sub.split("/");

      // SSO: access token whose aud = our Entra client ID; no OBO needed for our own API (F.2).
      const token = await authentication.getAuthToken();

      // Server validates signature, aud, iss/tid, scp=access_as_user, exp; derives user from oid/tid claims,
      // then checks channel membership (§13). We pass channel id only as a lookup hint, never as identity.
      const qs = new URLSearchParams({ feature: feature || "", view, attempt: attempt || "",
                                       channel: ctx.channel?.id || "" });
      const res = await fetch(`/api/artifacts?${qs}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`artifact API ${res.status}`);
      const { mermaidSource, sha } = await res.json(); // .mmd text read from git at a SHA (§7.4)

      mermaid.initialize({ startOnLoad: false, securityLevel: "strict" }); // strict = default; DOMPurify on
      await mermaid.parse(mermaidSource);           // throws on invalid diagrams (validate before render)
      const { svg } = await mermaid.render("arch-" + (sha || "x").slice(0, 7), mermaidSource);
      document.getElementById("diagram").innerHTML = svg; // mermaid output (sanitized under 'strict')
      status(`${feature} · ${view} @ ${sha}`);
      app.notifySuccess();                          // needed only if manifest sets showLoadingIndicator: true
    }

    main().catch((e) => {
      status("Could not load artifact: " + e);
      try { app.notifyFailure({ reason: app.FailedReason.Other, message: String(e) }); } catch {}
    });
  </script>
</body>
</html>
```

Manifest fragment the snippet assumes (manifest ≥ 1.16; DOC per F.1/F.2/F.3):

```json
"staticTabs": [{
  "entityId": "factory",
  "name": "Factory",
  "contentUrl": "https://tab.example.com/",
  "websiteUrl": "https://tab.example.com/",
  "scopes": ["team"],
  "context": ["channelTab"]
}],
"validDomains": ["tab.example.com", "mocks.example-isolated.net"],
"webApplicationInfo": { "id": "<clientId>", "resource": "api://tab.example.com/<clientId>" }
```

If this app package also contains a bot, the resource is `api://tab.example.com/botid-<botClientId>` (F.2).

---

### Open items with severity (for §4.3)

| Item | Severity | Next step |
|---|---|---|
| F.5 nested `sandbox="allow-scripts"` iframe from an isolated origin: undocumented on all clients; desktop/mobile webview subframe behaviour unknown | **changes design** | Spike on web, new Teams desktop, iOS, Android; ship "open in browser" with signed URL first |
| F.7 / E.6 deep link with `subEntityId` + `channelId` into a **static** tab pinned in a channel: docs still say channelId is for configurable tabs | **changes design** (card buttons) | Spike; fallback Stageview `tab/tabInfoAction` or `websiteUrl` |
| Mobile deep links for custom / org-catalog apps (docs only cover Store-approved apps and the iOS Team ID) | detail | Device test |
| Mock origin can't use SSO (single domain per Entra app; opaque sandbox origin) | changes design | Signed, expiring mock URLs minted by the artifact API |
| F.2: docs/80 §7.4 says "SSO-exchanged token"; no exchange is needed for our own API | detail (wording + validator) | Update §7.4; OBO only if Graph is needed (H.3) |
| `botid-` Application ID URI if the tab shares a package with a bot | detail (feeds K.1) | Decide tab-owning app package |
| TeamsJS ≥2.56 may fetch valid-origins from a CDN, so a strict `connect-src` might break init | detail | Strict-CSP smoke test |
| Mermaid needs `style-src 'unsafe-inline'` (no nonce support); 2026 CSS/HTML-injection CVEs | detail | Pin ≥11.16.1; sibling-free containers; strict level |
| Latest mermaid major version unclear (12.x tags reported with inconsistent dates) | detail | Check npm before pinning |
| SharePoint .md viewer (secondary source only), mermaid in it, HTML rendering in SharePoint | detail (only matters if Files-tab mirror is reconsidered) | None, option rejected |
