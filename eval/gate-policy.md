# Eval/Gate Policy (§3.6)

Braintrust is the promotion gate (CI-style rejection, not advisory — the
PDF's "buy, never build" verdict applies to the tool; the *threshold* is
still this factory's own decision, encoded here).

## Promotion threshold
A candidate agent version promotes to `registry/` only if:
- All `success_criteria` from its spec score >= pass on the sandbox trace
- No `guardrails.requires_human_approval` item is untouched without sign-off

## On fail
Route back to Build (`harness/`) with the failing eval trace attached — not
a bare fail signal (architecture doc §2). Braintrust trace -> Langfuse
(`observability/`) for the human debugging that follows.

## Ongoing (production) scoring
Same Braintrust project, scheduled re-scoring against live Langfuse traces —
this is what feeds the Monitor -> Retire/Version decision gate.
