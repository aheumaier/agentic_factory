# Feature Specification: Code Index

**Feature Branch**: `021-code-index`
**Created**: 2026-10-17
**Status**: Draft
**Input**: User description:

> One code index per target-repo commit, built by a Temporal activity before the first stage that reads the repo,
> cached by commit, run outside the E2B sandbox, served over HTTP MCP. Tools:
> - search_code (Zoekt exact/regex)
> - find_symbol, find_references (SCIP; ctags fallback)
> - repo_map(paths, budget), seeded from tasks.md paths, default ~1k tokens
>
> Wiring: architect candidates + pm review_spec first (they run on the worker host and can reach a local service).
> swe-agent second: E2B runs in the cloud and cannot reach docker-compose on this host, so it needs an authenticated
> endpoint (how: left to plan). Explicit tool lists add mcp__<server>__<tool>. Grep/Glob/Read stay.
>
> Rules: never build inside a tool call (MCP_TIMEOUT 30 s); a missing index leaves today's tools and the run goes on;
> no embeddings; no generated CLAUDE.md or overview; no prompt text added (019's lessons keep the prompt start;
> repo_map is a tool only). Spikes first: SDK LSP tool on 0.2.152/0.2.165; align the 3 SDK locks, pin the sandbox
> install. Measure on 5-10 tasks: turns to first correct edit, tokens (018 record), gate pass rate, localization.
> Out: semantic search, lesson search (019), sparse clones, the GitHub-comment path.

The input above is kept as written. It was approved by the operator on 2026-10-17. Two facts found while writing this
spec differ from it:

- "The 3 SDK locks" are, on 2026-10-17, five lock files at three versions: `claude-agent-sdk` 0.2.152 in
  `orchestration/uv.lock` (which also runs the architect stage), `harness/architect-agent/uv.lock` and
  `harness/pm-agent/uv.lock`; 0.2.165 in `harness/swe-agent/uv.lock`; and 0.2.150 in `harness/template-agent/uv.lock`.
  Two images install the SDK with no exact version: `sandbox/swe-agent/Dockerfile:27` (`>=0.2.152`) and
  `sandbox/Dockerfile:6` (no version). FR-003 names the ones this feature aligns.
- `review_spec()` in `harness/pm-agent/` has no Temporal caller today (its `SKILL.md`). So in a pipeline run the first
  stage that reads the repo is the architect stage. `review_spec()` gets the tools when it is called with an index;
  its place in a run waits for spec 005's PM stage.

## Why this feature exists

The agents have no shared knowledge of the code they change. Each stage clones the target repo on its own and searches
it with `Grep`, `Glob` and `Read` (and `Bash` in swe-agent). One run clones the repo up to four times:
`harness/swe-agent/agent.py:146`, `harness/architect-agent/agent.py:243`, `harness/pm-agent/agent.py:273` and the
Eval-Gate in `orchestration/activities.py:344`. No agent sets `mcp_servers`, and `docker-compose.yml` has no search
service. The architect's candidates run in parallel and each one explores the repo from zero.

The research behind this feature is `docs/research/reports/Codebase knowledge index and search for agents.md`
(2026-10-17), with its notes in `docs/research/research_notes/Codebase knowledge index and search for agents/`. It
finds:

- Grep is a strong default, and Anthropic's own guidance adds symbol search (LSP) for large repos, because a common
  function name returns thousands of grep matches.
