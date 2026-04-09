import pytest
from pathlib import Path
from tests.test_factory_install import run_python_script

def test_verifier_flags_legacy_root_folder_as_transitional_mode(tmp_path: Path):
    target_repo = tmp_path / "throwaway-target"
    target_repo.mkdir(parents=True, exist_ok=True)
    legacy_dir = target_repo / ".softwareFactoryVscode"
    legacy_dir.mkdir(parents=True, exist_ok=True)

    verifier_script = Path("scripts/verify_factory_install.py").absolute()
    
    result = run_python_script(
        str(verifier_script),
        "--target",
        str(target_repo),
        "--no-smoke-prompt",
    )
    
    assert "transitional/legacy mode" in result.stdout
    assert "Please migrate to the namespace-first architecture" in result.stdout

