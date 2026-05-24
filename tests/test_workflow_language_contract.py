import json
import os
from pathlib import Path

import jsonschema
import pytest
import yaml

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent / "schemas" / "workflow-language.schema.json"
)
CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "configs" / "workflow_language.yml"
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


def test_workflow_config_exists_and_validates(workflow_schema):
    assert CONFIG_PATH.exists(), f"Config file not found at {CONFIG_PATH}"
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    assert "terms" in config, "Config must contain a 'terms' list"
    assert isinstance(config["terms"], list), "'terms' must be a list"

    expected_terms = {
        "accepted_adr",
        "derived_projection",
        "implementation_authority",
        "readiness_projection",
        "production_readiness_claim",
    }
    found_terms = set()

    for term in config["terms"]:
        # Validate against schema
        jsonschema.validate(instance=term, schema=workflow_schema)

        # Verify required specific terms based on Acceptance Criteria
        if "term_id" in term:
            found_terms.add(term["term_id"])

    # Check that all expected terms are defined
    missing_terms = expected_terms - found_terms
    assert not missing_terms, f"Missing required terms in config: {missing_terms}"


def test_execution_terms_coverage(workflow_schema):
    import yaml

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    found_terms = {term["term_id"]: term for term in config["terms"]}

    execution_terms = [
        "approved_plan",
        "issue_slice",
        "execution_surface",
        "github_truth",
        "checkpoint_truth",
        "blocker",
        "pending_timeout",
        "bypass",
        "closeout",
    ]

    for term in execution_terms:
        assert term in found_terms, f"Missing execution term: {term}"
        term_data = found_terms[term]

        # Test exact hallucination / ambiguity gap coverage based on Acceptance Criteria
        assert (
            len(term_data.get("required_evidence", [])) > 0
        ), f"{term} needs required_evidence"
        assert (
            len(term_data.get("forbidden_interpretations", [])) > 0
        ), f"{term} needs forbidden_interpretations"
        assert "ambiguity_action" in term_data, f"{term} needs ambiguity_action"
