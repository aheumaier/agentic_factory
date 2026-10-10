# L / I — Orchestration patterns and artifact generation (research notes)

Researched 2026-10-09. Scope: research prompt §3 questions L.1–L.4 and I.1–I.2
(`docs/research/teams-workspace-research-prompt.md`). Format per prompt §4.1.
Labels: **DOC** = a primary source says it; **CODE** = read in source or verified by
running it; **INFER** = my reasoning. Where a page shows no last-updated date it is
marked "(accessed 2026-10-09)"; GitHub-hosted files carry their tag or commit date.
The Teams-SDK `PRE-GA` staleness rule doesn't apply here: none of these sources are
Teams/Bot Framework sources.

**Pinned versions (all checked 2026-10-09 against the registries):**

| Thing | Version | Date | Source |
|---|---|---|---|
| `temporalio` (Python SDK), latest | **1.34.0** (`requires_python >=3.10`) | 2026-09-30 | pypi.org/pypi/temporalio/json |
| `temporalio` in this repo | 1.32.0 (`orchestration/pyproject.toml` floor `>=1.32.0`, uv.lock) | 2026-08-24 | local |
| Temporal Server, latest | **v1.32.1** | 2026-10-08 | github.com/temporalio/temporal/releases |
| Temporal Server in this repo | `temporalio/auto-setup:latest` → **1.29.3** (verified: `temporal-server --version`). The image is **DEPRECATED** on Docker Hub ("no longer maintained"); its `latest` tag was last pushed 2026-02-05 | 2026-02-05 | hub.docker.com/r/temporalio/auto-setup |
| GitHub Spec Kit, upstream | **v1.1.2** | 2026-10-07 | github.com/github/spec-kit/releases |
| Spec Kit in this repo | 0.13.0 (`.specify/init-options.json`) | — | local |
| mermaid | 12.1.0 | 2026-10-02 | npm |
| `@mermaid-js/mermaid-cli` | 12.0.0 (`engines.node >=22.13.0`; peer `puppeteer ^25.0.0`) | 2026-09-24 | npm |
| `@mermaid-js/parser` | 2.0.1 | 2026-10-02 | npm |
| Structurizr (new consolidated tool) | `structurizr/structurizr` **2026.09.19** | 2026-09-19 | docs.structurizr.com/binaries |
| `structurizr/cli` (old) | v2025.11.09, **frozen** ("will not receive any further updates") | 2025-11-09 | github.com/structurizr/cli README |
| Tailwind CSS | v4.3.3 | 2026-07-16 | github.com/tailwindlabs/tailwindcss/releases |
| Storybook | 10.6.1 | (npm latest, accessed 2026-10-09) | npm |
| Playwright for Python | 1.63.0 | 2026-09-15 | PyPI |

---

### L.1 Temporal entity-workflow patterns for a long-lived feature

**Answer:**
Everything docs/80 §5 assumes exists in `temporalio` 1.34.0, with these
constraints and one real design fork.

1. **Parent "feature" workflow with child lanes.**
   - API: `await workflow.start_child_workflow(LaneWf.run, args=…, id=…, parent_close_policy=…)`
     returns a `ChildWorkflowHandle`. `workflow.execute_child_workflow(...)` starts the
     child and awaits its result.
   - The **default `parent_close_policy` is `ParentClosePolicy.TERMINATE`**. The other
     options are `ABANDON`, `REQUEST_CANCEL` and `UNSPECIFIED`.
   - `id_reuse_policy` defaults to `ALLOW_DUPLICATE`. Children also accept
     `search_attributes`, `memo`, `static_summary` and `static_details`.
   - Server default limit: 2,000 pending children per execution
     (`limit.numPendingChildExecutions.error`).
2. **Signalling a specific child.**
   - Inside workflow code, either use `child_handle.signal(LaneWf.some_signal, arg)`
     from the handle you hold, or
     `workflow.get_external_workflow_handle(workflow_id, run_id=None)` /
     `get_external_workflow_handle_for(LaneWf.run, workflow_id)` and then `.signal(...)`.
   - `ChildWorkflowHandle` exposes only `id`, `first_execution_run_id` and `signal`.
     `ExternalWorkflowHandle` exposes only `id`, `run_id`, `signal` and `cancel`.
   - So **workflow code cannot send an Update** to another workflow. Updates come only
     from a `Client`, meaning the bridge or an activity.
   - From outside, the bridge uses `client.get_workflow_handle(lane_id)` and then
     `.signal` / `.query` / `.execute_update` / `.start_update`.
   - For any of this to work, lane workflow IDs must be deterministic, e.g.
     `feature/{repo}/{NNN}/architect`, or discoverable via search attributes.
3. **Workflow-to-workflow signalling.**
   - Downward (parent → child): the child handle or an external handle, as above.
   - Upward (child → parent): `workflow.info().parent` (a `ParentInfo` with
     `namespace`, `run_id`, `workflow_id`; CODE `_context.py`) gives the parent's id,
     and the child calls `get_external_workflow_handle(parent.workflow_id).signal(...)`.
     Omitting `run_id` targets the latest run, which survives a parent continue-as-new.
   - The sender records `SignalExternalWorkflowExecutionInitiated`; the recipient
     records `WorkflowExecutionSignaled`.
   - Server limit: 2,000 pending outgoing signals (`limit.numPendingSignals.error`) and
     10,000 received signals per execution (`history.maximumSignalsPerExecution`).
