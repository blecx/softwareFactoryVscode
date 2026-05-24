import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
CATALOG_PATH = REPO_ROOT / "manifests" / "ai-surface-catalog.json"

WEAK_PATTERNS = [
    r"Workflow or rule module extracted",
    r"Use this when working on tasks related to",
    r"^\s*$",  # Empty
]

ALLOWLIST = [
    ".copilot/skills/ux-responsive/SKILL.md",
    ".copilot/skills/ux-delegation-policy/SKILL.md",
    ".copilot/skills/resolve-issue-workflow/SKILL.md",
    ".copilot/skills/ux-a11y-basics/SKILL.md",
    ".copilot/skills/ux-consult-request/SKILL.md",
    ".copilot/skills/ux-ia-navigation/SKILL.md",
    ".copilot/skills/ux-context-sources/SKILL.md",
    ".copilot/skills/ux-pr-checklist/SKILL.md",
    ".copilot/skills/ux-artifact-grouping/SKILL.md",
    ".copilot/skills/interruption-recovery-workflow/SKILL.md",
    ".copilot/skills/harness-bypass/SKILL.md",
    ".copilot/skills/react-ts-testing-practices/SKILL.md",
    ".copilot/skills/a2a-communication/SKILL.md",
    ".github/agents/agents-catalog-maintainer.md",
    ".github/agents/workflow.md",
    ".github/agents/factory-operator.md",
]


def test_weak_descriptions():
    if not CATALOG_PATH.exists():
        pytest.skip(f"Catalog not found at {CATALOG_PATH}")

    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    failures = []

    for entry in catalog:
        desc = entry.get("description", "")
        file_path = entry.get("file", "")

        if file_path.replace("\\", "/") in dict.fromkeys(
            a.replace("\\", "/") for a in ALLOWLIST
        ):
            continue

        for pattern in WEAK_PATTERNS:
            if re.search(pattern, desc, re.IGNORECASE):
                failures.append(
                    f"{file_path}: matched weak pattern '{pattern}' with description '{desc}'"
                )
                break

    if failures:
        pytest.fail(
            "Found weak AI surface discovery descriptions:\n" + "\n".join(failures)
        )
