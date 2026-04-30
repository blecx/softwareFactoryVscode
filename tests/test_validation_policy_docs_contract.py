from __future__ import annotations

from pathlib import Path

from factory_runtime.agents.validation_policy import (
    CANONICAL_VALIDATION_POLICY_DOCUMENTATION_PATH,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_DOC_PATH = REPO_ROOT / CANONICAL_VALIDATION_POLICY_DOCUMENTATION_PATH


def test_validation_policy_contract_doc_identifies_authority_and_deferred_surfaces() -> (
    None
):
    contract = CONTRACT_DOC_PATH.read_text(encoding="utf-8")
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
    assert "configs/validation_policy.yml" in contract
    assert "factory_runtime/agents/validation_policy.py" in contract
    assert "issue `#228`" in contract
    assert "merge-full" in contract
    assert "production" in contract
    assert "scripts/local_ci_parity.py" in contract
    assert ".github/workflows/ci.yml" in contract
    assert "VALIDATION-POLICY-CONTRACT.md" in docs_readme
    assert "four-level model" in docs_readme
    assert "VALIDATION-POLICY-CONTRACT.md" in guardrails
    assert "changed-surface selection contract" in guardrails
