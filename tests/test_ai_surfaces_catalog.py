import importlib.util
import os
import sys
from pathlib import Path

import pytest

scripts_dir = Path(__file__).parent.parent / "scripts"
script_path = scripts_dir / "validate-ai-surfaces.py"

spec = importlib.util.spec_from_file_location("validate_ai_surfaces", script_path)
validate_ai_surfaces = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate_ai_surfaces)


def test_parse_frontmatter():
    content = "---\nname: foo\ndescription: bar\n---\n# Content"
    meta, _ = validate_ai_surfaces.parse_frontmatter(content)
    assert meta["name"] == "foo"


def test_parse_frontmatter_chatagent():
    content = (
        "something\n```chatagent\n---\ndescription: agent foo\n---\ninner\n```\nmore"
    )
    meta, _ = validate_ai_surfaces.parse_frontmatter(content)
    assert meta["description"] == "agent foo"


def test_validate_form_b_valid(tmp_path):
    f = tmp_path / "valid.md"
    content = (
        "---\nname: Foo\ndescription: test\n---\n"
        "# Foo\n## Objective\n1\n## When to Use\n2\n"
        "## When Not to Use\n3\n## Required Sources\n- .copilot/some.md\n"
    )
    f.write_text(content, encoding="utf-8")

    res = validate_ai_surfaces.validate_file(f, tmp_path)
    assert res["form"] == "Form B"
    assert len(res["errors"]) == 0


def test_validate_form_b_missing_sections(tmp_path):
    f = tmp_path / "invalid.md"
    f.write_text("---\nname: Foo\n---\n# Foo\n## When to Use\n1", encoding="utf-8")

    res = validate_ai_surfaces.validate_file(f, tmp_path)
    assert "Expected exactly one '## Objective', found 0" in res["errors"]


def test_validate_placeholder(tmp_path):
    f = tmp_path / "invalid.md"
    content = (
        "---\nname: Foo\n---\n# Foo\n## Objective\n1\n## When to Use\n2\n"
        "## When Not to Use\nFollow domain guidelines."
    )
    f.write_text(content, encoding="utf-8")

    res = validate_ai_surfaces.validate_file(f, tmp_path)
    assert "Contains placeholder 'Follow domain guidelines.'" in res["errors"]


def test_validate_form_c_missing_authority(tmp_path):
    f = tmp_path / "agent.md"
    content = (
        "```chatagent\n---\ndescription: a\n---\n```\n## Objective\n1\n"
        "## When to Use\n2\n## When Not to Use\n3\n"
    )
    f.write_text(content, encoding="utf-8")

    res = validate_ai_surfaces.validate_file(f, tmp_path)
    assert res["form"] == "Form C"
    assert (
        "Missing authority references (no links to canonical owner paths)"
        in res["errors"]
    )


def test_duplicate_headings(tmp_path):
    f = tmp_path / "invalid.md"
    content = (
        "---\nname: Foo\n---\n# Foo\n## Objective\n1\n## When to Use\n2\n"
        "## When Not to Use\n3\n## Objective\n2"
    )
    f.write_text(content, encoding="utf-8")

    res = validate_ai_surfaces.validate_file(f, tmp_path)
    assert "Expected exactly one '## Objective', found 2" in res["errors"]
    assert "Duplicate heading found: '## Objective'" in res["errors"]
