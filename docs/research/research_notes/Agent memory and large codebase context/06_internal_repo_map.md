# Internal repo map: memory, learning and context handling

Written 2026-10-17 from a read-only sweep of this repo (one Explore subagent), with
the claims marked "Checked by hand" re-read in the code and corrected where marked. Citations are `path:line`
as of commit `704ed29`.

### Takeaway

The pipeline learns only inside one run. A failed Eval-Gate sends one line of text
into the next Build attempt (at most `MAX_BUILD_ATTEMPTS=3`). Nothing carries over
to the next run: no memory files, no learned rules, no dataset built from traces.
Each agent session starts empty. The sandbox clones the whole repo with full history
and has no code index, so code search is Bash, Grep and Glob over a full working tree.

## 1. swe-agent context assembly

### Cited Findings
- The prompt is inline: `IMPLEMENT_PROMPT` at `harness/swe-agent/agent.py:38` and
  `FEEDBACK_PROMPT_SUFFIX` at `harness/swe-agent/agent.py:73`.
- **Checked by hand:** no code loads `prompts/agentic-swe.json`. Only docs, specs,
  `SKILL.md` and the registry manifest mention it. CLAUDE.md calls it "the
  system-prompt-as-data for the SWE agent". In practice it is a design artifact that
  nothing runs.
- Tools: `allowed_tools=["Bash", "Read", "Edit", "Write", "Grep", "Glob"]`,
  `permission_mode="bypassPermissions"` (`harness/swe-agent/agent.py:320-321`).
- `setting_sources` stays at its default on purpose, so user, project and local
  settings load. That is what lets the CLI find `/speckit-implement`
  (`harness/swe-agent/agent.py:325-336`).
- One model session per open task (specs/011 F7-a). Each task session starts empty
  and resumes from checkpoint commits, not from conversation memory.
- No `max_turns` is set. Sessions end when the work is done, the seat runs out, or
  the sandbox times out.

### Inferences
- Because project settings load, a `CLAUDE.md` or `AGENTS.md` in the target repo is
  probably the one context channel that already survives from run to run. Whether
  the Agent SDK puts the target repo's `CLAUDE.md` into context with this
  configuration is **not verified**. Check it in one live run before you build on it.

## 2. pm-agent and architect-agent context

### Cited Findings
- `shape_issue()` binds no tools and calls Anthropic directly
  (`harness/pm-agent/agent.py:202-206`).
- `review_spec()` binds `Read`/`Grep`/`Glob` with `setting_sources=[]`, so no project
  memory loads. It routes through LiteLLM (`harness/pm-agent/agent.py:294-305`).
- Each architect candidate gets `Read`/`Grep`/`Glob` with `setting_sources=[]`, and no
  candidate sees another (`harness/architect-agent/agent.py:313-355`). The judge,
  synthesis and critic each run as a separate call with no tools. The prompts for
  scoring, synthesis and the critic are inline (`harness/architect-agent/agent.py:457-525`).
- Each candidate has a 600-second limit (`harness/architect-agent/agent.py:75`).

## 3. How gate feedback reaches the next Build attempt

### Cited Findings
- `feedback = f"Eval-Gate failed (attempt {attempt}): {eval_result['reason']}"`
  (`orchestration/workflows/pipeline_workflow.py:355`).
- The text is appended to the prompt when it is set (`harness/swe-agent/agent.py:354`).
- The reason is one of: no `specs/*/spec.md` found, `sandbox exit_code=<N>`, no
  `pr_url` in the sandbox trace, or coverage passed (the gate is in
  `eval/braintrust/eval.config.py`).
- The plan loop has its own feedback channel: the `plan_rejected(feedback)` signal
  feeds `plan_feedback` (`orchestration/workflows/pipeline_workflow.py:97-99, 234-317`).

### Corrections
- The subagent said feedback piles up across retries. **That is wrong.** Line 355
  replaces `feedback` each time, so the next attempt sees only the latest failure,
  not earlier ones. The real gap is the opposite: attempt 3 does not learn what went
  wrong in attempt 1.

