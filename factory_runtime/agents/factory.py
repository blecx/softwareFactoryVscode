"""FactoryOrchestrator — top-level FACTORY agent pipeline.

Wires together:
  RouterAgent → CoderAgent → (PR creation) → (memory lesson)

One call to ``FactoryOrchestrator.run_issue()`` does everything needed to
implement a GitHub issue end-to-end.

Typical usage (programmatic):
    orq = FactoryOrchestrator(server_urls={...})
    result = await orq.run_issue(42, "YOUR_ORG/YOUR_REPO", "Fix bug", "Body...")
    print(result.pr_url)

See: docs/agents/FACTORY-DESIGN.md
Implements: GitHub issue #715
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from openai import AsyncOpenAI

from factory_runtime.agents.coder_agent import CoderAgent, CoderResult
from factory_runtime.agents.mcp_client import MCPMultiClient
from factory_runtime.agents.planner_agent import PlannerAgent
from factory_runtime.agents.router_agent import RouterAgent, RoutingDecision
from factory_runtime.mcp_runtime import MCPRuntimeManager, RuntimeProfileName

# ---------------------------------------------------------------------------
# Default server URLs (overridden by env or constructor arg)
# ---------------------------------------------------------------------------

_DEFAULT_SERVERS = {
    "mcp-memory": "http://localhost:3030",
    "mcp-agent-bus": "http://localhost:3031",
    "mcp-github-ops": "http://localhost:3018",
    "mcp-search": "http://localhost:3013",
    "mcp-filesystem": "http://localhost:3014",
}

_RUNTIME_MANIFEST_SERVER_MAPPING: dict[str, tuple[str, str]] = {
    "mcp-memory": ("runtime_health", "mcp-memory"),
    "mcp-agent-bus": ("runtime_health", "mcp-agent-bus"),
    "mcp-github-ops": ("mcp_servers", "githubOps"),
    "mcp-search": ("mcp_servers", "search"),
    "mcp-filesystem": ("mcp_servers", "filesystem"),
}
_RUNTIME_SERVER_ENV_MAPPING = {
    "mcp-memory": "FACTORY_MEMORY_URL",
    "mcp-agent-bus": "FACTORY_BUS_URL",
    "mcp-github-ops": "FACTORY_GITHUB_URL",
    "mcp-search": "FACTORY_SEARCH_URL",
    "mcp-filesystem": "FACTORY_FILESYSTEM_URL",
}


def _build_runtime_manager() -> MCPRuntimeManager:
    return MCPRuntimeManager()


def _load_workspace_id(workspace_root: Path) -> str | None:
    env_workspace_id = os.environ.get("PROJECT_WORKSPACE_ID", "").strip()
    if env_workspace_id:
        return env_workspace_id

    return _build_runtime_manager().load_workspace_id(workspace_root)


def _load_server_urls_from_runtime_manifest(workspace_root: Path) -> dict[str, str]:
    """Load FACTORY MCP endpoints from the manager-backed runtime accessors.

    The manager owns source-checkout companion-runtime resolution and the
    manifest/env fallback shim when a full runtime snapshot is not available.
    """
    return _build_runtime_manager().load_named_urls_from_workspace(
        workspace_root,
        _RUNTIME_MANIFEST_SERVER_MAPPING,
        selected_profiles=(RuntimeProfileName.HARNESS_DEFAULT,),
    )


def _load_server_urls(workspace_root: Path | None = None) -> dict[str, str]:
    """Build server URLs from env, then runtime manifest, then legacy defaults."""
    resolved_root = (workspace_root or Path.cwd()).resolve()
    runtime_manifest_urls = _load_server_urls_from_runtime_manifest(resolved_root)
    result: dict[str, str] = {}
    for name, env_key in _RUNTIME_SERVER_ENV_MAPPING.items():
        result[name] = os.environ.get(
            env_key,
            runtime_manifest_urls.get(name, _DEFAULT_SERVERS[name]),
        )
    return result


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class OrchestratorResult:
    """End-to-end result of running FACTORY on one issue."""

    issue_number: int
    repo: str
    run_id: Optional[str] = None
    pr_url: Optional[str] = None
    files_changed: list[str] = field(default_factory=list)
    complexity_score: int = 0
    model_tier: str = "mini"
    tests_passed: bool = False
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and self.tests_passed


# ---------------------------------------------------------------------------
# FactoryOrchestrator
# ---------------------------------------------------------------------------


class FactoryOrchestrator:
    """Top-level orchestrator: route → code → validate → PR → memory."""

    def __init__(
        self,
        server_urls: Optional[dict[str, str]] = None,
        llm_client: Optional["AsyncOpenAI"] = None,
        workspace_root: Optional[Path] = None,
    ) -> None:
        """
        Args:
            server_urls:    Dict of {server_name: url}.  Falls back to
                            FACTORY_*_URL env vars, generated runtime-manifest
                            endpoints, or legacy localhost defaults.
            llm_client:     Optional AsyncOpenAI client (injected for testing).
            workspace_root: Root for file operations (defaults to cwd).
        """
        self._root = workspace_root or Path.cwd()
        self._server_urls = server_urls or _load_server_urls(self._root)
        self._workspace_id = _load_workspace_id(self._root)
        self._llm = llm_client

    async def run_issue(
        self,
        issue_number: int,
        repo: str,
        issue_title: str = "",
        issue_body: str = "",
        changed_files: Optional[list[str]] = None,
    ) -> OrchestratorResult:
        """Execute the full FACTORY pipeline for one GitHub issue.

        Args:
            issue_number:   GitHub issue number.
            repo:           Repository in ``owner/name`` format.
            issue_title:    Issue title string.
            issue_body:     Issue body (markdown) string.
            changed_files:  Optional list of files already known to be relevant.

        Returns:
            OrchestratorResult — never raises.
        """
        try:
            return await self._pipeline(
                issue_number, repo, issue_title, issue_body, changed_files or []
            )
        except Exception as exc:  # noqa: BLE001
            return OrchestratorResult(
                issue_number=issue_number,
                repo=repo,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    async def _pipeline(
        self,
        issue_number: int,
        repo: str,
        issue_title: str,
        issue_body: str,
        changed_files: list[str],
    ) -> OrchestratorResult:
        async with MCPMultiClient(
            [{"name": k, "url": v} for k, v in self._server_urls.items()],
            workspace_id=self._workspace_id,
        ) as mcp:
            # ── 1. Route ─────────────────────────────────────────────
            router = RouterAgent(mcp)
            decision: RoutingDecision = await router.route(
                issue_number=issue_number,
                issue_title=issue_title,
                issue_body=issue_body,
                repo=repo,
                changed_files=changed_files,
            )

            # ── 1.5. Plan ─────────────────────────────────────────────
            planner = PlannerAgent(
                mcp,
                model_tier=decision.planning_model_tier,
                llm_client=self._llm,
                workspace_root=self._root,
            )
            await planner.run(decision.run_id, issue_body, decision.similar_issues)

            # ── 2. Code ───────────────────────────────────────────────
            coder = CoderAgent(
                mcp,
                model_tier=decision.coder_model_tier,
                llm_client=self._llm,
                workspace_root=self._root,
            )
            coder_result: CoderResult = await coder.run(decision.run_id)

            if coder_result.error:
                return OrchestratorResult(
                    issue_number=issue_number,
                    repo=repo,
                    run_id=decision.run_id,
                    complexity_score=decision.complexity_score,
                    model_tier=decision.coder_model_tier,
                    error=coder_result.error,
                )

            # ── 3. Create PR ──────────────────────────────────────────
            pr_url: Optional[str] = None
            if coder_result.pr_ready:
                pr_url = await self._create_pr(
                    mcp=mcp,
                    run_id=decision.run_id,
                    issue_number=issue_number,
                    repo=repo,
                    issue_title=issue_title,
                    files_changed=coder_result.files_changed,
                )

            # ── 4. Store memory lesson ────────────────────────────────
            await self._store_lesson(
                mcp=mcp,
                issue_number=issue_number,
                repo=repo,
                decision=decision,
                coder_result=coder_result,
                pr_url=pr_url,
            )

            return OrchestratorResult(
                issue_number=issue_number,
                repo=repo,
                run_id=decision.run_id,
                pr_url=pr_url,
                files_changed=coder_result.files_changed,
                complexity_score=decision.complexity_score,
                model_tier=decision.coder_model_tier,
                tests_passed=coder_result.tests_passed,
            )

    # ------------------------------------------------------------------
    # PR creation
    # ------------------------------------------------------------------

    async def _create_pr(
        self,
        mcp: MCPMultiClient,
        run_id: str,
        issue_number: int,
        repo: str,
        issue_title: str,
        files_changed: list[str],
    ) -> Optional[str]:
        """Call github-ops MCP to create a PR. Returns PR URL or None on failure."""
        branch = f"factory/issue-{issue_number}"
        title = (
            f"feat: {issue_title} (#{issue_number})"
            if issue_title
            else f"feat: issue #{issue_number}"
        )
        body = (
            f"Implements #{issue_number}\n\n"
            f"Generated by FACTORY (run `{run_id}`).\n\n"
            f"**Files changed:**\n" + "\n".join(f"- `{f}`" for f in files_changed)
        )
        try:
            result: Any = await mcp.call_tool(
                "create_pr",
                {
                    "repo": repo,
                    "title": title,
                    "body": body,
                    "head": branch,
                    "base": "main",
                },
            )
            # github-ops returns {"html_url": "..."} or {"url": "..."}
            if isinstance(result, dict):
                return result.get("html_url") or result.get("url")
        except Exception:  # noqa: BLE001
            pass
        return None

    # ------------------------------------------------------------------
    # Memory storage
    # ------------------------------------------------------------------

    async def _store_lesson(
        self,
        mcp: MCPMultiClient,
        issue_number: int,
        repo: str,
        decision: RoutingDecision,
        coder_result: CoderResult,
        pr_url: Optional[str],
    ) -> None:
        """Persist a memory lesson so future similar issues route better."""
        outcome = "success" if coder_result.tests_passed else "failure"
        insight = (
            f"Issue #{issue_number} in {repo}: "
            f"complexity={decision.complexity_score} ({decision.coder_model_tier}), "
            f"outcome={outcome}, "
            f"files={len(coder_result.files_changed)}"
            + (f", pr={pr_url}" if pr_url else "")
        )
        learnings = [
            f"Model tier used: {decision.coder_model_tier}",
            f"Complexity score: {decision.complexity_score}",
            f"Files changed: {len(coder_result.files_changed)}",
            f"Outcome: {outcome}",
        ]
        if pr_url:
            learnings.append(f"Pull request created: {pr_url}")
        try:
            await mcp.call_tool(
                "memory_store_lesson",
                {
                    "issue_number": issue_number,
                    "repo": repo,
                    "outcome": outcome,
                    "summary": insight,
                    "learnings": learnings,
                },
            )
        except Exception:  # noqa: BLE001
            pass  # Memory failure never blocks the pipeline
