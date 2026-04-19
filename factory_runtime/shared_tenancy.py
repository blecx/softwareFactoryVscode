"""Shared helpers for tenant identity extraction across FACTORY services.

The current per-workspace runtime remains in compatibility mode by default and
may fall back to ``PROJECT_WORKSPACE_ID`` when no explicit tenant selector is
present. Promoted shared mode must be stricter: every request needs an explicit
tenant identity and mismatched selectors must be rejected.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

COMPATIBILITY_TENANCY_MODE = "compatibility"
PROMOTED_SHARED_TENANCY_MODE = "shared"
TENANCY_MODE_ENV_VAR = "FACTORY_TENANCY_MODE"
WORKSPACE_ID_HEADER = "X-Workspace-ID"


class TenantIdentityError(ValueError):
    """Raised when a request does not carry a valid explicit tenant identity."""


def default_project_id() -> str:
    """Return the compatibility-mode workspace identity fallback."""
    project_id = os.getenv("PROJECT_WORKSPACE_ID", "default").strip()
    return project_id or "default"


def tenancy_mode() -> str:
    """Return the normalized tenancy mode for shared-service request handling."""
    mode = os.getenv(TENANCY_MODE_ENV_VAR, COMPATIBILITY_TENANCY_MODE).strip().lower()
    if mode in {"", COMPATIBILITY_TENANCY_MODE, "compat", "per-workspace"}:
        return COMPATIBILITY_TENANCY_MODE
    if mode in {PROMOTED_SHARED_TENANCY_MODE, "promoted-shared", "strict"}:
        return PROMOTED_SHARED_TENANCY_MODE
    return COMPATIBILITY_TENANCY_MODE


def is_promoted_shared_mode() -> bool:
    """Return True when shared services must require explicit tenant identity."""
    return tenancy_mode() == PROMOTED_SHARED_TENANCY_MODE


def header_workspace_id(headers: Mapping[str, str] | None) -> str | None:
    """Extract ``X-Workspace-ID`` from a mapping-like headers object."""
    if not headers:
        return None

    if hasattr(headers, "get"):
        for key in (WORKSPACE_ID_HEADER, WORKSPACE_ID_HEADER.lower()):
            value = headers.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    for key, value in headers.items():
        if str(key).lower() == WORKSPACE_ID_HEADER.lower():
            if isinstance(value, str) and value.strip():
                return value.strip()
            break
    return None


def resolve_tenant_identity(
    *,
    header_project_id: str | None = None,
    query_project_id: str | None = None,
    explicit_project_id: str | None = None,
    fallback_project_id: str | None = None,
) -> str:
    """Resolve one tenant identity and reject ambiguity in shared-service traffic."""

    selectors: list[tuple[str, str]] = []
    for label, raw_value in (
        (WORKSPACE_ID_HEADER, header_project_id),
        ("project_id", query_project_id),
        ("explicit_project_id", explicit_project_id),
    ):
        if isinstance(raw_value, str):
            value = raw_value.strip()
            if value:
                selectors.append((label, value))

    distinct_values = {value for _, value in selectors}
    if len(distinct_values) > 1:
        mismatch = ", ".join(f"{label}={value}" for label, value in selectors)
        raise TenantIdentityError(
            f"Tenant identity mismatch across explicit selectors: {mismatch}."
        )

    if selectors:
        return selectors[0][1]

    if is_promoted_shared_mode():
        raise TenantIdentityError(
            "Promoted shared mode requires an explicit tenant identity via "
            "X-Workspace-ID or another explicit tenant selector."
        )

    if isinstance(fallback_project_id, str) and fallback_project_id.strip():
        return fallback_project_id.strip()
    return default_project_id()