4. **Signal-with-start and update-with-start.**
   - **Signal-with-start:** `client.start_workflow(Wf.run, id=…, task_queue=…, start_signal="name", start_signal_args=[…])`.
     It signals the running workflow if there is one, otherwise starts it and signals it.
   - **Update-with-start** takes a
     `WithStartWorkflowOperation(Wf.run, id=…, id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING, task_queue=…)`
     plus either `client.execute_update_with_start_workflow(Wf.upd, arg, start_workflow_operation=op)`,
     which blocks until the update completes, or `client.start_update_with_start_workflow(...)`,
     which returns a `WorkflowUpdateHandle`.
   - The SDK raises `ValueError("WorkflowIDConflictPolicy is required")` if the policy
     is `UNSPECIFIED`.
   - Docs: update-with-start is **"_not_ atomic"**. If the update can't be delivered, the
     new execution still starts. "Temporal Server version 1.28 is recommended" for
     self-hosted.
   - Our compose server is 1.29.3, so it clears 1.28. It is unpinned and deprecated
     (see the risk below).
5. **Continue-as-new for weeks-long workflows.**
   - API: `workflow.continue_as_new(...)`, `workflow.info().is_continue_as_new_suggested()`,
     `workflow.info().get_current_history_length()` and `.get_current_history_size()`.
   - Docs: wait for handlers first with
     `await workflow.wait_condition(workflow.all_handlers_finished)`.
   - Server defaults (v1.32.1 `constants.go`):
     - hard limit 51,200 events / 50 MiB;
     - warnings at 10,240 events / 10 MiB;
     - continue-as-new is *suggested* at 4,096 events or 4 MiB, or at 90% of
       `history.maxTotalUpdates` (2,000).
   - **Trap for the lane model (DOC + CODE):**
     - Docs: "Child Workflows do not carry over when the Parent uses Continue-As-New …
       any ongoing Child Workflow Executions will not be retained in the new continued
       instance of the Parent". Also: "Consider the Child's Parent Close Policy if the
       Parent does not await on the result of the Child, which includes any use of
       Continue-As-New by the Parent".
     - The server's close-execution task runs `processParentClosePolicy` on every close
       except a reset (`transfer_queue_active_task_executor.go` ~L475–490).
     - So a `FeatureWorkflow` that continues-as-new while lanes run under the default
       `TERMINATE` policy kills its lanes.
     - Mitigations: start lanes with `ParentClosePolicy.ABANDON` and re-address them by
       ID, or only continue-as-new at a point where no lane is running.
     - Either way, child result futures don't survive continue-as-new, so lanes should
       report completion *upward by signal*.
   - Also (DOC): Update-ID dedup is per run. "If you are using Updates with
     Continue-As-New you should implement the deduplication in your Workflow code."
6. **Updates (validated, acknowledged) vs Signals for human decisions.**
   - Declaring them:
     - signal: `@workflow.signal`;
     - update: `@workflow.update(unfinished_policy=…)` plus `@my_update.validator`.
   - What the validator may do:
     - it is sync only, takes the same args and returns `None`;
     - it may *read* state but "cannot mutate state";
     - raising any exception rejects the update.
   - Rejected updates (DOC): "the Workflow will have no indication that it was ever
     requested". `WorkflowExecutionUpdateAccepted` is not written, and the caller gets
     `WorkflowUpdateFailedError`.
   - Docs (handling-messages) on when to choose an Update: the client "wants to track
     the completion", "needs a result or exception", or you "want to validate the Update
     before accepting it into the Workflow and its history".
   - Docs on Signals: "Clients don't depend on the Worker being available."
   - Server defaults: at most **10 in-flight updates** per execution
     (`history.maxInFlightUpdates`) and **2,000 total** (`history.maxTotalUpdates`).
     `frontend.enableUpdateWorkflowExecution` defaults to `true` in v1.32.1, and also
     in v1.29.3, the version actually deployed (CODE, both tags).

**Can an Update validator reject a stale decision (wrong attempt) or a second decision
(first-valid-wins)?** Yes for both, with one caveat that needs a test.

- *Stale attempt.* A validator like
  `if attempt != self._open_attempt or self._window_closed: raise ValueError("stale")`
  is exactly its intended use: it reads state and rejects. Nothing goes into history,
  and the caller gets a named failure the bridge can map to `duplicate_ignored`/😕.
  - CODE: the SDK runs the validator inside `_as_read_only(in_query_or_validator=True)`.
    A mutation attempt raises `ReadOnlyContextError`, which **fails the workflow task**
    rather than rejecting the update (`_workflow_instance.py` ~L714–760). So the
    validator must be strictly read-only.
  - CODE: validators run only when `job.run_validator` is set, so they don't re-run on
    replay. A validator reading state can't cause non-determinism on replay.
- *Second decision in the same window.* Validator: `if self._decision is not None:
  raise ...`. Handler: `self._decision = ...`.
  - CODE: each `DoUpdate` job runs `run_update()` as its own asyncio task, in arrival
    order. Validator, accept and handler run in that task with no yield between
    validation and the start of the handler.
  - INFER: if the handler is a `def`, or sets state before its first `await`, the first
    update's mutation completes before the second update's task runs its validator. Two
    decisions in one workflow task are then serialized correctly. **This should be
    pinned by a `WorkflowEnvironment` unit test in 008/012**; I didn't run one.
  - The handler should *also* be set-if-unset as defence in depth. Signals in the same
    activation still mutate state without validation.
- *Fork for §12.* GitHub comments carry no attempt (docs/80 §12). Two options:
  - (a) keep GitHub on signals, made set-if-unset and "applies to the open window", and
    use Updates for Teams;
  - (b) have the bridge `query` the open attempt, then send an Update carrying that
    attempt for both surfaces. This has a small TOCTOU gap that the validator closes:
    a stale attempt is rejected.
  - Either way the workflow is the arbiter, as §12 requires.
