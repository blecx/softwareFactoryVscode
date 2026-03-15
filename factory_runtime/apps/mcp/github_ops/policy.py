from __future__ import annotations

from dataclasses import dataclass


class GitHubOpsPolicyError(ValueError):
    """Raised when a request violates GitHub Ops policy."""


@dataclass(frozen=True)
class GitHubOpsPolicy:
    allowed_repos: frozenset[str]

    @classmethod
    def from_env(
        cls,
        *,
        allowed_repos_env: str | None,
        default_allowed_repos: list[str],
    ) -> "GitHubOpsPolicy":
        raw = allowed_repos_env.strip() if allowed_repos_env else ""
        if raw:
            repos = [item.strip() for item in raw.split(",") if item.strip()]
        else:
            repos = list(default_allowed_repos)

        normalized: list[str] = []
        for repo in repos:
            value = repo.strip()
            if not value or "/" not in value:
                raise GitHubOpsPolicyError(f"Invalid repo identifier: {repo}")
            normalized.append(value)

        if not normalized:
            raise GitHubOpsPolicyError("At least one allowed repo must be configured")

        return cls(allowed_repos=frozenset(normalized))

    def validate_repo(self, repo: str) -> str:
        value = (repo or "").strip()
        if not value:
            raise GitHubOpsPolicyError("repo is required")
        if value not in self.allowed_repos:
            raise GitHubOpsPolicyError(f"Repo not allowed: {value}")
        return value
