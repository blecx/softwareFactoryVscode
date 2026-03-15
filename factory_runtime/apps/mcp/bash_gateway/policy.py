"""Policy model and validation for MCP Bash Gateway."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml


class PolicyViolationError(ValueError):
    """Raised when a script execution request violates policy."""


@dataclass(frozen=True)
class ProfilePolicy:
    """Single profile policy definition."""

    scripts: List[str]
    default_timeout_sec: int = 300
    max_timeout_sec: int = 900
    default_dry_run: bool = True


@dataclass(frozen=True)
class BashGatewayPolicy:
    """Top-level bash gateway policy."""

    profiles: Dict[str, ProfilePolicy]

    @classmethod
    def from_yaml_file(cls, path: Path) -> "BashGatewayPolicy":
        """Load policy from YAML file."""
        data = yaml.safe_load(path.read_text())
        return cls.from_dict(data or {})

    @classmethod
    def from_dict(cls, data: Dict) -> "BashGatewayPolicy":
        """Build policy model from dict."""
        profiles_data = data.get("profiles", {})
        if not profiles_data:
            raise ValueError("Policy must define at least one profile")

        profiles: Dict[str, ProfilePolicy] = {}
        for name, value in profiles_data.items():
            scripts = list(value.get("scripts", []))
            if not scripts:
                raise ValueError(f"Profile '{name}' must define scripts")

            profiles[name] = ProfilePolicy(
                scripts=scripts,
                default_timeout_sec=int(value.get("default_timeout_sec", 300)),
                max_timeout_sec=int(value.get("max_timeout_sec", 900)),
                default_dry_run=bool(value.get("default_dry_run", True)),
            )

        return cls(profiles=profiles)

    def get_profile(self, profile: str) -> ProfilePolicy:
        """Return profile or raise policy violation."""
        value = self.profiles.get(profile)
        if value is None:
            raise PolicyViolationError(f"Unknown profile: {profile}")
        return value

    def validate_script(
        self, *, profile: str, script_path: str, repo_root: Path
    ) -> Path:
        """Validate script path against allowlist and traversal policy."""
        profile_policy = self.get_profile(profile)

        if script_path.startswith("/"):
            raise PolicyViolationError("Absolute paths are not allowed")

        candidate = Path(script_path)
        if ".." in candidate.parts:
            raise PolicyViolationError("Path traversal is not allowed")

        normalized = candidate.as_posix()
        if normalized not in profile_policy.scripts:
            raise PolicyViolationError(
                f"Script not allowlisted for profile '{profile}': {normalized}"
            )

        resolved = (repo_root / candidate).resolve()
        if not str(resolved).startswith(str(repo_root.resolve())):
            raise PolicyViolationError("Script path escapes repository root")

        if not resolved.exists() or not resolved.is_file():
            raise PolicyViolationError(f"Script file not found: {normalized}")

        return resolved

    def resolve_timeout(
        self,
        *,
        profile: str,
        timeout_sec: Optional[int],
    ) -> int:
        """Resolve timeout with policy bounds."""
        p = self.get_profile(profile)
        if timeout_sec is None:
            return p.default_timeout_sec
        if timeout_sec <= 0:
            raise PolicyViolationError("timeout_sec must be > 0")
        if timeout_sec > p.max_timeout_sec:
            raise PolicyViolationError(
                f"timeout_sec exceeds profile max ({p.max_timeout_sec})"
            )
        return timeout_sec

    def resolve_dry_run(self, *, profile: str, dry_run: Optional[bool]) -> bool:
        """Resolve dry-run value from request or profile default."""
        p = self.get_profile(profile)
        if dry_run is None:
            return p.default_dry_run
        return bool(dry_run)
