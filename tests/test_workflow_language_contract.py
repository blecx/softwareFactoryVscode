import json
import os
from pathlib import Path

import jsonschema
import pytest

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent / "schemas" / "workflow-language.schema.json"
)


@pytest.fixture
def workflow_schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_workflow_schema_validates_minimal_valid_term(workflow_schema):
    valid_term = {
        "term_id": "test_term",
        "definition": "A valid definition",
        "authority_sources": ["ADR-013"],
        "allowed_phrases": ["valid phrase"],
        "forbidden_interpretations": ["invalid phrase"],
        "required_evidence": ["test passed"],
        "classifier_task_kind": "validation",
        "ambiguity_action": "stop and ask",
    }
    # Should not raise an exception
    jsonschema.validate(instance=valid_term, schema=workflow_schema)


def test_workflow_schema_rejects_missing_authority_sources(workflow_schema):
    invalid_term = {
        "term_id": "test_term",
        "definition": "A valid definition",
        "allowed_phrases": ["valid phrase"],
        "forbidden_interpretations": ["invalid phrase"],
        "required_evidence": ["test passed"],
        "classifier_task_kind": "validation",
        "ambiguity_action": "stop and ask",
    }
    with pytest.raises(jsonschema.exceptions.ValidationError) as exc_info:
        jsonschema.validate(instance=invalid_term, schema=workflow_schema)
    assert "'authority_sources' is a required property" in str(exc_info.value)


def test_workflow_schema_rejects_missing_ambiguity_action(workflow_schema):
    invalid_term = {
        "term_id": "test_term",
        "definition": "A valid definition",
        "authority_sources": ["ADR-013"],
        "allowed_phrases": ["valid phrase"],
        "forbidden_interpretations": ["invalid phrase"],
        "required_evidence": ["test passed"],
        "classifier_task_kind": "validation",
    }
    with pytest.raises(jsonschema.exceptions.ValidationError) as exc_info:
        jsonschema.validate(instance=invalid_term, schema=workflow_schema)
    assert "'ambiguity_action' is a required property" in str(exc_info.value)
