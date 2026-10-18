# Feature Specification: Merged-PR Terminus

**Feature Branch**: `017-merged-pr-terminus`

**Created**: 2026-10-17

**Status**: Draft

**Input**: User description: "Make a merged pull request the end of a product run. Today every run ends by opening a PR in
this repo that writes a registry entry (`registry/agents/<name>/manifest.yaml`). That end step was built for releasing the
factory's own agents. It doesn't fit a run whose real output is a feature PR in a target repo. Changes: (1) After the
checks pass, the run marks the target PR 'ready for review'. Then it waits, for days if needed, until a person merges or
closes it. Merged ends the run as 'shipped'; closed without merging ends it as 'abandoned'. The registry step runs only for
runs that build one of the factory's own agents. The run says which kind it is in an explicit input; nothing guesses it.
(2) Something has to send the 'PR merged' event. Today nothing does, so the registry release step can never be reached.
The webhook bridge (spec 002) learns GitHub's 'PR closed' events and passes them to the waiting run, and to the registry
release step. (3) Today the `@swe-agent build` comment can open a PR with no check at all. That stops: the comment starts
the same pipeline run (`AgentPipelineWorkflow`) as everything else, so it gets the same checks. Out of scope: deploying,
auto-merge, and the run history (018)."

## Background: how a run ends today

- `AgentPipelineWorkflow.run(repo, branch, agent_name, version)` (`orchestration/workflows/pipeline_workflow.py`) ends
  on the first Eval-Gate pass by calling `register_activity`. That activity opens a PR **in the factory repo** that writes
  `registry/agents/<agent_name>/manifest.yaml` and `versions/<version>.yaml`, and the run returns that PR's URL. It does
  this for every run, even when the run built a feature in some other repo.
- The target-repo PR is opened by `ensure_target_pr_activity` as a normal PR, not a draft, titled
  `[<branch>] automated pipeline run`. Nothing waits for anyone to merge it.
- `RegistryPromotionWaiterWorkflow` (`orchestration/workflows/registry_promotion_waiter.py`) waits for a `pr_merged`
  signal and then opens a second factory PR setting `status: active`. Nothing starts this workflow and nothing sends the
  signal, so the registry release step (what docs/70 calls Deploy) can never be reached (docs/70 §10 step 10 says the same).
- The webhook bridge (`orchestration/webhook_bridge/`, spec 002) handles only new PR comments
  (`@pipeline-agent run mode=… agent=… version=…` and the gate commands). It ignores every other GitHub event. It can
  add a reaction to a comment but cannot post a comment. Its duplicate-delivery memory is lost when it restarts.
- A run's ID is built from the repo, the agent name and the version (`pipeline/<repo>/<agent>/v<version>`, spec 002).
  A product run has no agent name or version of its own, so this ID does not fit it.
- The Build stage (`run_swe_agent_activity`) does not report progress to Temporal while it runs. A request to stop the
  run reaches it only when the sandbox finishes, up to 60 minutes later.
- The sandbox's GitHub token (spec 013) can write contents and pull requests on the target repo. That is enough to merge
  a PR, so "the bot never merges" is today a matter of the agent's instructions, not of its permissions.
- The `@swe-agent build` comment runs `.github/workflows/swe-agent-build.yml`. That workflow starts the agent directly in
  an E2B sandbox, lets it push and open a PR, and posts the result. No Eval-Gate, no human plan check and no credential
  pool are involved.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A product run ends when a person merges or closes the feature PR (Priority: P1)

An operator starts a product run on a target repo (for example the disposable test repo). The run plans, builds and
passes its checks. It then marks the target PR "ready for review" and posts a short comment saying the checks passed.
The run now waits. Days later a reviewer merges the PR. The run notices, records the merge, posts a closing comment and
ends as **shipped**. No registry PR is opened in the factory repo, because the run did not build a factory agent.

**Why this priority**: This is the gap the feature exists to close. Today the product pipeline's output (a merged feature
PR) is invisible to the run, and every run ends with a registry entry that means nothing for a product feature.

**Independent Test**: On the disposable repo, start a product run, let it pass its checks, merge the PR by hand, and
check that the run ends as shipped, that it recorded the merge commit, and that the factory repo got no new PR.

