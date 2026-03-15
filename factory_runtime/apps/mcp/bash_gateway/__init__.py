"""MCP Bash Gateway package.

Safe, policy-based script execution primitives for AI agents.
"""

from .policy import BashGatewayPolicy, PolicyViolationError
from .executor import ScriptExecutor, ScriptRunResult
from .audit_store import AuditStore
from .server import BashGatewayServer

__all__ = [
    "BashGatewayPolicy",
    "PolicyViolationError",
    "ScriptExecutor",
    "ScriptRunResult",
    "AuditStore",
    "BashGatewayServer",
]
