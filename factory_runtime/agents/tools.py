"""agents.tools

Tools for the workflow agent.

These tools enable the agent to interact with GitHub, files, git, and testing.

Note: This repository is multi-repo (backend + `${CLIENT_DIR:-../client}`).
Most tools therefore accept an optional `working_directory` and/or `repo` argument so
the agent can operate on the correct repository root.
"""

import json
import subprocess
import time
from pathlib import Path
from typing import Annotated, Optional

from factory_runtime.agents.command_cache import get_cache
from factory_runtime.agents.coverage_analyzer import get_coverage_analyzer
from factory_runtime.agents.time_estimator import TimeEstimator
from factory_runtime.agents.tooling.filesystem_tools import (
    list_directory_contents_typed,
    read_file_content_typed,
    write_file_content_typed,
)
from factory_runtime.agents.tooling.git_tools import (
    create_feature_branch_typed,
    get_changed_files_typed,
    git_commit_typed,
)
from factory_runtime.agents.tooling.github_tools import (
    create_github_pr_typed,
    fetch_github_issue_typed,
    list_github_issues_typed,
)
from factory_runtime.agents.tooling.mockup_image_generation import (
    generate_issue_mockup_artifacts,
)

# ============================================================================
# GitHub Tools
# ============================================================================


def _legacy_result_or_error(
    result,
    *,
    error_prefix: str,
    fallback_error_message: str,
) -> str:
    """Convert typed results to legacy string responses for compatibility."""
    if result.ok:
        return result.value or ""

    details = None
    if result.error:
        details = result.error.details or result.error.message
    details = details or fallback_error_message
    return f"{error_prefix}{details}"


def fetch_github_issue(
    issue_number: Annotated[int, "GitHub issue number"],
    repo: Annotated[Optional[str], "GitHub repo in owner/name form (optional)"] = None,
    working_directory: Annotated[str, "Working directory for gh command"] = ".",
) -> str:
    """
    Fetch GitHub issue details using gh CLI.

    Returns JSON string with issue title, body, labels, etc.
    """
    result = fetch_github_issue_typed(
        issue_number=issue_number,
        repo=repo,
        working_directory=working_directory,
    )
    return _legacy_result_or_error(
        result,
        error_prefix="Error fetching issue: ",
        fallback_error_message="failed to fetch issue",
    )


def create_github_pr(
    title: Annotated[str, "PR title"],
    body: Annotated[str, "PR description"],
    working_directory: Annotated[str, "Working directory for gh command"] = ".",
) -> str:
    """
    Create GitHub pull request with gh CLI.

    Returns PR URL or error message.
    """
    result = create_github_pr_typed(
        title=title,
        body=body,
        working_directory=working_directory,
    )
    return _legacy_result_or_error(
        result,
        error_prefix="Error creating PR: ",
        fallback_error_message="failed to create pull request",
    )


def list_github_issues(
    repo: Annotated[str, "GitHub repo in owner/name form (required)"],
    state: Annotated[str, "Issue state: open or closed"] = "open",
    limit: Annotated[int, "Max issues to return"] = 50,
    label: Annotated[Optional[str], "Optional single label filter"] = None,
    search: Annotated[Optional[str], "Optional search query"] = None,
    working_directory: Annotated[str, "Working directory for gh command"] = ".",
) -> str:
    """List GitHub issues via gh CLI.

    Returns JSON array string with fields needed for selection/triage.
    """
    result = list_github_issues_typed(
        repo=repo,
        state=state,
        limit=limit,
        label=label,
        search=search,
        working_directory=working_directory,
    )
    if (not result.ok) and result.error and result.error.code == "INVALID_ARGUMENT":
        return f"Error: {result.error.message}"

    return _legacy_result_or_error(
        result,
        error_prefix="Error listing issues: ",
        fallback_error_message="failed to list issues",
    )


# ============================================================================
# File System Tools
# ============================================================================


