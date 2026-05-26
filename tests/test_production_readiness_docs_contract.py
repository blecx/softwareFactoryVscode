from pathlib import Path


def test_production_readiness_docs_contract_anchors():
    repo_root = Path(__file__).resolve().parent.parent
    readiness_doc = (repo_root / "docs" / "PRODUCTION-READINESS.md").read_text(
        encoding="utf-8"
    )

    # Stable semantic anchors, rather than brittle exact prose
    assert "ADR-013" in readiness_doc
    assert "ADR-012" in readiness_doc
    assert "ADR-008" in readiness_doc
    assert "ADR-014" in readiness_doc
    assert "software-factory.code-workspace" in readiness_doc
    assert "scripts/factory_stack.py" in readiness_doc
    assert "scripts/verify_factory_install.py" in readiness_doc
