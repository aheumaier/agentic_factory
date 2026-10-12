# Quickstart: Per-Run GitHub App Token for the Build Sandbox

**Feature**: 013-sandbox-app-token | **Date**: 2026-10-11

**Usage Constraint (binding, from 009 and 011):** internal, single-operator use only. The seats and the GitHub App belong to the operator, the pipeline and its seat pool are never offered to third parties, and seat rotation is a knowingly accepted Consumer-Terms grey area.

Details live in [contracts/sandbox-token-activity.md](contracts/sandbox-token-activity.md) and [contracts/github-app-mint.md](contracts/github-app-mint.md). This page is the run guide.

## V0: Operator setup (once, by hand)

1. **App permissions** (GitHub → Settings → Developer settings → GitHub Apps → the swe-agent App → Permissions):
   - Repository: **Contents** read and write, **Pull requests** read and write, **Metadata** read.
   - Keep the rights the webhook bridge already uses.
   - **No Administration**, no Workflows. A token can never hold more than the App has.
2. **Install the App** on `aheumaier/agentic_factory` and `aheumaier/pm-agent-scratch-test` ("Only select repositories").
   - **Precondition per installed repo: branch rules on the default branch.** The token has Contents write, so where the default branch needs no approval the agent's bot can merge its own PR (architect finding A2). Checked 2026-10-11: `pm-agent-scratch-test` `main` is unprotected; `agentic_factory` `main` requires a PR with 0 approvals. The operator decides between:
     - (a) branch protection with **1 required approval** and `enforce_admins: false`, so the operator can still merge their own PRs. This reverses the operator's 2026-10-11 choice of `enforce_admins: true`.
     - (b) a **ruleset** that requires 1 approval, with the operator as the only bypass actor. This keeps admins bound by the rule for everything else.
     - Code does not enforce either. The smoke script below prints whether the target's default branch is protected.
3. **`.env`** (the operator edits it; no session reads it):
   - `SWE_AGENT_APP_ID=<App ID>`
   - `SWE_AGENT_APP_PRIVATE_KEY=<base64 of the .pem>`, made with `base64 -i <app>.private-key.pem | tr -d '\n'`.
   - The `.pem` comes from the App's settings → **Credentials** → **Key pairs** tab → **New key** (as of 2026-10-11; older GitHub UIs had it under "Private keys" at the bottom of General). A client secret (the **Client secrets** tab) is for the OAuth flow and is not used here.
4. **Check** with the operator's own `!` command (prints the grant, an HTTP status code and repo names, never a token). A worktree has no `.env` of its own, so pass the main checkout's with `--env-file`:
   ```
   ! cd orchestration && uv run --locked --env-file /Users/aheumaier/Codebox/agentic_factory/.env python scripts/sandbox_token_smoke.py aheumaier/pm-agent-scratch-test
   ```
   **Pass**:
   - a `minted for aheumaier/pm-agent-scratch-test` line with `repositories=['pm-agent-scratch-test']` and exactly the 3 rights;
   - `target repo: HTTP 200`;
   - `token repos: ['pm-agent-scratch-test']`: GitHub's own list of the repos the token reaches, so it can't push to any other repo. (Asking for another repo and expecting a 404 does not work: `agentic_factory` is public, so any token can read it.)
   - A `default branch <name>: protected=<true|false>` line. `false` is not a failure of the script, but it means the precondition above is not met for that repo.

## V1: Unit tests

From the repo root, one after the other (live-Temporal tests time out when suites run at the same time):

```
uv run --locked ruff check .
uv run --locked pytest tests/ -q
cd orchestration && uv run --locked pytest -q
```

**Pass**: all green. The new tests cover: the narrowing request body; no cache (two mints, two requests); sandbox env holds the minted token and not the worker's `GH_TOKEN`; a failed mint creates no sandbox and raises `SandboxTokenMintFailed`; 5xx and network errors are retried up to 3 tries, a 4xx is not; grant mismatch fails; each activity call mints anew; the sandbox-failure `RuntimeError` carries no token; captured logs carry no token.

## V2: Live Build on the scratch repo

1. `make up`. No other worker on `agent-factory-pipeline`.
2. A fixture branch on `aheumaier/pm-agent-scratch-test` with a small `specs/<dir>/` (spec, plan, tasks), cut like 011's V5 step 2 (for example from commit `fe874169`, renamed to `v013-app-token`). The spec dir must be named after the branch (`specs/v013-app-token/`): the architect stage looks for `specs/<branch>/spec.md` and fails otherwise.
3. Worker, from `orchestration/`:
   ```
   FACTORY_REPO=aheumaier/pm-agent-scratch-test PYTHONUNBUFFERED=1 uv run --locked --env-file /Users/aheumaier/Codebox/agentic_factory/.env python worker.py 2>&1 | tee /tmp/013-worker.log
   ```
