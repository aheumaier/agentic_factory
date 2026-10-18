# Give the agents a code index service, starting with exact search, symbols and a task-seeded map

*Research report, written 2026-10-17. Sources were accessed 2026-10-17. It is based on the 6 research
notes in `docs/research/research_notes/Codebase knowledge index and search for agents/`. Repo citations
are `path:line` as of commit `704ed29` and come from note 06 unless marked otherwise. A source marked
(secondary) was not read at its origin. A claim marked (UNVERIFIED) has no source we could open.*

Today every agent in this pipeline starts from a fresh clone and knows nothing about the code until it
greps for it. On a 4M-line target repo that means each agent, on each run, rebuilds the same picture
from scratch, and does it up to four times per run (note 06 §4). The evidence does not say "replace grep".
It says grep is a strong baseline, and that an index helps most where grep is weakest: finding all the
files a multi-file change touches, and following a symbol to its real definition and callers. So the
recommendation is a small **code index service**, built once per target-repo commit outside the
sandbox and offered to the agents over MCP. Start it with three tools: exact search (Zoekt), symbol
lookup (definitions and references), and a repo map ranked from the file paths in `tasks.md`. Do not
start with embeddings, and do not auto-generate a CLAUDE.md or repository overview: the one controlled
study of generated context files found they cost more and did not help. Measure each tool on 5–10 real
tasks before adding the next.

## What the evidence says

The evidence is mixed. It does not support a single "best" design, and the numbers below come from
different tasks with different baselines. Each group below says what it shows and what it does not.

### Anthropic and harness studies: grep is a strong default

- Claude Code dropped its vector index. Boris Cherny (Claude Code lead), on X in January 2026: "Early
  versions of Claude Code used RAG + a local vector db, but we found pretty quickly that agentic search
  generally works better. It is also simpler and doesn't have the same issues around security,
  privacy, staleness, and reliability." (Found and quoted by a fact-check subagent; I did not open the
  post myself.)
- Anthropic's context-engineering guidance: "Start with agentic search, and only add semantic search
  if you need faster results or more variations." The same guidance recommends LSP so the agent can
  search by symbol: grep for a common function name "returns thousands of matches, while LSP returns
  only the references that point to the same symbol."
- "Is Grep All You Need?" (arXiv 2605.15184) found grep-style search beat vector retrieval for agents,
  and that the result depended strongly on the harness, meaning how the tools are offered and
  sequenced.
- GrepRAG: an LLM writing ripgrep commands matched graph-based baselines on CrossCodeEval and improved
  exact match by 7.04–15.58% relative to the best baselines.

**What this shows:** plain search tools, used well, are hard to beat, and vector search is not the
first thing to add. **What it does not show:** that grep alone is enough at 4M lines. Anthropic
publishes no line-count threshold, and the "LSP matters beyond 1M lines" rule of thumb in note 01 is
UNVERIFIED.

### Academic studies: an index helps on multi-file and large-repo tasks

- **Code Isn't Memory** (arXiv 2606.22417): localization accuracy on changes that touch 3 or more files
  was 91.3% with a structural index and 44.9% without it. This is the strongest result in favour of an
  index, and it is exactly the case a large repo produces.
- **Codebase-Memory** (arXiv 2603.27277, abstract checked): across 31 repos, its tree-sitter index
  scored 83% answer quality against 92% for an agent exploring files, with 10x fewer tokens and 2.1x
  fewer tool calls. It indexed the Linux kernel (28M lines) in about 3 minutes. So: much cheaper, but
  less accurate.
- **RepoMod-Bench** (21 repos, 1.6M lines, 8 languages; I opened it): pass rate falls from 91.3% on
  repos under 10K lines to 66.9% at 10K–50K and 15.3% above 50K. It tests no search method, so it
  shows the problem, not a fix.
- **LoLBench** (100 tasks on 29 systems averaging 2.4M lines): giving the agent the file tree and API
  spec raised resolution by 16–22 points; incomplete localization was the main bottleneck.
- **LocAgent** reached 92.7% file-level accuracy with a code graph, but on a fine-tuned Qwen-32B, not
  Claude. **RepoGraph** lifted Agentless from 27.33% to 29.67%: a small gain.