- A structural index helps most on changes that touch three or more files: 91.3% with an index and 44.9% without one,
  in one study (Code Isn't Memory, arXiv 2606.22417).
- A short map of the code around the task (about 1k tokens, as in Aider) helps; a generated overview file
  (CLAUDE.md or a repo summary) cost 20% more and did not help (ETH, arXiv 2602.11988).
- The index must live outside the sandbox. The swe-agent sandbox has 1,024 MB of memory
  (`sandbox/swe-agent/e2b.toml`), and a later narrow clone would make in-sandbox search incomplete.

The report replaces rows 7, 8 and 11 of the earlier report,
`docs/research/reports/Agent memory and large codebase context.md`. This feature builds it: one index per commit,
shared by every stage, with three kinds of tool, and a measurement that decides whether each tool stays.

This feature indexes code only. It does not index or search lessons; lessons are spec 019's, and 019 puts them near
the start of the prompt. This feature adds no prompt text, so it does not compete with 019 for that space.

In this spec, "FR" means functional requirement and "SC" means success criterion. "Operator" means the person who runs
the factory. "Index" means the searchable data built from one commit of one target repo. "Index tools" means
`search_code`, `find_symbol`, `find_references` and `repo_map`. "Stage" means one step of `AgentPipelineWorkflow`
that runs an agent (architect, Build, and later the PM stage).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The architect's candidates search one shared index (Priority: P1)

A product run on `aheumaier/demo-app` PR 42 reaches the architect stage. Before the candidates start, the run builds
the index for the branch's head commit, or finds it already built. Each of the three candidates can call
`search_code` and `repo_map` from that one index, next to its usual `Read`, `Grep` and `Glob`. A candidate that wants
every caller of `parse_config` calls `search_code` once instead of running several greps.

**Why this priority**: The candidates run on the worker host, so they can reach a service next to Temporal without new
network work. They are also the stage the earlier report called out (row 8): N candidates each exploring cold.

**Independent Test**: Run the architect stage on a disposable target repo with the index service up. Check that the
candidates' tool calls include index tools, that every candidate got answers from the same index (same commit), and
that the stage result is valid as before.

**Acceptance Scenarios**:

1. **Given** a run reaches the architect stage and no index exists for the head commit, **When** the stage starts,
   **Then** the index is built before the first candidate's first model call, and every candidate's index tools answer
   from that commit.
2. **Given** an index for that commit already exists, **When** the stage starts, **Then** it is reused and not built
   again.
3. **Given** a candidate calls `repo_map` with no paths, **When** the call returns, **Then** it holds a map of the
   whole repo within the default budget of about 1,000 tokens, and says it was not seeded.

---

### User Story 2 - A missing or failed index never stops a run (Priority: P1)

The index service is down, or building the index for a large commit fails. The run goes on with today's tools only,
and the run's record says the index was missing and why.

**Why this priority**: The index is a speed-up, not a gate. A run that works today must not fail because of it.

**Independent Test**: Stop the index service and run the architect stage. It finishes as it does today, and the record
names the missing index.

**Acceptance Scenarios**:

1. **Given** the index service cannot be reached, **When** a stage starts, **Then** the stage starts without the index
   tools, and the run's record says "index missing" with the reason.
2. **Given** an index build runs past its time limit (FR-011), **When** the limit is reached, **Then** the build is
   stopped, the stage starts without the index tools, and the next stage on the same commit may try again.
3. **Given** the service fails in the middle of a stage, **When** an agent calls an index tool, **Then** the tool
   returns a short error the agent can read, within the tool timeout, and the agent can go on with `Grep`.

---

### User Story 3 - An agent finds a definition and its callers (Priority: P2)

A candidate needs the definition of `Settings` and every place that uses it. It calls `find_symbol("Settings")` and
`find_references` on the result, and gets file paths and line numbers instead of hundreds of text matches.

**Why this priority**: Symbol lookup is what the study above measured on multi-file changes. It needs a language
indexer per language, so it comes after exact search.

**Independent Test**: Index a repo in a language with a symbol indexer, call both tools for a known symbol, and compare
the answer with the definitions and references found by hand.

**Acceptance Scenarios**:

1. **Given** a repo in a language with a precise symbol indexer, **When** an agent calls `find_symbol`, **Then** it gets
   each definition's path, line and kind, marked "precise".
2. **Given** a repo in a language with no precise indexer, **When** an agent calls `find_symbol`, **Then** it gets
   tag-based results marked "approximate", or a clear "not supported for this language".
3. **Given** a symbol with more references than the result limit, **When** an agent calls `find_references`,
   **Then** it gets the first results up to the limit, the total count, and a note that the list was cut.

---

### User Story 4 - swe-agent in the sandbox uses the same index (Priority: P2)

Build runs swe-agent in an E2B sandbox in the cloud. The sandbox reaches the index for its run's commit through an
authenticated endpoint, and gets the same index tools, seeded by the paths in `tasks.md`.

**Why this priority**: Build is where most turns and tokens are spent, but the sandbox cannot reach a service on the
operator's host. It needs an endpoint and a credential, so it comes second.

**Independent Test**: Run Build on a disposable repo. Check that the sandbox's index calls succeed, that they carry a
credential that only opens this repo's index, and that a call with no credential or another repo's name is refused.

**Acceptance Scenarios**:

1. **Given** a Build attempt starts, **When** swe-agent runs, **Then** it can call the index tools for its repo, and a
   `repo_map` call with no paths is seeded from the paths named in the open tasks of `tasks.md`.
2. **Given** a sandbox holds the index credential for repo A, **When** it asks for repo B's index, **Then** the call is
   refused.
3. **Given** swe-agent has edited files that are not committed, **When** it calls `search_code`, **Then** the answer is
   from the indexed commit and says which commit, so the agent knows to `Grep` or `Read` its own edits.

---

### User Story 5 - Each tool stays only if it pays off (Priority: P3)

The operator runs 5 to 10 real tasks with today's tools, then with each index tool added in turn. They keep a tool
only if it lowers turns or tokens without lowering the gate pass rate.

**Why this priority**: The evidence comes from other setups. This pipeline has to show the gain on its own tasks.

**Independent Test**: Run the measurement (FR-022) and read its table.

**Acceptance Scenarios**:

1. **Given** the measurement has run, **When** the operator reads it, **Then** each tool has its turns to first correct
   edit, tokens per task, gate pass rate and localization hit rate, next to the baseline.
2. **Given** a tool did not lower turns or tokens, or lowered the gate pass rate, **When** the result is recorded,
   **Then** that tool is turned off by its setting and the reason is written down.

---

### Edge Cases

- **The commit moves inside a run.** The architect stage pushes a plan commit, and Build commits a `checkpoint:` each
  time a task is ticked (spec 011). Each stage uses the index of the commit it starts from. Build uses the commit after
  the architect's push, so `tasks.md` is in the index it seeds from. A later Build attempt or a successor seat
  (spec 009) uses the head commit at its own start; when that commit is not yet indexed, the old index is used and its
  commit is named, while the new one builds.
- **The agent's own edits are never in the index.** That is why `Grep`, `Glob` and `Read` stay, and why every answer
  names its commit (FR-014).
- **Several runs on the same commit at once.** One build runs; the others wait for it or use its result. No commit is
  built twice at the same time.
- **A huge repo.** A first build of a repo of several million lines may take minutes. It never runs inside a tool call
  (FR-010). When it does not finish in time, the stage runs without the index (US2).
- **Generated, vendored or binary files.** They are left out of the index by the repo's own ignore rules and a size
  limit per file, so search answers are not filled with them.
- **A private target repo.** Index data holds the repo's code. It is kept only on the factory's own storage, with the
  same access as the clones are today, and removed after its retention time (FR-020).
- **The SDK hides MCP tools behind its tool search.** If the pinned SDK defers MCP tools until the model searches for
  them, the agent may not see the index tools. The plan checks this in spike 1 and makes sure they are offered.
- **A tool answer that is too long.** Every tool has a size limit. A cut answer says so and how many results there were.

## Requirements *(mandatory)*

### Functional Requirements

**Spikes before the build**

- **FR-001**: Before the symbol tools are designed, the plan MUST record whether the Claude Agent SDK's `LSP` tool works
  in a headless `query()` call on 0.2.152 and on 0.2.165, with a small test repo. If it works, the plan MUST say whether
  `find_symbol` and `find_references` are still needed (for example because a language server needs the full repo and
  memory the sandbox does not have) or are dropped.
- **FR-002**: The same spike MUST record how each pinned SDK version handles `mcp_servers` over HTTP: whether the tools
  are offered at once or only through tool search, and how the tool timeout is set.
- **FR-003**: Before any agent is wired to the index, the SDK version MUST be the same in `orchestration/uv.lock`,
  `harness/architect-agent/uv.lock`, `harness/pm-agent/uv.lock` and `harness/swe-agent/uv.lock`, and
  `sandbox/swe-agent/Dockerfile` MUST install that exact version. `harness/template-agent/` (a stub) and
  `sandbox/Dockerfile` (the template agent's image) are out of scope; the plan says if they follow.

**The index**

- **FR-004**: The factory MUST build one index per target repo and commit, and MUST reuse an index that already exists
  for that commit.
- **FR-005**: An index MUST hold exact and regular-expression text search over every indexed file of that commit.
- **FR-006**: An index MUST hold symbol definitions and references. They MUST come from a precise language indexer
  where one exists for the language, and from tag-based symbols where none does. Each result MUST say which ("precise"
  or "approximate").
- **FR-007**: An index MUST be able to answer a ranked map of files and their main symbols, starting from a set of seed
  paths.
- **FR-008**: The index MUST NOT use embeddings or semantic search, and the factory MUST NOT generate a CLAUDE.md, a
  repo overview or any other summary file from it. Any per-module summary added later MUST be tied to a commit and off
  by default.
- **FR-009**: The index MUST leave out files the target repo ignores, files over a size limit, and binary files. The
  limit is a setting.

**Building it**

- **FR-010**: The index MUST be built by a step of the run before the stage that first needs it, never inside an agent's
  tool call.
- **FR-011**: A build MUST have a time limit, a setting with a default of 15 minutes. A build past the limit MUST be
  stopped, and the stage MUST start without the index.
- **FR-012**: A build MUST read the target repo with read-only access to that repo only, and MUST NOT need any model
  call.
- **FR-013**: Two builds of the same repo and commit MUST NOT run at the same time.

**The tools**

- **FR-014**: The index MUST be offered to agents over MCP as four tools: `search_code(query, path filter)`,
  `find_symbol(name)`, `find_references(symbol)` and `repo_map(paths, budget)`. Every answer MUST name the repo and the
  commit it comes from.
- **FR-015**: Every tool MUST answer within 5 seconds for 95% of calls, well inside the 30-second MCP tool timeout. A
  tool that cannot answer MUST return a short error the agent can read, not hang.
- **FR-016**: Every answer MUST be size-limited. `search_code` and `find_references` MUST return at most a set number of
  results (default 50) with the total count. `repo_map` MUST stay within its `budget` in tokens, with a default of
  1,000 and a maximum of 4,000. A cut answer MUST say it was cut.
- **FR-017**: When `repo_map` is called with no paths in Build, it MUST be seeded from the file paths named in the open
  tasks of the branch's `tasks.md`. In other stages, and when `tasks.md` names no paths, it MUST map the whole repo
  and say it was not seeded.

**Wiring**

- **FR-018**: The index tools MUST be added to the architect candidates, to `review_spec()` and to swe-agent, by name
  (`mcp__<server>__<tool>`) in each agent's tool list. They MUST be added next to the tools each agent has today,
  never instead of them: `Read`, `Grep` and `Glob` stay for every agent, and swe-agent keeps `Bash`, `Edit` and
  `Write`. The architect's judge, synthesis and critic calls stay without tools.
- **FR-019**: This feature MUST NOT add text to any agent prompt. Tool names and tool descriptions are the only way the
  agents learn of the index.
- **FR-020**: An agent in a run MUST be able to reach only the index of its own run's target repo. For swe-agent in the
  sandbox, the endpoint MUST need a credential that is minted for that run and repo, expires within the Build time
  limit, and never appears in Temporal history, logs or the agent's prompt (as with spec 013's token). Index data MUST
  be removed after a retention time, a setting with a default of 14 days since last use.
- **FR-021**: When no index is ready for a stage, the stage MUST start without the index tools, and the run MUST go on.
  The run's record (spec 018's ledger, once it exists) MUST say "index used", "index missing" or "index stale" for
  each stage, with the commit and, when missing, the reason.

