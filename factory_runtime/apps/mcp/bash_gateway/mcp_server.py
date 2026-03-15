"""Transport-level MCP server for the Bash Gateway.

Exposes the existing policy/audit-enforced BashGatewayServer through a real
MCP Streamable HTTP endpoint.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from mcp.server.fastmcp import FastMCP

from .policy import BashGatewayPolicy, PolicyViolationError
from .server import BashGatewayServer


def _load_gateway() -> BashGatewayServer:
    repo_root = Path(os.getenv("BASH_GATEWAY_REPO_ROOT", "/workspace")).resolve()
    policy_path = Path(
        os.getenv(
            "BASH_GATEWAY_POLICY_PATH",
            str(repo_root / "configs" / "bash_gateway_policy.default.yml"),
        )
    ).resolve()

    if not policy_path.exists():
        raise FileNotFoundError(f"Bash Gateway policy file not found: {policy_path}")

    policy = BashGatewayPolicy.from_yaml_file(policy_path)
    audit_dir_env = os.getenv("BASH_GATEWAY_AUDIT_DIR")
    audit_dir = Path(audit_dir_env).resolve() if audit_dir_env else None

    return BashGatewayServer(
        repo_root=repo_root,
        policy=policy,
        audit_dir=audit_dir,
    )


gateway = _load_gateway()
mcp = FastMCP("maestro Bash Gateway", json_response=True)


@mcp.tool()
def list_project_scripts(profile: Optional[str] = None) -> Dict[str, Any]:
    """List allowlisted scripts for one profile or all profiles."""
    return gateway.list_project_scripts(profile=profile)


@mcp.tool()
def describe_script(profile: str, script_path: str) -> Dict[str, Any]:
    """Return metadata for one allowlisted script."""
    try:
        return gateway.describe_script(profile=profile, script_path=script_path)
    except PolicyViolationError as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def run_project_script(
    profile: str,
    script_path: str,
    args: Optional[List[str]] = None,
    dry_run: Optional[bool] = None,
    timeout_sec: Optional[int] = None,
) -> Dict[str, Any]:
    """Run an allowlisted bash script with policy enforcement and audit logs."""
    try:
        return gateway.run_project_script(
            profile=profile,
            script_path=script_path,
            args=args,
            dry_run=dry_run,
            timeout_sec=timeout_sec,
        )
    except PolicyViolationError as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def get_script_run_log(run_id: str) -> Optional[Dict[str, Any]]:
    """Read one stored execution log by run ID."""
    return gateway.get_script_run_log(run_id)


def main() -> None:
    """Run MCP server with Streamable HTTP transport mounted at /mcp."""
    host = os.getenv("BASH_GATEWAY_MCP_HOST", "0.0.0.0")
    port = int(os.getenv("BASH_GATEWAY_MCP_PORT", "3011"))
    app = mcp.streamable_http_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
