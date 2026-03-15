import json
import os
import pytest
from aws_cdk.assertions import Template, Match, Capture

# Injected by evaluate_template_with_cdk_assertions via environment variable.
# Never hardcode this path — always set TEMPLATE_JSON_PATH before running pytest.
_TEMPLATE_PATH = os.environ.get("TEMPLATE_JSON_PATH", "")

@pytest.fixture(scope="module")
def template() -> Template:
    if not _TEMPLATE_PATH:
        raise EnvironmentError(
            "TEMPLATE_JSON_PATH environment variable is not set. "
            "This file must be run via evaluate_template_with_cdk_assertions()."
        )
    if not os.path.exists(_TEMPLATE_PATH):
        raise FileNotFoundError(f"Template JSON not found at: {_TEMPLATE_PATH}")
    with open(_TEMPLATE_PATH) as f:
        return Template.from_json(json.load(f))


# ──────────────────────────────────────────────
# LLM-GENERATED ASSERTIONS INSERTED BELOW
# ──────────────────────────────────────────────

{assertions_placeholder}