**Acceptance Scenarios**:

1. **Given** a product run whose checks pass, **When** the run reaches its end stage, **Then** the target PR leaves draft
   ("ready for review"), the run posts one comment saying the checks passed, and the run keeps waiting.
2. **Given** a product run that is waiting, **When** a person merges the target PR, **Then** the run ends as shipped and
   records the merge commit, the merge time and who merged it.
3. **Given** a product run that is waiting, **When** a person closes the target PR without merging, **Then** the run ends
   as abandoned and records who closed it and when.
4. **Given** a product run that ended as shipped or abandoned, **When** anyone looks at the factory repo, **Then** it has
   no registry PR from that run.
5. **Given** a product run that is waiting, **When** nobody merges or closes the PR within the maximum wait (default 30
   days), **Then** the run ends as timed out, posts one comment saying so, and leaves the PR open as it was.

---

### User Story 2 - The run learns about the merge even if a GitHub event is lost (Priority: P1)

GitHub sends a "pull request closed" event when a PR is merged or closed. The bridge receives it, checks it really came
from GitHub, finds the run for that PR and tells it to look now. The run then asks GitHub for the PR's state and acts on
that answer, never on the event's own content. Events can be lost (the bridge was restarted, the relay dropped the
delivery) or replayed. So the run also asks GitHub for the PR's state itself at a fixed interval, from run start to
run end.

**Why this priority**: Without a sender of this event the waiting step from Story 1 never ends, and the registry release
step stays unreachable, as it is today. Without the backup check, one lost event leaves a run waiting until its maximum
wait expires.

**Independent Test**: Merge a waiting run's PR while the bridge is stopped. Check that the run still ends as shipped
within one check interval. Then send the same "closed" event twice and check that the run ends once and posts one
closing comment.

**Acceptance Scenarios**:

1. **Given** a run waiting on target PR #57, **When** GitHub sends a validly signed "PR #57 closed" event, **Then** the
   bridge tells that run to look now, the run asks GitHub, sees the PR merged and ends as shipped.
2. **Given** the same event, **When** its signature is missing or wrong, **Then** the bridge rejects it and the run keeps
   waiting.
3. **Given** a "PR closed" event for a PR that no run is in flight for, **When** the bridge receives it, **Then** the
   bridge ignores it and changes nothing.
4. **Given** a run waiting on PR #57, which is still open, **When** a "PR #57 closed and merged" event arrives with a
   valid signature (in a test, a payload signed with the webhook secret), **Then** the run asks GitHub, sees the PR open
   and keeps waiting.
5. **Given** a waiting run, **When** the PR is merged and the event never arrives, **Then** the run's own check finds the
   merge within one check interval (default 1 hour) and ends as shipped.
6. **Given** a run that already ended, **When** the same event arrives again, or the event arrives after the backup check
   already found the merge, **Then** nothing more happens: no second end state, no second comment.

---

### User Story 3 - A factory-agent run still reaches the registry and the release step (Priority: P2)

An operator starts a run that builds one of the factory's own agents (for example a new `pm-agent` version). The start
command says so explicitly, and names the agent and the version. The run passes its checks and waits for its feature PR
like any other run. When a person merges that PR, the run opens the registry PR in the factory repo (as
`register_activity` does today) and starts the registry release step for it. When a person merges the registry PR, the
release step opens a third PR, the release PR, that sets the agent version's `status: active`. The version is active
once a person merges that release PR. For the first time, a run can reach the registry release step end to end.

**Why this priority**: Factory-agent runs are fewer than product runs, and the registry step already works up to the
registry PR. What is missing is the release after the registry PR merges, which this story connects.

**Independent Test**: With the factory repo setting pointed at a disposable stand-in repo, start a factory-agent run,
merge its feature PR, then the registry PR it opens, then the release PR. Check that the agent version ends
`status: active` and that the run's and the release step's records link all three PRs.

**Acceptance Scenarios**:

1. **Given** a factory-agent run waiting on its feature PR, **When** a person merges it, **Then** the run opens the
   registry PR for the named agent and version and starts the release step for that registry PR.
