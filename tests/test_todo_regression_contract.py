import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TODO_REGRESSION_SCRIPT = REPO_ROOT / "scripts" / "todo_app_regression.py"


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
