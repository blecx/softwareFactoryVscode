import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from scripts.github_access import probe_git_transport


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

        if lane != "git_transport":
            assert lanes[lane]["status"] == "unknown"


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


@patch("scripts.github_access.get_git_remote_url")
@patch("scripts.github_access.has_ssh_auth_sock")
@patch("scripts.github_access.get_ssh_add_status")
@patch("scripts.github_access.probe_github_ssh")
def test_probe_git_transport_ready(mock_ssh, mock_add, mock_sock, mock_remote):
    mock_remote.return_value = "git@github.com:test/repo.git"
    mock_sock.return_value = True
    mock_add.return_value = (True, "Keys loaded.")
    mock_ssh.return_value = (True, "Successfully authenticated.")

    result = probe_git_transport()
    assert result["status"] == "ready"


@patch("scripts.github_access.get_git_remote_url")
def test_probe_git_transport_https(mock_remote):
    mock_remote.return_value = "https://github.com/test/repo.git"

    result = probe_git_transport()
    assert result["status"] == "action_required"
    assert "HTTPS remote detected" in result["notes"]


@patch("scripts.github_access.get_git_remote_url")
@patch("scripts.github_access.has_ssh_auth_sock")
def test_probe_git_transport_no_sock(mock_sock, mock_remote):
    mock_remote.return_value = "git@github.com:test/repo.git"
    mock_sock.return_value = False

    result = probe_git_transport()
    assert result["status"] == "blocked"
    assert "SSH_AUTH_SOCK is missing" in result["notes"]
