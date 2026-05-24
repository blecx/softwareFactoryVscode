import json
import re
import subprocess
import sys
from pathlib import Path


def test_zero_placeholder_instruction_defects() -> None:
    repo_root = Path(__file__).parent.parent
    directories = [
        repo_root / ".copilot" / "skills",
        repo_root / ".github" / "prompts",
        repo_root / ".github" / "agents",
    ]
    for directory in directories:
        for p in directory.rglob("*.md"):
            content = p.read_text(encoding="utf-8")
            assert (
                "Follow domain guidelines." not in content
            ), f"File {p.relative_to(repo_root)} contains placeholder instruction"


def test_duplication_ceilings_for_targeted_shared_guardrails() -> None:
    repo_root = Path(__file__).parent.parent
    directories = [
        repo_root / ".copilot" / "skills",
        repo_root / ".github" / "prompts",
        repo_root / ".github" / "agents",
    ]

    # We count how many times "fast evidence-first ladder" appears
    evidence_first_count = 0
    formatter_first_count = 0

    for directory in directories:
        for p in directory.rglob("*.md"):
            content = p.read_text(encoding="utf-8")
            if "fast evidence-first ladder" in content.lower():
                evidence_first_count += 1
            if "formatter-first" in content.lower():
                formatter_first_count += 1

    # Targeted shared guardrails ceilings
    assert (
        evidence_first_count <= 5
    ), f"Ceiling exceeded for 'evidence-first': {evidence_first_count}"
    assert (
        formatter_first_count <= 10
    ), f"Ceiling exceeded for 'formatter-first': {formatter_first_count}"


def test_low_context_routing_fixtures() -> None:
    repo_root = Path(__file__).parent.parent
    catalog_path = repo_root / "manifests" / "ai-surface-catalog.json"
    assert catalog_path.exists(), "ai-surface-catalog.json must exist"

    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    descriptions = [r.get("description", "").lower() for r in catalog]

    # A deterministic check: verify there are no tautological routing words
    # Like "Use this to resolve issue workflow" for name "resolve-issue-workflow"
    for r in catalog:
        name = r.get("name", "").lower()
        desc = r.get("description", "").lower()
        if name and name.replace("-", " ") in desc:
            # We allow some, but verify we don't just echo the exact title
            # if description is exactly "use this to X" where X is the name
            if desc.startswith(f"use this to {name.replace('-', ' ')}"):
                assert False, f"Tautological description in {name}: '{desc}'"


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main(["-v", __file__]))
