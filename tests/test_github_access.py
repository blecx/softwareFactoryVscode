import json
import subprocess
import sys
from pathlib import Path


def test_github_access_status_json_shape():
    """Verify that 'status --json' returns all required lanes and no secret strings."""
    script_path = Path(__file__).parent.parent / "scripts" / "github_access.py"

    result = subprocess.run(
        [sys.executable, str(script_path), "status", "--json"],
        capture_output=True,
        text=True,
        check=True,
    )

    data = json.loads(result.stdout)
    assert "lanes" in data

    lanes = data["lanes"]
    required_lanes = ["git_transport", "signing", "github_api"]

    for lane in required_lanes:
        assert lane in lanes
        assert "status" in lanes[lane]
        assert "notes" in lanes[lane]

        # Verify no secret-looking values are leaked in placeholder
        # For now, it should just be "unknown"
        assert lanes[lane]["status"] == "unknown"
        assert "ADR-019" in lanes[lane]["notes"]


def test_github_access_status_human():
    """Verify that 'status' returns an exit code of 0 and expected string output."""
    script_path = Path(__file__).parent.parent / "scripts" / "github_access.py"

    result = subprocess.run(
        [sys.executable, str(script_path), "status"],
        capture_output=True,
        text=True,
        check=True,
    )

    assert "GitHub Access Status" in result.stdout
    assert "git_transport" in result.stdout
    assert "signing" in result.stdout
    assert "github_api" in result.stdout