2. **Given** a factory-agent run waiting on its feature PR, **When** a person closes it without merging, **Then** the run
   ends as abandoned and opens no registry PR.
3. **Given** a release step waiting on a registry PR, **When** a person merges the registry PR, **Then** the release step
   opens the release PR that sets that agent version active, and ends as released once that PR is merged.
4. **Given** a release step waiting on a registry PR, **When** a person closes the registry PR without merging, **Then**
   the release step ends as not released and makes no further registry change.
5. **Given** a registry PR that a person merges within seconds of it being opened, before the release step is fully
   started, **When** the release step starts, **Then** it still sees the merge and goes on as in scenario 3.
6. **Given** a release step waiting on a registry PR, **When** nobody merges or closes it within the maximum wait,
   **Then** the release step ends as timed out, makes no further registry change and leaves the PR open.

---

### User Story 4 - The `@swe-agent build` comment goes through the same run and the same checks (Priority: P2)

A developer writes `@swe-agent build` on a PR in a target repo. Instead of a sandbox run straight from GitHub Actions,
this now starts a normal product run, the same one `@pipeline-agent run` starts, with the plan check, the build checks and
the merge wait. The developer sees the same reaction and the same comments as for any other run.

**Why this priority**: Today this comment is a second way to get agent-written code into a PR with no check at all. The
pipeline's checks mean little while a gate-free path sits next to them.

**Independent Test**: On the disposable repo, write `@swe-agent build` on a PR. Check that a pipeline run starts for that
PR, that no Build commit (agent-written code) is pushed before the plan is approved, and that no GitHub Actions job starts a sandbox.

**Acceptance Scenarios**:

1. **Given** a PR on an allowed repo, **When** a person with write access writes `@swe-agent build`, **Then** a product
   run starts for that PR exactly as `@pipeline-agent run kind=product` would start it. `@swe-agent build` itself means
   the product kind; it takes no other words.
2. **Given** the same comment on a repo that is not on the bridge's allowed list, **When** it is posted, **Then** no run
   starts and no code is pushed.
3. **Given** a target repo that still has an old copy of `swe-agent-trigger.yml`, **When** the comment is posted,
   **Then** the GitHub Actions job finishes without error, starts no sandbox, pushes nothing, and posts one fixed note
   saying that nothing was built by this job and that a pipeline run starts only if the bridge is running (look for the
   start reaction).
4. **Given** a run already running for that PR, **When** a second `@swe-agent build` is posted, **Then** no second run
   starts and the reply names the run that is already running.

### Edge Cases

- **Merged before the checks finish.** A person merges the PR while the run is still building or waiting for a plan
  decision. The run stops its sandbox within 5 minutes of learning about it, pushes nothing more, and ends as **merged
  before checks**. It is not shipped, because the checks never passed. It posts one comment saying so.
- **Closed while building.** The run stops the same way, pushes nothing more, and ends as abandoned. Reopening the PR
  later does not revive the run; a new run must be started.
- **Merged by the bot account.** If the PR is merged by the GitHub App's own account (the agent's account), the run does
  not count it as shipped. It ends as failed, with a reason saying the bot merged the PR, so the operator sees it.
- **Commits pushed after "ready for review".** People may push to the branch while the run waits. The run does not build
  or check again. It records the commit its checks passed on and the PR's last commit before the merge, and marks the
  result "changed after checks" when the two differ.
- **A second start for the same PR.** While a run is in flight for a PR, another start command on that PR is refused
  with a reply naming the run in flight.
- **A replayed old "merged" event.** The run asks GitHub, sees the PR is still open, and keeps waiting.
- **The release step starts after its registry PR was already merged.** It checks the PR's state when it starts, sees
  the merge and goes on.
- **The PR is marked ready by hand before the checks pass.** The run does not fight it. The merge wait and its end states
  stay the same.
- **The target PR is not on GitHub any more** (repo deleted, PR number unknown). The backup check sees it and the run ends
  as abandoned with a reason saying the PR is gone.
- **GitHub is unreachable during a backup check.** The run tries again at the next interval. A failed check never ends the
  run.
- **A "PR closed" event for the factory repo.** The bridge accepts it only to pass it to a waiting release step. It never
  starts a run in the factory repo, and it does not add the factory repo to the list of repos runs may target.