**Measurement**

- **FR-022**: The feature MUST ship with a repeatable measurement. It runs 5 to 10 real tasks on a large target repo,
  at least half touching three or more files, first with today's tools, then adding `search_code`, then the symbol
  tools, then `repo_map`. For each run it records turns to the first correct edit, tokens per task (from spec 018's
  record), the gate pass rate and the localization hit rate (defined in Key Entities).
- **FR-023**: Each index tool MUST have a setting that turns it off. A tool that does not lower the median turns or tokens by at
  least 20% (the keep threshold, a setting), or that lowers the gate pass rate, in the measurement MUST be turned off
  by default, with the reason written in the spec
  directory.

**Out of scope**

- **FR-024**: This feature MUST NOT add semantic or embedding search, search over lessons (spec 019), narrow or sparse
  clones, or index tools on the GitHub-comment path (`.github/workflows/swe-agent-build.yml`).

### Key Entities

- **Index**: the searchable data for one target repo at one commit. Holds text search data, symbols and the data for
  the map. Keyed by repo and commit; has a built time, a last-used time and a state (building, ready, failed).
- **Index build**: one step of a run that makes an index ready. Has the repo, the commit, a start and end time, and an
  outcome (built, reused, timed out, failed with reason).
- **Index credential**: a short-lived secret that opens one repo's index for one run. Minted per sandbox, never stored
  in Temporal.