- *Bridge ergonomics (DOC/CODE).*
  - `execute_update` / `execute_update_with_start_workflow` block until **completed**,
    and "will not return successfully until the update has been delivered to a worker"
    (SDK docstring). A down worker means a blocked or timed-out webhook handler, whereas
    a signal is accepted by the server with no worker.
  - Use `handle.start_update(Wf.decide, arg, wait_for_stage=WorkflowUpdateStage.ACCEPTED, rpc_timeout=…)`
    to get the accept/reject verdict fast, and treat `WorkflowUpdateRPCTimeoutOrCancelledError`
    as "worker unavailable, retry/queue". This is a behaviour change from today's
    fire-and-forget signals.
  - Updates target a *lane* workflow directly, because the parent cannot forward an
    Update.
  - If the parent receives the Update instead, it can only forward by signal, and
    per-lane validation then has to live in the parent's state, i.e. the parent mirrors
    each lane's open window.

**Evidence:**
- https://docs.temporal.io/develop/python/message-passing (accessed 2026-10-09; DOC) — validator rules, rejection not in history, `get_external_workflow_handle_for`, signal-with-start `start_signal`, update-with-start API, `all_handlers_finished`, Signal/Query/Update table.
- https://docs.temporal.io/develop/python/child-workflows (accessed 2026-10-09; DOC) — `start_child_workflow`/`execute_child_workflow`; default policy terminates the child.
- https://docs.temporal.io/child-workflows (accessed 2026-10-09; DOC) — children do not carry over on parent continue-as-new; Parent Close Policy applies, "which includes any use of Continue-As-New by the Parent".
- https://docs.temporal.io/develop/python/continue-as-new (accessed 2026-10-09; DOC) — `continue_as_new`, `is_continue_as_new_suggested`, wait for handlers first.
- https://docs.temporal.io/sending-messages (accessed 2026-10-09; DOC) — update-with-start "not atomic", `WorkflowIDConflictPolicy` required, "Temporal Server version 1.28 is recommended"; update wait stages Accepted/Completed.
- https://docs.temporal.io/handling-messages (accessed 2026-10-09; DOC) — rejected update leaves no trace; Update-ID dedup per run and the continue-as-new caveat; messages processed in arrival order.
- https://docs.temporal.io/encyclopedia/workflow-message-passing (accessed 2026-10-09; DOC) — Signals vs Updates choice; signals don't depend on worker availability.
- https://docs.temporal.io/workflow-execution/limits (accessed 2026-10-09; DOC) — 51,200 events / 50 MB; warn 10,240 / 10 MB; 2,000 pending activities/children/signals/cancels.
- https://github.com/temporalio/sdk-python/blob/1.34.0/temporalio/workflow/_workflow_ops.py (tag 1.34.0, 2026-09-30; CODE) — `ParentClosePolicy` enum; `start_child_workflow(... parent_close_policy=ParentClosePolicy.TERMINATE ...)`; `ChildWorkflowHandle`/`ExternalWorkflowHandle` expose only signal (+cancel); `all_handlers_finished`.
- https://github.com/temporalio/sdk-python/blob/1.34.0/temporalio/workflow/_handlers.py (CODE) — `HandlerUnfinishedPolicy.WARN_AND_ABANDON|ABANDON`; `UpdateMethodMultiParam.validator`.
- https://github.com/temporalio/sdk-python/blob/1.34.0/temporalio/workflow/_context.py (CODE) — `get_current_history_length/size`, `is_continue_as_new_suggested`.
- https://github.com/temporalio/sdk-python/blob/1.34.0/temporalio/worker/_workflow_instance.py (CODE) — `_apply_do_update`: validator under read-only, `ReadOnlyContextError` fails the task, rejected → `update_response.rejected`, `job.run_validator`.
- https://github.com/temporalio/sdk-python/blob/1.34.0/temporalio/client/_workflow.py and `_client.py` (CODE) — `WithStartWorkflowOperation` raises `ValueError` on UNSPECIFIED conflict policy; `execute_update_with_start_workflow` docstring (blocks until delivered to a worker); `start_workflow(..., start_signal=...)`.
- https://github.com/temporalio/sdk-python/releases (1.31.0 2026-07-29 … 1.34.0 2026-09-30; DOC) — no breaking change to these APIs noted in 1.32–1.34 release notes.
- https://github.com/temporalio/temporal/blob/v1.32.1/common/dynamicconfig/constants.go (tag 2026-10-08; CODE) — history limits/suggest-CAN 4 MiB/4,096; `history.maxInFlightUpdates=10`; `history.maxTotalUpdates=2000` (+0.9 suggest-CAN); `history.maximumSignalsPerExecution=10000`; `frontend.enableUpdateWorkflowExecution=true`.
- https://github.com/temporalio/temporal/blob/v1.32.1/service/history/transfer_queue_active_task_executor.go (CODE) — parent close policy processed on close unless reset.
- https://hub.docker.com/r/temporalio/auto-setup (accessed 2026-10-09; DOC) — "DEPRECATED … no longer maintained"; points to `temporalio/server` + `temporalio/admin-tools` compose samples. Local `temporal-server --version` → 1.29.3 (CODE).

**Confidence:** high for API names, defaults and limits (read in source at pinned
tags). Medium for "validator serializes two same-task decisions" (inferred from code
structure, untested). High for "parent continue-as-new applies the parent close
policy to running lanes" (DOC, and consistent with the server code).

**Gaps:**
- I didn't find the server version where Updates became GA. Docs give only the ≥1.28
  recommendation for update-with-start.
- I found no doc statement on Update behaviour when a worker is down beyond the SDK
  docstring.

