"""Typed contracts for agent tooling operations."""

from dataclasses import dataclass
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class ToolError:
    """Structured error metadata for tool failures."""

    code: str
    message: str
    details: Optional[str] = None


@dataclass(frozen=True)
class ToolResult(Generic[T]):
    """Typed success/failure result for tooling operations."""

    ok: bool
    value: Optional[T] = None
    error: Optional[ToolError] = None

    @classmethod
    def success(cls, value: T) -> "ToolResult[T]":
        return cls(ok=True, value=value)

    @classmethod
    def failure(
        cls,
        *,
        code: str,
        message: str,
        details: Optional[str] = None,
    ) -> "ToolResult[T]":
        return cls(
            ok=False, error=ToolError(code=code, message=message, details=details)
        )
