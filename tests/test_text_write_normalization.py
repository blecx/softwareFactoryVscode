from __future__ import annotations

import ast
import inspect
import textwrap

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


# ---------------------------------------------------------------------------
# Formatter-fidelity audit lock: coder_agent writer surfaces
# ---------------------------------------------------------------------------


def test_coder_agent_implement_writer_uses_require_python_formatter() -> None:
    """Lock coder_agent._implement writer to require_python_formatter=True.

    Parses the source of coder_agent._implement and asserts that every call to
    normalize_repo_text_for_write passes require_python_formatter=True.  This is
    a structural audit lock — it fails if a future edit drops the formatter
    enforcement flag on the issue-execution write path without a deliberate review.
    """
    import factory_runtime.agents.coder_agent as coder_agent_module

    source = inspect.getsource(coder_agent_module.CoderAgent._implement)
    tree = ast.parse(textwrap.dedent(source))

    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "normalize_repo_text_for_write"
    ]

    assert (
        calls
    ), "_implement must contain at least one normalize_repo_text_for_write call"

    for call in calls:
        kw_names = {kw.arg for kw in call.keywords}
        assert "require_python_formatter" in kw_names, (
            "Every normalize_repo_text_for_write call in CoderAgent._implement "
            "must pass require_python_formatter=True"
        )
        for kw in call.keywords:
            if kw.arg == "require_python_formatter":
                assert (
                    isinstance(kw.value, ast.Constant) and kw.value.value is True
                ), "require_python_formatter must be True in CoderAgent._implement"


def test_coder_agent_validate_retry_writer_uses_require_python_formatter() -> None:
    """Lock coder_agent._validate_with_retry repair writer to require_python_formatter=True.

    Same structural audit lock as above but for the retry/repair write path inside
    _validate_with_retry, which also persists LLM-generated Python files.
    """
    import factory_runtime.agents.coder_agent as coder_agent_module

    source = inspect.getsource(coder_agent_module.CoderAgent._validate_with_retry)
    tree = ast.parse(textwrap.dedent(source))

    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "normalize_repo_text_for_write"
    ]

    assert (
        calls
    ), "_validate_with_retry must contain at least one normalize_repo_text_for_write call"

    for call in calls:
        kw_names = {kw.arg for kw in call.keywords}
        assert "require_python_formatter" in kw_names, (
            "Every normalize_repo_text_for_write call in CoderAgent._validate_with_retry "
            "must pass require_python_formatter=True"
        )
        for kw in call.keywords:
            if kw.arg == "require_python_formatter":
                assert (
                    isinstance(kw.value, ast.Constant) and kw.value.value is True
                ), "require_python_formatter must be True in CoderAgent._validate_with_retry"
