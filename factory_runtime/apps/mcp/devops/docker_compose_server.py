import os
from pathlib import Path

import uvicorn
from mcp.server.fastmcp import FastMCP

from .docker_compose_service import DockerComposeService, DockerComposeServiceError


DEFAULT_TARGETS = {
    "main": "docker-compose.yml",
    "context7": "docker-compose.context7.yml",
    "bash_gateway": "docker-compose.mcp-bash-gateway.yml",
    "repo_fundamentals": "docker-compose.repo-fundamentals-mcp.yml",
    "devops_mcp": "docker-compose.mcp-devops.yml",
}


def _load_targets() -> dict[str, str]:
    raw = os.getenv("DOCKER_COMPOSE_MCP_TARGETS")
    if not raw:
        return DEFAULT_TARGETS

    targets: dict[str, str] = {}
    for pair in raw.split(","):
        item = pair.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"Invalid target mapping: {item}")
        name, compose_file = item.split("=", 1)
        targets[name.strip()] = compose_file.strip()
    return targets


def _load_service() -> DockerComposeService:
    repo_root = Path(os.getenv("DOCKER_COMPOSE_MCP_REPO_ROOT", "/workspace")).resolve()
    audit_dir = Path(
        os.getenv(
            "DOCKER_COMPOSE_MCP_AUDIT_DIR",
            str(repo_root / ".tmp" / "mcp-docker-compose"),
        )
    ).resolve()
    return DockerComposeService(
        repo_root=repo_root, compose_targets=_load_targets(), audit_dir=audit_dir
    )


service = _load_service()
mcp = FastMCP("maestro Docker Compose MCP", json_response=True)


@mcp.tool()
def docker_compose_targets() -> dict:
    """Return allowed compose targets and mapped compose files."""
    return service.list_targets()


@mcp.tool()
def docker_compose_ps(target: str = "main") -> dict:
    """Show compose service status for one allowed target."""
    try:
        return service.compose_ps(target=target)
    except (DockerComposeServiceError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def docker_compose_up(
    target: str = "main", build: bool = False, detach: bool = True
) -> dict:
    """Run docker compose up for one allowed target."""
    try:
        return service.compose_up(target=target, build=build, detach=detach)
    except (DockerComposeServiceError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def docker_compose_down(target: str = "main", remove_orphans: bool = True) -> dict:
    """Run docker compose down for one allowed target."""
    try:
        return service.compose_down(target=target, remove_orphans=remove_orphans)
    except (DockerComposeServiceError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def docker_compose_logs(
    target: str = "main", service_name: str | None = None, tail: int = 200
) -> dict:
    """Fetch compose logs for one allowed target and optional service."""
    try:
        return service.compose_logs(target=target, service=service_name, tail=tail)
    except (DockerComposeServiceError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def docker_compose_health(target: str = "main") -> dict:
    """Return normalized container state/health for one compose target."""
    try:
        return service.container_health(target=target)
    except (DockerComposeServiceError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def docker_compose_run_log(run_id: str) -> dict | None:
    """Return one audited run log by run ID."""
    return service.get_run_log(run_id)


def main() -> None:
    host = os.getenv("DOCKER_COMPOSE_MCP_HOST", "0.0.0.0")
    port = int(os.getenv("DOCKER_COMPOSE_MCP_PORT", "3015"))
    app = mcp.streamable_http_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
