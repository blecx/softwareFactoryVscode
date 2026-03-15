"""GitHub-related tool implementations with typed contracts."""

import subprocess
from typing import Optional

from agents.tooling.contracts import ToolResult
from agents.tooling.gh_throttle import run_gh_throttled


def fetch_github_issue_typed(
    issue_number: int,
    repo: Optional[str] = None,
    working_directory: str = ".",
) -> ToolResult[str]:
    """Fetch GitHub issue details using gh CLI."""
    try:
        cmd = [
            "gh",
            "issue",
            "view",
            str(issue_number),
            "--json",
            "number,title,body,labels,state,assignees",
        ]
        if repo:
            cmd.extend(["--repo", repo])

        result = run_gh_throttled(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=working_directory,
        )

        if result.returncode != 0:
            return ToolResult.failure(
                code="COMMAND_FAILED",
                message="Failed to fetch GitHub issue",
                details=result.stderr.strip() or "gh issue view failed",
            )

        return ToolResult.success(result.stdout)
    except Exception as exc:
        return ToolResult.failure(
            code="UNEXPECTED_EXCEPTION",
            message="Unexpected error while fetching GitHub issue",
            details=str(exc),
        )


def create_github_pr_typed(
    title: str,
    body: str,
    working_directory: str = ".",
) -> ToolResult[str]:
    """Create GitHub pull request with gh CLI."""
    try:
        result = run_gh_throttled(
            ["gh", "pr", "create", "--title", title, "--body", body],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=working_directory,
        )

        if result.returncode != 0:
            return ToolResult.failure(
                code="COMMAND_FAILED",
                message="Failed to create pull request",
                details=result.stderr.strip() or "gh pr create failed",
            )

        return ToolResult.success(result.stdout)
    except Exception as exc:
        return ToolResult.failure(
            code="UNEXPECTED_EXCEPTION",
            message="Unexpected error while creating pull request",
            details=str(exc),
        )


def list_github_issues_typed(
    repo: str,
    state: str = "open",
    limit: int = 50,
    label: Optional[str] = None,
    search: Optional[str] = None,
    working_directory: str = ".",
) -> ToolResult[str]:
    """List GitHub issues via gh CLI."""
    try:
        state_norm = (state or "open").strip().lower()
        if state_norm in {"opened"}:
            state_norm = "open"
        if state_norm not in {"open", "closed"}:
            return ToolResult.failure(
                code="INVALID_ARGUMENT",
                message="state must be 'open' or 'closed'",
            )

        cmd = [
            "gh",
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            state_norm,
            "--limit",
            str(limit),
            "--json",
            "number,title,labels,createdAt,updatedAt,author,assignees",
        ]
        if label:
            cmd.extend(["--label", label])
        if search:
            cmd.extend(["--search", search])

        result = run_gh_throttled(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=working_directory,
        )
        if result.returncode != 0:
            return ToolResult.failure(
                code="COMMAND_FAILED",
                message="Failed to list GitHub issues",
                details=result.stderr.strip() or "gh issue list failed",
            )
        return ToolResult.success(result.stdout)
    except Exception as exc:
        return ToolResult.failure(
            code="UNEXPECTED_EXCEPTION",
            message="Unexpected error while listing GitHub issues",
            details=str(exc),
        )
