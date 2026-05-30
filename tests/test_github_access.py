import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from scripts.github_access import (
    probe_git_transport,
    probe_github_api,
    probe_gpg_signing,
    probe_signing,
    probe_ssh_signing,
)


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


@patch("scripts.github_access.get_git_version")
@patch("scripts.github_access.get_git_config")
def test_probe_ssh_signing_blocked_by_version(mock_config, mock_version):
    mock_version.return_value = (2, 30)
    result = probe_ssh_signing()
    assert result["status"] == "blocked"
    assert "below 2.34" in result["notes"]


@patch("scripts.github_access.get_git_version")
@patch("scripts.github_access.get_git_config")
def test_probe_ssh_signing_ready(mock_config, mock_version):
    mock_version.return_value = (2, 34)
    mock_config.return_value = "ssh-ed25519 AAA..."
    result = probe_ssh_signing()
    assert result["status"] == "ready"


@patch("scripts.github_access.get_git_config")
@patch("subprocess.run")
def test_probe_gpg_signing_ready(mock_run, mock_config):
    mock_config.return_value = "DEADBEEF"
    mock_run.return_value.returncode = 0
    result = probe_gpg_signing()
    assert result["status"] == "ready"


@patch("scripts.github_access.get_git_config")
@patch("subprocess.run")
def test_probe_gpg_signing_missing_key(mock_run, mock_config):
    mock_config.return_value = "DEADBEEF"
    mock_run.return_value.returncode = 2
    result = probe_gpg_signing()
    assert result["status"] == "blocked"


@patch("scripts.github_access.probe_ssh_signing")
@patch("scripts.github_access.probe_gpg_signing")
def test_probe_signing_default_priority(mock_gpg, mock_ssh):
    mock_ssh.return_value = {"status": "ready", "notes": "ssh ok"}
    mock_gpg.return_value = {"status": "blocked", "notes": "gpg fail"}

    with patch.dict(os.environ, {}, clear=True):
        result = probe_signing()
        assert result["primary"] == "ssh"
        assert result["status"] == "ready"


@patch("scripts.github_access.probe_ssh_signing")
@patch("scripts.github_access.probe_gpg_signing")
def test_probe_signing_override_priority(mock_gpg, mock_ssh):
    mock_ssh.return_value = {"status": "ready", "notes": "ssh ok"}
    mock_gpg.return_value = {"status": "blocked", "notes": "gpg fail"}

    with patch.dict(os.environ, {"FACTORY_GIT_SIGNING_PRIORITY": "gpg,ssh"}):
        result = probe_signing()
        assert result["primary"] == "gpg"
        assert result["status"] == "blocked"
        assert "Fallback backend 'ssh' is ready" in result["notes"]


@patch("subprocess.run")
def test_probe_github_api_ready_env_only(mock_run):
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = (
        "Logged in to github.com account (GITHUB_TOKEN)\nToken: github_pat_11AAAAA"
    )
    mock_run.return_value.stderr = ""

    with patch.dict(os.environ, {"GITHUB_TOKEN": "github_pat_11AAAAA"}, clear=True):
        result = probe_github_api()

    assert result["status"] == "ready"
    assert "Sources: GITHUB_TOKEN" in result["notes"]
    assert "github_pat_11AAAAA" not in result["details"]
    assert "[REDACTED]" in result["details"]


@patch("subprocess.run")
def test_probe_github_api_blocked(mock_run):
    mock_run.return_value.returncode = 1
    mock_run.return_value.stdout = ""
    mock_run.return_value.stderr = (
        "You are not logged into any GitHub hosts.\nTo log in, run: gh auth login"
    )

    with patch.dict(os.environ, {}, clear=True):
        result = probe_github_api()

    assert result["status"] == "blocked"
    assert "GitHub API authentication failed" in result["notes"]
    assert "gh auth login" in result["details"]


@patch("subprocess.run")
def test_probe_github_api_not_found(mock_run):
    mock_run.side_effect = FileNotFoundError()

    with patch.dict(os.environ, {}, clear=True):
        result = probe_github_api()

    assert result["status"] == "blocked"
    assert "'gh' command not found" in result["notes"]
