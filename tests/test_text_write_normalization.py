from __future__ import annotations

import pytest

import factory_runtime.text_write_normalization as text_write_normalization
from factory_runtime.agents.tooling.filesystem_tools import write_file_content_typed
from factory_runtime.apps.mcp.repo_fundamentals.filesystem_service import (
    FilesystemService,
)
from factory_runtime.text_write_normalization import normalize_repo_text_for_write


def test_normalize_repo_text_for_write_appends_trailing_newline_for_python() -> None:
    assert normalize_repo_text_for_write("generated.py", "value = 1") == "value = 1\n"


def test_normalize_repo_text_for_write_normalizes_python_line_endings() -> None:
    assert (
        normalize_repo_text_for_write("generated.py", "value = 1\r\nprint(value)")
        == "value = 1\nprint(value)\n"
    )


def test_normalize_repo_text_for_write_keeps_non_python_files_verbatim() -> None:
    assert normalize_repo_text_for_write("README.md", "headline") == "headline"


def test_normalize_repo_text_for_write_runs_black_for_valid_python() -> None:
    assert (
        normalize_repo_text_for_write("generated.py", 'value={  "a":1}')
        == 'value = {"a": 1}\n'
    )


def test_normalize_repo_text_for_write_requires_black_when_enforced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(text_write_normalization, "black", None)

    with pytest.raises(RuntimeError, match="Black must be available"):
        text_write_normalization.normalize_repo_text_for_write(
            "generated.py",
            "value = 1",
            require_python_formatter=True,
        )


def test_normalize_repo_text_for_write_keeps_invalid_python_but_normalizes_shape() -> (
    None
):
    assert (
        normalize_repo_text_for_write("generated.py", "def broken(\r\n")
        == "def broken(\n"
    )


def test_write_file_content_typed_normalizes_python_source_for_black(
    tmp_path,
) -> None:
    result = write_file_content_typed(
        "generated.py",
        'value={  "a":1}',
        base_directory=str(tmp_path),
    )

    assert result.ok is True
    assert result.value == "Successfully wrote 17 bytes to generated.py"
    assert (tmp_path / "generated.py").read_text(encoding="utf-8") == (
        'value = {"a": 1}\n'
    )


def test_filesystem_service_write_text_normalizes_python_source_for_black(
    tmp_path,
) -> None:
    service = FilesystemService(repo_root=tmp_path)

    result = service.write_text("pkg/generated.py", 'value={  "a":1}')

    assert result == {"path": "pkg/generated.py", "bytes_written": 17}
    assert (tmp_path / "pkg" / "generated.py").read_text(encoding="utf-8") == (
        'value = {"a": 1}\n'
    )