- **The bridge is down when `@swe-agent build` is posted.** No run starts and the bridge posts no reply. A repo with an
  old `swe-agent-trigger.yml` still gets the fixed note (FR-030), which says a run starts only if the bridge is running;
  otherwise the missing start reaction is the only sign. This is accepted for internal, single-operator use.
- **Missing or unknown run kind.** A start command without a kind, or with an unknown one, is refused with a reply that
  lists the accepted kinds. Nothing guesses the kind.

## Requirements *(mandatory)*

### Functional Requirements

**Run kind and run identity**

- **FR-001**: Every run MUST be started with an explicit run kind: **product** (the run builds a feature in a target repo)
  or **factory agent** (the run builds one of the factory's own agents). The run kind MUST be visible on the running run
  and in its final result.
- **FR-002**: The start commands MUST be `@pipeline-agent run kind=product` and
  `@pipeline-agent run kind=factory-agent agent=<name> version=<version>`, plus `@swe-agent build` (FR-029). The bridge
  MUST refuse a `@pipeline-agent run` without a kind, or with an unknown one, and MUST reply on the PR with the accepted
  kinds. It MUST NOT infer the kind from the agent name, the repo or anything else. `mode=` becomes optional (today
  it is required, spec 002 FR-005): when it is left out, no mode is passed and spec 005 FR-001's default (rigorous)
  applies; `mode=vibe` is still refused, as spec 002 FR-005 says.
- **FR-003**: A factory-agent start MUST name the agent and the version, as today's run command does. A product start
  MUST NOT need an agent name or version.
- **FR-004**: A run's identity MUST be its target repo and PR number, for both kinds. At most one run MUST be in flight
  per target PR. A run MUST start only from a comment on an open PR; a start without a PR is out of scope. A second start for the same PR MUST be refused with a reply naming the run that is in flight, including a
  run started before this change under its old identity. This replaces spec 002's identity (repo, agent and version), which a product run cannot fill.
- **FR-005**: The bridge MUST be able to post a comment on a PR, not only add a reaction, so that FR-002, FR-004 and
  FR-029 can reply.

**Target PR state**

- **FR-006**: At run start the target PR MUST be a draft. Every run starts on a PR that already exists (FR-004 needs
  its number), so the run never opens the target PR itself. If that PR is not a draft, the run MUST turn it into a draft and post one comment saying why. This is the
  normal case, not a rare one: every run started by a comment starts on a PR a person already opened, so every such run
  turns that person's PR into a draft until the checks pass.
- **FR-007**: When all of the run's checks pass and the PR is still open, the run MUST mark the target PR ready for
  review and post one comment saying which checks passed, with a link to the run's recorded gate result (today the
  Eval-Gate's `eval_result`).
- **FR-008**: The run MUST NOT merge, close, reopen or approve the target PR, at any point and with any credential it
  holds (the sandbox's App token or the worker's own token). A merge by the GitHub App's own account MUST NOT count as
  shipped (see FR-010).
- **FR-009**: Live checks of this feature MUST run on a target repo whose main branch requires an approving review from
  a code owner, with a code-owners file that lists only people (no bot or App account), so an approval by the App does
  not count. Each live check MUST record who opened, who approved and who merged the PR. Because a person cannot approve
  their own PR, a live check needs a second person's GitHub account to approve; a merge through an admin bypass does not
  count as a pass.

**Watching the PR and end states**

- **FR-010**: A run MUST end in exactly one of these end states, recorded in its final result:
  - **shipped**: the checks passed and a person merged the PR;
  - **abandoned**: the PR was closed without merging, or it no longer exists;
  - **merged before checks**: the PR was merged before the checks passed;
  - **timed out**: the maximum wait expired;
  - **failed**: the run stopped on an error or a spent attempt budget, as today, or the bot account merged the PR.
- **FR-011**: From run start to run end, the run MUST watch the target PR's state on GitHub. After FR-007 it MUST wait
  until the PR is merged or closed, or until the maximum wait expires. The maximum wait MUST be configurable, with a
  default of 30 days.
- **FR-012**: For shipped and merged before checks, the final result MUST record the merge commit, the merge time and
  the GitHub account that merged. For abandoned, it MUST record who closed the PR and when, when GitHub reports it.
- **FR-013**: The final result MUST record the commit the checks passed on and the PR's last commit before the merge.
  When the two differ, the result MUST be marked "changed after checks". (The merge commit itself is not compared: a
  squash or rebase merge always makes a new commit.)
- **FR-014**: When the target PR is merged or closed before the checks pass, the run MUST stop its current stage. If
  that stage is running a sandbox, the run MUST stop the sandbox within 5 minutes of learning about the merge or close.
  It MUST push no further commits and MUST end as FR-010 says.
- **FR-015**: On timed out, the run MUST post one comment saying so and MUST leave the PR as it is.
- **FR-016**: The run MUST post exactly one closing comment, however many times it is told the PR closed.

**Sending the "PR closed" event**

- **FR-017**: The bridge MUST accept GitHub's "pull request closed" events, with the same signature check it uses for
  comment events today. Events that fail the check MUST be rejected and change nothing.
- **FR-018**: For a target repo on the allowed list, the bridge MUST tell the run in flight for that PR to look now. If
  no run is in flight for it, the bridge MUST ignore the event.
- **FR-019**: A run told to look now MUST ask GitHub for the PR's current state and act only on that answer. It MUST
  NOT act on what the event says (merged or not, merge commit, who merged). So a replayed old event can at most make the
  run look early.
- **FR-020**: For the factory repo, the bridge MUST accept "closed" events only to tell a release step waiting on that
  registry PR or release PR to look now. This MUST NOT let any command start a run in the factory repo.
- **FR-021**: An event delivered twice, or delivered after the run already ended, MUST change nothing. This MUST hold
  after a bridge restart too.
- **FR-022**: The run MUST also ask GitHub for the PR's state itself at a fixed interval (configurable, default 1 hour),
  so a lost event delays the end by at most one interval. A failed check MUST NOT end the run.

**Factory-agent runs and the registry**

- **FR-023**: For product runs, the run MUST NOT open a registry PR or change anything under `registry/`.
- **FR-024**: For factory-agent runs, the run MUST open the registry PR only after the feature PR is merged, writing the
  same files `register_activity` writes today, from the run's recorded gate result. A factory-agent run whose feature PR
  is closed without merging MUST open no registry PR. Opening the registry PR MUST be retried safely (an open registry PR
  on the same branch is reused, not duplicated). If it still fails, the run MUST end as shipped, because the feature code
  is merged, record the registry failure next to the merge facts, and post one comment telling the operator how to open
  the registry PR by hand.
- **FR-025**: After opening the registry PR, the factory-agent run MUST start the registry release step
  (`RegistryPromotionWaiterWorkflow`) for that registry PR. Starting it twice for the same registry PR MUST NOT create a
  second release step.
- **FR-026**: The release step MUST watch its registry PR the same way a run watches its target PR (FR-018 to FR-022):
  events only make it look now, it also checks at the fixed interval, and it has its own maximum wait (default 30 days).
  It MUST see a merge that happened before it started. It MUST end as **released** (registry PR merged, then the release
  PR that sets `status: active` merged), **not released** (registry PR or release PR closed without merging) or **timed
  out**. Not released and timed out MUST make no further registry change, and a timed-out release step MUST leave its
  open PR as it is.
- **FR-027**: A factory-agent run MUST end as shipped once its feature PR is merged and the registry PR is opened (or
  the registry step failed as FR-024 says). The
  release step that follows is its own run, with its own wait. The run's final result MUST link the feature PR, the
  registry PR and the release step; the release step's result MUST link the registry PR and the release PR.
- **FR-028**: Runs and release steps MUST be findable by repo, PR number, run kind and whether they are in flight or
  ended, and, once ended, by end state, so an operator can list what is waiting.

**The `@swe-agent build` comment**

- **FR-029**: The bridge MUST treat `@swe-agent build` on a PR as a product-run start for that PR, with the same rules as
  `@pipeline-agent run kind=product`: the allowed-repo list, the write-access check, the fork refusal and the
  duplicate-delivery check.
- **FR-030**: The reusable GitHub Actions workflow `swe-agent-build.yml` MUST no longer start a sandbox, run the agent,
  push or open a PR. It MUST still finish without error when an old copy of `swe-agent-trigger.yml` in a target repo
  calls it, and MUST post the same fixed note every time: nothing was built by this job, and a pipeline run starts only
  if the bridge is running (look for the start reaction). (It cannot tell which repos the bridge allows, because that list lives only on the bridge host. On an
  allowed repo the PR therefore gets this note and the bridge's own reply.)
- **FR-031**: After this feature, no path in this repo that a GitHub comment or event can trigger MUST be able to push
  agent-written code or open a PR outside a pipeline run.

**Compatibility**

- **FR-032**: Runs started before this change MUST finish the way they would have before (ending in
  `register_activity`), so their recorded history replays without error. Such runs carry no run kind; the run kind is
  required at the bridge, not in the recorded input of an old run.
- **FR-033**: The gate commands the bridge accepts today (`plan_approved`, `plan_rejected: …` and the others) MUST keep
  working unchanged.

### Key Entities

- **Run kind**: product or factory agent. Set once at start, never changed. Runs started before this change have none.
- **Run identity**: the target repo plus the PR number. At most one run in flight per target PR.
- **End state**: shipped, abandoned, merged before checks, timed out or failed, with the facts FR-012 and FR-013 list.
  Spec 018 (run ledger) is expected to store it.
- **Target PR**: the PR in the target repo that carries the run's work. Draft until the checks pass, then ready for review.
- **Registry PR**: the factory-repo PR that writes an agent version's registry entry. Only factory-agent runs open one,
  and only after their feature PR is merged.
- **Release PR**: the factory-repo PR the release step opens once the registry PR is merged. It sets `status: active`.
- **Registry release step**: the existing `RegistryPromotionWaiterWorkflow`, now started for each registry PR. It ends
  as released, not released or timed out.
- **"Look now" nudge**: what the bridge sends a waiting run or release step when GitHub reports a PR closed. It carries
  no facts; the run asks GitHub itself.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a live check on the disposable repo, a product run whose checks pass ends as shipped within 5 minutes of
  a person merging its PR, and the factory repo gets 0 registry PRs from it.
- **SC-002**: In the same live check, closing a waiting run's PR without merging ends the run as abandoned within 5
  minutes, and the run pushes 0 commits after the close.
- **SC-003**: Closing the PR while the run is building stops the sandbox within 5 minutes, and the run pushes 0 commits
  after it learned of the close.
- **SC-004**: With the bridge stopped while the PR is merged, the run still ends as shipped within one backup-check
  interval (default 1 hour).
- **SC-005**: Delivering the same "closed" event 3 times, plus letting the backup check see the merge, produces exactly
  1 end state and exactly 1 closing comment. A validly signed "merged" event for a PR that GitHub reports as still open
  (in a test, a payload signed with the webhook secret) leaves the run waiting.
- **SC-006**: A factory-agent run on a disposable stand-in for the factory repo goes from start to `status: active` for
  its agent version through 3 merged PRs (feature PR, registry PR, release PR), each merged by a person, with no step
  started by hand. This is the first time the registry release step (what docs/70 calls Deploy) runs end to end.
- **SC-007**: Over 5 test `@swe-agent build` comments on the disposable repo and 2 on a repo not on the allowed list, 0
  commits are pushed and 0 PRs are opened by anything other than a pipeline run, and every run that reached the Eval-Gate
  has a recorded gate result.
- **SC-008**: In every test run, no credential the run holds (the sandbox's App token or the worker's own token)
  merges, closes or approves a PR: 0 such actions. A test merge by the bot account ends
  the run as failed, never as shipped.
- **SC-009**: A recorded history of a run started before this change, kept as a test fixture, replays without error and
  ends in the old registry step.
- **SC-010**: A start command without a run kind, or with an unknown one, is refused every time, with a reply listing the
  accepted kinds. A second start for a PR that has a run in flight is refused every time.

## Assumptions

- **Registry step after the feature merge (operator decided 2026-10-17).** The registry PR is opened after the feature PR merges, not when the
  checks pass as today. An agent version should only enter the registry for code that is actually on the main branch.
  This also settles a conflict: docs/70 ties the release step to the target PR's merge, while the release step's own code
  ties it to the registry PR. Under this spec all three PRs matter, in order: the feature PR's merge opens the registry
  PR, the registry PR's merge opens the release PR, and the release PR's merge marks the version active. It changes the
  order in spec 005 FR-018, which ends a run "through Register" right after the checks pass.
- **The person's PR is turned into a draft (operator decided 2026-10-17).** FR-006. It tells reviewers the PR is not ready yet. The
  alternative is to leave the PR as it is and only comment; then "ready for review" (FR-007) becomes a comment, not a
  state change.
- **Only a person's merge ships (operator decided 2026-10-17).** FR-008 and FR-009. The sandbox's token (spec 013) can merge and approve, so a
  merge by the bot account is treated as a failure, and live checks use a repo that requires a code owner's review, with
  only people as code owners. Under spec 013 the bot opened the PR; now a person does, so a plain "one approving review"
  rule could be met by the bot's own approval. The live check therefore needs a second person to approve.
- **Run identity changes (reopens specs 002 and 005).** Spec 002 identifies a run by repo, agent and version, and so do
  spec 005 FR-008, FR-009, SC-004 and its clarification. This spec also changes spec 002 FR-001 (the bridge reads only
  comment events today) and FR-005 (the start command's exact words). A product run has no
  agent or version of its own, so this spec identifies every run by repo and PR number (FR-004). Old runs keep their old
  IDs. Because the PR number is the identity, a run only starts from a comment on an existing PR; the branch of
  `ensure_target_pr_activity` that opens a new PR is no longer used by new runs.
- **"Abandoned" here is not spec 005's abandon command.** In this spec, abandoned means the PR was closed without merging
  or no longer exists. Spec 005 FR-013 has an operator command that abandons a run; when 005 lands, its runs should end in
  this spec's abandoned state too, with a reason that says the operator abandoned it.
- **Defaults.** Maximum wait 30 days, for runs and for release steps; backup check every hour. All are settings, not
  fixed values.
- **Spec 002's allowed-repo rule still holds.** Until spec 005 ships, the bridge's allowed list stays disposable-repo only
  (spec 002 FR-016). This feature does not change that. The factory repo is accepted for "closed" events only (FR-020),
  which can never start a run. Live checks for factory-agent runs use a disposable stand-in repo as the factory repo.
- **Behaviour change for `@swe-agent build`.** Today the comment builds at once on a pre-planned branch. After this
  feature it goes through the plan stage first, so a person must approve the plan before any code is pushed. That is the
  point of the change, but it makes the command slower.
- **The bridge must be running.** Without it, `@swe-agent build` does nothing. Acceptable for internal, single-operator
  use (spec 002's usage constraint). Making the bridge always-on is out of scope.
- **The agent's local command line stays.** `harness/swe-agent/agent.py` can still be run by hand for development. It is
  not triggered by GitHub, so FR-031 does not cover it.
- **Which checks.** "The checks pass" means every blocking gate the run has at the time: today the Eval-Gate, later the
  outcome gate (015) and the quality and security gates (006, 007). This feature does not add or change a gate.
- **Long waits make worker versioning more urgent.** Runs that wait up to 30 days will span many worker deploys. Each
  workflow change then needs a replay-safe path (a new patch ID here) until Temporal worker versioning is adopted. That is
  known tech debt, not solved here.
- **Related specs.** Spec 005 FR-018 says a run ends "through the pipeline's standard terminal step (Register)"; after
  this feature that terminal step is the merge wait. Spec 008's status view should show the end states of FR-010. Spec
  018 (run ledger) stores them. Spec 015 (outcome gate, committed on its own branch, not on main yet) says in its
  scenario 3 that a run "continues to Register"; after this feature it continues to the merge wait. docs/70 §1.2 and §10 need updating to match when this is built.
- **Out of scope.** Deploying a target repo's code anywhere, auto-merge, cleanup of branches or PRs after abandon, the run
  ledger and metrics (spec 018), and making `mode=vibe` work (spec 005).
