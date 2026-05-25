import os
import tempfile

import pytest
import yaml

from scripts.workflow_language_loader import LanguageLoader, TermAmbiguityError


@pytest.fixture
def temp_project_root():
    with tempfile.TemporaryDirectory() as root:
        yield root


def create_yaml(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)


def test_loader_returns_separate_namespaces(temp_project_root):
    factory_data = {"terms": [{"term_id": "factory_term"}]}
    host_data = {"terms": [{"term_id": "host_term"}]}

    create_yaml(
        os.path.join(temp_project_root, "configs", "workflow_language.yml"),
        factory_data,
    )
    create_yaml(
        os.path.join(temp_project_root, ".copilot", "project-language.yml"), host_data
    )

    loader = LanguageLoader()
    namespaces = loader.load(temp_project_root)

    assert "factory" in namespaces
    assert "host" in namespaces
    assert "factory_term" in namespaces["factory"]
    assert "host_term" in namespaces["host"]

    # Confirm it does not merge host terms into factory term data
    assert "host_term" not in namespaces["factory"]
    assert "factory_term" not in namespaces["host"]


def test_loader_handles_missing_host_language(temp_project_root):
    factory_data = {"terms": [{"term_id": "factory_term"}]}
    create_yaml(
        os.path.join(temp_project_root, "configs", "workflow_language.yml"),
        factory_data,
    )

    loader = LanguageLoader()
    namespaces = loader.load(temp_project_root)

    assert "factory_term" in namespaces["factory"]
    assert len(namespaces["host"]) == 0


def test_term_collision_produces_blocker(temp_project_root):
    factory_data = {"terms": [{"term_id": "collide_term", "source": "factory"}]}
    host_data = {"terms": [{"term_id": "collide_term", "source": "host"}]}

    create_yaml(
        os.path.join(temp_project_root, "configs", "workflow_language.yml"),
        factory_data,
    )
    create_yaml(
        os.path.join(temp_project_root, ".copilot", "project-language.yml"), host_data
    )

    loader = LanguageLoader()
    namespaces = loader.load(temp_project_root)

    # Needs explicit context or ambiguity blocker
    with pytest.raises(TermAmbiguityError):
        loader.get_term("collide_term", namespaces)

    term_factory = loader.get_term("collide_term", namespaces, context="factory")
    assert term_factory["source"] == "factory"

    term_host = loader.get_term("collide_term", namespaces, context="host")
    assert term_host["source"] == "host"
