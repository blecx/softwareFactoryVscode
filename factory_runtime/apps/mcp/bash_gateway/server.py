"""Minimal MCP-style gateway facade.

This file provides the callable tool contract that can be wrapped by an MCP
transport layer later, while already enforcing policy and audit requirements.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from .audit_store import AuditStore
from .executor import ScriptExecutor
from .policy import BashGatewayPolicy


class BashGatewayServer:
    """Gateway facade exposing tool-like methods."""

    def __init__(
        self,
        *,
        repo_root: Path,
        policy: BashGatewayPolicy,
        audit_dir: Optional[Path] = None,
    ):
        self.repo_root = repo_root
        self.policy = policy
        self.audit_store = AuditStore(
            audit_dir or repo_root / ".tmp" / "agent-script-runs"
        )
        self.executor = ScriptExecutor(
            repo_root=repo_root, audit_store=self.audit_store
        )

    def list_project_scripts(self, profile: Optional[str] = None) -> Dict:
        """Return allowlisted scripts for all profiles or one profile."""
        if profile is None:
            return {
                "profiles": {
                    name: p.scripts for name, p in self.policy.profiles.items()
                }
            }

        p = self.policy.get_profile(profile)
        return {"profile": profile, "scripts": p.scripts}

    def describe_script(self, *, profile: str, script_path: str) -> Dict:
        """Validate and return script metadata."""
        resolved = self.policy.validate_script(
            profile=profile,
            script_path=script_path,
            repo_root=self.repo_root,
        )
        return {
            "profile": profile,
            "script_path": script_path,
            "exists": True,
            "size_bytes": resolved.stat().st_size,
            "absolute_path": str(resolved),
        }

    def run_project_script(
        self,
        *,
        profile: str,
        script_path: str,
        args: Optional[List[str]] = None,
        dry_run: Optional[bool] = None,
        timeout_sec: Optional[int] = None,
    ) -> Dict:
        """Validate policy and execute script."""
        resolved = self.policy.validate_script(
            profile=profile,
            script_path=script_path,
            repo_root=self.repo_root,
        )
        resolved_timeout = self.policy.resolve_timeout(
            profile=profile,
            timeout_sec=timeout_sec,
        )
        resolved_dry_run = self.policy.resolve_dry_run(
            profile=profile,
            dry_run=dry_run,
        )

        result = self.executor.execute(
            profile=profile,
            script_path=script_path,
            absolute_script_path=resolved,
            timeout_sec=resolved_timeout,
            dry_run=resolved_dry_run,
            args=args or [],
        )
        return {
            "run_id": result.run_id,
            "status": result.status,
            "exit_code": result.exit_code,
            "duration_sec": result.duration_sec,
            "output": result.output,
            "log_path": result.log_path,
        }

    def get_script_run_log(self, run_id: str) -> Optional[Dict]:
        """Return audit record for run ID."""
        return self.audit_store.get(run_id)
