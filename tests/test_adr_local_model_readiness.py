from pathlib import Path

import pytest


def test_adr_local_model_readiness_contract():
    adr_path = Path(
        "docs/architecture/ADR-019-Provider-Agnostic-LLM-Execution-and-Local-Model-Readiness.md"
    )
    assert adr_path.exists(), "ADR file missing"
    content = adr_path.read_text()

    assert (
        "GitHub" in content and "baseline" in content.lower()
    ), "Must keep GitHub as current production baseline"
    assert (
        "local-provider eligibility gates" in content.lower()
        or "eligibility gates" in content.lower()
    ), "Must define local-provider eligibility gates"
