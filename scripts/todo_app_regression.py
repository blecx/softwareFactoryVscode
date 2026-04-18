#!/usr/bin/env python3
"""Run the canonical throwaway todo-app regression workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SOURCE_CHECKOUT_MODE = "source-checkout"
INSTALLED_HOST_MODE = "installed-host"
SUPPORTED_PROVIDER = "github"
SOURCE_THROWAWAY_ROOT = Path(".tmp") / "todo-regression-run"
INSTALLED_THROWAWAY_ROOT = (
    Path(".copilot") / "softwareFactoryVscode" / ".tmp" / "todo-regression-run"
)
SKILL_DIR_RELATIVE = Path(".copilot") / "skills" / "todo-app-regression"
SKILL_FILE_RELATIVE = SKILL_DIR_RELATIVE / "SKILL.md"
MODEL_CASES_RELATIVE = SKILL_DIR_RELATIVE / "model-compatibility-cases.json"
REPORT_RELATIVE = Path("reports") / "todo-app-regression-report.json"
ARTIFACTS_RELATIVE = Path("artifacts")
IGNORE_DIR_NAMES = {".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache"}
REQUIRED_SKILL_HEADINGS = [
    "## Objective",
    "## Canonical ownership",
    "## Throwaway execution paths",
    "## Minimum todo-app contract",
    "## Definition of done",
    "## Quality metrics",
    "## Model and provider compatibility checks",
    "## Execution steps",
    "## Reporting contract",
]
REQUIRED_FEATURE_TERMS = [
    "create todo",
    "edit todo",
    "mark complete/incomplete",
    "delete todo",
    "empty-state behavior",
    "persistence across reload/restart",
]
REQUIRED_DOD_TERMS = [
    "canonical skill committed under `.copilot`",
    "approved throwaway paths enforced",
    "minimum todo-app contract evaluated",
    "semantic model compatibility checks pass",
    "report written only in throwaway workspace",
    "no unexpected filesystem changes outside throwaway workspace",
]
REQUIRED_METRIC_TERMS = [
    "skill contract coverage: 100%",
    "definition of done coverage: 100%",
    "semantic compatibility rate: 100%",
    "throwaway cleanliness: 100%",
    "repeat-run stability: 100%",
]
SEMANTIC_KEYWORDS = {
    "create": ("create", "add"),
    "edit": ("edit", "update"),
    "toggle_complete": (
        "complete or incomplete",
        "complete/incomplete",
        "done or undone",
        "toggle",
        "mark tasks done",
        "mark complete",
    ),
    "delete": ("delete", "deleting", "remove"),
    "empty_state": (
        "empty state",
        "empty-state",
        "no todos",
        "no tasks",
    ),
    "persistence": (
        "persist",
        "persistence",
        "after reload",
        "across refreshes",
        "across reload",
        "localstorage",
        "local storage",
    ),
}


@dataclass
class CompatibilityResult:
    case_id: str
    provider: str
    model: str
    passed: bool
    missing_checks: list[str]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the canonical throwaway todo-app regression workflow."
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root or installed host root to inspect (default: current directory).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the generated report as JSON after writing it.",
    )
    return parser.parse_args(argv)


def resolve_repo_root(path: str) -> Path:
    return Path(path).expanduser().resolve()


def detect_factory_layout(repo_root: Path) -> tuple[Path, str]:
    source_checkout_marker = repo_root / "scripts" / "install_factory.py"
    source_skill_dir = repo_root / ".copilot" / "skills"
    installed_factory_root = repo_root / ".copilot" / "softwareFactoryVscode"
    installed_marker = installed_factory_root / "scripts" / "install_factory.py"

    if source_checkout_marker.exists() and source_skill_dir.is_dir():
        return repo_root, SOURCE_CHECKOUT_MODE
    if installed_marker.exists():
        return installed_factory_root, INSTALLED_HOST_MODE

    raise FileNotFoundError(
        "Could not detect a source checkout or installed host layout for todo-app regression."
    )


def resolve_throwaway_root(repo_root: Path, mode: str) -> Path:
    if mode == SOURCE_CHECKOUT_MODE:
        return repo_root / SOURCE_THROWAWAY_ROOT
    if mode == INSTALLED_HOST_MODE:
        return repo_root / INSTALLED_THROWAWAY_ROOT
    raise ValueError(f"Unsupported mode: {mode}")


def approved_workspace_markers() -> list[str]:
    return [
        ".tmp/todo-regression-run/workspace",
        ".copilot/softwareFactoryVscode/.tmp/todo-regression-run/workspace",
    ]


def ensure_clean_throwaway_workspace(throwaway_root: Path) -> Path:
    if throwaway_root.exists():
        shutil.rmtree(throwaway_root)
    workspace_root = throwaway_root / "workspace"
    (workspace_root / ARTIFACTS_RELATIVE).mkdir(parents=True, exist_ok=True)
    (workspace_root / REPORT_RELATIVE.parent).mkdir(parents=True, exist_ok=True)
    return workspace_root


def _should_skip_path(path: Path, excluded_root: Path) -> bool:
    if excluded_root == path or excluded_root in path.parents:
        return True
    return any(part in IGNORE_DIR_NAMES for part in path.parts)


def snapshot_non_throwaway_files(
    repo_root: Path, excluded_root: Path
) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if _should_skip_path(path, excluded_root):
            continue
        relative = path.relative_to(repo_root).as_posix()
        snapshot[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


def diff_snapshots(before: dict[str, str], after: dict[str, str]) -> list[str]:
    changes: list[str] = []
    keys = sorted(set(before) | set(after))
    for key in keys:
        if before.get(key) != after.get(key):
            changes.append(key)
    return changes


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_skill_text(factory_root: Path) -> str:
    return (factory_root / SKILL_FILE_RELATIVE).read_text(encoding="utf-8")


def audit_skill_contract(factory_root: Path) -> dict[str, Any]:
    text = read_skill_text(factory_root)
    lowered = text.lower()

    missing_headings = [
        heading for heading in REQUIRED_SKILL_HEADINGS if heading not in text
    ]
    missing_features = [term for term in REQUIRED_FEATURE_TERMS if term not in lowered]
    missing_dod = [term for term in REQUIRED_DOD_TERMS if term not in lowered]
    missing_metrics = [term for term in REQUIRED_METRIC_TERMS if term not in lowered]

    return {
        "missing_headings": missing_headings,
        "missing_features": missing_features,
        "missing_definition_of_done": missing_dod,
        "missing_quality_metrics": missing_metrics,
        "skill_contract_coverage": 1.0 if not missing_headings else 0.0,
        "definition_of_done_contract_coverage": 1.0 if not missing_dod else 0.0,
        "quality_metrics_contract_coverage": 1.0 if not missing_metrics else 0.0,
    }


def load_model_cases(factory_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = load_json(factory_root / MODEL_CASES_RELATIVE)
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported todo regression model case schema version.")

    fixed_cases: list[dict[str, Any]] = []
    generic_case: dict[str, Any] | None = None
    for case in payload.get("cases", []):
        if case.get("template"):
            generic_case = case
        else:
            fixed_cases.append(case)
    if generic_case is None:
        raise ValueError(
            "Todo regression compatibility cases are missing the generic template."
        )
    return fixed_cases, generic_case


def resolve_active_model(config: dict[str, Any]) -> str:
    if config.get("model"):
        return str(config["model"])
    for key in ("planning_model", "coding_model", "review_model"):
        if config.get(key):
            return str(config[key])
    return ""


def load_active_llm_config(factory_root: Path) -> dict[str, Any]:
    candidates = [
        factory_root / "configs" / "llm.json",
        factory_root / "configs" / "llm.default.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return load_json(candidate)
    raise FileNotFoundError(
        "No LLM config found for todo-app regression compatibility checks."
    )


def build_active_config_case(
    factory_root: Path,
    generic_case: dict[str, Any],
    workspace_marker: str,
) -> dict[str, Any]:
    config = load_active_llm_config(factory_root)
    model = resolve_active_model(config)
    provider = str(config.get("provider", "")).strip()
    response = str(generic_case.get("response", ""))
    response = response.replace("{workspace}", workspace_marker)
    response = response.replace("{model}", model or "configured-model")
    return {
        "id": "active-config-model",
        "provider": provider,
        "model": model,
        "template": False,
        "response": response,
    }


def _response_contains_any(response: str, fragments: tuple[str, ...]) -> bool:
    return any(fragment in response for fragment in fragments)


def evaluate_compatibility_case(
    case: dict[str, Any],
    *,
    allowed_workspace_markers: list[str],
) -> CompatibilityResult:
    provider = str(case.get("provider", "")).strip()
    model = str(case.get("model", "")).strip()
    response = str(case.get("response", "")).lower()
    missing: list[str] = []

    if provider.lower() != SUPPORTED_PROVIDER:
        missing.append("supported provider")
    if not model or model in {"*", "your-model-name"}:
        missing.append("configured model")
    if not any(marker.lower() in response for marker in allowed_workspace_markers):
        missing.append("approved throwaway workspace")
    if not _response_contains_any(response, SEMANTIC_KEYWORDS["create"]):
        missing.append("create behavior")
    if not _response_contains_any(response, SEMANTIC_KEYWORDS["edit"]):
        missing.append("edit behavior")
    if not _response_contains_any(response, SEMANTIC_KEYWORDS["toggle_complete"]):
        missing.append("complete/incomplete behavior")
    if not _response_contains_any(response, SEMANTIC_KEYWORDS["delete"]):
        missing.append("delete behavior")
    if not _response_contains_any(response, SEMANTIC_KEYWORDS["empty_state"]):
        missing.append("empty-state behavior")
    if not _response_contains_any(response, SEMANTIC_KEYWORDS["persistence"]):
        missing.append("persistence behavior")

    return CompatibilityResult(
        case_id=str(case.get("id", "unknown")),
        provider=provider,
        model=model,
        passed=not missing,
        missing_checks=missing,
    )


def evaluate_cases_twice(
    cases: list[dict[str, Any]],
    *,
    allowed_workspace_markers: list[str],
) -> tuple[list[CompatibilityResult], list[CompatibilityResult]]:
    first = [
        evaluate_compatibility_case(
            case, allowed_workspace_markers=allowed_workspace_markers
        )
        for case in cases
    ]
    second = [
        evaluate_compatibility_case(
            case, allowed_workspace_markers=allowed_workspace_markers
        )
        for case in cases
    ]
    return first, second


def serialize_results(results: list[CompatibilityResult]) -> list[dict[str, Any]]:
    return [
        {
            "case_id": result.case_id,
            "provider": result.provider,
            "model": result.model,
            "passed": result.passed,
            "missing_checks": result.missing_checks,
        }
        for result in results
    ]


def build_definition_of_done(
    *,
    skill_path: Path,
    skill_audit: dict[str, Any],
    results: list[CompatibilityResult],
    report_path: Path,
    throwaway_root: Path,
    unexpected_changes: list[str],
) -> dict[str, Any]:
    required = REQUIRED_DOD_TERMS
    satisfied: list[str] = []
    if skill_path.exists():
        satisfied.append(REQUIRED_DOD_TERMS[0])
    if not any(
        result
        for result in results
        if "approved throwaway workspace" in result.missing_checks
    ):
        satisfied.append(REQUIRED_DOD_TERMS[1])
    if not skill_audit["missing_features"] and all(
        not any(check.endswith("behavior") for check in result.missing_checks)
        for result in results
    ):
        satisfied.append(REQUIRED_DOD_TERMS[2])
    if all(result.passed for result in results):
        satisfied.append(REQUIRED_DOD_TERMS[3])
    if throwaway_root in report_path.parents:
        satisfied.append(REQUIRED_DOD_TERMS[4])
    if not unexpected_changes:
        satisfied.append(REQUIRED_DOD_TERMS[5])

    missing = [item for item in required if item not in satisfied]
    return {
        "required": required,
        "satisfied": satisfied,
        "missing": missing,
        "coverage": len(satisfied) / len(required),
    }


def build_quality_metrics(
    *,
    skill_audit: dict[str, Any],
    definition_of_done: dict[str, Any],
    first_results: list[CompatibilityResult],
    second_results: list[CompatibilityResult],
    unexpected_changes: list[str],
) -> dict[str, float]:
    semantic_pass_count = sum(1 for result in first_results if result.passed)
    semantic_total = len(first_results) or 1
    repeat_run_stability = (
        1.0
        if serialize_results(first_results) == serialize_results(second_results)
        else 0.0
    )
    return {
        "skill_contract_coverage": skill_audit["skill_contract_coverage"],
        "definition_of_done_coverage": definition_of_done["coverage"],
        "semantic_compatibility_rate": semantic_pass_count / semantic_total,
        "throwaway_cleanliness": 1.0 if not unexpected_changes else 0.0,
        "repeat_run_stability": repeat_run_stability,
    }


def run_regression(repo_root: Path) -> dict[str, Any]:
    factory_root, mode = detect_factory_layout(repo_root)
    throwaway_root = resolve_throwaway_root(repo_root, mode)
    workspace_root = ensure_clean_throwaway_workspace(throwaway_root)
    before = snapshot_non_throwaway_files(repo_root, throwaway_root)

    skill_path = factory_root / SKILL_FILE_RELATIVE
    skill_audit = audit_skill_contract(factory_root)
    fixed_cases, generic_case = load_model_cases(factory_root)
    workspace_markers = approved_workspace_markers()
    active_workspace_marker = (
        ".tmp/todo-regression-run/workspace"
        if mode == SOURCE_CHECKOUT_MODE
        else ".copilot/softwareFactoryVscode/.tmp/todo-regression-run/workspace"
    )
    active_case = build_active_config_case(
        factory_root, generic_case, active_workspace_marker
    )
    compatibility_cases = [*fixed_cases, active_case]
    first_results, second_results = evaluate_cases_twice(
        compatibility_cases,
        allowed_workspace_markers=workspace_markers,
    )

    artifacts_dir = workspace_root / ARTIFACTS_RELATIVE
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    artifacts_path = artifacts_dir / "model-compatibility-results.json"
    artifacts_path.write_text(
        json.dumps(
            {
                "cases": compatibility_cases,
                "first_pass": serialize_results(first_results),
                "second_pass": serialize_results(second_results),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    after = snapshot_non_throwaway_files(repo_root, throwaway_root)
    unexpected_changes = diff_snapshots(before, after)
    definition_of_done = build_definition_of_done(
        skill_path=skill_path,
        skill_audit=skill_audit,
        results=first_results,
        report_path=workspace_root / REPORT_RELATIVE,
        throwaway_root=throwaway_root,
        unexpected_changes=unexpected_changes,
    )
    quality_metrics = build_quality_metrics(
        skill_audit=skill_audit,
        definition_of_done=definition_of_done,
        first_results=first_results,
        second_results=second_results,
        unexpected_changes=unexpected_changes,
    )
    report = {
        "status": (
            "passed"
            if all(value == 1.0 for value in quality_metrics.values())
            else "failed"
        ),
        "mode": mode,
        "repo_root": str(repo_root),
        "factory_root": str(factory_root),
        "throwaway_root": str(throwaway_root),
        "workspace_root": str(workspace_root),
        "report_path": str(workspace_root / REPORT_RELATIVE),
        "artifacts_path": str(artifacts_path),
        "skill_path": str(skill_path),
        "skill_audit": skill_audit,
        "definition_of_done": definition_of_done,
        "quality_metrics": quality_metrics,
        "compatibility_results": serialize_results(first_results),
        "unexpected_changes_outside_throwaway": unexpected_changes,
        "active_config": {
            "provider": active_case["provider"],
            "model": active_case["model"],
        },
    }

    report_path = workspace_root / REPORT_RELATIVE
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = resolve_repo_root(args.repo_root)
    report = run_regression(repo_root)

    print("============================================================")
    print("Todo-app throwaway regression")
    print("============================================================")
    print(f"mode={report['mode']}")
    print(f"throwaway_root={report['throwaway_root']}")
    print(f"report_path={report['report_path']}")
    print(f"status={report['status']}")
    if report["unexpected_changes_outside_throwaway"]:
        print("unexpected_changes_outside_throwaway=")
        for change in report["unexpected_changes_outside_throwaway"]:
            print(f"- {change}")

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))

    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
