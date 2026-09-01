"""Braintrust eval config skeleton (§3.6). Braintrust has no self-host
tier — pilot volume fits the free Starter plan (1GB trace, 10k scores/mo).
"""
import os

import braintrust

PROJECT = "agent-factory-pilot"


def load_success_criteria(spec_path: str) -> list[str]:
    # TODO: parse `success_criteria` out of the agent's spec.yaml/md
    raise NotImplementedError(spec_path)


def run_eval(spec_path: str, sandbox_trace: dict) -> None:
    criteria = load_success_criteria(spec_path)
    braintrust.init(project=PROJECT, api_key=os.environ["BRAINTRUST_API_KEY"])
    # TODO: score sandbox_trace against criteria, raise on regression so
    # this step blocks promotion per ../gate-policy.md.
    raise NotImplementedError((criteria, sandbox_trace))


if __name__ == "__main__":
    raise SystemExit("wire this to a sandbox trace before running")