**Implication for docs/80:**
- **§5 / §5.2: confirm.** Parent `FeatureWorkflow` plus child lanes is supported. Add
  three things:
  - lanes need deterministic IDs, plus `ParentClosePolicy.ABANDON` (or a "no
    continue-as-new while lanes run" rule);
  - lanes report upward by signal;
  - signal-with-start is the simpler lane-start primitive from the bridge, and
    update-with-start (needs `USE_EXISTING`) only if the bridge needs a synchronous
    verdict.
- **§12.1: change.** Pick Update + validator for Teams decisions, with set-if-unset
  handlers, and either keep GitHub on validated-by-state signals or have the bridge
  query the attempt and then Update.
- **§7 bridge: new risk.** Updates need a live worker, so the bridge must use
  `start_update(wait_for_stage=ACCEPTED)` with a timeout.
- **§15: new risk.** Compose runs the deprecated `temporalio/auto-setup:latest`
  (server 1.29.3, unpinned). Move to pinned `temporalio/server` + `admin-tools`.

---

### L.2 `@workflow.query` or Update for "status" while blocked in `wait_condition`

**Answer:** Use a **Query**.

- **A Query works while the workflow is blocked in `wait_condition`.** A blocked
  workflow has no task in flight, and the worker serves the query against cached or
  replayed state.
- **Query constraints:**
  - handlers are `def`, never `async def`;
  - they must not mutate state, start activities or call `wait_condition`. The SDK runs
    them under `_as_read_only(in_query_or_validator=True)`, and `wait_condition`,
    `start_activity` and `continue_as_new` all `_assert_not_read_only`;
  - a worker must be online and polling (DOC: "A Worker must be online and polling the
    Task Queue to process a Query");
  - queries leave no history events;
  - they also work on *closed* workflows within retention, unlike signals and updates.
- **Values may be stale inside a query.** `get_current_history_length()`,
  `get_current_history_size()` and `is_continue_as_new_suggested()` are documented as
  "may not be up to date if accessed inside a query". So a `status()` query should
  return the workflow's own fields (open gate, attempt, lane states), not history
  metrics.
- **Don't use an Update for status:**
  - each accepted update writes Accepted + Completed events to history;
  - updates count toward `maxTotalUpdates=2000`, whose 90% mark triggers a
    continue-as-new suggestion;
  - they occupy one of 10 in-flight slots;
  - a status poll from a card refresh would bloat history and could crowd out real
    decisions.
- **Use a validator-only Update only to *assert* state** ("is window N open?") as part
  of a decision, not for reads.
- **For the parent's board, aggregate in the parent.** Lanes signal state changes
  upward, and the parent's `status()` query returns the aggregate. A query can't fan
  out to children, because it can't do async work.

**Evidence:**
- https://docs.temporal.io/develop/python/message-passing (accessed 2026-10-09; DOC) — "A Query handler uses `def`, not `async def`", "can inspect but must not mutate", worker must be polling, works on closed workflows.
- https://github.com/temporalio/sdk-python/blob/1.34.0/temporalio/worker/_workflow_instance.py (CODE) — `_apply_query_workflow` wraps in `_as_read_only`; `_assert_not_read_only("wait condition")`, `("start activity")`, `("continue as new")`.
- https://github.com/temporalio/sdk-python/blob/1.34.0/temporalio/workflow/_context.py (CODE) — the "may not be up to date if accessed inside a query" docstrings.
- https://github.com/temporalio/temporal/blob/v1.32.1/common/dynamicconfig/constants.go (CODE) — update limits above.

**Confidence:** high.

**Implication for docs/80:**
- **§5 diagram ("status() query") and §12.5 ("Teams adapter calls `status()` first"):
  confirm, as a Query.**
- Note that the pre-check is advisory (TOCTOU). The authoritative check is the
  validator or set-if-unset handler from L.1.
- When the worker is down, a status query fails. The card should render "pipeline
  unavailable", not a guess.

---

### L.3 Spec Kit `[P]` semantics as a fan-out rule

**Answer:** Upstream defines `[P]` only as a per-task property:

- in the template, "Can run in parallel (different files, no dependencies)";
- in the `/tasks` command, "Include ONLY if task is parallelizable (different files, no
  dependencies on incomplete tasks)".

It defines **no grouping rule for `[P]` runs and no machine-readable dependency
notation.** Dependencies are expressed as:

1. **Phase order**, with explicit barriers only at Setup → Foundational ("BLOCKS all
   user stories") → User-story phases → Polish ("Depends on all desired user stories
   being complete").
2. **Prose sections**: "Phase Dependencies", "User Story Dependencies", "Within Each
   User Story" (Tests → Models → Services → Endpoints → Integration).
3. A **free-text inline example**, `T014 [US1] Implement [Service] … (depends on T012, T013)`.
   It is not a grammar.

Two points cut against docs/80 §5.1 invariant 4.

- **Upstream's parallel *team* unit is the user story, not a run of `[P]` tasks.**
  - The template says "Once Foundational phase completes, all user stories can start in
    parallel (if team capacity allows)", and "Different user stories can be worked on in
    parallel by different team members".
  - Its "Parallel Team Strategy" assigns "Developer A: User Story 1 / Developer B: User
    Story 2 …". So **user-story phases are not barriers to each other**; only
    Setup/Foundational/Polish are.
  - `[P]` within a story is shown as intra-developer concurrency ("Launch all tests for
    User Story 1 together").
- **`/implement` gives execution and failure semantics, not grouping.** It says:
  - "Phase-by-phase execution: Complete each phase before moving to the next";
  - "Run sequential tasks in order, parallel tasks [P] can run together";
  - "Tasks affecting the same files must run sequentially";
  - "Halt execution if any non-parallel task fails";
  - "For parallel tasks [P], continue with successful tasks, report failed ones".

  Read literally, "phase-by-phase" in `/implement` conflicts with the template's
  "stories in parallel". `/implement` is written for one agent, and the template's
  parallel-team guidance for humans (INFER).

The local `.specify/templates/tasks-template.md` is byte-identical to upstream v1.1.2
except one line: `/speckit-tasks` locally vs the placeholder `__SPECKIT_COMMAND_TASKS__`
upstream. The local CLI pin is 0.13.0 against upstream 1.1.2.

**Evidence:**
- https://github.com/github/spec-kit/blob/v1.1.2/templates/tasks-template.md (file last changed 2026-05-12, commit "fix: make template metadata line breaks markdownlint-safe (#2505)"; tag v1.1.2 2026-10-07; DOC) — `[P]` definition, Phase/User Story dependency prose, "(depends on T012, T013)", Parallel Opportunities, Parallel Team Strategy, Notes "[P] tasks = different files, no dependencies".
- https://github.com/github/spec-kit/blob/v1.1.2/templates/commands/tasks.md (last changed 2026-09-09; DOC) — checklist format `- [ ] [TaskID] [P?] [Story?] Description with file path`; "[P] marker: Include ONLY if task is parallelizable (different files, no dependencies on incomplete tasks)"; "Generate dependency graph showing user story completion order"; "Mark story dependencies (most stories should be independent)".
- https://github.com/github/spec-kit/blob/v1.1.2/templates/commands/implement.md (last changed 2026-09-09; DOC) — steps 5–8 quoted above.
- https://github.com/github/spec-kit/releases (v1.1.2, 2026-10-07; DOC).
- Local diff vs upstream (CODE): only line 33 differs.

**Confidence:** high. All quotes were read from the pinned tag.

**Implication for docs/80:**
- **§5.1 invariant 4: change.**
  - Keep phases as barriers *only* for Setup, Foundational and Polish.
  - Make the default Coder-lane unit **one lane per user-story phase**, matching
    upstream's team model.
  - Optionally split a story further by `[P]` runs whose tasks name disjoint file
    paths, which is checkable because every task must carry a file path.
- The dependency check has to be ours. Parse the "(depends on Tnnn…)" free text
  best-effort, and fall back to file-path overlap.
- §5.1 invariant 5 / budgets: `/implement`'s failure rule maps onto lane outcomes. A
  non-`[P]` failure halts the lane; `[P]` failures are reported and the rest continue.
- **§16 / §17 detail:** decide whether to bump the local Spec Kit from 0.13.0 to 1.1.2
  first. The template is unchanged; command files differ.

---

### L.4 Git strategies for parallel agent lanes

**Answer:**

- **Sub-branch per lane.** Each lane pushes `lane/<NNN>/<role><n>`, and a code-side
  activity merges it into the feature branch.
- **Worktree per lane.** Several checkouts share one `.git`, each on its own branch.
- **They are not alternatives at the same layer.** A worktree is a *local checkout
  mechanism*; the lane still needs its own branch.
  - Git enforces that: "add refuses to create a new worktree when <commit-ish> is a
    branch name and is already checked out by another worktree" (unless `--force`).
  - Codex's docs explain why: one branch has "a single authoritative working copy".
- **In this repo every lane runs in its own E2B sandbox** (CLAUDE.md), so lanes never
  share a filesystem and worktrees add nothing between lanes (INFER).
- **Worktrees only matter on the merge host.** If the `FeatureWorkflow`'s merge
  activity needs a working tree, it can use one throwaway worktree per merge.
- **Conflict detection without a working tree:**
  - `git merge-tree --write-tree <feature> <lane>`, the modern mode since Git 2.38.0,
    2022-10-02, "Perform[s] merge without touching index or working tree".
  - Exit status "0" for a clean merge and "1" when the merge has conflicts; `--quiet`
    "allows merge-tree to exit early when it finds a conflict".
  - This gives the merge activity a cheap, deterministic conflict pre-check whose result
    can be charged to the lane's budget (docs/80 §5.1 invariant 1), with no model
    involved.
- **Who merges, in existing tools (primary docs):**
  - **GitHub Copilot cloud (coding) agent:** one branch and one PR per task. It "can
    only push to a single branch", either a new `copilot/` branch or the PR's branch
    when mentioned on a PR.
    - It "cannot mark its pull requests as 'Ready for review' and cannot approve or
      merge a pull request".
    - Draft PRs "must be reviewed and merged by a human".
    - The requester cannot approve, and unattributed agent PRs need one extra approval.
    - It does no cross-task merge orchestration: parallelism means N independent PRs.
  - **Claude Code:**
    - `claude --worktree <name>` creates `.claude/worktrees/<name>/` on branch
      `worktree-<name>`.
    - Subagents can declare `isolation: worktree`. Each gets a temporary worktree,
      removed if unchanged, branched by default from the default branch
      (`worktree.baseRef: "fresh"`), or from the current HEAD with `"head"`.
    - It holds a `git worktree lock` while an agent runs.
    - No automatic merge-back is documented. Integration is the user's or main
      session's job.
    - For agent teams the guidance is "Two teammates editing the same file leads to
      overwrites. Break the work so each teammate owns a different set of files."
  - **OpenAI Codex app:** worktrees in `$CODEX_HOME/worktrees`, in **detached HEAD** by
    default ("lets Codex create several worktrees without polluting your branches").
    The user moves work back via "Handoff" or "Create branch here" → commit → push → PR.
  - **Codex Cloud:** "commit or open a pull request when you're ready". The human
    decides.
  - **Devin:** a coordinator session spins up "managed Devins … each running in its own
    isolated VM". The coordinator "scopes the work, monitors progress, **resolves
    conflicts**, and compiles results". The user can prompt "Open a separate PR for
    each". This is the only vendor where an agent resolves conflicts.
- **Pattern across vendors:** isolation per agent (a branch, worktree or VM), a
  human-merged PR per unit of work, and conflicts avoided upfront by partitioning files
  rather than resolved automatically. Devin is the exception: it delegates resolution
  to a coordinator agent.

**Evidence:**
- https://git-scm.com/docs/git-worktree (accessed 2026-10-09; DOC) — branch already checked out → `add` refuses unless `--force`.
- https://git-scm.com/docs/git-merge-tree (accessed 2026-10-09; DOC) — `--write-tree` mode (2.38.0 2022-10-02), exit status 0/1/other, `--quiet`.
- https://docs.github.com/en/copilot/concepts/agents/coding-agent/risks-and-mitigations (accessed 2026-10-09; DOC) — single-branch push, `copilot/` branch, cannot approve/merge, requester can't approve, extra approval for unattributed PRs.
- https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-coding-agent (accessed 2026-10-09; DOC) — "can only work on one branch at a time and can open one pull request per task"; single repository per run.
- https://code.claude.com/docs/en/worktrees (accessed 2026-10-09; DOC) — `--worktree`, `.claude/worktrees/<name>`, `worktree-<name>` branch, subagent `isolation: worktree`, `worktree.baseRef`, locks, cleanup.
- https://code.claude.com/docs/en/sub-agents (accessed 2026-10-09; DOC) — `isolation` frontmatter field semantics.
- https://code.claude.com/docs/en/agent-teams (accessed 2026-10-09; DOC) — "Avoid file conflicts … each teammate owns a different set of files."
- https://developers.openai.com/codex/app/worktrees (accessed 2026-10-09; DOC) — `$CODEX_HOME/worktrees`, detached HEAD, Handoff, one-branch-per-worktree rationale.
- https://developers.openai.com/codex/cloud (accessed 2026-10-09; DOC) — review then commit/open PR.
- https://docs.devin.ai/work-with-devin/advanced-capabilities (accessed 2026-10-09; DOC) — managed Devins in isolated VMs; coordinator "resolves conflicts"; separate PR per module.

**Confidence:** high for each tool's documented behaviour and the git semantics. Medium
for the conclusion that worktrees are irrelevant across E2B lanes (INFER from this
repo's sandbox model).

**Gaps:**
- None of the vendors documents an *automatic* merge of parallel agent branches into
  one feature branch. Devin says the coordinator "resolves conflicts" without specifying
  how.
- Copilot's docs don't say whether several Copilot tasks can run concurrently on one
  repo. I found no explicit statement.

**Implication for docs/80:**
- **§5.1 invariant 1: confirm and settle L.4.**
  - Use a **sub-branch per lane**, pushed from each lane's sandbox, plus a code-side
    merge activity in the parent.
  - The activity pre-checks with `git merge-tree --write-tree`. Exit 1 is a lane
    failure that charges the budget, never auto-resolution.
  - It uses a throwaway worktree only if it needs one locally.
- Partition lanes by disjoint file paths, which L.3's file-path requirement makes
  checkable. This matches Claude Code's and Devin's guidance.
- The final feature PR stays human-merged. That matches Copilot's model and the repo's
  "merged PR is the unit of output".
- **§14.5 takeover: confirm.** A lane branch is a normal ref, so "branch + PR + clone
  command" works with any tool.

---

### I.1 Architecture diagrams from LLMs: C4 in mermaid vs Structurizr DSL

**Answer:** **Mermaid C4 is the weakest option for "validated in Python, not trusted
from the model"**; Structurizr DSL is the strongest; mermaid `flowchart` is in between.

- **Mermaid `C4Context`/`C4Container`/`C4Component`/`C4Dynamic`/`C4Deployment`:**
  - Status (DOC): "an experimental diagram for now. The syntax and properties can change
    in future releases."
  - It does not use an automated layout. Position follows statement order and is tuned
    via `UpdateLayoutConfig`.
  - `sprite`, `tags` and `link` are "not supported in the short term".
- **Validation by parse:**
  - `mermaid.parse(text, {suppressErrors})` returns `{diagramType}` or `false`, or
    throws. **There is no Python-callable mermaid parser**; any validator runs Node.
  - `@mermaid-js/parser` 2.0.1 (Langium) ships grammars only for architecture, gitGraph,
    info, packet, pie, radar, treemap, treeView, wardley, railroad*, cynefin and
    eventmodeling. It covers **neither C4 nor flowchart**.
- **Empirical results** (mermaid 12.1.0 / mmdc 12.0.0, Node 26, run here 2026-10-09):

  | Input | `mermaid.parse` (Node + jsdom) | `mmdc` render |
  |---|---|---|
  | valid C4Container | OK | exit 0, correct PNG |
  | C4 with missing `)` (`Person(u,"User"` then `Rel(...)`) | **OK (accepted)** | **exit 0, wrong PNG**: the Rel was swallowed into the person's label as text "Rel(u" |
  | C4 `Rel` to undefined alias | **OK (accepted)** | exit 1, `C4 rel "u" -> "nosuch" references an unknown shape or boundary` |
  | valid flowchart | OK | — |
  | broken flowchart `A[User --> B]]` | **error with line number** | — |

  - In bare Node *without* a DOM shim, `mermaid.parse` fails on **valid** input with
    `DOMPurify.addHook is not a function`. A jsdom `window`/`document` shim is required.
  - So for C4, parse catches almost nothing, and even a full render can exit 0 on
    malformed input. Flowchart parse errors are caught.
- **Structurizr DSL** (new consolidated `structurizr/structurizr` 2026.09.19; the old
  `structurizr/cli` is frozen):
  - `validate -workspace x.dsl` rejected all three faults with line-numbered errors and
    exit 1:
    - undefined destination: `The destination element "nosuch" does not exist at line 5`;
    - unbalanced block: `Unexpected tokens … at line 6`;
    - a one-line `container s "c" { include * autolayout lr }`: `Too many tokens …`.
      The DSL is newline-sensitive, and my own first draft tripped on it, an anecdotal
      sign that LLM output will too.
  - The DSL has real model semantics (elements, relationships, views), so it can check
    referential integrity.
  - Structurizr's own AI page shows LLM-generated DSL where "A little cleanup is
    required".
  - It can also `export -format mermaid|plantuml|plantuml/c4plantuml|png|svg|static|json`,
    so a **hybrid** works: model in DSL, validate with Structurizr, and export mermaid
    for client-side rendering in the tab (F.4). Docs caveat: "the export formats do not
    support all available shapes/features".
- **Headless rendering in a container:**
  - *mermaid-cli*:
    - `mmdc -i in.mmd -o out.png`, with options `-t`, `-b`, `--size` and `-p puppeteer-config.json`.
    - Requires Node ≥22.13 and **puppeteer ^25 as a peer dependency**, which downloads
      or needs a Chromium.
    - Running as root in a container needs `{"args": ["--no-sandbox"]}` via `-p`, or
      Chromium fails with "Running as root without --no-sandbox is not supported".
    - Official images: `minlag/mermaid-cli` and `ghcr.io/mermaid-js/mermaid-cli/mermaid-cli`.
    - There is a Node API, and a doc for using an already-installed Chromium.
  - *Structurizr*:
    - PNG/SVG export uses "the Structurizr browser-based renderer" and **only works in
      the `-playwright` image or `.war`**.
    - The base image refused with `Exporting to PNG/SVG is not supported in this build`
      (exit 1).
    - Measured locally: base image 430 MB; **`2026.09.19-playwright` 4.03 GB**; one
      container-view export took about 35 s on a cold run that included the first image
      pull and JVM start, so it's not a steady-state figure. It produced
      `c.png` + `c-key.png`.
    - Requires Java 21 (`.war`) or Docker.

**Evidence:**
- https://github.com/mermaid-js/mermaid/blob/develop/packages/mermaid/src/docs/syntax/c4.md (develop branch, accessed 2026-10-09; DOC) — experimental status, diagram types, layout, unsupported sprite/tags/link.
- https://github.com/mermaid-js/mermaid/blob/develop/packages/mermaid/src/docs/config/usage.md (accessed 2026-10-09; DOC) — "Syntax validation without rendering", `mermaid.parse(text, parseOptions)` contract.
- https://github.com/mermaid-js/mermaid/tree/develop/packages/parser/src/language (accessed 2026-10-09; CODE) — grammar list (no c4/flowchart); npm `@mermaid-js/parser` 2.0.1 (2026-10-02).
- https://github.com/mermaid-js/mermaid-cli (README + docs/linux-sandbox-issue.md, accessed 2026-10-09; DOC) — CLI usage, Docker images, `--no-sandbox` puppeteer config; npm 12.0.0 (2026-09-24) engines/peer deps (CODE).
- Local experiment, scratchpad `mmtest/` (2026-10-09; CODE) — the table above; `c4bad.png` inspected visually.
- https://docs.structurizr.com/commands , /export , /validate , /binaries , /ai/dsl-generation (accessed 2026-10-09; DOC) — command list, export formats (png/svg via browser renderer), validate, image tags (`-playwright` includes Playwright deps), "A little cleanup is required".
- https://github.com/structurizr/cli README (accessed 2026-10-09; DOC) — "will not receive any further updates … migrate to the new consolidated tooling".
- Local experiment, scratchpad `sz/` with `structurizr/structurizr:2026.09.19` and `:2026.09.19-playwright` (2026-10-09; CODE) — validate errors, PNG export, image sizes.

**Confidence:** high for tool behaviour (verified by running pinned versions); medium
for generalising from a 3–5-case experiment.

**Gaps:**
- **I found no primary-source measurement of LLM generation reliability** for mermaid
  C4, mermaid flowchart or Structurizr DSL. The only primary signal is Structurizr's
  "a little cleanup is required". A small eval in spec 010 (N generations × parse/
  validate pass rate) would answer it.
- Didn't test `minlag/mermaid-cli` image size or cold-start time.
- Didn't test whether the E2B `swe-agent-sandbox` template has Chromium.

**Implication for docs/80:**
- **§9.1: change.** "Validation by parse, in Python" has no Python implementation and
  is ineffective for mermaid C4 even in Node.
- Options, in order:
  - (a) **Structurizr DSL as the source of truth**: `validate` as the gate, with
    `export -format mermaid` for the tab and `-format png` (playwright image) for card
    thumbnails;
  - (b) mermaid **`flowchart`** with C4-style classes instead of `C4*`, gated by
    `mermaid.parse` (Node + jsdom) **plus** a render-must-exit-0 check **plus** our own
    structural check (all edge endpoints declared);
  - (c) mermaid C4, only with a custom validator. Not recommended while it is
    "experimental".
- **§15:** budget for a Chromium-bearing renderer container: puppeteer/Chromium for
  mmdc, or the 4 GB Structurizr playwright image. Run as non-root, or with
  `--no-sandbox` inside an already-isolated sandbox.
- **§17:** C4 in mermaid vs Structurizr resolves toward Structurizr, or flowchart.

---

### I.2 Clickable UI prototypes from LLMs, and screenshots for card thumbnails

**Answer:**

- **Static HTML + Tailwind.** This is the most reliable target for an agent: one
  self-contained file, no build graph, and docs/80 §9.2 already assumes it.
  - **CDN:** the Play CDN (`<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4">`)
    is "designed for development purposes only, and is not intended for production".
    It also violates §9.2's "no network" rule and needs JS execution in the frame.
  - **Compiled:** `npx @tailwindcss/cli -i in.css -o out.css --minify` scans the HTML
    and emits only the used utilities. **v4.3.3 ships standalone binaries**
    (`tailwindcss-linux-x64`, `-linux-arm64`, `-musl` variants), so the sandbox needs
    no Node. Inline the output CSS into the HTML to keep it self-contained.
  - Clickability comes from plain anchors or `<details>`, or a few lines of inline JS
    switching screens (INFER).
- **Design-system components** (e.g. shadcn/ui, an in-house library). **Not researched
  in depth; gap.** They need a build step and a component runtime, which INFER pushes
  them into the Storybook option below.
- **Storybook 10.6.1.**
  - `npm run build-storybook` "create[s] a static web application capable of being
    served by any web server". Each story is addressable in an iframe, so it can be
    screenshotted.
  - Visual testing is offered "natively using Chromatic, a cloud service", which is an
    external dependency.
  - It is heavier for an agent: a framework project, `package.json` and a build. Only
    worth it if the target repo already has a component library (INFER).
- **Figma.**
  - The **REST API is read/extract-oriented**: "view and extract any objects or layers,
    and their properties from files, get usage data, or listen for events with
    webhooks". It doesn't document creating frames or nodes.
  - Writing to the canvas goes through the **Figma MCP server's `use_figma` ("write to
    canvas")**. It creates frames, components, variants, variables and auto layout in a
    Figma Design file, and is available only through the **remote** MCP server with a
    **Full seat** and edit permission on the file ("Dev seat holders can use the Figma
    MCP server for read-only workflows").
  - Listed clients include Claude Code, Claude Desktop, Codex and Cursor. Docs note a
    "20kb output response limit per call".
  - Documented limitations: no image/asset support, no custom fonts.
  - It is user-session-driven. **Headless, service-account use from a Temporal
    activity is not addressed**, and prototype interactions or clickable flows are not
    mentioned.
  - Source conflict on status: a search-result snippet said write-to-canvas is "free
    during the beta period", but the fetched page doesn't say so. Treat beta/pricing
    status as unconfirmed.
- **Screenshot for a card thumbnail (Playwright for Python 1.63.0).**
  - Capture: `page.screenshot(path=…, full_page=True)` or
    `page.locator(sel).screenshot(...)`, with `animations="disabled"` (finite animations
    fast-forwarded, infinite ones cancelled).
  - Enforce "no network" while capturing: `browser.new_context(offline=True,
    java_script_enabled=…, service_workers="block")` and/or `page.route("**/*", lambda r:
    r.abort())` for non-`file:` URLs.
  - Load the mock via `page.goto("file:///…/index.html")` or `page.set_content(html)`.
    One screenshot per screen: click through anchors or set a hash per screen.
  - Structurizr's own renderer already uses Playwright, which shows the same
    Chromium-in-container cost as I.1.

**Evidence:**
- https://tailwindcss.com/docs/installation/play-cdn (accessed 2026-10-09; DOC) — "designed for development purposes only, and is not intended for production"; `@tailwindcss/browser@4`.
- https://tailwindcss.com/docs/installation/tailwind-cli (accessed 2026-10-09; DOC) — `npx @tailwindcss/cli -i … -o …`.
- https://github.com/tailwindlabs/tailwindcss/releases/tag/v4.3.3 (2026-07-16; CODE) — standalone binary assets listed.
- https://storybook.js.org/docs/sharing/publish-storybook (accessed 2026-10-09; DOC) — `build-storybook` static output.
- https://storybook.js.org/docs/writing-tests/visual-testing (accessed 2026-10-09; DOC) — visual testing via Chromatic cloud.
- https://developers.figma.com/docs/rest-api/ (accessed 2026-10-09; DOC) — "What can I do with the Figma API?" quote.
- https://developers.figma.com/docs/figma-mcp-server/write-to-canvas (accessed 2026-10-09; DOC) — `use_figma`, Full seat, edit permission, client list, 20 kb limit, no images/custom fonts.
- https://playwright.dev/python/docs/screenshots and https://playwright.dev/python/docs/api/class-page (accessed 2026-10-09; DOC) — `screenshot`, `full_page`, locator screenshot, `animations="disabled"`.
- https://playwright.dev/python/docs/api/class-browser (accessed 2026-10-09; DOC) — `new_context(offline=, java_script_enabled=, service_workers="block")`.
- https://playwright.dev/python/docs/network (accessed 2026-10-09; DOC) — `page.route(...)` + `route.abort()`.

**Confidence:**
- high: Tailwind CDN vs compiled, Figma REST scope and seat requirements, Playwright
  APIs;
- medium: Figma headless feasibility (not documented either way);
- low: design-system components (not researched).

**Gaps:**
- I found no primary source on how reliably LLMs produce each format.
- Didn't research design-system component libraries.
- Unconfirmed: Figma `use_figma` beta/pricing status, server-side or headless use, and
  prototype-interaction support.
- Unverified whether the E2B sandbox template includes Chromium/Playwright browsers. It
  needs a spike: `playwright install --with-deps chromium` adds the system deps.

**Implication for docs/80:**
- **§9.2: confirm the "self-contained HTML, CSS inlined or compiled, no network"
  output**, and make it concrete: compiled Tailwind via the standalone binary, inlined;
  **forbid the Play CDN**.
- Screenshots come from Playwright in the E2B sandbox, with `offline=True`.
- Storybook only when the target repo already has a component library.
- **Figma is not viable as the agent's primary output**: it needs a Full-seat human
  session via MCP, with no documented headless path. At most it is a later "export to
  Figma" nicety.
- **§17:** close "design-system vs Tailwind vs Figma" → Tailwind-compiled.
- **§15:** a Chromium dependency now appears in two producers (diagrams and mocks).
  Consider one shared renderer image.
