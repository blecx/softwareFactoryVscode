import json
from pathlib import Path

import jsonschema
import pytest

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "schemas"
    / "host-project-language.schema.json"
)


@pytest.fixture
def host_lang_schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_host_lang_schema_validates_minimal_valid_term(host_lang_schema):
    valid_term = {
        "term_id": "test_domain_term",
        "definition": "A meaningful business concept.",
        "bounded_context": "Core Business",
        "authority_source": "Domain Expert John",
        "aliases": ["domain idea"],
        "forbidden_meanings": ["Not a workflow term"],
        "ambiguity_action": "stop and ask business logic",
    }
    # Should not raise an exception
    jsonschema.validate(instance=valid_term, schema=host_lang_schema)


def test_host_lang_schema_rejects_missing_bounded_context(host_lang_schema):
    invalid_term = {
        "term_id": "missing_context",
        "definition": "A valid definition",
        "authority_source": "ADR-001",
        "aliases": ["valid phrase"],
        "forbidden_meanings": ["invalid phrase"],
        "ambiguity_action": "stop and ask",
    }
    with pytest.raises(jsonschema.exceptions.ValidationError):
        jsonschema.validate(instance=invalid_term, schema=host_lang_schema)


def test_host_lang_schema_rejects_missing_authority_source(host_lang_schema):
    invalid_term = {
        "term_id": "missing_authority",
        "definition": "A valid definition",
        "bounded_context": "Core Business",
        "aliases": ["valid phrase"],
        "forbidden_meanings": ["invalid phrase"],
        "ambiguity_action": "stop and ask",
    }
    with pytest.raises(jsonschema.exceptions.ValidationError):
        jsonschema.validate(instance=invalid_term, schema=host_lang_schema)


def test_host_lang_schema_is_distinct_from_workflow_schema(host_lang_schema):
    # Tests assert the schema is for host-owned project language, not factory workflow language
    assert (
        host_lang_schema["title"] == "Host Project Language Schema"
    ), "Schema title mismatch."
    assert (
        "bounded_context" in host_lang_schema["properties"]
    ), "Missing host project specific field."
    assert (
        "classifier_task_kind" not in host_lang_schema["properties"]
    ), "Should not contain workflow-specific fields."
