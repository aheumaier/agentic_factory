# Sandbox vendors, OWASP/CSA/Google frameworks, and supply-chain postmortems (gap-fill)

Access date for all sources: 2026-10-13. Sources marked "search excerpt" were read only as search-result text, not fetched. Items marked UNVERIFIED were not confirmed on a primary page. Does not repeat 06_sandbox_security.md except where a claim there was corrected.

## Sandbox vendors

### Takeaway
E2B documents per-sandbox pause that keeps state and a 24-hour cap on Pro. Modal documents a 5-minute default lifetime and gVisor or VM runtimes. Vercel documents Firecracker microVMs with auto-saved persistence. Daytona documents containers plus VM classes. Cloudflare's lifetime page did not load. Egress control and pricing for several vendors were not found on primary pages.

### Cited Findings
- E2B: sessions run up to "24 hours (Pro) or 1 hour (Hobby)"; "pausing ... your sandbox's full state is preserved indefinitely" — [E2B docs](https://docs.e2b.dev/sandbox) (redirect from e2b.dev/docs/sandbox). Isolation technology not named on that page. A `getInfo` example shows `allowInternetAccess`; no allow/deny-out options were documented on that page.
- E2B pricing (secondary only): per-second, about $0.000014/s per vCPU and $0.0000045/GiB/s; Firecracker base per third-party sources — [Morph E2B pricing](https://www.morphllm.com/e2b-pricing). UNVERIFIED against e2b.dev pricing.
- E2B cold start (sources conflict, all secondary): 717 ms create and 662 ms resume in one benchmark; sub-200 ms claims elsewhere — [LogRocket comparison](https://blog.logrocket.com/comparing-ai-agent-sandbox-platforms-e2b-modal-daytona-and-more/). Whether paused sandboxes bill: not found.
- Modal: "gVisor" and "VM runtime" options; default maximum lifetime "5 minutes"; `timeout` up to "24 hours"; separate `idle_timeout` — [Modal sandbox guide](https://modal.com/docs/guide/sandbox). Network egress controls: not found on that page. Snapshot mechanics: only "Filesystem Snapshots" mentioned, not detailed.
- Modal pricing: Sandboxes CPU "$0.00003942 / core / sec"; memory "$0.00000667 / GiB / sec" — [Modal pricing](https://modal.com/pricing).
- Vercel Sandbox: "Each sandbox runs in a secure Firecracker microVM"; "Persistence is the default" with state auto-saved on stop; Snapshotting is a separate feature; Secure Compute routes public traffic via static IPs — [Vercel Sandbox docs](https://vercel.com/docs/vercel-sandbox), accessed 2026-10-13. Billing unit: Active CPU per vCPU-second plus provisioned memory (example pricing page section). Max duration per plan and an egress allow-list: not found (pricing page not fetched).
- Daytona: "Each sandbox runs in isolation ... a dedicated kernel, filesystem, network stack"; container default, VM class also offered; container runtime cold start "<90ms" (vendor claim); pause/resume and fork are VM-only; snapshots create-from-sandbox for VMs — [Daytona sandbox management](https://www.daytona.io/docs/en/sandbox-management/). Auto-stop defaults, egress control and pricing unit: not found in excerpt.
- Cloudflare Sandbox SDK: "Each instance is a microVM with its own kernel and network"; containers reach the internet via `enableInternet: false` in the example; Dynamic Workers block outbound with `globalOutbound: null` — [Cloudflare Sandbox](https://developers.cloudflare.com/sandbox/). Sleep default, file loss on stop, max session, pricing unit: not found (the linked lifetime page returned HTTP 404).

Comparison table (N/F = not found on primary page):

| Vendor | Isolation | Cold start | Max session | Snapshot / pause | Egress control | Pricing unit |
|---|---|---|---|---|---|---|
| E2B | Firecracker per secondary sources; not named on docs page | 662-717 ms (secondary, conflicting) | 24 h Pro, 1 h Hobby | Pause keeps state indefinitely | `allowInternetAccess` field; policy options N/F | per second per vCPU and GiB (secondary) |
| Modal | gVisor or VM | N/F | 5 min default, up to 24 h | Filesystem snapshot (brief) | N/F | per core-sec and GiB-sec |
| Vercel | Firecracker microVM | "milliseconds" (vendor, no number) | N/F (plan page not read) | Auto-save on stop; snapshots | Static IPs via Secure Compute; allow-list N/F | Active CPU + provisioned memory |
| Daytona | Container default; VM class | "<90ms" container (vendor) | N/F | VM pause/resume and snapshot | N/F | N/F (billing page not read) |
| Cloudflare | microVM per instance | N/F | N/F (lifetime page 404) | Snapshots, mechanics N/F | `enableInternet`; `globalOutbound` for Dynamic Workers | N/F |

### Inferences
- E2B sessions over 24 hours need a snapshot or re-create step. Modal's 5-minute default needs an explicit `timeout` in the factory's sandbox call.
- Only Modal and Cloudflare name a network-off switch on their docs pages. The factory's default-deny egress needs a check on each vendor's current API before choosing one.
- Cold start and cost numbers are not comparable across vendors yet. Benchmark on the factory's own template in its region before deciding.

### Gaps
- Primary egress allow-list docs for E2B, Modal, Vercel and Daytona: not found.
- Whether E2B paused sandboxes bill: not found.

## OWASP Top 10 for Agentic Applications

### Takeaway
The OWASP agentic list is dated 2025-12-09 and has ten IDs. The primary page did not list the items. The names below come from a secondary aggregator and are UNVERIFIED.

### Cited Findings
- Date 2025-12-09 — [OWASP GenAI resource page](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026), accessed 2026-10-13. Item list not on the page; download link required.
- Secondary list (UNVERIFIED): ASI01 Agent Goal Hijack; ASI02 Tool Misuse & Exploitation; ASI03 Identity & Privilege Abuse; ASI04 Agentic Supply Chain Vulnerabilities; ASI05 Unexpected Code Execution (RCE); ASI06 Memory & Context Poisoning; ASI07 Insecure Inter-Agent Communication; ASI08 Cascading Failures; ASI09 Human-Agent Trust Exploitation; ASI10 Rogue Agents — [Galileo ASI01 post](https://galileo.ai/blog/owasp-agentic-ai-asi01-goal-hijack) (search excerpt; the aggregator says ASI07, ASI09 and ASI10 names came from memory).

### Inferences
- Implication for factory architecture: use ASI04 (supply chain) and ASI02/ASI03 (tool misuse, privilege) as the threat-review rows for the Build agent. Confirm the exact titles from the downloaded PDF before citing them in a factory document.

### Gaps
- Primary item list and IDs: not found on the fetched page. Download the PDF and read it.

## OWASP Top 10 for LLM Applications 2025

### Takeaway
Primary page confirmed the ten 2025 items.

### Cited Findings
- LLM01:2025 Prompt Injection; LLM02:2025 Sensitive Information Disclosure; LLM03:2025 Supply Chain; LLM04:2025 Data and Model Poisoning; LLM05:2025 Improper Output Handling; LLM06:2025 Excessive Agency; LLM07:2025 System Prompt Leakage; LLM08:2025 Vector and Embedding Weaknesses; LLM09:2025 Misinformation; LLM10:2025 Unbounded Consumption — [OWASP LLM Top 10](https://genai.owasp.org/llm-top-10/), accessed 2026-10-13.

### Inferences
- Implication for factory architecture: LLM06 (Excessive Agency) maps to the lethal-trifecta controls in 06_sandbox_security.md; LLM03 (Supply Chain) maps to the Nx and Shai-Hulud incidents below.

## CSA MAESTRO and Google

### Takeaway
MAESTRO is a layered threat-model method. Google's SAIF gives six elements, and its agent paper gives three principles.

### Cited Findings
- MAESTRO: seven layers (Foundation Models, Data Operations, Agent Frameworks, Deployment and Infrastructure, Evaluation and Observability, Security and Compliance, Agent Ecosystem) — [CSA MAESTRO](https://labs.cloudsecurityalliance.org/maestro/) (search excerpt; layer names UNVERIFIED on the primary page).
- Google SAIF six elements, verbatim: "Expand strong security foundations to the AI ecosystem"; "Extend detection and response to bring AI into an organization's threat universe"; "Automate defenses to keep pace with existing and new threats"; "Harmonize platform-level controls to ensure consistent security across the organization"; "Adapt controls to adjust mitigations and create faster feedback loops for AI deployment"; "Contextualize AI system risks in surrounding business processes" — [Google SAIF](https://safety.google/intl/en_us/cybersecurity-advancements/saif/), accessed 2026-10-13. The page has no agent-specific guidance.
- Google agents paper (Díaz and Olive, 2025): three principles, a human controller for each agent, tightly limited powers, and observable actions and planning; hybrid deterministic plus reasoning-based defenses — [Google Research](https://research.google/pubs/an-introduction-to-googles-approach-for-secure-ai-agents/) (search excerpt; describes itself as a working position).

### Inferences
- Implication for factory architecture: the three Google principles map directly onto the factory's human approval gate, per-role token scoping, and logged agent plans. Use MAESTRO layer 4 (infrastructure) and layer 6 (security) as the sandbox and credential review scope.

### Gaps
- MAESTRO primary layer definitions: not read.

## Supply-chain postmortems (class level)

### Takeaway
Both incidents combined a stolen publish credential with an AI coding CLI on the victim's machine. The Shai-Hulud root causes are a CI workflow that ran untrusted pull request code with secrets, and a token held by a bot.

### Cited Findings
- Nx "s1ngularity": the attack ran from 2025-08-26 to at least 2025-08-31 ([Wiz, published 2025-09-03](https://wiz.io/blog/s1ngularitys-aftermath), accessed 2026-10-13). The malicious install step checked for installed AI CLIs (Claude, Gemini, Amazon Q) and prompted them to inventory sensitive files. Wiz says the approach worked in under a quarter of cases, because of missing configuration, model refusals and workspace limits. Wiz lists GitHub audit-log checks, not AI-CLI defenses.
- Nx root cause (per a secondary summary of Nx's 2025-09-01 update): a CI workflow change arrived by pull request, and a later change sent the publish token to an external server — [Snyk, Nx write-up](https://snyk.io/pt-BR/blog/weaponizing-ai-coding-agents-for-malware-in-the-nx-malicious-package/) (search excerpt; Nx's own advisory not read; the attribution of this root-cause text to Snyk is from a search summary and UNVERIFIED).
- Shai-Hulud 2.0: PostHog's postmortem calls the incident its "largest and most impactful security incident"; root cause was a CI workflow that let a malicious pull request run with access to a bot token, which then gave access to an npm token — [The Register](https://www.theregister.com/2025/11/28/posthog_shaihulud/) and [SpecterOps](https://specterops.io/blog/2026/03/19/graph-the-planet-shai-hulud-2-0/) (both search excerpts; PostHog's own postmortem not read). Unit 42 assesses with moderate confidence that an LLM generated the worm's script — [Unit 42](https://origin-unit42.paloaltonetworks.com/?p=157750) (executive summary only).
- npm mass revocation of classic tokens on 2025-12-09 — secondary source only, UNVERIFIED against npm's own notice.

### Inferences
- Controls that would have stopped the class (factory inference, not from the sources):
  - Publish with short-lived or OIDC-scoped credentials, not long-lived tokens, so a stolen token expires.
  - Run pull-request code in CI with no secrets and no publish rights; review any workflow file changed in a PR before merge.
  - Never run an agent CLI with permission-prompt bypass flags on a machine that holds credentials. The factory's E2B sandbox with no secrets in it is the control.
  - Block outbound network from the agent sandbox except the model API and GitHub, so an exfiltration step has no route.
- Implication for factory architecture: the factory's Build sandbox must hold no publish token, and the register step must not run agent-authored workflow changes without a human merge.

### Gaps
- Nx and PostHog primary postmortems: not read. Unit 42 full report: not read.

## Corrections to 06_sandbox_security.md
- Section "Execution sandboxes" said Modal "uses gVisor" and Vercel "uses Firecracker". Modal's docs now list gVisor or a VM runtime, chosen by the caller or by Modal. Vercel's docs confirm Firecracker.
- Its Nx date was not confirmed; this note confirms 2025-08-26 to 2025-08-31 from Wiz.
- Its OWASP Agentic item names were UNVERIFIED; this note still does not confirm them.

## Open items
- Read the OWASP agentic PDF for the ten item titles.
- Re-check E2B egress and billing on docs.e2b.dev pricing pages.
- Read the Cloudflare sandbox lifetime page (404 on the URL tried).
