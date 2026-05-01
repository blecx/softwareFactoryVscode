"""Shared text-write normalization for repository-owned writer surfaces.

The repository's validation lane enforces Black for Python sources. Several
agent/MCP writer paths persist text verbatim, so Python files created from LLM
or tool output can drift from the actual formatter contract even before
`black --check` runs.

This module centralizes the repository-owned Python write discipline:

- normalize LF line endings plus the trailing newline Black expects; and
- when formatter enforcement is required, run Black itself instead of trying to
    approximate its output by hand.
"""

from __future__ import annotations

from pathlib import Path, PurePath

try:
    import black
except ImportError:  # pragma: no cover - exercised via monkeypatch in tests.
    black = None

PYTHON_SOURCE_SUFFIXES = frozenset({".py", ".pyi"})


def normalize_repo_text_for_write(
    path: str | Path,
    content: str,
    *,
    require_python_formatter: bool = False,
) -> str:
    """Normalize text content before repository writer surfaces persist it.

    Python files are normalized to LF line endings and a trailing newline. When
    ``require_python_formatter`` is true, Black itself must also be available so
    valid Python sources are written in the formatter-approved shape rather than
    a hand-rolled approximation.

    Non-Python files are kept verbatim.
    """

    if PurePath(path).suffix not in PYTHON_SOURCE_SUFFIXES:
        return content

    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    if normalized and not normalized.endswith("\n"):
        normalized += "\n"

    if black is None:
        if require_python_formatter:
            raise RuntimeError(
                "Black must be available when repository writer surfaces save "
                "Python files in formatter-enforced mode. Run ./setup.sh or "
                "install the runtime formatter dependencies first."
            )
        return normalized

    try:
        return black.format_str(normalized, mode=black.FileMode())
    except black.NothingChanged:
        return normalized
    except black.InvalidInput:
        return normalized
