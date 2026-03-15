"""Agent registry for issue-resolution runners."""

from importlib import import_module
from typing import Type

from factory_runtime.agents.factory_adapter import FactoryAdapter

AGENT_ALIASES = {
    "autonomous": "agents.factory_adapter:FactoryAdapter",
    "default": "agents.factory_adapter:FactoryAdapter",
    "ralph": "agents.ralph_agent:RalphAgent",
    "ralph-agent": "agents.ralph_agent:RalphAgent",
    "resolve-issue": "agents.factory_adapter:FactoryAdapter",
}


def _load_agent_class(spec: str) -> Type[FactoryAdapter]:
    if ":" not in spec:
        raise ValueError(
            f"Invalid agent spec '{spec}'. Expected format 'module.path:ClassName'."
        )

    module_name, class_name = spec.split(":", 1)
    module = import_module(module_name)
    cls = getattr(module, class_name, None)
    if cls is None:
        raise ValueError(
            f"Agent class '{class_name}' not found in module '{module_name}'."
        )
    if not issubclass(cls, FactoryAdapter):
        raise ValueError(f"Agent class '{class_name}' must inherit FactoryAdapter.")
    return cls


def resolve_agent_spec(agent_name_or_spec: str) -> str:
    requested = (agent_name_or_spec or "autonomous").strip().lower()
    if requested in AGENT_ALIASES:
        return AGENT_ALIASES[requested]
    return agent_name_or_spec.strip()


def create_issue_agent(
    *,
    agent_name_or_spec: str,
    issue_number: int,
    dry_run: bool,
) -> FactoryAdapter:
    spec = resolve_agent_spec(agent_name_or_spec)
    cls = _load_agent_class(spec)
    return cls(issue_number=issue_number, dry_run=dry_run)
