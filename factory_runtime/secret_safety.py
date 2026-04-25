from __future__ import annotations

import os
import re
from typing import Iterable, Mapping

RUNTIME_MODE_ENV_KEY = "FACTORY_RUNTIME_MODE"
PRODUCTION_RUNTIME_MODE = "production"
KNOWN_SECRET_ENV_KEYS = (
    "CONTEXT7_API_KEY",
    "OPENAI_API_KEY",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "GITHUB_PAT",
)

_PLACEHOLDER_EXACT_VALUES = frozenset(
    {
        "your-api-key-here",
        "your-token-here",
        "your token here",
        "your_token_here",
        "your_context7_key_here",
        "your_live_github_token_here",
        "your_github_pat_here",
        "your_live_openai_key_here",
        "your_org/your_repo",
        "changeme",
        "placeholder",
        "sk-dummy-test",
    }
)
_PLACEHOLDER_SUBSTRINGS = (
    "your token here",
    "your_token_here",
    "example.invalid",
)
_REPO_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_ENV_ASSIGNMENT_PATTERN = re.compile(
    r"(?P<key>\b(?:CONTEXT7_API_KEY|OPENAI_API_KEY|GITHUB_TOKEN|GH_TOKEN|"
    r"GITHUB_PAT|api_key)\b)(?P<sep>\s*=\s*)(?P<value>\"[^\"]*\"|"
    r"'[^']*'|[^\s,;]+)",
    re.IGNORECASE,
)
_YAML_ASSIGNMENT_PATTERN = re.compile(
    r"(?P<key>\b(?:CONTEXT7_API_KEY|OPENAI_API_KEY|GITHUB_TOKEN|GH_TOKEN|"
    r"GITHUB_PAT|api_key)\b)(?P<sep>\s*:\s*)(?P<value>\"[^\"]*\"|"
    r"'[^']*'|[^\s,;#]+)",
    re.IGNORECASE,
)
_JSON_ASSIGNMENT_PATTERN = re.compile(
    r'(?P<prefix>"(?:CONTEXT7_API_KEY|OPENAI_API_KEY|GITHUB_TOKEN|GH_TOKEN|GITHUB_PAT|api_key)"\s*:\s*)"[^\"]*"',
    re.IGNORECASE,
)
_TOKEN_PATTERNS = (
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
)


def production_runtime_mode_enabled(
    env: Mapping[str, str] | None = None,
) -> bool:
    values = env if env is not None else os.environ
    return (
        str(values.get(RUNTIME_MODE_ENV_KEY, "")).strip().lower()
        == PRODUCTION_RUNTIME_MODE
    )


def looks_like_placeholder(value: str | None) -> bool:
    text = str(value or "").strip()
    if not text:
        return False

    lowered = text.lower()
    if lowered in _PLACEHOLDER_EXACT_VALUES:
        return True
    if any(token in lowered for token in _PLACEHOLDER_SUBSTRINGS):
        return True
    if lowered.startswith("your_") and lowered.endswith("_here"):
        return True
    if lowered.startswith("your-") and lowered.endswith("-here"):
        return True
    return False


def is_blank_or_placeholder(value: str | None) -> bool:
    return not str(value or "").strip() or looks_like_placeholder(value)


def is_placeholder_repo_list(value: str | None) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return True

    repos = [item.strip() for item in raw.split(",") if item.strip()]
    if not repos:
        return True

    return any(
        looks_like_placeholder(repo) or not _REPO_IDENTIFIER_PATTERN.match(repo)
        for repo in repos
    )


def _known_secret_values(
    extra_secret_values: Iterable[str] = (),
) -> tuple[str, ...]:
    values: list[str] = []
    for key in KNOWN_SECRET_ENV_KEYS:
        candidate = str(os.environ.get(key, "")).strip()
        if (
            candidate
            and not looks_like_placeholder(candidate)
            and candidate not in values
        ):
            values.append(candidate)

    for raw_value in extra_secret_values:
        candidate = str(raw_value or "").strip()
        if (
            candidate
            and not looks_like_placeholder(candidate)
            and candidate not in values
        ):
            values.append(candidate)

    return tuple(values)


def redact_secret_text(
    text: str,
    *,
    extra_secret_values: Iterable[str] = (),
) -> str:
    value = text or ""
    value = _ENV_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group('key')}{match.group('sep')}[REDACTED]",
        value,
    )
    value = _YAML_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group('key')}{match.group('sep')}[REDACTED]",
        value,
    )
    value = _JSON_ASSIGNMENT_PATTERN.sub(
        lambda match: f'{match.group("prefix")}"[REDACTED]"',
        value,
    )
    for pattern in _TOKEN_PATTERNS:
        value = pattern.sub("[REDACTED]", value)

    for secret_value in _known_secret_values(extra_secret_values):
        value = value.replace(secret_value, "[REDACTED]")

    return value
