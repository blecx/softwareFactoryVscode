import json
import os

import jsonschema
import pytest

SCHEMA_PATH = os.path.join(
    os.path.dirname(__file__), "..", "schemas", "agent-routing-contract.schema.json"
)


@pytest.fixture
def routing_schema():
    with open(SCHEMA_PATH, "r") as f:
        return json.load(f)


def test_valid_minimal_example(routing_schema):
    valid_data = {
        "agent": "@resolve-issue",
        "task_kinds": ["implementation"],
        "authority_rank": 10,
        "canonical_skill": ".copilot/skills/resolve/SKILL.md",
        "requirements": ["issue_number"],
        "forbidden_routes": ["@harness-bypass-resolution"],
        "human_only": False,
    }
    # Should not raise an exception
    jsonschema.validate(instance=valid_data, schema=routing_schema)


def test_valid_human_only_example(routing_schema):
    valid_data = {
        "agent": "@harness-bypass-resolution",
        "task_kinds": ["bypass"],
        "authority_rank": 0,
        "canonical_skill": "none",
        "requirements": [],
        "forbidden_routes": [],
        "human_only": True,
    }
    jsonschema.validate(instance=valid_data, schema=routing_schema)


def test_invalid_missing_required_fields(routing_schema):
    invalid_data = {
        "agent": "@test-agent"
        # missing other required fields
    }
    with pytest.raises(jsonschema.exceptions.ValidationError):
        jsonschema.validate(instance=invalid_data, schema=routing_schema)


def test_invalid_forbidden_field(routing_schema):
    invalid_data = {
        "agent": "@test-agent",
        "task_kinds": [],
        "authority_rank": 10,
        "canonical_skill": "doc",
        "requirements": [],
        "forbidden_routes": [],
        "extra_field": "not-allowed",
    }
    with pytest.raises(jsonschema.exceptions.ValidationError):
        jsonschema.validate(instance=invalid_data, schema=routing_schema)
