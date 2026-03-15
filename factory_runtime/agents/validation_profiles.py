"""Canonical validation command profiles for workflow agents.

This module provides a single source of truth for validation command sets used
across workflow orchestration and phase services.
"""

from __future__ import annotations

from typing import List
import re


_PROFILE_MAP = {
    "backend": {
        "full": [
            "python -m black apps/api/",
            "python -m flake8 apps/api/",
            "pytest",
        ],
        "test_only": [
            "python -m black apps/api/",
            "python -m flake8 apps/api/",
            "pytest",
        ],
        "type_only": ["python -m mypy apps/api/"],
        "doc_only": [],
    },
    "client": {
        "full": ["npm run lint", "npm test", "npm run build"],
        "test_only": ["npm run lint", "npm test"],
        "type_only": ["npx tsc --noEmit", "npm run lint"],
        "doc_only": ["npx markdownlint '**/*.md' --ignore node_modules"],
    },
}

_COMMAND_NAMESPACE_PATTERN = re.compile(r"^(speckit|blecs)\.(.+)$")
_DEFAULT_REQUIRED_MARKERS = ["---", "description:", "User request:"]


def get_validation_commands(repo_type: str, profile: str = "full") -> List[str]:
    """Return validation commands for a repo/profile combination.

    Unknown repo/profile combinations return an empty list.
    """

    repo_profiles = _PROFILE_MAP.get(repo_type)
    if not repo_profiles:
        return []

    commands = repo_profiles.get(profile)
    if not commands:
        return []

    return list(commands)


def validate_namespace_collision(command_ids: List[str]) -> List[str]:
    """Validate command namespace shadowing between speckit and blecs.

    A collision exists when both namespaces define the same command suffix,
    for example `speckit.plan` and `blecs.plan`.
    """
    suffix_to_namespaces: dict[str, set[str]] = {}

    for command_id in command_ids:
        match = _COMMAND_NAMESPACE_PATTERN.match(command_id)
        if not match:
            continue

        namespace = match.group(1)
        suffix = match.group(2)
        if suffix not in suffix_to_namespaces:
            suffix_to_namespaces[suffix] = set()
        suffix_to_namespaces[suffix].add(namespace)

    errors: List[str] = []
    for suffix, namespaces in sorted(suffix_to_namespaces.items()):
        if {"speckit", "blecs"}.issubset(namespaces):
            errors.append(
                f"Namespace shadowing detected for '{suffix}': "
                f"speckit.{suffix} conflicts with blecs.{suffix}"
            )

    return errors


def validate_contract_markers(
    content: str,
    required_markers: List[str] | None = None,
) -> List[str]:
    """Validate command contract content for required textual markers."""
    markers = required_markers or _DEFAULT_REQUIRED_MARKERS
    missing_markers: List[str] = []

    for marker in markers:
        if marker not in content:
            missing_markers.append(marker)

    return missing_markers