- **Index use record**: per stage, whether the index was used, missing or stale, and its commit. Part of the run's
  record.
- **Measurement run**: one task run under one tool set. Holds turns to the first correct edit, tokens, the gate result
  and the localization hit rate.
  - *Turns to the first correct edit*: the model turns before the agent first edits a file that the final diff keeps.
    Lower is better.
  - *Localization hit rate*: the share of files in the final diff that the agent opened or got in a tool answer before
    its first edit. Higher is better.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In the architect stage, every candidate of a run gets index answers from the same commit, in 10 of 10
  test runs.
- **SC-002**: With the index service stopped, 10 of 10 test runs end the same way they end today, and each run's record
  says "index missing".
- **SC-003**: For a target repo of at least 1 million lines, a first index build finishes within 15 minutes on the
  worker host, and a build for a commit that changes fewer than 100 files over an indexed parent finishes within
  2 minutes.
- **SC-004**: 95% of index tool calls in the measurement answer within 5 seconds; none hits the 30-second tool timeout.
- **SC-005**: No tool answer in the measurement is longer than its limit (FR-016).
- **SC-006**: A sandbox call with no credential, an expired credential, or another repo's name is refused in 3 of 3
  tests.
- **SC-007**: The measurement table exists in the spec directory with all four numbers for the baseline and each tool
  set, and each tool is marked kept or turned off with its reason.
