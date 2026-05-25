import re
from pathlib import Path


def test_runbook_reason_code_coverage():
    docs_dir = Path("docs/ops")
    incident_doc = docs_dir / "INCIDENT-RESPONSE.md"
    content = incident_doc.read_text()

    # Required reason codes that must be explicitly mapped to actions
    required_codes = [
        "missing-config",
        "missing-secret",
        "dependency-unhealthy",
        "endpoint-unreachable",
        "mcp-initialize-failed",
        "profile-mismatch",
    ]

    # 1. Assert the mapping table exists (semantic anchor)
    assert (
        "## Reason-code families and operator actions" in content
    ), "Missing Reason-code table semantic anchor"

    # 2. Extract the table contents following that heading up to the next heading
    section_match = re.search(
        r"## Reason-code families and operator actions\n(.*?)(?=\n## |\Z)",
        content,
        re.DOTALL,
    )
    assert section_match, "Could not extract Reason-code families section"
    table_content = section_match.group(1)

    # 3. Assert each reason code is covered in the mapping table
    for code in required_codes:
        assert (
            code in table_content
        ), f"Reason code '{code}' is not covered in the operator actions table"

    # 4. Assert the target semantic anchors (headings) for resolution exist
    assert "## Startup failure or runtime not ready" in content
    assert "## Unhealthy service or degraded runtime" in content
    assert "## Missing secret, missing config, or config drift" in content


def test_monitoring_surface_coverage():
    docs_dir = Path("docs/ops")
    monitoring_doc = docs_dir / "MONITORING.md"
    content = monitoring_doc.read_text()

    # Monitoring runbook should reference reason codes explicitly under the services section
    assert "### `services`" in content, "Missing services JSON shape anchor"
    assert (
        "reason code" in content.lower()
    ), "Monitoring runbook must mention triage via reason codes"


def test_backup_restore_surface_coverage():
    docs_dir = Path("docs/ops")
    doc = docs_dir / "BACKUP-RESTORE.md"
    content = doc.read_text()

    # Asserting basic semantic anchors are present for disaster recovery expectations
    assert "## Supported restore contract" in content
    assert "## Canonical roundtrip recovery flow" in content
