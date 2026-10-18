# Observability, inference routing, economics and governance for agent-native software factories

Access date for all URLs: 2026-10-13. Items marked UNVERIFIED have no live source in this pass. Several figures come from vendor blogs or secondary coverage; the source line says so.

## Observability: how agent runs are traced and measured

### Takeaway
OpenTelemetry GenAI agent spans exist in the spec but are still in Development status, so attribute names can change. Claude Code can export metrics and events by default, and traces only as a beta. A factory should pin a semantic-convention version and record its own run-level trace schema.

### Cited Findings
- The OTel agent-span spec page has moved to a separate repo, and that repo marks agent spans as Development. `create_agent` uses span kind CLIENT and the name `create_agent {gen_ai.agent.name}`. `gen_ai.system_instructions` is opt-in. Span status follows the Recording Errors page, which I did not retrieve. — [OTel GenAI agent spans (moved)](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans); [semantic-conventions-genai repo](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md)
- Third-party coverage says GenAI and MCP conventions stayed in Development as of May 2026, with no published stabilization date. Instrumentations emit the older schema unless `OTEL_SEMCONV_STABILITY_OPT_IN` is set. — [Greptime, 2026-05-09](https://greptime.com/blogs/2026-05-09-opentelemetry-genai-semantic-conventions); [OTel GenAI spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans)
- Claude Code metrics (official docs): `claude_code.session.count`, `token.usage` (types input, output, cacheRead, cacheCreation), `cost.usage` (USD, per model), `commit.count`, `pull_request.count`, `code_edit_tool.decision`, `active_time.total`, `lines_of_code.count`. Attributes include `agent.name`, `skill.name`, `mcp_tool.name`, `effort`. — [Claude Code monitoring](https://code.claude.com/docs/en/monitoring-usage)
- Claude Code events: `user_prompt`, `tool_result`, `tool_decision`, `api_request`, `api_error`, `api_refusal`, `skill_activated`, `plugin_loaded`, and others. Prompt and tool-input text are redacted unless `OTEL_LOG_USER_PROMPTS` and `OTEL_LOG_TOOL_DETAILS` are set. — [Claude Code monitoring](https://code.claude.com/docs/en/monitoring-usage)
- Claude Code traces are beta and off by default. They need `CLAUDE_CODE_ENABLE_TELEMETRY=1`, `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` and `OTEL_TRACES_EXPORTER`. Spans: `claude_code.interaction`, `llm_request`, `tool`, `tool.execution`, `hook`. — [Claude Code monitoring](https://code.claude.com/docs/en/monitoring-usage)
- LangSmith, Arize Phoenix, Langfuse and Braintrust logging: not found in this pass (no retrieved source). — Gap.
- OpenAI traces: not found in this pass. — Gap.

### Inferences
- Implication for factory architecture: Emit one run-level trace per pipeline stage (spec, plan, build, gate, PR). Record for each model call: model, input and output tokens split into cache read and cache write, cost, tool name, agent name, and PR or task ID. Do not depend on a single vendor's trace model.
- Implication for factory architecture: Keep prompt and tool content out of default telemetry. Turn on content capture only for a named debug run. The redaction defaults match this.
- Implication for factory architecture: Treat `claude_code.*` metrics as a cost source of truth for interactive sessions. Seat-backed headless runs need their own counters, because the metrics are not guaranteed to cover every caller (UNVERIFIED for the Agent SDK path).

### Gaps
- Exact `invoke_agent` and `execute_tool` span kinds and required attributes: the fetched page was truncated. Re-fetch the semconv repo before writing a schema.
- Whether Claude Code telemetry covers headless `claude -p` and Agent SDK runs: not verified.

## Inference routing and gateways

### Takeaway
Gateways in the market (LiteLLM, Cloudflare AI Gateway) offer fallback, per-key or per-team budgets, rate limits and caching. Budget behavior differs: Cloudflare blocks with HTTP 429 by default and can instead fall back to a cheaper model. LiteLLM's budget-fallback behavior is only partly verified.

### Cited Findings
- LiteLLM has a budget-fallbacks feature that maps a model to fallback models per virtual key. Virtual keys need PostgreSQL. — [LiteLLM budget fallbacks](https://docs.litellm.ai/docs/proxy/budget_fallbacks)
- LiteLLM per-key and per-team budgets, rate limits (RPM/TPM), and cost breakdowns per team: third-party sources only. Sources disagree on whether an exhausted budget reroutes or hard-stops. — [Elest.io guide](https://blog.elest.io/self-host-litellm-one-api-gateway-for-every-llm/); [Medium overview](https://medium.com/@mrutyunjaya.mohapatra/litellm-a-unified-llm-api-gateway-for-enterprise-ai-de23e29e9e68). Official confirmation: not found.
- Cloudflare AI Gateway spend limits: when exceeded, the gateway returns 429. Default is to block until the window resets. A fallback option routes to a cheaper model from a Dynamic Route. Limits can be scoped by provider, model, or custom metadata such as user or team. Spend is estimated, so check against provider billing. — [Cloudflare spend limits](https://developers.cloudflare.com/ai-gateway/features/spend-limits/index.md); features list: [Cloudflare AI Gateway features](https://developers.cloudflare.com/ai-gateway/features/)
- Cloudflare caching is controllable per request with headers such as `cf-aig-cache-ttl` and `cf-aig-skip-cache`. Third-party guidance: cache only repeatable requests. — [Redwerk guide](https://redwerk.com/blog/cloudflare-ai-gateway/) (secondary)
- Anthropic prompt caching multipliers, as found in search snippets of Anthropic's docs: 5-minute cache write 1.25x base input, 1-hour write 2x, cache read 0.1x. Break-even is one hit for the 5-minute write and two for the 1-hour write. A Helicone doc says Bedrock and Vertex support only 5-minute caching. — [Anthropic prompt caching](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching) (multipliers from snippet, not fetched); [Helicone](https://docs.helicone.ai/gateway/concepts/prompt-caching) (secondary)
- Portkey, OpenRouter, Bedrock and Vertex gateway features: not found in this pass. — Gap.

### Inferences
- Implication for factory architecture: Use a budget per agent role and per repo, not per developer. The factory's unit of spend is a task, so budget keys should match it. Cloudflare's metadata-scoped limits show the shape.
- Implication for factory architecture: Choose between block and fallback on purpose. A fallback to a cheaper model can change code quality. Gate it so the gate still runs on the fallback model's output.
- Implication for factory architecture: Caching pays off for repeated large prefixes such as system prompts and skill files. The 1-hour write only pays off if the same prefix is hit at least twice inside the hour. Check whether the pipeline's cache hit rate justifies the 2x write.

### Gaps
- Official LiteLLM behavior on budget exhaustion: not confirmed.
- Current Anthropic per-model cache prices: the multipliers are from snippets; the per-model table was not fetched.

## Economics: token cost per task and per PR

### Takeaway
Published multi-agent token ratios are about 4x (agents) and 15x (multi-agent) versus chat, from Anthropic's own write-up. No primary source gives a verified cost per merged PR. Vendor blogs give per-task costs and merge rates, but these are not audited.

### Cited Findings
- Anthropic's multi-agent research system: agents use about 4x more tokens than chat, multi-agent about 15x. Token usage alone explained 80% of variance in the BrowseComp evaluation. The multi-agent system beat single-agent Opus 4 by 90.2% on an internal research eval. The post says coding is less parallelizable. — [Anthropic engineering blog](https://www.anthropic.com/engineering/multi-agent-research-system) (fetched)
- Median SWE-bench Verified task cost $3.26 (range $0.08 to $32.00), from a study of 242 runs. Vendor blog, secondary. — [Pixis](https://inference-website.pixis.ai/blog/best-ai-coding-agents-in-2026-a-practical-comparison)
- AI-generated PRs merge at 32.7% versus 84.5% for human PRs. LinearB reports autonomous agent PRs merge within 30 days at 79% versus 92% for human PRs. Vendor data, secondary. — same Pixis page citing LinearB; [LinearB benchmarks](https://linearb.io/resources/ai-engineering-productivity-gap)
- Cost per merged PR, defined as total agent spend divided by PRs that merged, and stricter versions that also survive a churn window. The stricter version is the only one that counts shipped and kept code. — [Unblocked](https://getunblocked.com/blog/cost-per-merged-pr/index.md); [Larridin](https://larridin.com/measurement-guide/agent-effectiveness/cost-per-outcome/)
- Per-review tooling cost: $15 to $25 per AI review per one vendor (GitLab's own claim); GitLab's flat option is $0.25 per review. Vendor claim. — [GitLab](https://about.gitlab.com/blog/agentic-code-reviews-with-flat-rate-pricing)
- Subscription versus API: Anthropic's support article says that if `ANTHROPIC_API_KEY` is set, Claude Code bills to the API key, not the subscription. Pro and Max limits are shared between chat and Claude Code. — [Anthropic support](https://support.claude.com/en/articles/11145838)
- Subscription OAuth terms: one secondary guide quotes the terms as limiting OAuth on Free/Pro/Max/Team/Enterprise plans to ordinary individual use of Claude Code and native apps, and says products and Agent SDK use should use an API key. The Agent SDK OAuth change dated February 2026 is reported by a blog only. I did not fetch Anthropic's terms. — [Autonomee](https://autonomee.ai/blog/claude-code-terms-of-service-explained/); [Morphllm](https://www.morphllm.com/claude-code-subscription) (secondary)
- Token-spend percentile: $481 per developer per month at the 90th percentile. Vendor benchmark, secondary. — [LinearB](https://linearb.io/resources/ai-engineering-productivity-gap)

### Inferences
- Implication for factory architecture: Budget a multi-agent run at roughly 4x to 15x a single-agent run, using Anthropic's ratio as a planning assumption, not a measured value for this factory. Measure your own ratio from `token.usage` first.
- Implication for factory architecture: Report cost as cost per merged-and-kept PR. Divide total spend by PRs that merged and were not reverted or heavily rewritten within a set window. Dividing by runs hides the cost of rejected attempts; a 33% merge rate triples the real cost of a shipped change.
- Implication for factory architecture: Do not run unattended CI or scheduled builds on a personal subscription. Use an API key for automation and check that no stray `ANTHROPIC_API_KEY` is set on a seat host, since it silently switches billing.

### Gaps
- Published measured cost per merged PR from an independent source: not found.
- Anthropic's own Consumer and Commercial Terms text on automation: not fetched; the claims above are secondary.
- Quantified FinOps for AI guidance from finops.org: not found in this pass. — Gap.

## Metrics for the factory: DORA, SPACE, DX Core 4

### Takeaway
DORA's 2025 AI report says AI amplifies existing team conditions and that only some team types benefit. DX says AI telemetry should be diagnostic context, not an outcome metric. Measure delivery outcomes (lead time, change failure rate, rework) alongside agent-specific rates (merge rate, review time).

### Cited Findings
- DORA 2025 (State of AI-assisted Software Development, about 5,000 respondents): 90% AI adoption, 65% rely on it heavily; over 80% say it improves productivity (self-reported). "AI's primary role... is that of an amplifier." Only two of seven team clusters improve throughput without higher change failure rate. — [TechRepublic summary](https://www.techrepublic.com/article/news-dora-ai-report-2025/); [Rob Bowley blog review](https://blog.robbowley.net/2025/10/01/dora-2025-ai-assisted-dev-report-some-benefit-most-dont/); [Google blog](https://blog.google/technology/developers/dora-report-2025/). Primary DORA report not fetched.
- DX Core 4 unifies DORA, SPACE and DevEx into four dimensions (speed, effectiveness, quality, impact). DX recommends AI telemetry as diagnostic context and triangulating across diagnostic, system and outcome metrics. Some system-level Core 4 data requires DX's paid product. — [DX docs](https://docs.getdx.com/dx-core-4/); [DX blog](https://getdx.com/blog/revisiting-the-dx-core-4-in-the-age-of-ai/)
- Agent PR review-time effects, all secondary: time to review a PR rose 49% after agent adoption (Harvard working paper, Chen and Stratton; Jellyfish data, 718 firms). Lines of code rose 30% without a significant rise in finished tasks. — [FourWeekMBA summary](https://fourweekmba.com/ai-coding-agents-add-30-more-code-not-more-finished-work/)
- NBER WP 35275: autonomous agents produced 741% more lines of code and releases rose 20% (GitHub data, 100,000+ developers, May 2026). Secondary; primary not fetched. — same FourWeekMBA page.
- Agent PRs are merged faster, reviewed less, and discussed less in one 2026 study, but the direction flips under different defensible analysis choices (arXiv 2607.07980). — [arXiv 2607.07980](https://www.alphaxiv.org/abs/2607.07980.md)
- 33,707 agent PRs: 28.3% merge instantly, but agents often fail iterative review and are abandoned. — [arXiv 2601.00753](https://arxiv.org/html/2601.00753v2)
- Claude Code telemetry gives `pull_request.count`, `commit.count` and `code_edit_tool.decision`, which can feed these metrics directly. — [Claude Code monitoring](https://code.claude.com/docs/en/monitoring-usage)

### Inferences
- Implication for factory architecture: Build a dashboard with four rows: delivery (lead time, deploy frequency, change failure rate, time to restore), agent quality (merge rate, rework rate within 14 or 30 days, gate pass rate on first attempt), review (time to first review, time to merge), and cost (cost per merged PR). Use the DORA definitions as the source of truth.
- Implication for factory architecture: Keep the agent merge rate and the review time next to each other. A high merge rate with rising review time means reviewers are rubber-stamping or the queue is growing.

### Gaps
- SPACE original definitions and current status: not fetched.
- DORA's own recommended metric list for AI-assisted delivery: primary page not fetched.

## Governance: autonomy, accountability, and regulation

### Takeaway
EU AI Act high-risk obligations were postponed (Regulation (EU) 2026/1744, in force 2026-07-27) to 2027 and 2028. A general software-development agent is probably outside the high-risk tier unless it is used for an Annex III purpose such as employment decisions. ISO/IEC 42001 is certifiable but not a legal presumption under the Act.

### Cited Findings
- Omnibus amendment: Annex III high-risk obligations moved to 2027-12-02; Annex I to 2028-08-02. Article 50 transparency and GPAI enforcement stayed on 2026-08-02. — [Gibson Dunn](https://www.gibsondunn.com/eu-ai-act-omnibus-agreement); secondary summaries by [CASRAI](https://casrai.org/news/digital-omnibus-ai-act). Regulation number and dates were reported by a secondary source; verify against the Official Journal.
- Article 14 human oversight for high-risk systems requires technical ability to override, interrupt or stop the system, not just documentation. Deployers must keep logs for at least six months (Article 26, per a secondary summary). — [Software Improvement Group summary](https://www.softwareimprovementgroup.com/eu-ai-act-summary/) (secondary)
- No source found that addresses coding agents specifically under the AI Act. — Gap.
- ISO/IEC 42001 is a certifiable AI management system standard. It is not a harmonised standard and gives no presumption of conformity under the AI Act. Practitioner guidance says to inventory AI systems (including MCP servers and API keys), assign owners, set access controls, and require review evidence before merge. — [Codacy](https://blog.codacy.com/iso-42001-what-engineering-leaders-need-to-know-about-the-ai-management-system-standard); [Modulos](https://www.modulos.ai/iso-42001-vs-nist-ai-rmf.html) (vendor, secondary)
- Company AI usage policies requiring human review before merge, and agent identity in audit logs: not found in this pass beyond the practitioner guidance above. — Gap.
- The factory's own repo rules: `harness/swe-agent` is marked `requires_human_supervision: true`, and its GitHub App token limits writes to one repo (per the project CLAUDE.md). These are internal facts, not external sources.

### Inferences
- Implication for factory architecture: Keep a human approval step before merge for every agent-authored PR. This is also the simplest answer to human-oversight expectations, even if the AI Act does not apply yet.
- Implication for factory architecture: Give each agent its own identity (the GitHub App bot, plus a run ID in the commit trailer or PR body). Audit logs then show which agent acted and which run it belonged to.
- Implication for factory architecture: Track the EU AI Act dates, but do not design around them yet. The factory's risk tier depends on its use, which is outside the coding task itself.

### Gaps
- Primary text of Regulation (EU) 2026/1744: not fetched.
- Clause-level ISO/IEC 42001 requirements: paywalled, not reviewed.

## The review bottleneck

### Takeaway
Several 2026 studies, mostly secondary, report that agent output rises much faster than review capacity and that review time rises. One study finds the trend reverses under different analysis choices. Mitigations in the sources are mostly process ones: smaller PRs, automated gates, and reviewer capacity planning.

### Cited Findings
- Harvard working paper (Chen and Stratton): review time per PR up 49% after agent adoption; the paper calls code review the bottleneck. — [FourWeekMBA](https://fourweekmba.com/ai-coding-agents-add-30-more-code-not-more-finished-work/) (secondary)
- A Carnegie Mellon and Stanford study of 802 developers and about 200,000 PRs (data through April 2026) reports PR volume up 3.1x while reviewers grew 1.5x; AI PRs took about 20% longer from first review to merge. No primary URL retrieved. — Not found (UNVERIFIED).
- AI-assisted PRs are about 18.2% larger (Jellyfish data, cited by Unblocked). — [Unblocked](https://getunblocked.com/blog/cost-per-merged-pr/index.md) (secondary)
- Counter-evidence: arXiv 2607.07980 finds the no-review rate for agent PRs falls toward the human rate by early 2026. — [arXiv 2607.07980](https://www.alphaxiv.org/abs/2607.07980.md)
- Vendor argument that code review is ending as a model (Semgrep): a vendor position, not evidence. — [Semgrep](https://semgrep.dev/blog/2026/end-is-nigh-for-code-review)
- The "61% of agent PRs get no review" figure: source could not be confirmed. Do not use. — Not found.

### Inferences
- Implication for factory architecture: Cap PR size at the gate, not at the reviewer. A stage that splits or rejects large diffs before review protects the reviewer queue.
- Implication for factory architecture: Put automated checks (tests, gate, security scan) before the human step, so the human reviews only what the gate passes. Measure reviewer minutes per merged PR to see whether the bottleneck is shifting.
- Implication for factory architecture: Plan reviewer capacity. If PR volume triples and reviewers grow 1.5x, merge time grows even if quality holds.

### Gaps
- Primary papers (Harvard, NBER 35275, CMU/Stanford) not fetched; all figures are secondary.
- Evidence on which mitigations (merge queues, review bots, stacked PRs) actually reduce review time: not found.
