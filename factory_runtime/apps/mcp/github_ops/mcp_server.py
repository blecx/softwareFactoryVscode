from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from mcp.server.fastmcp import FastMCP

from .policy import GitHubOpsPolicyError
from .service import GitHubOpsService, GitHubOpsServiceError, load_default_policy


def _load_service() -> GitHubOpsService:
    repo_root = Path(os.getenv("GITHUB_OPS_MCP_REPO_ROOT", "/workspace")).resolve()
    audit_dir = Path(
        os.getenv(
            "GITHUB_OPS_MCP_AUDIT_DIR",
            str(repo_root / ".copilot/softwareFactoryVscode/.tmp" / "mcp-github-ops"),
        )
    ).resolve()

    policy = load_default_policy()
    return GitHubOpsService(repo_root=repo_root, policy=policy, audit_dir=audit_dir)


service = _load_service()
mcp = FastMCP("factory GitHub Ops MCP", json_response=True)


def _wrap_error(exc: Exception) -> ValueError:
    return ValueError(str(exc))


@mcp.tool()
def github_ops_repos_allowed() -> Dict[str, Any]:
    """Return server-side allowlisted GitHub repositories."""
    return service.repos_allowed()


@mcp.tool()
def github_ops_issue_view(repo: str, issue_number: int) -> Dict[str, Any]:
    """View issue details for an allowlisted repo."""
    try:
        return service.issue_view(repo=repo, issue_number=issue_number)
    except (GitHubOpsPolicyError, GitHubOpsServiceError, ValueError) as exc:
        raise _wrap_error(exc) from exc


@mcp.tool()
def github_ops_issue_exists(repo: str, issue_number: int) -> Dict[str, Any]:
    """Check if an issue exists without failing hard."""
    try:
        return service.issue_exists(repo=repo, issue_number=issue_number)
    except (GitHubOpsPolicyError, ValueError) as exc:
        raise _wrap_error(exc) from exc


@mcp.tool()
def github_ops_pr_find_for_issue(
    issue_number: int,
    repos: List[str],
    prefer_state: str = "open",
    limit: int = 30,
) -> Dict[str, Any]:
    """Best-effort PR discovery for an issue across allowlisted repos."""
    try:
        return service.pr_find_for_issue(
            issue_number=issue_number,
            repos=repos,
            prefer_state=prefer_state,  # type: ignore[arg-type]
            limit=limit,
        )
    except (GitHubOpsPolicyError, GitHubOpsServiceError, ValueError) as exc:
        raise _wrap_error(exc) from exc


@mcp.tool()
def github_ops_pr_view(repo: str, pr_number: int) -> Dict[str, Any]:
    """View PR details for an allowlisted repo."""
    try:
        return service.pr_view(repo=repo, pr_number=pr_number)
    except (GitHubOpsPolicyError, GitHubOpsServiceError, ValueError) as exc:
        raise _wrap_error(exc) from exc


@mcp.tool()
def github_ops_pr_body(repo: str, pr_number: int) -> Dict[str, Any]:
    """Return PR body text."""
    try:
        return service.pr_body(repo=repo, pr_number=pr_number)
    except (GitHubOpsPolicyError, GitHubOpsServiceError, ValueError) as exc:
        raise _wrap_error(exc) from exc


@mcp.tool()
def github_ops_pr_files(repo: str, pr_number: int) -> Dict[str, Any]:
    """Return PR file list and totals."""
    try:
        return service.pr_files(repo=repo, pr_number=pr_number)
    except (GitHubOpsPolicyError, GitHubOpsServiceError, ValueError) as exc:
        raise _wrap_error(exc) from exc


@mcp.tool()
def github_ops_pr_checks_summary(repo: str, pr_number: int) -> Dict[str, Any]:
    """Return normalized CI check rollup summary for a PR."""
    try:
        return service.pr_checks_summary(repo=repo, pr_number=pr_number)
    except (GitHubOpsPolicyError, GitHubOpsServiceError, ValueError) as exc:
        raise _wrap_error(exc) from exc


@mcp.tool()
def github_ops_pr_checks_watch(
    repo: str,
    pr_number: int,
    timeout_sec: int = 1200,
    interval_sec: int = 15,
    fail_fast: bool = True,
) -> Dict[str, Any]:
    """Poll PR check status until success/failure/timeout."""
    try:
        return service.pr_checks_watch(
            repo=repo,
            pr_number=pr_number,
            timeout_sec=timeout_sec,
            interval_sec=interval_sec,
            fail_fast=fail_fast,
        )
    except (GitHubOpsPolicyError, GitHubOpsServiceError, ValueError) as exc:
        raise _wrap_error(exc) from exc


@mcp.tool()
def github_ops_workflow_runs_list(
    repo: str,
    branch: str,
    status: str = "in_progress",
    limit: int = 50,
) -> Dict[str, Any]:
    """List GitHub Actions workflow runs for a repo and branch."""
    try:
        return service.workflow_runs_list(
            repo=repo, branch=branch, status=status, limit=limit
        )
    except (GitHubOpsPolicyError, GitHubOpsServiceError, ValueError) as exc:
        raise _wrap_error(exc) from exc


@mcp.tool()
def github_ops_workflow_run_cancel(
    repo: str, run_id: int, dry_run: bool = False
) -> Dict[str, Any]:
    """Cancel a workflow run by ID (supports dry_run)."""
    try:
        return service.workflow_run_cancel(repo=repo, run_id=run_id, dry_run=dry_run)
    except (GitHubOpsPolicyError, GitHubOpsServiceError, ValueError) as exc:
        raise _wrap_error(exc) from exc


@mcp.tool()
def github_ops_pr_merge_squash(
    repo: str,
    pr_number: int,
    delete_branch: bool = True,
    admin: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Squash-merge a PR (supports dry_run) and return merge commit SHA if available."""
    try:
        return service.pr_merge_squash(
            repo=repo,
            pr_number=pr_number,
            delete_branch=delete_branch,
            admin=admin,
            dry_run=dry_run,
        )
    except (GitHubOpsPolicyError, GitHubOpsServiceError, ValueError) as exc:
        raise _wrap_error(exc) from exc


@mcp.tool()
def github_ops_issue_close(
    repo: str,
    issue_number: int,
    comment: str,
    reason: str = "completed",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Close an issue with a comment (supports dry_run)."""
    try:
        return service.issue_close(
            repo=repo,
            issue_number=issue_number,
            comment=comment,
            reason=reason,
            dry_run=dry_run,
        )
    except (GitHubOpsPolicyError, GitHubOpsServiceError, ValueError) as exc:
        raise _wrap_error(exc) from exc


@mcp.tool()
def github_ops_run_log(run_id: str) -> Optional[Dict[str, Any]]:
    """Read a stored audit log by run ID."""
    return service.get_run_log(run_id)


def main() -> None:
    host = os.getenv("GITHUB_OPS_MCP_HOST", "0.0.0.0")
    port = int(os.getenv("GITHUB_OPS_MCP_PORT", "3018"))
    app = mcp.streamable_http_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
