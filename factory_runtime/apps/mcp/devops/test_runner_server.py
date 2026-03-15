import os
from pathlib import Path

import uvicorn
from mcp.server.fastmcp import FastMCP

from .test_runner_service import TestRunnerService, TestRunnerServiceError


def _load_service() -> TestRunnerService:
    repo_root = Path(os.getenv("TEST_RUNNER_MCP_REPO_ROOT", "/workspace")).resolve()
    audit_dir = Path(
        os.getenv(
            "TEST_RUNNER_MCP_AUDIT_DIR", str(repo_root / ".tmp" / "mcp-test-runner")
        )
    ).resolve()
    return TestRunnerService(repo_root=repo_root, audit_dir=audit_dir)


service = _load_service()
mcp = FastMCP("maestro Test Runner MCP", json_response=True)


@mcp.tool()
def test_runner_profiles() -> dict:
    """Return deterministic test/lint/build profiles available for execution."""
    return service.list_profiles()


@mcp.tool()
def test_runner_run(profile_name: str) -> dict:
    """Execute one deterministic profile and return captured output."""
    try:
        return service.run_profile(profile_name=profile_name)
    except (TestRunnerServiceError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def test_runner_run_log(run_id: str) -> dict | None:
    """Return one audited run log by run ID."""
    return service.get_run_log(run_id)


def main() -> None:
    host = os.getenv("TEST_RUNNER_MCP_HOST", "0.0.0.0")
    port = int(os.getenv("TEST_RUNNER_MCP_PORT", "3016"))
    app = mcp.streamable_http_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
