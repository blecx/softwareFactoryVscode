"""Filesystem-related tool implementations with typed contracts."""

from pathlib import Path

from agents.tooling.contracts import ToolResult


def read_file_content_typed(
    file_path: str,
    base_directory: str = ".",
) -> ToolResult[str]:
    """Read contents of a file."""
    try:
        path = Path(base_directory) / file_path
        if not path.exists():
            return ToolResult.failure(
                code="FILE_NOT_FOUND",
                message=f"File {file_path} does not exist",
            )

        if path.stat().st_size > 1_000_000:
            return ToolResult.failure(
                code="FILE_TOO_LARGE",
                message=f"File {file_path} is too large (>1MB)",
            )

        with open(path, "r", encoding="utf-8") as handle:
            return ToolResult.success(handle.read())
    except Exception as exc:
        return ToolResult.failure(
            code="IO_ERROR",
            message="Error reading file",
            details=str(exc),
        )


def write_file_content_typed(
    file_path: str,
    content: str,
    base_directory: str = ".",
) -> ToolResult[str]:
    """Write content to a file, creating directories if needed."""
    try:
        path = Path(base_directory) / file_path
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)

        return ToolResult.success(
            f"Successfully wrote {len(content)} bytes to {file_path}"
        )
    except Exception as exc:
        return ToolResult.failure(
            code="IO_ERROR",
            message="Error writing file",
            details=str(exc),
        )


def list_directory_contents_typed(
    directory_path: str,
    base_directory: str = ".",
) -> ToolResult[str]:
    """List files and directories in a given path."""
    try:
        path = Path(base_directory) / directory_path
        if not path.exists():
            return ToolResult.failure(
                code="DIRECTORY_NOT_FOUND",
                message=f"Directory {directory_path} does not exist",
            )

        if not path.is_dir():
            return ToolResult.failure(
                code="NOT_A_DIRECTORY",
                message=f"{directory_path} is not a directory",
            )

        entries = []
        for item in sorted(path.iterdir()):
            entries.append(f"{item.name}/" if item.is_dir() else item.name)

        return ToolResult.success("\n".join(entries))
    except Exception as exc:
        return ToolResult.failure(
            code="IO_ERROR",
            message="Error listing directory",
            details=str(exc),
        )
