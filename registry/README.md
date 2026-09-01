# Agent Registry (§3.7 Deployment/Lifecycle)

Git-backed catalog — no vendor product exists for this at the pilot scale
(architecture doc §3.7: "the pattern is assembled, not bought"). CI
(`.github/workflows/registry-gate.yml`) blocks Deploy unless an agent has a
registry entry here.

## Layout

```
registry/agents/<agent-name>/
  manifest.yaml       # identity, current version, owner, status
  versions/
    v1.yaml           # one file per promoted version, immutable once written
  SKILL.md            # portable skill definition (owned format, not vendor-locked)
```

## Operations (mirrors UiPath Maestro / MS Agent 365 registry ops, §3.7)

| Op | How |
|---|---|
| Register | New `manifest.yaml` + `versions/v1.yaml`, PR merged after Eval/Gate pass |
| Version | New `versions/vN.yaml`, `manifest.yaml.current_version` bumped |
| Rollback | `manifest.yaml.current_version` set back to prior `vN`, PR + CI re-check |
| Retire | `manifest.yaml.status: retired`, agent deregistered from Deploy |

## Portability metric (§1.4)

Every entry's skill/tool definitions live in `SKILL.md` / MCP manifest
format here — the metric this scaffold optimizes for is "% of agents whose
definitions are in this owned format," not vendor registry lock-in.
