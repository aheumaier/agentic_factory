# Eval/Gate Policy (§3.6)

Braintrust is the promotion gate (CI-style rejection, not advisory — the
PDF's "buy, never build" verdict applies to the tool; the *threshold* is
still this factory's own decision, encoded here).

## Promotion threshold
**Current (v1): a binary coverage gate.** `eval/braintrust/eval.config.py::run_eval`
runs only as the Temporal `eval_gate_activity` (`orchestration/activities.py`).
The activity clones the branch and passes the first `specs/*/spec.md` in
sorted order. A run passes only if all of these hold, checked in this order:
- at least one `- **SC-NNN**: …` bullet is found under that spec's
  `### Measurable Outcomes` section;
- the sandbox trace's `exit_code` is 0 (`AgentPipelineWorkflow` passes 0
  once `run_swe_agent_activity` returns; a failed Build raises instead);
- the sandbox trace has a `pr_url`.

It does not score any criterion's content. A branch with no
`specs/*/spec.md` fails with no criteria. A spec with no
`### Measurable Outcomes` heading raises a `ValueError` rather than failing
the gate.

**Eventual threshold (not current behaviour):** every success criterion
from the spec scores >= pass on the sandbox trace.

## On fail
Route back to Build (`harness/`) with the failing eval trace attached — not
a bare fail signal (architecture doc §2). Braintrust trace -> Langfuse
(`observability/`) for the human debugging that follows.

## Ongoing (production) scoring
Same Braintrust project, scheduled re-scoring against live Langfuse traces —
this is what feeds the Monitor -> Retire/Version decision gate.