- **SC-008**: At least one index tool lowers the median turns to the first correct edit, or the median tokens per task,
  by 20% or more on the multi-file tasks, without lowering the gate pass rate. If none does, the feature still ships
  with the tools turned off, and the result is reported, not hidden.
- **SC-009**: No agent prompt text changes in this feature (checked in the diff), and the repo has no generated
  overview file after it.

## Assumptions

- **Building blocks.** The input names Zoekt for text search, SCIP for precise symbols and ctags as the fallback. They
  are the report's picks and are kept as the default. The plan may swap one for an equal tool (for example Serena or
  an LSP bridge for symbols, per FR-001) and must say why, per `agent-factory-architecture.md`.
- **Where it runs.** The index service runs next to Temporal, Langfuse and LiteLLM, started with `make up`. How the
  cloud sandbox reaches it (a tunnel, a hosted endpoint or other) is left to the plan, as the input says.
- **Which commit.** Each stage uses the index of the commit it starts from (see Edge Cases). The default is to build the
  architect's pushed commit before Build starts, so `tasks.md` is searchable.
- **Time limits.** The 15-minute build limit, the 5-second answer target, the 50-result limit, the 1,000/4,000-token map
  budget and the 14-day retention are defaults from the report and common practice. They are settings.
- **Depends on.** Spec 018 for tokens per stage and the run record (FR-021, FR-022). Until 018 ships, the measurement
  reads tokens from each session's own usage report. Spec 013's per-sandbox token pattern for the credential. Spec 019
  only for the rule that lessons own the prompt start. Spec 005's PM stage before `review_spec()` is used inside a run.
- **Changes to other specs.** None. Spec 018 gets a new field (index use per stage) only if its owner agrees; otherwise
  this feature keeps its own record and links it by run ID.
- **Research files.** The report and its notes are untracked on main on 2026-10-17. This branch carries them so the
  paths above resolve.
