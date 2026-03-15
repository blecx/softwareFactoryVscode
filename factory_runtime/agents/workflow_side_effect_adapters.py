#!/usr/bin/env python3
"""Adapters for workflow side effects.

This module isolates subprocess/CLI side effects behind explicit adapter
interfaces and provides consistent error mapping.
"""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol, Sequence, Union


CommandInput = Union[str, Sequence[str]]


@dataclass(frozen=True)
class CommandExecutionResult:
    """Normalized command execution result."""

    returncode: int
    stdout: str
    stderr: str


class WorkflowSideEffectError(RuntimeError):
    """Standardized error for adapter execution failures."""

    def __init__(
        self,
        message: str,
        *,
        command: Optional[str] = None,
        returncode: Optional[int] = None,
        stderr: str = "",
        cause: Optional[BaseException] = None,
    ):
        super().__init__(message)
        self.command = command
        self.returncode = returncode
        self.stderr = stderr
        self.cause = cause


class WorkflowSideEffectAdapter(Protocol):
    """Interface for CLI/subprocess side effects used by workflow phases."""

    def run(
        self,
        command: CommandInput,
        *,
        cwd: Optional[Path] = None,
        check: bool = True,
        shell: bool = False,
    ) -> CommandExecutionResult:
        """Run a command and return normalized execution result."""

    async def run_async_shell(
        self, command: str, *, cwd: Optional[Path] = None
    ) -> CommandExecutionResult:
        """Run a shell command asynchronously."""


class SubprocessWorkflowSideEffectAdapter:
    """Default workflow side-effect adapter backed by ``subprocess``."""

    def run(
        self,
        command: CommandInput,
        *,
        cwd: Optional[Path] = None,
        check: bool = True,
        shell: bool = False,
    ) -> CommandExecutionResult:
        command_repr = self._command_repr(command)

        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                shell=shell,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise WorkflowSideEffectError(
                "Failed to execute workflow side effect command",
                command=command_repr,
                cause=exc,
            ) from exc

        result = CommandExecutionResult(
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )

        if check and result.returncode != 0:
            raise WorkflowSideEffectError(
                "Workflow side effect command failed",
                command=command_repr,
                returncode=result.returncode,
                stderr=result.stderr,
            )

        return result

    async def run_async_shell(
        self, command: str, *, cwd: Optional[Path] = None
    ) -> CommandExecutionResult:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
        except OSError as exc:
            raise WorkflowSideEffectError(
                "Failed to execute async workflow side effect command",
                command=command,
                cause=exc,
            ) from exc

        return CommandExecutionResult(
            returncode=proc.returncode,
            stdout=stdout.decode() if stdout else "",
            stderr=stderr.decode() if stderr else "",
        )

    @staticmethod
    def _command_repr(command: CommandInput) -> str:
        if isinstance(command, str):
            return command
        return " ".join(str(part) for part in command)
