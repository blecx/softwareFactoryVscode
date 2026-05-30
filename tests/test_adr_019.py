import os
from pathlib import Path

import pytest


def test_adr_019_github_access_credential_lanes_exists():
    """ADR-019 must exist and contain the required credential lane anchors."""
    adr_path = Path("docs/architecture/ADR-019-GitHub-Access-Credential-Lanes.md")
    assert adr_path.exists(), "ADR-019 file is missing"

    content = adr_path.read_text()

    # Assert existence of required headings/anchors per acceptance criteria
    assert (
        "### 1. Git Transport Lane" in content
        or "Git Transport" in content
        or "ssh-agent" in content
    )
    assert (
        "### 2. Git Signing Lane" in content
        or "FACTORY_GIT_SIGNING_PRIORITY" in content
    )
    assert "### 3. GitHub API Lane" in content or "GitHub API operations" in content

    # Assert the specifics
    assert (
        "ssh-agent" in content
    ), "SSH remote transport via ssh-agent default is missing"
    assert (
        "FACTORY_GIT_SIGNING_PRIORITY=ssh,gpg" in content
    ), "FACTORY_GIT_SIGNING_PRIORITY default is missing"
    assert (
        "token/gh/GitHub-App-style credentials" in content
        or "GitHub API operations continue to require" in content
    ), "GitHub API credentials rule is missing"

    assert (
        ".factory.env" in content and "forbidden" in content.lower()
    ), "Forbidding private keys in .factory.env is missing"
    assert (
        "keyring mounts" in content and "forbidden" in content.lower()
    ), "Forbidding default keyring mounts is missing"