- **ETH Zurich, context files** (arXiv 2602.11988; I opened the HTML). With Sonnet-4.5 and no context
  file the baselines were 59.9% (SWE-bench Lite) and 40.7% (CTXbench, 138 instances, 12 repos).
  - LLM-generated context files changed success by −0.5% and −2% (p = 87% and 37%, so no real effect),
    added 2.45 and 3.92 steps, and raised cost by 20% and 23% (p < 0.001%).
  - Developer-written files raised success by 2.4% (p = 21%, not significant), added 3.34 steps and
    raised cost by up to 19%.
  - The authors state that "repository overviews… are not helpful" and that "Neither context file
    length nor specific instruction categories have a strong effect on performance". The files
    averaged 641 words.

**What this shows:** structure helps most on multi-file changes, success collapses with repo size, and
a generated overview is cost without benefit. **What it does not show:** a controlled test of Zoekt,
LSP or a repo map inside a Claude Agent SDK harness. No study ran this repo's setup.

### Vendors: everyone builds an index, but the numbers are not comparable

- **Snap** runs Zoekt over "millions of files and close to a terabyte of source" and exposes it to
  agents over MCP.
- **JetBrains** (vendor, best case, no method published): "up to 68% fewer agent turns, 59% lower
  latency, and 48% lower cost" on "thousands of benchmark tasks". Their blog returns 403 to fetches;
  a subagent quoted it.
- **Cursor**: 12.5% average accuracy gain from its trained embeddings on its own Context Bench (range
  6.5–23.5% across models); the baseline is not stated.
- **GitHub Copilot**: its coding agent with a semantic search tool took "2% less time without any
  change in quality" compared with the agent without the tool.
- **Windsurf SWE-grep** uses only grep, read and glob, with an RL-trained model making parallel calls;
  "20x faster", baseline unclear. **Windsurf Codemaps** is acknowledged as unbenchmarked.
- **Sourcegraph Deep Search** runs an agent loop over its code search and code navigation tools
  (enterprise plans only). **Augment** claims 400,000+ files under 200 ms (secondary, vendor only).

**What this shows:** at large scale, every serious vendor adds a search or symbol service beside the
agent, and MCP is the common interface. **What it does not show:** which part of the service earns
the gain. Baselines differ, and most figures are vendor best cases.

### Buildable tooling: the pieces exist and are open source

