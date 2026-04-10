import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.test_factory_install import install_factory


def test_install_factory_removes_legacy_structure_after_spinning_down(tmp_path: Path):
    target_dir = tmp_path / "mock-repo"
    target_dir.mkdir()

    # Create legacy `.softwareFactoryVscode` and `.tmp/softwareFactoryVscode`
    legacy_factory = target_dir / ".softwareFactoryVscode"
    legacy_factory.mkdir()
    legacy_tmp = target_dir / ".tmp" / "softwareFactoryVscode"
    legacy_tmp.mkdir(parents=True)

    with patch("subprocess.run") as mock_run:
        # We only want to mock the factory_stack.py stop call during install
        # Let's mock everything in subprocess to avoid actual side effects
        from tests.test_factory_install import git

        git("init", cwd=target_dir)

        # Mock out the rest of the installation
        with patch.object(install_factory, "validate_target_repo"), patch.object(
            install_factory, "clone_factory"
        ), patch.object(
            install_factory, "update_factory", return_value="v1.0"
        ), patch.object(
            install_factory, "head_commit", return_value="abcdef"
        ), patch.object(
            install_factory, "run_command"
        ), patch.object(
            install_factory, "invoke_bootstrap"
        ):

            install_factory.main(["--target", str(target_dir)])

        # Check if subprocess.run was called to stop the legacy stack
        stop_called = False
        for call in mock_run.call_args_list:
            args, kwargs = call
            cmd = args[0]
            if "factory_stack.py" in str(cmd) and "stop" in cmd:
                stop_called = True
                break

        assert stop_called, "Should have stopped the legacy stack before deletion"
        assert not legacy_factory.exists(), "Legacy factory should be deleted"
        assert not legacy_tmp.exists(), "Legacy tmp should be deleted"


def test_bootstrap_auto_creates_data_directories(tmp_path: Path):
    target_dir = tmp_path / "target-repo"
    target_dir.mkdir()

    from tests.test_factory_install import bootstrap_host

    bootstrap_host.ensure_tmp_dir(target_dir)

    # Assert
    tmp_dir = target_dir / bootstrap_host.TMP_SUBPATH
    assert tmp_dir.exists()

    # Required data dirs must be created
    for sub in [
        "agent-script-runs",
        "mcp-docker-compose",
        "mcp-test-runner",
        "mcp-github-ops",
        "mcp-offline-docs",
    ]:
        assert (tmp_dir / sub).exists(), f"Data dir {sub} was not auto-created"
