from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RESOLVER_CONTRACT_PATH = (
    REPO_ROOT / "docs" / "maintainer" / "VALIDATION-RESOLVER-CONTRACT.md"
)


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def test_validation_resolver_contract_doc_identifies_authority() -> None:
    contract = RESOLVER_CONTRACT_PATH.read_text(encoding="utf-8")
    normalized_contract = _normalize_text(contract)
    docs_readme = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    guardrails = (REPO_ROOT / "docs" / "maintainer" / "GUARDRAILS.md").read_text(
        encoding="utf-8"
    )

    assert "# Validation plan resolver contract" in contract
    assert "issue `#234`" in contract
    assert "validation_plan_resolver.py" in contract
    assert "validation_policy.py" in contract
    assert "validation_policy.yml" in contract
    assert "ValidationPlan" in contract
    assert "resolve_validation_plan" in contract

    assert "VALIDATION-RESOLVER-CONTRACT.md" in docs_readme
    assert "shared validation plan resolver entrypoint" in docs_readme
    assert "VALIDATION-RESOLVER-CONTRACT.md" in guardrails
    assert "Shared validation plan resolver and routing" in guardrails
