from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNNER_CONTRACT_PATH = (
    REPO_ROOT / "docs" / "maintainer" / "VALIDATION-RUNNER-CONTRACT.md"
)


def test_validation_runner_contract_doc_identifies_authority_and_deferred_callers() -> (
    None
):
    contract = RUNNER_CONTRACT_PATH.read_text(encoding="utf-8")
    docs_readme = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    guardrails = (REPO_ROOT / "docs" / "maintainer" / "GUARDRAILS.md").read_text(
        encoding="utf-8"
    )

    assert "# Validation runner contract and structured reporting" in contract
    assert "issue `#235`" in contract
    assert "validation_plan_resolver.py" in contract
    assert "validation_runner.py" in contract
    assert "validation_policy.py" in contract
    assert "per-bundle status, timing, and terminal outcome" in contract
    assert "watchdog.max_minutes" in contract
    assert "effective_budget_minutes" in contract
    assert "scripts/local_ci_parity.py" in contract
    assert ".github/workflows/ci.yml" in contract
    assert "## Structured report contract" in contract
    assert "## Caller boundary and deferred migrations" in contract
    assert "tests/test_validation_runner.py" in contract
    assert "tests/test_validation_runner_docs_contract.py" in contract

    assert "VALIDATION-RUNNER-CONTRACT.md" in docs_readme
    assert "shared validation runner/reporting contract" in docs_readme
    assert "VALIDATION-RUNNER-CONTRACT.md" in guardrails
    assert "Shared validation runner and reporting contract" in guardrails
    assert "structured validation results" in guardrails
