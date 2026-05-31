import json
from pathlib import Path

import jsonschema
import pytest


def test_model_execution_profiles():
    schema_path = Path("schemas/model-execution-profiles.schema.json")
    config_path = Path("configs/model-execution-profiles.json")

    assert schema_path.exists(), "Schema file is missing"
    assert config_path.exists(), "Config file is missing"

    with schema_path.open() as f:
        schema = json.load(f)

    with config_path.open() as f:
        config = json.load(f)

    # Validation against schema
    jsonschema.validate(instance=config, schema=schema)

    # Check that required profiles exist
    assert "github-mini" in config
    assert "github-full" in config

    # Check properties for github-mini
    mini = config["github-mini"]
    assert "file_cap" in mini
    assert "diff_budget" in mini
    assert "domain_cap" in mini
    assert "context_class" in mini
    assert "fallback_actions" in mini
    assert "tool_subset" in mini

    # Specific assertions matching issue requirements limits
    assert mini["file_cap"] <= 5
    assert mini["diff_budget"] <= 250
    assert mini["domain_cap"] == 1
