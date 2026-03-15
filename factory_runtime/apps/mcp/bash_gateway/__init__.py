"""MCP Bash Gateway package.

Safe, policy-based script execution primitives for AI agents.
"""

from .audit_store import AuditStore
from .executor import ScriptExecutor, ScriptRunResult
from .policy import BashGatewayPolicy, PolicyViolationError
from .server import BashGatewayServer

__all__ = [
    "BashGatewayPolicy",
    "PolicyViolationError",
    "ScriptExecutor",
    "ScriptRunResult",
    "AuditStore",
    "BashGatewayServer",
]
