import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
CATALOG_PATH = REPO_ROOT / "manifests" / "ai-surface-catalog.json"
COPILOT_INSTRUCTIONS = REPO_ROOT / ".github" / "copilot-instructions.md"


def get_catalog():
    if not CATALOG_PATH.exists():
        pytest.skip(f"Catalog not found at {CATALOG_PATH}")
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_production_readiness_mandates_adr_013():
    catalog = get_catalog()
    if COPILOT_INSTRUCTIONS.exists():
        content = COPILOT_INSTRUCTIONS.read_text(encoding="utf-8")
        if "production-readiness" in content.lower():
            if (
                "ADR-013" not in content
                and "ADR-013-First Assessment Gate" not in content
            ):
                pytest.fail(
                    "copilot-instructions.md mentions production-readiness without mandating ADR-013."
                )
    failures = []
    for entry in catalog:
        file_path = entry.get("file", "")
        full_path = REPO_ROOT / file_path
        if full_path.exists():
            file_content = full_path.read_text(encoding="utf-8").lower()
            if (
                "production-readiness" in file_content
                or "production readiness" in file_content
            ):
                if "adr-013" not in file_content:
                    failures.append(
                        f"{file_path}: mentions production-readiness but does not mandate ADR-013"
                    )
    if failures:
        pytest.fail(
            "Found surfaces allowing production-readiness without ADR-013:\n"
            + "\n".join(failures)
        )


def test_docs_do_not_claim_architecture_authority():
    catalog = get_catalog()
    failures = []
    for entry in catalog:
        file_path = entry.get("file", "")
        if not file_path.startswith("docs/"):
            continue
        full_path = REPO_ROOT / file_path
        if full_path.exists() and not file_path.startswith("docs/architecture/"):
            file_content = full_path.read_text(encoding="utf-8").lower()
            forbidden_claims = [
                "normative source of truth",
                "architecture authority",
                "overrides adr",
            ]
            for claim in forbidden_claims:
                if claim in file_content:
                    failures.append(
                        f"{file_path}: makes forbidden authority claim '{claim}'"
                    )
    if failures:
        pytest.fail(
            "Found non-architecture docs claiming architecture authority:\n"
            + "\n".join(failures)
        )


def test_agent_wrappers_do_not_claim_architecture_authority():
    catalog = get_catalog()
    failures = []
    for entry in catalog:
        file_path = entry.get("file", "")
        if not file_path.startswith(".github/agents/"):
            continue
        full_path = REPO_ROOT / file_path
        if full_path.exists():
            file_content = full_path.read_text(encoding="utf-8").lower()
            forbidden_claims = [
                "normative source of truth",
                "architecture authority",
                "overrides adr",
                "canonical architecture",
            ]
            for claim in forbidden_claims:
                if claim in file_content:
                    failures.append(
                        f"{file_path}: agent wrapper makes forbidden authority claim '{claim}'"
                    )
    if failures:
        pytest.fail(
            "Found agent wrappers claiming architecture authority:\n"
            + "\n".join(failures)
        )


def test_standard_agent_does_not_route_to_bypass():
    catalog = get_catalog()
    failures = []
    for entry in catalog:
        file_path = entry.get("file", "")
        if file_path == ".github/agents/harness-bypass-resolution.md":
            continue
        if not file_path.startswith(".github/agents/") and not file_path.startswith(
            ".copilot/skills/"
        ):
            continue
        full_path = REPO_ROOT / file_path
        if full_path.exists():
            file_content = full_path.read_text(encoding="utf-8").lower()
            forbidden_routings = [
                "route to bypass",
                "delegate to @harness-bypass",
                "invoke @harness-bypass",
                "invoke the @harness-bypass",
                "suggest @harness-bypass",
                "suggest the @harness-bypass",
            ]
            for routing in forbidden_routings:
                if routing in file_content:
                    failures.append(
                        f"{file_path}: standard agent routes to bypass with '{routing}'"
                    )
    if failures:
        pytest.fail("Found standard agent routing to bypass:\n" + "\n".join(failures))


def test_p0_wrappers_require_preflight():
    p0_wrappers = [
        ".github/agents/resolve-issue.md",
        ".github/agents/pr-merge.md",
        ".github/agents/execute-approved-plan.md",
        ".github/agents/harness-bypass-resolution.md",
    ]
    failures = []
    required_phrases = [
        "workflow preflight",
        "routing-manifest",
        "manifest-backed routing",
    ]
    for wrapper in p0_wrappers:
        full_path = REPO_ROOT / wrapper
        if full_path.exists():
            content = full_path.read_text(encoding="utf-8").lower()
            if not any(phrase in content for phrase in required_phrases):
                failures.append(
                    f"{wrapper}: missing workflow preflight or manifest-backed routing checks lock"
                )

    if failures:
        pytest.fail(
            "P0 wrappers must explicitly mention workflow preflight or manifest-backed routing checks before action:\n"
            + "\n".join(failures)
        )