def read_file_content(
    file_path: Annotated[str, "Path to file relative to base directory"],
    base_directory: Annotated[str, "Base directory to resolve file_path"] = ".",
) -> str:
    """
    Read contents of a file.

    Returns file content or error message.
    """
    result = read_file_content_typed(
        file_path=file_path,
        base_directory=base_directory,
    )
    if (
        (not result.ok)
        and result.error
        and result.error.code
        in {
            "FILE_NOT_FOUND",
            "FILE_TOO_LARGE",
        }
    ):
        return f"Error: {result.error.message}"

    return _legacy_result_or_error(
        result,
        error_prefix="Error reading file: ",
        fallback_error_message="failed to read file",
    )


def write_file_content(
    file_path: Annotated[str, "Path to file relative to base directory"],
    content: Annotated[str, "File content to write"],
    base_directory: Annotated[str, "Base directory to resolve file_path"] = ".",
) -> str:
    """
    Write content to a file, creating directories if needed.

    Returns success message or error.
    """
    result = write_file_content_typed(
        file_path=file_path,
        content=content,
        base_directory=base_directory,
    )
    return _legacy_result_or_error(
        result,
        error_prefix="Error writing file: ",
        fallback_error_message="failed to write file",
    )


def list_directory_contents(
    directory_path: Annotated[str, "Path to directory relative to base directory"],
    base_directory: Annotated[str, "Base directory to resolve directory_path"] = ".",
) -> str:
    """
    List files and directories in a given path.

    Returns newline-separated list of entries.
    """
    result = list_directory_contents_typed(
        directory_path=directory_path,
        base_directory=base_directory,
    )
    if (
        (not result.ok)
        and result.error
        and result.error.code
        in {
            "DIRECTORY_NOT_FOUND",
            "NOT_A_DIRECTORY",
        }
    ):
        return f"Error: {result.error.message}"

    return _legacy_result_or_error(
        result,
        error_prefix="Error listing directory: ",
        fallback_error_message="failed to list directory",
    )


# ============================================================================
# Git Tools
# ============================================================================


def git_commit(
    message: Annotated[str, "Commit message"],
    working_directory: Annotated[str, "Working directory for git command"] = ".",
) -> str:
    """
    Stage all changes and create a git commit.

    Returns commit hash or error message.
    """
    result = git_commit_typed(
        message=message,
        working_directory=working_directory,
    )
    return _legacy_result_or_error(
        result,
        error_prefix="Error committing: ",
        fallback_error_message="failed to commit",
    )


def get_changed_files(
    working_directory: Annotated[str, "Working directory for git command"] = ".",
) -> str:
    """
    Get list of files changed in working directory.

    Returns list of changed files or empty string.
    """
    result = get_changed_files_typed(working_directory=working_directory)
    if not result.ok:
        details = result.error.details if result.error else "failed to read git status"
        return f"Error: {details}"
    return result.value or ""


# ==========================================================================
# Mockup Tools
# ==========================================================================


def generate_mockup_artifacts(
    issue_number: Annotated[int, "GitHub issue number for deterministic output folder"],
    prompt: Annotated[str, "Prompt describing the UI mockup to generate"],
    image_count: Annotated[int, "Number of images to generate (default: 1)"] = 1,
) -> str:
    """Generate UI mockup images under `.tmp/mockups/issue-<n>/`.

    Requires dynamic external overrides. If missing, returns a structured
    error message without raising.
    """
    result = generate_issue_mockup_artifacts(
        issue_number,
        prompt=prompt,
        image_count=image_count,
    )

    payload = {
        "ok": result.ok,
        "message": result.message,
        "output_dir": str(result.output_dir),
        "index_html": str(result.index_html_path) if result.index_html_path else None,
        "images": [str(p) for p in result.image_paths],
    }
    if not result.ok:
        payload["suggestion"] = "Provide dynamic configuration overrides."

    return json.dumps(payload, indent=2)


