from __future__ import annotations

import json
import re
from pathlib import Path

from factory_runtime.agents.validation_policy import (
    CANONICAL_VALIDATION_POLICY_DOCUMENTATION_PATH,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_DOC_PATH = REPO_ROOT / CANONICAL_VALIDATION_POLICY_DOCUMENTATION_PATH


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def test_validation_policy_contract_doc_identifies_authority_and_lock_suite() -> None:
    contract = CONTRACT_DOC_PATH.read_text(encoding="utf-8")
    normalized_contract = _normalize_text(contract)
    docs_readme = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    guardrails = (REPO_ROOT / "docs" / "maintainer" / "GUARDRAILS.md").read_text(
        encoding="utf-8"
    )

    assert "# Validation policy contract and official bundle taxonomy" in contract
    assert "## Four-level validation model" in contract
    assert "## Representative changed-surface selection rules" in contract
    assert "## Explicit local-vs-GitHub exceptions" in contract
    assert "fresh-checkout-bootstrap" in contract
    assert "runner-ownership-parity" in contract
    assert "issue `#230`" in contract
    assert "valid bundle-selection scenarios" in normalized_contract
    assert "invalid-policy rejection cases" in normalized_contract
    assert "watchdog.max_minutes" in contract
    assert "event-driven-deadline" in contract
    assert "45 minutes" in normalized_contract
    assert "effective enforced budget" in normalized_contract
    assert "## Contract lock test surfaces" in contract
    assert "configs/validation_policy.yml" in contract
    assert "factory_runtime/agents/validation_policy.py" in contract
    assert "tests/test_validation_policy.py" in contract
    assert "tests/test_validation_policy_selection_contract.py" in contract
    assert "tests/test_validation_policy_errors.py" in contract
    assert "issue `#228`" in contract
    assert "merge-full" in contract
    assert "production" in contract
    assert "scripts/local_ci_parity.py" in contract
    assert ".github/workflows/ci.yml" in contract
    assert "VALIDATION-POLICY-CONTRACT.md" in docs_readme
    assert "four-level model" in docs_readme
    assert "per-bundle watchdog/runtime budgets" in docs_readme
    assert "VALIDATION-POLICY-CONTRACT.md" in guardrails
    assert "changed-surface selection contract" in guardrails
    assert "bounded-runtime metadata" in guardrails


def test_wiki_projection_manifest_has_unique_slug_keys() -> None:
    """Fail CI when multiple manifest wiki_page entries normalize to the same slug.

    This detects filename-drift and collisions that previously produced
    duplicate pages on the live wiki (for example "Install and Update" vs
    "Install-and-Update"). Keeping this in the docs-contract bundle prevents
    regressions from being merged without maintainers noticing the collision.
    """

    repo_root = Path(__file__).resolve().parent.parent
    manifest_path = repo_root / "manifests" / "wiki-projection-manifest.json"
    if not manifest_path.exists():
        # No manifest to validate in some automation contexts; don't fail noisily.
        return

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    pages = [p.get("wiki_page") for p in data.get("pages", []) if p.get("wiki_page")]

    def normalize(name: str) -> str:
        base = (name + ".md") if not name.lower().endswith(".md") else name
        key = re.sub(r"[^0-9A-Za-z]+", "-", base).strip("-")
        return key.lower()

    mapping: dict[str, list[str]] = {}
    for p in pages:
        k = normalize(p)
        mapping.setdefault(k, []).append(p)

    collisions = {k: v for k, v in mapping.items() if len(v) > 1}
    if collisions:
        msgs = [f"{k}: {v}" for k, v in collisions.items()]
        raise AssertionError(
            "Found wiki projection manifest slug collisions. Normalize collisions:\n"
            + "\n".join(msgs)
        )