4. Start and approve the run with 011's driver:
   ```
   V5_WF_ID=v013-app-token-run V5_BRANCH=v013-app-token V5_POOL_ID=credential-pool uv run --locked python ../.handoff/v5/v5_driver.py start
   ```
   Watch `status`. When the architect stage is done and nothing is pending, run `approve`.

**Pass** means all of:
- the worker log has one `sandbox token minted for aheumaier/pm-agent-scratch-test` line per Build call, each with one repo and the 3 rights (SC-002);
- the feature PR's author is `<app-slug>[bot]`, not the operator (SC-001): `gh pr view <n> -R aheumaier/pm-agent-scratch-test --json author`;
- `grep -cE 'ghs_[A-Za-z0-9]{20}|github_pat_' /tmp/013-worker.log` prints `0`, and so does the same search over the run's history (`temporal workflow show -w v013-app-token-run -o json`) (SC-003).

Afterwards: stop the worker. Close the scratch PR or leave it for the operator.

**Known rejection (architect finding A3, fixed in 014):** the token has no Workflows right, on purpose. If the agent commits a change under `.github/workflows/`, GitHub rejects the push ("refusing to allow a GitHub App to create or update workflow … without `workflows` permission"), and every later checkpoint push fails with exit 1. That is the safety property working, not a token bug.

## V3: Mint failure fails the run (optional)

Start the worker with `SWE_AGENT_APP_ID` set to a wrong value (only in that shell), and start a run as in V2.

**Pass**: Build fails with `SandboxTokenMintFailed` naming the repo, no E2B sandbox was created for it, the seat is released, and no handoff was charged.

## After merge: branch protection (operator step, not code)

Apply the operator's choice from V0 step 2, option (a) or (b), on every repo the App is installed on. Until then, the agent's bot can merge its own PRs there.

With the App as PR author, the operator can approve the agent's PRs; with 1 required approval, the agent can no longer merge its own.

## Results

**V0, 2026-10-11: PASS.** The App was installed on `pm-agent-scratch-test` and `agentic_factory` ("Only select repositories"). The smoke script printed:
- `repositories=['pm-agent-scratch-test'] permissions={'contents': 'write', 'metadata': 'read', 'pull_requests': 'write'}`;
- `target repo: HTTP 200` and `token repos: ['pm-agent-scratch-test']`;
- `default branch main: protected=False`, so the V0 step 2 precondition is still open for the scratch repo.

The App itself holds 15 repository rights. These include Issues read and write, which the bridge uses, and read-only or unneeded ones such as Discussions read and write. It has no Administration and no Workflows right. Minted tokens are cut down to the 3 rights above. Trimming the App's own rights is an open operator step.

**V1, 2026-10-11: PASS** (T015).

**V2, 2026-10-12: PASS for the sandbox token, with two open points.** Run `v013-app-token-run` on fixture branch `v013-app-token` (PR #8 on `pm-agent-scratch-test`).
- **Sandbox used the App token:** `run_swe_agent_activity` completed, and the sandbox's push of `c5266ae` (2026-10-12T06:52:12Z) was made by `7ed-swe-agent[bot]` (`gh api repos/aheumaier/pm-agent-scratch-test/activity?ref=refs/heads/v013-app-token`). The pushes before it (fixture, architect plan) are the operator's, as expected: they use the worker's own token.
- **SC-003, no token written down:** 0 token-shaped matches in the worker log (135 lines), and 0 in the run history after base64-decoding its 59 payloads (control: the repo name appears 14 times in the decoded payloads, so the search reads real content).
- **SC-002, grant line: not visible in this run.** `worker.py` set up no log handler, so Python printed WARNING and up only, and the INFO grant line was dropped. The line itself is covered by the unit tests (caplog). Fixed in the same change: `worker.py` now opens INFO for the `temporalio.activity` logger only. Live visibility is proven on the next worker run.
- **SC-001, PR author: open on the Temporal path.** PR #8's author is the operator, because `ensure_target_pr_activity` opens the PR with the worker's own token before any sandbox exists (out of scope here). So the operator still can't approve this PR as a reviewer. The bot is the PR author only when the sandbox itself opens the PR. Follow-up: open the target PR with an App token too.
- The commits in the sandbox carry the git identity `claude`, not the bot. Only the push shows the bot.
- **The run failed after Build, outside 013:** Eval-Gate completed, then `register_activity` failed because the push of `registry/promote-v5-wordstats-0.0.1` to the scratch repo was rejected. That branch already exists there from 011's V5 runs. Register uses the worker's own token, not the sandbox token.