def create_feature_branch(
    branch_name: Annotated[str, "Branch name (e.g., issue/26-description)"],
    working_directory: Annotated[str, "Working directory for git command"] = ".",
) -> str:
    """
    Create and checkout a new feature branch from main.

    Returns success message or error.
    """
    result = create_feature_branch_typed(
        branch_name=branch_name,
        working_directory=working_directory,
    )
    return _legacy_result_or_error(
        result,
        error_prefix="Error creating branch: ",
        fallback_error_message="failed to create branch",
    )


# ============================================================================
# Testing & Build Tools
# ============================================================================


def _resolve_working_directory(working_directory: str) -> str:
    """Resolve working directory safely for subprocess execution."""
    repo_root = Path(__file__).resolve().parent.parent
    provided_path = Path(working_directory)

    if provided_path.exists():
        return working_directory

    if working_directory in {"factory", "./factory"}:
        return str(repo_root)

    candidate = repo_root / working_directory
    if candidate.exists():
        return str(candidate)

    return working_directory


def run_command(
    command: Annotated[str, "Shell command to execute"],
    working_directory: Annotated[str, "Working directory for command"] = ".",
    use_cache: Annotated[bool, "Use command cache for idempotent operations"] = True,
) -> str:
    """
    Execute a shell command and return output.

    Use for running tests, builds, linting, etc.
    Returns combined stdout and stderr.

    Caching:
    - Enabled by default for idempotent commands (npm install, pip install, linting)
    - 1-hour TTL per command+cwd combination
    - Saves 8-12s per issue by avoiding redundant npm installs
    - Set use_cache=False for non-idempotent commands (git commit, file writes)
    """
    cache = get_cache()

    # Check cache first
    if use_cache:
        cached = cache.get(command, working_directory)
        if cached:
            output = []
            output.append(f"[CACHED] Exit code: {cached.returncode}")
            output.append(f"[Cache saved {cached.execution_time_seconds:.1f}s]")

            if cached.stdout:
                output.append("STDOUT:")
                output.append(cached.stdout)

            if cached.stderr:
                output.append("STDERR:")
                output.append(cached.stderr)

            return "\n".join(output)

    # Run command and measure time
    start_time = time.time()
    resolved_working_directory = _resolve_working_directory(working_directory)

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            cwd=resolved_working_directory,
        )

        elapsed = time.time() - start_time

        # Store in cache if enabled
        if use_cache:
            cache.set(
                command,
                working_directory,
                result.stdout,
                result.stderr,
                result.returncode,
                elapsed,
            )

        output = []
        output.append(f"Exit code: {result.returncode}")

        if result.stdout:
            output.append("STDOUT:")
            output.append(result.stdout)

        if result.stderr:
            output.append("STDERR:")
            output.append(result.stderr)

        return "\n".join(output)
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 5 minutes"
    except Exception as e:
        return f"Error executing command: {str(e)}"


# ============================================================================
# Knowledge Base Tools
# ============================================================================


_KB_PRIMARY_LIST_KEYS = {
    "workflow_patterns": "issues",
    "time_estimates": "completed_issues",
    "problem_solutions": "problems",
}


def _deep_merge_dicts(existing: dict, incoming: dict) -> dict:
    """Merge nested dictionaries while preserving existing schema structure."""
    merged = dict(existing)

    for key, incoming_value in incoming.items():
        existing_value = merged.get(key)

        if isinstance(existing_value, dict) and isinstance(incoming_value, dict):
            merged[key] = _deep_merge_dicts(existing_value, incoming_value)
        elif isinstance(existing_value, list) and isinstance(incoming_value, list):
            merged[key] = [*existing_value, *incoming_value]
        else:
            merged[key] = incoming_value

    return merged


def _append_into_primary_list(existing: dict, incoming, category: str) -> dict:
    """Append incoming record(s) into the category's primary list field."""
    primary_key = _KB_PRIMARY_LIST_KEYS.get(category)
    if not primary_key:
        return existing

    updated = dict(existing)
    current_items = updated.get(primary_key, [])
    if not isinstance(current_items, list):
        current_items = []

    if isinstance(incoming, list):
        current_items = [*current_items, *incoming]
    else:
        current_items = [*current_items, incoming]

    updated[primary_key] = current_items
    return updated