- **Zoekt** (Go, Apache 2.0): trigram index for substring and regex search. It re-indexes per repo and
  replaces index shards. Its index size is not published (the 3–5x of source text figure is
  livegrep's).
- **SCIP**: a language-neutral symbol index format, 4x smaller than LSIF (gzipped) and 3x faster to
  process. Indexers exist for TypeScript, Java/Scala/Kotlin and Python; scip-python is incomplete.
  An MCP server would have to wrap it.
- **Serena**: an LSP-backed MCP server for 40+ languages. LSP-MCP bridge servers also exist
  (secondary).
- **Universal Ctags**: fast, simple symbol tags, a fallback where no SCIP indexer or language server
  fits.
- **Aider's repo map**: a ranked list of the most relevant files and symbols with a default budget of
  "1k tokens". Aider scored 26.3% on SWE-bench Lite, but that is the whole tool, not the map alone.
- **Embeddings, if ever needed** (my estimate, not a measurement): 4M lines ≈ 40M tokens ≈ 80K chunks
  ≈ 0.3 GB of vectors and about 15 minutes to embed.

**What this shows:** nothing here needs to be invented. **What it does not show:** index size and
build time for a 4M-line repo in this setup. Those have to be measured.

## The index must be remote

The earlier report, `Agent memory and large codebase context`, suggested a partial or sparse clone to
cut clone time (its gap row 7). That conflicts with its own advice to grep the whole repo: a sparse
checkout cannot be searched for files that were not checked out. A remote index resolves this. The
sandbox can keep a small checkout of the files it edits while the index answers questions about the
whole repo. A remote index also avoids the sandbox's 1024 MB memory limit
(`sandbox/swe-agent/e2b.toml:9-10`), which a local index of a 4M-line repo would compete for.

This report replaces three rows of the earlier report's gap table:

- **Row 7** (partial or sparse clone): only together with a remote index, never on its own.
- **Row 8** (the architect's N candidates each grepping on their own; a shared map): the shared map is
  the `repo_map` tool below, served to all candidates from one index.
- **Row 11** ("Start with a repo map or ctags… Add an LSP MCP server next. Add Zoekt or semantic search
  only if the numbers…"): the order changes. Exact search and symbols come first, together with the
  task-seeded map, because Code Isn't Memory and Snap point at search and structure, and ETH warns
  against overviews. Semantic search stays last.

## Where it plugs into this repo

- No agent sets `mcp_servers` or `agents` today, so the index is a new, additive option on
  `ClaudeAgentOptions`, not a change to an existing tool.
  - swe-agent: `allowed_tools=["Bash", "Read", "Edit", "Write", "Grep", "Glob"]`
    (`harness/swe-agent/agent.py:318-337`).
  - Architect candidates: an explicit `tools=["Read", "Grep", "Glob"]` with `setting_sources=[]`
    (`harness/architect-agent/agent.py:313-321`). The judge, synthesis and critic have no tools
    (`:136-141`).
  - pm `review_spec`: `tools=["Read", "Grep", "Glob"]` (`harness/pm-agent/agent.py:294-305`).
  - Agents with an explicit `tools` list must name the new MCP tools (`mcp__<server>__<tool>`);
    nothing reaches them by default.
- One run clones the target repo up to four times: swe-agent with full history
  (`harness/swe-agent/agent.py:146`), the architect (`harness/architect-agent/agent.py:243`) and pm
  (`harness/pm-agent/agent.py:273`) with `--depth 1`, and the Eval-Gate
  (`orchestration/activities.py:344`). One index per commit can serve all of them.
- swe-agent requires `specs/*/tasks.md` (`harness/swe-agent/agent.py:159`) and names it in each task
  prompt (`:61-68`). The paths in `tasks.md` are a ready seed for the repo map.
- The sweep found no egress restriction on the sandbox, so an HTTP MCP server it can reach would work.
  How the worker host reaches the service, and where index files live, were not checked.
- `docker-compose.yml` has no search service yet. The index service would be one more container next
  to Temporal, Langfuse and LiteLLM.
- MCP calls time out after 30 s by default (`MCP_TIMEOUT`), so slow first-time indexing must happen
  before the agent starts, not inside a tool call.

## Gap analysis

### What already matches

- Each agent already has a clean tool list, so adding MCP tools is a small, reviewable change.
- `tasks.md` already names the files a task touches, which is the seed a ranked map needs.
- The pipeline is a Temporal workflow, so "build the index for this commit" fits as one activity
  before Build, with retries and caching.

### What is missing

Rows that touch `harness/`, `orchestration/` or `eval/` need a new spec first: AF-SPEC blocks edits
there without a feature branch that has `specs/NNN-*/tasks.md`.

| # | Gap | Repo evidence | Outside evidence | Recommendation | Where it lands |
|---|---|---|---|---|---|
| 1 | No exact-search service; each agent greps its own clone | no `mcp_servers` in any agent; no search service in `docker-compose.yml` | Snap runs Zoekt over MCP at terabyte scale; grep is a strong baseline (GrepRAG, 2605.15184) | Run Zoekt per target-repo commit and expose `search_code` over HTTP MCP | New spec: `orchestration/` activity + docker-compose service + agent options |
| 2 | No symbol lookup; agents cannot follow a definition or its callers | no agent has a symbol tool; search is `Grep`/`Glob` (plus `Bash` in swe-agent) (note 06 §1) | Code Isn't Memory: 91.3% vs 44.9% on 3+ file changes; Anthropic recommends LSP for monorepos | Add `find_symbol` and `find_references` from SCIP where an indexer exists, ctags or Serena otherwise | Same new spec as row 1 |
| 3 | No shared, task-specific map; architect candidates each start cold | candidates run in parallel with no shared state (`harness/architect-agent/agent.py:313-321`) | Aider's ranked map in about 1k tokens; LoLBench +16–22 points from tree and API context | `repo_map(paths, budget)` seeded from the paths in `tasks.md` (`harness/swe-agent/agent.py:61-68`, `:159`) | Same new spec |
| 4 | Up to four clones per run, each searched separately | `harness/swe-agent/agent.py:146`, `harness/architect-agent/agent.py:243`, `harness/pm-agent/agent.py:273`, `orchestration/activities.py:344` | Codebase-Memory: 10x fewer tokens and 2.1x fewer tool calls with an index | Build the index once per commit, outside the sandbox, and reuse it across stages | Same new spec |
| 5 | `LSP` tool availability in the Agent SDK is unknown | locks pin 0.2.165 (swe-agent) and 0.2.152 (architect, pm); the sandbox image is unlocked (`sandbox/swe-agent/Dockerfile:27`) | Claude Code docs list LSP plugins for the terminal; SDK docs do not list the tool | Test the `LSP` tool on both pinned versions before choosing between it and an LSP-MCP bridge | Spike first; then the new spec |
| 6 | SDK behaviour for `mcp_servers` may differ across the pinned versions | two lock versions plus an unlocked sandbox install (note 06 §2) | MCP tool search is on by default in current SDK docs | Align the three locks and pin the sandbox install before wiring MCP | New spec (touches `harness/`; the Dockerfile is outside AF-SPEC) |
| 7 | No measurement of what any search tool buys | the Eval-Gate is a binary coverage check (`eval/braintrust/eval.config.py`, per `CLAUDE.md`) | vendor numbers use different baselines (Cursor, GitHub, JetBrains) | Run the measurement plan below before and after each tool | New spec (touches `eval/`) |
| 8 | Risk of adding a generated overview as "codebase knowledge" | none exists today | ETH: generated files −0.5% / −2%, cost +20% / +23% | Do not generate CLAUDE.md or repo overviews; keep any `module_summary` tied to a commit and off by default | Design rule in the new spec |

## Measurement plan

1. Pick 5–10 real tasks on a large target repo, with at least half touching 3 or more files.
2. Run each task with today's tools (the baseline), then with each new tool added one at a time:
   `search_code`, then symbols, then `repo_map`.
3. For each run, record:
   - **Turns to the first correct edit**: how many model turns before the agent edits a file the
     final diff keeps. Lower is better.
   - **Tokens per task**: input plus output, from the run's usage records. Lower is better at equal
     quality.
   - **Gate pass rate**: share of runs that pass the Eval-Gate. It must not drop.
   - **Localization hit rate**: share of files in the final diff that the agent opened before its
     first edit. Higher is better.
4. Keep a tool only if it lowers turns or tokens without lowering the gate pass rate. Five to ten
   tasks will not give statistical significance; treat the result as a direction, and rerun as tasks
   accumulate.

## Conclusion

The agents do not need a smarter grep. They need a shared memory of the repo's structure that outlives
a single clone. Build it as one service per target-repo commit, outside the sandbox, over MCP: exact
search, symbols, and a map seeded by `tasks.md`. Keep embeddings and generated overviews out until a
measurement says otherwise. The strongest single result (Code Isn't Memory, 91.3% vs 44.9%) is from
one paper on one setup, and the one cheap index that was measured head to head (Codebase-Memory) was
less accurate than plain exploration. So the service has to prove itself on this pipeline's own tasks
before it becomes the default.

*Method note: five haiku research subagents wrote notes 01–05 from web sources; note 06 came from a
haiku Explore sweep of this repo, with SDK versions and clone lines re-checked by hand. Four fact-check
subagents then checked the notes' key claims against their sources, and I corrected the notes before
writing this report. A backup of the uncorrected notes is in the session scratchpad.*

*Citation spot-check, 2026-10-17. I opened myself: the ETH paper's HTML (arXiv 2602.11988; all ETH
figures above) and RepoMod-Bench. The Codebase-Memory figures were checked against its arXiv abstract
(2603.27277) during the fact-check.
Quoted by subagents, not opened by me: the Cherny post on X, the JetBrains blog (returns 403), and the
"Is Grep All You Need?" abstract. Removed or corrected in the notes and not used here: a RepoMod-Bench "50K–100K, 35.5%" bucket the
paper does not have; "AGENTbench" and "+4%" for the ETH paper (the current text says CTXbench and
+2.4%); the "94.5% of RAG's
faithfulness" figure (content-farm sources, no study named); `claude-explorer` and
`.clausecodeignore` (no source found); a ContextBench "hotel-expense" line (not in the source); a
"2.5x" exploration figure (the paper says the `uv` tool was used 1.6 times per task when the context
file mentions it and under 0.01 times when it does not); a 48.8% multi-model ETH baseline that is not
in the paper (the Sonnet-4.5 baselines above replace it); derived tree-sitter speed estimates (benchmarks UNVERIFIED); and a "22 h / 80 GB"
embedding estimate, replaced by the estimate above. The "~400 lines" CLAUDE.md figure is secondary and
the "50–70%" figure is unsourced; neither is used here.*
