"""Git-related tool implementations with typed contracts."""

import subprocess

from agents.tooling.contracts import ToolResult


def git_commit_typed(
    message: str,
    working_directory: str = ".",
) -> ToolResult[str]:
    """Stage all changes and create a git commit."""
    try:
        subprocess.run(
            ["git", "add", "-A"],
            check=True,
            capture_output=True,
            cwd=working_directory,
        )

        result = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=working_directory,
        )

        if result.returncode != 0:
            return ToolResult.failure(
                code="COMMAND_FAILED",
                message="Failed to create git commit",
                details=result.stderr.strip() or "git commit failed",
            )

        hash_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=working_directory,
        )

        return ToolResult.success(
            f"Committed: {hash_result.stdout.strip()}\n{result.stdout}"
        )
    except Exception as exc:
        return ToolResult.failure(
            code="UNEXPECTED_EXCEPTION",
            message="Unexpected error while creating git commit",
            details=str(exc),
        )


def get_changed_files_typed(
    working_directory: str = ".",
) -> ToolResult[str]:
    """Get list of files changed in working directory."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=working_directory,
        )

        if result.returncode != 0:
            return ToolResult.failure(
                code="COMMAND_FAILED",
                message="Failed to get changed files",
                details=result.stderr.strip() or "git status failed",
            )

        return ToolResult.success(result.stdout)
    except Exception as exc:
        return ToolResult.failure(
            code="UNEXPECTED_EXCEPTION",
            message="Unexpected error while fetching changed files",
            details=str(exc),
        )


def create_feature_branch_typed(
    branch_name: str,
    working_directory: str = ".",
) -> ToolResult[str]:
    """Create and checkout a new feature branch from main."""
    try:
        subprocess.run(
            ["git", "switch", "main"],
            check=True,
            capture_output=True,
            cwd=working_directory,
        )
        subprocess.run(
            ["git", "pull", "origin", "main"],
            check=True,
            capture_output=True,
            cwd=working_directory,
        )

        result = subprocess.run(
            ["git", "switch", "-c", branch_name],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=working_directory,
        )

        if result.returncode != 0:
            return ToolResult.failure(
                code="COMMAND_FAILED",
                message="Failed to create feature branch",
                details=result.stderr.strip() or "git switch -c failed",
            )

        return ToolResult.success(f"Created and checked out branch: {branch_name}")
    except Exception as exc:
        return ToolResult.failure(
            code="UNEXPECTED_EXCEPTION",
            message="Unexpected error while creating feature branch",
            details=str(exc),
        )