def _merge_knowledge_payload(existing, incoming, category: str):
    """Merge knowledge payloads while preserving existing schema shape."""
    if isinstance(existing, dict):
        if isinstance(incoming, dict):
            return _deep_merge_dicts(existing, incoming)
        return _append_into_primary_list(existing, incoming, category)

    if isinstance(existing, list):
        if isinstance(incoming, list):
            return [*existing, *incoming]
        return [*existing, incoming]

    # Backward-compatible fallback for invalid/unexpected existing content.
    if isinstance(incoming, list):
        return incoming

    if category in _KB_PRIMARY_LIST_KEYS:
        if isinstance(incoming, dict):
            return incoming
        return {_KB_PRIMARY_LIST_KEYS[category]: [incoming]}

    return [incoming]


def get_knowledge_base_patterns() -> str:
    """
    Load workflow patterns from knowledge base.

    Returns JSON string of past successful workflows.
    """
    try:
        kb_file = Path(__file__).parent / "knowledge" / "workflow_patterns.json"
        if not kb_file.exists():
            return "[]"

        with open(kb_file, "r") as f:
            return f.read()
    except Exception as e:
        return f"Error loading knowledge base: {str(e)}"


def update_knowledge_base(
    category: Annotated[
        str, "Knowledge category (workflow_patterns, problem_solutions, time_estimates)"
    ],
    data: Annotated[str, "JSON data to add to knowledge base"],
) -> str:
    """
    Update knowledge base with new learnings.

    Returns success message or error.
    """
    try:
        kb_file = Path(__file__).parent / "knowledge" / f"{category}.json"
        kb_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing data
        existing = None
        if kb_file.exists():
            with open(kb_file, "r") as f:
                try:
                    existing = json.load(f)
                except json.JSONDecodeError:
                    existing = None

        # Parse new data
        new_data = json.loads(data)

        # Schema-aware merge with legacy-list compatibility
        existing = _merge_knowledge_payload(existing, new_data, category)

        with open(kb_file, "w") as f:
            json.dump(existing, f, indent=2)

        if isinstance(new_data, list):
            count = len(new_data)
        else:
            count = 1

        return f"Updated {category} with {count} new entries"
    except Exception as e:
        return f"Error updating knowledge base: {str(e)}"


def get_cache_metrics() -> str:
    """Get command cache performance metrics.

    Returns formatted metrics showing cache hits and time saved.
    Useful for understanding agent efficiency improvements.
    """
    cache = get_cache()
    metrics = cache.get_metrics()

    return (
        f"Command Cache Metrics:\n"
        f"  Cache hits: {metrics['cache_hits']}\n"
        f"  Time saved: {metrics['time_saved_from_cache_seconds']}s\n"
        f"  Cached entries: {metrics['cached_entries']}"
    )


def get_time_estimate(
    files_to_change: Annotated[int, "Number of files to modify"],
    lines_estimate: Annotated[int, "Estimated total lines changed"],
    domain: Annotated[
        str, "Domain: backend, frontend, docs, testing, ci, agent, other"
    ] = "other",
    is_multi_repo: Annotated[bool, "Requires changes in multiple repos"] = False,
    has_dependencies: Annotated[bool, "Depends on other issues"] = False,
    complexity_score: Annotated[int, "Complexity 1-5 (1=simple, 5=complex)"] = 3,
) -> str:
    """Get ML-based time estimate for an issue.

    Uses RandomForestRegressor trained on historical data to predict
    resolution time with confidence scoring.

    Returns formatted estimate with confidence and reasoning.
    """
    estimator = TimeEstimator()
    estimate = estimator.predict(
        files_to_change=files_to_change,
        lines_estimate=lines_estimate,
        domain=domain,
        is_multi_repo=is_multi_repo,
        has_dependencies=has_dependencies,
        complexity_score=complexity_score,
    )

    return (
        f"Time Estimate: {estimate.hours:.1f} hours\n"
        f"Confidence: {estimate.confidence:.0%}\n"
        f"Reasoning: {estimate.reasoning}\n"
        f"\nFeatures considered:\n"
        f"  - Files to change: {files_to_change}\n"
        f"  - Lines estimate: {lines_estimate}\n"
        f"  - Domain: {domain}\n"
        f"  - Multi-repo: {is_multi_repo}\n"
        f"  - Has dependencies: {has_dependencies}\n"
        f"  - Complexity: {complexity_score}/5"
    )


