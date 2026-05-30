from pathlib import Path

import yaml


def test_github_access_script_in_policy():
    """Regression test extending bash gateway policy for github access helper"""
    repo_root = Path(__file__).parent.parent
    policy_path = repo_root / "configs" / "bash_gateway_policy.default.yml"

    assert policy_path.exists(), "Bash gateway policy file is missing"

    with open(policy_path, encoding="utf-8") as f:
        policy = yaml.safe_load(f)

    repo_maintenance = policy.get("profiles", {}).get("repo-maintenance", {})
    scripts = repo_maintenance.get("scripts", [])

    assert (
        "scripts/github_access.py" in scripts
    ), "scripts/github_access.py not found in the repo-maintenance profile"
