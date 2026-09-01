"""Regression test: keep agent-spec schema and template frontmatter in sync.

`spec/schema/agent-spec.schema.json` declares the required shape of an
agent spec. `spec/templates/agent-spec.template.md` is the human-facing
template authors copy to start a new spec. Nothing else checks that the
template's frontmatter still carries every key the schema requires — this
test catches that drift immediately instead of letting it surface later
as a downstream validation failure on a real filled-in spec.

Deliberately does NOT run full JSON-Schema validation against the
template's frontmatter values (see spec FR-004): placeholders like
`tools: []` are legitimately incomplete and would fail full validation.
Only structural key-presence is checked.
"""

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "spec" / "schema" / "agent-spec.schema.json"
TEMPLATE_PATH = REPO_ROOT / "spec" / "templates" / "agent-spec.template.md"


def _load_schema_required_keys() -> list[str]:
    with SCHEMA_PATH.open() as f:
        schema = json.load(f)
    return schema.get("required", [])


def _load_template_frontmatter() -> dict:
    text = TEMPLATE_PATH.read_text()
    parts = text.split("---", 2)
    assert len(parts) >= 3, (
        f"{TEMPLATE_PATH} does not have a '---'-delimited frontmatter block "
        "(expected leading '---', frontmatter, then '---')"
    )
    frontmatter = yaml.safe_load(parts[1])
    assert isinstance(frontmatter, dict), (
        f"{TEMPLATE_PATH}'s frontmatter did not parse to a mapping "
        f"(got {type(frontmatter).__name__})"
    )
    return frontmatter


def test_template_frontmatter_has_all_schema_required_keys():
    required_keys = _load_schema_required_keys()
    assert required_keys, (
        f"{SCHEMA_PATH} declares no top-level 'required' keys — nothing to "
        "check; this is almost certainly not intended."
    )

    frontmatter = _load_template_frontmatter()

    missing = [key for key in required_keys if key not in frontmatter]
    assert not missing, (
        "Template frontmatter is missing schema-required key(s): "
        f"{missing}. Update {TEMPLATE_PATH} (or, if the schema changed in "
        "error, revert the schema) so the two stay in sync."
    )