def analyze_coverage_impact(
    changed_files: Annotated[list[str], "List of files that were changed"],
    coverage_threshold: Annotated[
        float, "Minimum coverage percentage (default 80)"
    ] = 80.0,
    working_directory: Annotated[str, "Working directory"] = ".",
) -> str:
    """
    Analyze test coverage impact of code changes.

    This tool:
    - Runs tests with coverage
    - Detects coverage regressions
    - Warns about files below threshold
    - Enforces coverage quality gates

    Returns JSON with coverage analysis results and pass/fail status.
    """
    try:
        analyzer = get_coverage_analyzer(
            coverage_threshold=coverage_threshold,
            working_directory=working_directory,
        )

        # Get current coverage
        current_coverage = analyzer.get_current_coverage()
        if not current_coverage:
            return json.dumps(
                {
                    "error": "Failed to generate coverage report",
                    "suggestion": "Run: bash scripts/run_pytest_coverage.sh --local-stable",
                },
                indent=2,
            )

        # Analyze changed files against threshold
        diff_result = {
            "total_coverage": current_coverage.total_percent,
            "files_analyzed": len(
                [f for f in changed_files if f in current_coverage.files]
            ),
            "low_coverage_files": [],
            "coverage_threshold": coverage_threshold,
        }

        # Check changed files against threshold
        low_coverage_files = []
        for file_path in changed_files:
            if file_path in current_coverage.files:
                file_cov = current_coverage.files[file_path]
                if file_cov.percent_covered < coverage_threshold:
                    low_coverage_files.append(
                        {
                            "path": file_cov.path,
                            "coverage": round(file_cov.percent_covered, 1),
                            "missing_lines": file_cov.missing_lines,
                        }
                    )

        diff_result["low_coverage_files"] = low_coverage_files
        diff_result["passed"] = len(low_coverage_files) == 0

        # Add metrics
        diff_result["metrics"] = analyzer.get_metrics()

        return json.dumps(diff_result, indent=2)

    except Exception as e:
        return json.dumps({"error": f"Coverage analysis failed: {e}"}, indent=2)


# ============================================================================
# Tool List for Agent
# ============================================================================


def get_all_tools():
    """Get all tools for the agent."""
    return [
        # GitHub
        fetch_github_issue,
        create_github_pr,
        list_github_issues,
        # File System
        read_file_content,
        write_file_content,
        list_directory_contents,
        # Git
        git_commit,
        get_changed_files,
        create_feature_branch,
        # Testing
        run_command,
        get_cache_metrics,
        get_time_estimate,
        analyze_coverage_impact,
        # Mockups
        generate_mockup_artifacts,
        # Knowledge Base
        get_knowledge_base_patterns,
        update_knowledge_base,
    ]


def get_compact_tools():
    """Get a compact tool subset for constrained token budgets."""
    return [
        fetch_github_issue,
        create_github_pr,
        list_github_issues,
        read_file_content,
        write_file_content,
        list_directory_contents,
        git_commit,
        get_changed_files,
        create_feature_branch,
        run_command,
    ]


def get_ultra_compact_tools():
    """Get an ultra-compact tool subset for strict request-size limits."""
    return [
        fetch_github_issue,
        read_file_content,
        write_file_content,
        list_directory_contents,
        get_changed_files,
        run_command,
    ]


def get_shell_only_tools():
    """Get a shell-only tool subset for maximum prompt compactness."""
    return [
        run_command,
    ]