### Gaps
- Feedback is a single reason string. It carries no failing test names, no diff and
  no per-criterion result.

## 4. What survives a run

### Cited Findings
- `docs/70-multi-agent-pipeline-design.md` §6.1 (about lines 600-651): every activity
  gets "its own fresh, memoryless Claude Agent SDK context". Only git commits, PR
  comments and Braintrust spans cross a stage boundary. The PR thread is the
  hand-off.
- All three agents log to Braintrust (`braintrust.init_logger` + `auto_instrument`)
  under one project, `BRAINTRUST_PROJECT` (default `agent-factory-pilot`)
  (`harness/swe-agent/agent.py:35-36`, `harness/pm-agent/agent.py:29-30`,
  `harness/architect-agent/agent.py:48-49`). The gate logs an `eval_gate` span
  (`eval/braintrust/eval.config.py:85-88`).
- No code reads those traces back. Nothing builds a dataset from them, and no agent
  queries them.
- Langfuse appears in `docker-compose.yml`, `.env.example`, the README and the
  quickstarts for specs 004 and 008. No Python code sends traces to it.

## 5. Sandbox: clone and tooling

### Cited Findings
- **Checked by hand (corrects an earlier draft):** inside the sandbox, swe-agent runs a
  plain `git clone <url>` with full history, then `git fetch origin <branch>` and
  `git checkout <branch>` (`harness/swe-agent/agent.py:129-155`, clone at `:146`). It is
  not shallow, not partial (no `--filter`), and the working tree is full (no sparse
  checkout).
- The shallow `git clone --depth 1 --branch` at `orchestration/activities.py:344` is
  the Eval-Gate's own read-only clone on the worker host, used only to find
  `specs/*/spec.md`.
- Template `swe-agent-sandbox` (`orchestration/activities.py:36`): 2 vCPU and
  1024 MB (`sandbox/swe-agent/e2b.toml:9-10`). The command limit is 3300 s and the
  sandbox limit is 3500 s (`orchestration/activities.py:41-42`).
- The image has git, curl, jq, gh, uv, the Agent SDK and Braintrust on
  python:3.11-slim (`sandbox/swe-agent/Dockerfile`). It has no ctags, no tree-sitter
  repo map, no LSP server and no search index.
- **Checked by hand:** the architect stage clones too, outside any sandbox (the §6.1
  carve-out). `_clone_spec_branch` runs `git clone --depth 1 --branch` into a temp dir
  on the worker host (`harness/architect-agent/agent.py:243`, temp dir at `:896`). All
  N candidates then search that one full tree with `Read`/`Grep`/`Glob`, in parallel,
  600 s each. On a 4M-LOC repo that is N concurrent greps on the worker host.

### Inferences
- On a 4M-LOC repo, a full-history, full-tree clone into a 1 GB sandbox and grep-only
  search are where things break first: clone time, disk and memory, and grep output
  flooding the context. See note 04.
- swe-agent does get full history, so `git log` and `git blame` work for it. The
  architect candidates get `--depth 1` and cannot use history.

## 6. Context budget

### Cited Findings
- `CTX_BUDGET=150000` / `CTX_WARN=120000` (`.claude/hooks/lib.sh:11-12`) cover only
  the **developer** Claude Code session working on this repo (feature 010).
- No agent inside the sandbox has a token budget, clears its context, or tracks how
  full its context is. Only the seat guard, which watches usage limits, and the
  sandbox timeout stop a session.

### Gaps
- The pipeline records no tokens, cost or context use per run, so context rot can't
  be measured today.

## 7. What the design docs say

### Cited Findings
- docs/70 §6.1 is the only statement on memory. It makes fresh context the rule.
- Neither `agent-factory-architecture.md` §3 nor any spec under `specs/` designs
  memory across runs. The existing research report's gap row 10 (in
  `docs/research/reports/Agent native software factory architecture.md`) is the only
  proposal for one.

### Inferences
- Fresh context is the right default for reproducible runs and safe hand-offs.
  Learning should be added outside the session, as reviewed files in the repo, not
  as hidden state inside it.
