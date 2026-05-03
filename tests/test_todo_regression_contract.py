import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TODO_REGRESSION_SCRIPT = REPO_ROOT / "scripts" / "todo_app_regression.py"
CI_SIMULATION_SCRIPT = REPO_ROOT / "scripts" / "ci_simulation.py"


def _load_todo_regression_module():
    spec = importlib.util.spec_from_file_location(
        "todo_app_regression_under_test",
        TODO_REGRESSION_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_ci_simulation_module():
    spec = importlib.util.spec_from_file_location(
        "ci_simulation_under_test",
        CI_SIMULATION_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _seed_source_checkout(target_root: Path) -> Path:
    (target_root / "scripts").mkdir(parents=True, exist_ok=True)
    (target_root / ".copilot" / "skills" / "todo-app-regression").mkdir(
        parents=True,
        exist_ok=True,
    )
    (target_root / "configs").mkdir(parents=True, exist_ok=True)
    (target_root / "scripts" / "install_factory.py").write_text(
        "# source checkout marker\n",
        encoding="utf-8",
    )
    (
        target_root / ".copilot" / "skills" / "todo-app-regression" / "SKILL.md"
    ).write_text(
        (
            REPO_ROOT / ".copilot" / "skills" / "todo-app-regression" / "SKILL.md"
        ).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (
        target_root
        / ".copilot"
        / "skills"
        / "todo-app-regression"
        / "model-compatibility-cases.json"
    ).write_text(
        (
            REPO_ROOT
            / ".copilot"
            / "skills"
            / "todo-app-regression"
            / "model-compatibility-cases.json"
        ).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (target_root / "configs" / "llm.default.json").write_text(
        (REPO_ROOT / "configs" / "llm.default.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return target_root


def _seed_installed_host(host_root: Path) -> Path:
    factory_root = host_root / ".copilot" / "softwareFactoryVscode"
    return _seed_source_checkout(
        factory_root.parent.parent / ".copilot" / "softwareFactoryVscode"
    )


def test_skill_exists_and_declares_canonical_todo_regression_contract():
    skill_path = REPO_ROOT / ".copilot" / "skills" / "todo-app-regression" / "SKILL.md"
    text = skill_path.read_text(encoding="utf-8")

    assert skill_path.exists()
    assert "## Throwaway execution paths" in text
    assert ".tmp/todo-regression-run/workspace" in text
    assert ".copilot/softwareFactoryVscode/.tmp/todo-regression-run/workspace" in text
    assert "## Definition of done" in text
    assert "## Quality metrics" in text
    assert "## Model and provider compatibility checks" in text


def test_model_compatibility_cases_include_fixed_variants_and_generic_template():
    cases_path = (
        REPO_ROOT
        / ".copilot"
        / "skills"
        / "todo-app-regression"
        / "model-compatibility-cases.json"
    )
    payload = json.loads(cases_path.read_text(encoding="utf-8"))
    cases = payload["cases"]

    assert payload["schema_version"] == 1
    # Use >= 3 so the matrix can grow without breaking this test.
    assert len(cases) >= 3
    assert any(case["model"] == "openai/gpt-4o" for case in cases)
    assert any(case["model"] == "openai/gpt-4o-mini" for case in cases)
    assert any(case["template"] is True and case["model"] == "*" for case in cases)
    # Ensure at least one Anthropic and one Meta named case exist.
    assert any(
        "anthropic/" in case["model"] and not case.get("template") for case in cases
    )
    assert any("meta/" in case["model"] and not case.get("template") for case in cases)


def test_tests_readme_mentions_todo_regression_contract():
    readme_text = (REPO_ROOT / "tests" / "README.md").read_text(encoding="utf-8")

    assert "Todo-app throwaway regression contract" in readme_text
    assert "tests/test_todo_regression_contract.py" in readme_text
    assert "scripts/todo_app_regression.py" in readme_text


def test_resolve_throwaway_root_uses_repo_tmp_for_source_checkout(tmp_path: Path):
    module = _load_todo_regression_module()
    repo_root = _seed_source_checkout(tmp_path / "source-repo")

    factory_root, mode = module.detect_factory_layout(repo_root)
    throwaway_root = module.resolve_throwaway_root(repo_root, mode)

    assert factory_root == repo_root
    assert mode == module.SOURCE_CHECKOUT_MODE
    assert throwaway_root == repo_root / ".tmp" / "todo-regression-run"


def test_resolve_throwaway_root_uses_installed_factory_tmp_for_host(tmp_path: Path):
    module = _load_todo_regression_module()
    host_root = tmp_path / "host-project"
    factory_root = host_root / ".copilot" / "softwareFactoryVscode"
    _seed_source_checkout(factory_root)

    resolved_factory_root, mode = module.detect_factory_layout(host_root)
    throwaway_root = module.resolve_throwaway_root(host_root, mode)

    assert resolved_factory_root == factory_root
    assert mode == module.INSTALLED_HOST_MODE
    assert (
        throwaway_root
        == host_root
        / ".copilot"
        / "softwareFactoryVscode"
        / ".tmp"
        / "todo-regression-run"
    )


def test_semantic_rubric_accepts_alternate_supported_github_model_wording():
    module = _load_todo_regression_module()
    case = {
        "id": "alt-model",
        "provider": "github",
        "model": "anthropic/claude-3.7-sonnet",
        "response": (
            "Write only into .tmp/todo-regression-run/workspace. "
            "The todo app must add tasks, update existing tasks, mark tasks done or undone, "
            "remove tasks, show a no todos empty state, and persist data after reload."
        ),
    }

    result = module.evaluate_compatibility_case(
        case,
        allowed_workspace_markers=module.approved_workspace_markers(),
    )

    assert result.passed is True
    assert result.missing_checks == []


def test_semantic_rubric_rejects_missing_persistence_behavior():
    module = _load_todo_regression_module()
    case = {
        "id": "missing-persistence",
        "provider": "github",
        "model": "openai/gpt-4o-mini",
        "response": (
            "Create the todo app in .tmp/todo-regression-run/workspace. "
            "Support add, edit, complete or incomplete, delete, and empty state behavior."
        ),
    }

    result = module.evaluate_compatibility_case(
        case,
        allowed_workspace_markers=module.approved_workspace_markers(),
    )

    assert result.passed is False
    assert "persistence behavior" in result.missing_checks


def test_semantic_rubric_rejects_unsupported_provider():
    module = _load_todo_regression_module()
    case = {
        "id": "unsupported-provider",
        "provider": "openai",
        "model": "gpt-4.1",
        "response": (
            "Create the todo app in .tmp/todo-regression-run/workspace with create, edit, "
            "complete/incomplete, delete, empty state, and persistence after reload."
        ),
    }

    result = module.evaluate_compatibility_case(
        case,
        allowed_workspace_markers=module.approved_workspace_markers(),
    )

    assert result.passed is False
    assert "supported provider" in result.missing_checks


def test_run_regression_writes_report_inside_source_throwaway_workspace(tmp_path: Path):
    module = _load_todo_regression_module()
    repo_root = _seed_source_checkout(tmp_path / "source-repo")

    report = module.run_regression(repo_root)
    report_path = Path(report["report_path"])
    artifacts_path = Path(report["artifacts_path"])

    assert report["status"] == "passed"
    assert report["mode"] == module.SOURCE_CHECKOUT_MODE
    assert report_path.exists()
    assert artifacts_path.exists()
    assert (
        report_path
        == repo_root
        / ".tmp"
        / "todo-regression-run"
        / "workspace"
        / "reports"
        / "todo-app-regression-report.json"
    )
    assert report["unexpected_changes_outside_throwaway"] == []


def test_run_regression_accepts_active_config_model_not_in_fixed_fixture_matrix(
    tmp_path: Path,
):
    module = _load_todo_regression_module()
    repo_root = _seed_source_checkout(tmp_path / "source-repo")
    (repo_root / "configs" / "llm.default.json").write_text(
        json.dumps(
            {
                "provider": "github",
                "model": "anthropic/claude-3.7-sonnet",
                "temperature": 0.0,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.run_regression(repo_root)

    assert report["status"] == "passed"
    assert report["active_config"]["provider"] == "github"
    assert report["active_config"]["model"] == "anthropic/claude-3.7-sonnet"
    # claude-3.7-sonnet is intentionally NOT a named case; the report must
    # surface this so operators know they are relying on the generic template.
    assert report["active_config"]["named_case_coverage"] is False


def test_report_named_case_coverage_is_true_for_model_in_fixed_matrix(
    tmp_path: Path,
):
    """active_config.named_case_coverage must be True when llm.default.json names
    a model that has a dedicated entry in model-compatibility-cases.json."""
    module = _load_todo_regression_module()
    repo_root = _seed_source_checkout(tmp_path / "source-repo")
    # gpt-4o is a known fixed case in the cases file.
    (repo_root / "configs" / "llm.default.json").write_text(
        json.dumps(
            {
                "provider": "github",
                "model": "openai/gpt-4o",
                "temperature": 0.0,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.run_regression(repo_root)

    assert report["status"] == "passed"
    assert report["active_config"]["named_case_coverage"] is True


def test_run_regression_uses_host_factory_tmp_root_for_installed_mode(tmp_path: Path):
    module = _load_todo_regression_module()
    host_root = tmp_path / "host-project"
    factory_root = host_root / ".copilot" / "softwareFactoryVscode"
    _seed_source_checkout(factory_root)

    report = module.run_regression(host_root)
    report_path = Path(report["report_path"])

    assert report["status"] == "passed"
    assert report["mode"] == module.INSTALLED_HOST_MODE
    assert report_path == (
        host_root
        / ".copilot"
        / "softwareFactoryVscode"
        / ".tmp"
        / "todo-regression-run"
        / "workspace"
        / "reports"
        / "todo-app-regression-report.json"
    )


# ---------------------------------------------------------------------------
# CI simulation contract tests
# ---------------------------------------------------------------------------


def test_ci_simulation_dockerfile_exists_at_canonical_path():
    """The CI simulation Dockerfile must exist and declare python:3.13 as base."""
    dockerfile = REPO_ROOT / "docker" / "ci-simulation" / "Dockerfile"

    assert dockerfile.exists(), f"Dockerfile not found at {dockerfile}"
    text = dockerfile.read_text(encoding="utf-8")
    assert "FROM python:3.13" in text, "Dockerfile must use python:3.13 base image"
    assert "git" in text, "Dockerfile must install git"
    assert "GITHUB_ACTIONS" in text, "Dockerfile must set GITHUB_ACTIONS env var"


def test_ci_simulation_module_exposes_required_interface():
    """ci_simulation.py must expose all public symbols consumed by the regression."""
    module = _load_ci_simulation_module()

    required_attrs = [
        "BundleSimResult",
        "DriftFinding",
        "detect_docker_available",
        "build_ci_simulation_image",
        "run_bundle_local",
        "run_bundle_in_container",
        "compute_drift",
        "create_simulation_checkout",
        "cleanup_simulation_checkout",
        "run_ci_simulation",
        "SIMULATABLE_BUNDLES",
        "DRIFT_LOCAL_PASS_CI_FAIL",
        "DRIFT_LOCAL_FAIL_CI_PASS",
        "CONSISTENT_PASS",
        "CONSISTENT_FAIL",
        "DOCKERFILE_REL",
    ]
    for attr in required_attrs:
        assert hasattr(
            module, attr
        ), f"ci_simulation module is missing attribute: {attr}"

    # SIMULATABLE_BUNDLES must be a non-empty tuple containing the core bundles
    bundles = module.SIMULATABLE_BUNDLES
    assert isinstance(bundles, tuple) and len(bundles) >= 1
    assert "docs-contract" in bundles
    assert "workflow-contract" in bundles


def test_compute_drift_classifies_local_pass_ci_fail():
    """Drift categorisation: bundle passes locally but fails in CI → LOCAL_PASS_CI_FAIL."""
    module = _load_ci_simulation_module()
    local = [
        module.BundleSimResult(
            bundle="docs-contract",
            exit_code=0,
            passed=True,
            stdout="all good",
            stderr="",
            elapsed_seconds=1.0,
        )
    ]
    ci = [
        module.BundleSimResult(
            bundle="docs-contract",
            exit_code=1,
            passed=False,
            stdout="",
            stderr="FAILED 2 tests",
            elapsed_seconds=2.0,
        )
    ]

    findings = module.compute_drift(local, ci)

    assert len(findings) == 1
    assert findings[0].category == module.DRIFT_LOCAL_PASS_CI_FAIL
    assert findings[0].local_passed is True
    assert findings[0].ci_passed is False
    assert "docs-contract" in findings[0].detail


def test_compute_drift_classifies_local_fail_ci_pass():
    """Drift categorisation: bundle fails locally but passes in CI → LOCAL_FAIL_CI_PASS."""
    module = _load_ci_simulation_module()
    local = [
        module.BundleSimResult(
            bundle="workflow-contract",
            exit_code=1,
            passed=False,
            stdout="",
            stderr="local failure",
            elapsed_seconds=1.5,
        )
    ]
    ci = [
        module.BundleSimResult(
            bundle="workflow-contract",
            exit_code=0,
            passed=True,
            stdout="all good",
            stderr="",
            elapsed_seconds=1.8,
        )
    ]

    findings = module.compute_drift(local, ci)

    assert len(findings) == 1
    assert findings[0].category == module.DRIFT_LOCAL_FAIL_CI_PASS
    assert findings[0].local_passed is False
    assert findings[0].ci_passed is True


def test_compute_drift_classifies_consistent_pass():
    """Both environments pass → CONSISTENT_PASS, no drift."""
    module = _load_ci_simulation_module()
    local = [
        module.BundleSimResult(
            bundle="docs-contract",
            exit_code=0,
            passed=True,
            stdout="ok",
            stderr="",
            elapsed_seconds=1.0,
        )
    ]
    ci = [
        module.BundleSimResult(
            bundle="docs-contract",
            exit_code=0,
            passed=True,
            stdout="ok",
            stderr="",
            elapsed_seconds=1.0,
        )
    ]

    findings = module.compute_drift(local, ci)

    assert len(findings) == 1
    assert findings[0].category == module.CONSISTENT_PASS


def test_compute_drift_classifies_consistent_fail():
    """Both environments fail → CONSISTENT_FAIL, no drift but still a problem."""
    module = _load_ci_simulation_module()
    local = [
        module.BundleSimResult(
            bundle="docs-contract",
            exit_code=1,
            passed=False,
            stdout="",
            stderr="fail",
            elapsed_seconds=1.0,
        )
    ]
    ci = [
        module.BundleSimResult(
            bundle="docs-contract",
            exit_code=1,
            passed=False,
            stdout="",
            stderr="fail",
            elapsed_seconds=1.0,
        )
    ]

    findings = module.compute_drift(local, ci)

    assert len(findings) == 1
    assert findings[0].category == module.CONSISTENT_FAIL


def test_run_ci_simulation_skips_gracefully_when_docker_unavailable(
    tmp_path: Path, monkeypatch
):
    """run_ci_simulation must return a SKIPPED report when Docker is unavailable."""
    module = _load_ci_simulation_module()
    monkeypatch.setattr(module, "detect_docker_available", lambda: False)

    result = module.run_ci_simulation(tmp_path, tmp_path / ".tmp")

    assert result["skipped"] is True
    assert result["drift_detected"] is False
    assert result["available"] is False
    assert "Docker" in result["skip_reason"]
    assert result["bundles_skipped"] == list(module.SIMULATABLE_BUNDLES)
    assert result["local_results"] == []
    assert result["ci_results"] == []


def test_run_regression_report_always_includes_ci_simulation_key(tmp_path: Path):
    """run_regression() must always include ci_simulation in the report.

    When include_ci_simulation is not set (default=False), the key must be
    present and report the simulation as skipped — so callers never need to
    guard against a missing key.
    """
    module = _load_todo_regression_module()
    repo_root = _seed_source_checkout(tmp_path / "source-repo")

    report = module.run_regression(repo_root)  # default: include_ci_simulation=False

    assert "ci_simulation" in report
    ci_sim = report["ci_simulation"]
    assert ci_sim["skipped"] is True
    assert ci_sim["drift_detected"] is False
    # Status must still be "passed" when CI simulation was not requested
    assert report["status"] == "passed"


def test_run_regression_with_ci_simulation_mocked_skipped(tmp_path: Path, monkeypatch):
    """When include_ci_simulation=True but Docker is unavailable, status stays 'passed'."""
    module = _load_todo_regression_module()
    repo_root = _seed_source_checkout(tmp_path / "source-repo")

    # Monkeypatch the wrapper so Docker is never invoked in the test
    mock_ci_result = {
        "available": False,
        "skipped": True,
        "skip_reason": "Docker unavailable (mocked for test).",
        "image_tag": "",
        "dockerfile_path": "docker/ci-simulation/Dockerfile",
        "bundles_simulated": [],
        "bundles_skipped": ["docs-contract", "workflow-contract"],
        "local_results": [],
        "ci_results": [],
        "drift_findings": [],
        "drift_detected": False,
        "os_note": "",
        "elapsed_seconds": 0.0,
    }
    monkeypatch.setattr(
        module, "_run_ci_simulation_for_report", lambda *a, **kw: mock_ci_result
    )

    report = module.run_regression(repo_root, include_ci_simulation=True)

    assert "ci_simulation" in report
    assert report["ci_simulation"]["skipped"] is True
    # Skipped CI simulation + all quality metrics pass → overall status is "passed"
    assert report["status"] == "passed"


def test_run_regression_with_ci_simulation_drift_detected_yields_drift_warning(
    tmp_path: Path, monkeypatch
):
    """When include_ci_simulation=True and drift is detected, status is 'drift-warning'."""
    module = _load_todo_regression_module()
    repo_root = _seed_source_checkout(tmp_path / "source-repo")

    mock_ci_result = {
        "available": True,
        "skipped": False,
        "skip_reason": "",
        "image_tag": "factory-ci-simulation:abc123",
        "dockerfile_path": "docker/ci-simulation/Dockerfile",
        "bundles_simulated": ["docs-contract"],
        "bundles_skipped": [],
        "local_results": [{"bundle": "docs-contract", "passed": True, "exit_code": 0}],
        "ci_results": [{"bundle": "docs-contract", "passed": False, "exit_code": 1}],
        "drift_findings": [
            {
                "bundle": "docs-contract",
                "category": "LOCAL_PASS_CI_FAIL",
                "local_passed": True,
                "ci_passed": False,
                "detail": "Bundle 'docs-contract' passes locally but FAILS in the CI simulation.",
            }
        ],
        "drift_detected": True,
        "os_note": "python:3.13-slim vs ubuntu-latest",
        "elapsed_seconds": 42.0,
    }
    monkeypatch.setattr(
        module, "_run_ci_simulation_for_report", lambda *a, **kw: mock_ci_result
    )

    report = module.run_regression(repo_root, include_ci_simulation=True)

    assert report["status"] == "drift-warning"
    assert report["ci_simulation"]["drift_detected"] is True
    assert (
        report["ci_simulation"]["drift_findings"][0]["category"] == "LOCAL_PASS_CI_FAIL"
    )
