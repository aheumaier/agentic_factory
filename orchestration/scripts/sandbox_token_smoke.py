"""Live sandbox-token smoke test (specs/013-sandbox-app-token quickstart V0).

Mints the Build sandbox's GitHub App token for TARGET the way
`run_swe_agent_activity` does, then proves what it can reach:

    cd orchestration && uv run --locked python scripts/sandbox_token_smoke.py TARGET

Prints the grant line, `target repo: HTTP <code>` (want 200), `token repos:
[...]` (want exactly TARGET's name: GitHub's own list of the repos the token
reaches, so the check holds for public repos too) and whether TARGET's default
branch is protected. Reads the App env from the repo .env (a worktree has
none: pass the main checkout's with `uv run --env-file`) and never prints the
token.
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

import aiohttp
from dotenv import dotenv_values

ORCH_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ORCH_ROOT.parent
sys.path.insert(0, str(ORCH_ROOT))

import activities  # noqa: E402 - needs ORCH_ROOT on sys.path

_API = "https://api.github.com"


async def main(target: str) -> int:
    env = dotenv_values(REPO_ROOT / ".env")
    for name in ("SWE_AGENT_APP_ID", "SWE_AGENT_APP_PRIVATE_KEY"):
        if env.get(name):
            os.environ[name] = env[name]
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        minted = await activities._mint_sandbox_token(target)
    except Exception as e:  # noqa: BLE001 - SandboxTokenMintFailed carries no secret
        print(f"MINT FAILED: {getattr(e, 'message', type(e).__name__)}")
        return 1

    headers = {"Authorization": f"Bearer {minted.token}",
               "Accept": "application/vnd.github+json"}
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        async with session.get(f"{_API}/repos/{target}") as r:
            target_status = r.status
            branch = (await r.json()).get("default_branch") if r.status == 200 else None
        async with session.get(f"{_API}/installation/repositories") as r:
            r.raise_for_status()
            reachable = sorted(repo["name"] for repo in (await r.json())["repositories"])
        print(f"target repo: HTTP {target_status}")
        print(f"token repos: {reachable}")
        if branch:
            async with session.get(f"{_API}/repos/{target}/branches/{branch}") as r:
                protected = (await r.json()).get("protected") if r.status == 200 else None
            print(f"default branch {branch}: protected={protected}")

    ok = target_status == 200 and reachable == [target.split("/")[1]]
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    sys.exit(asyncio.run(main(sys.argv[1])))
