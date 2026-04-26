"""Machine-readable quota-governance contract models.

These models define the long-term multi-requester quota-governance contract for
provider-facing LLM access. They intentionally separate quota governance from
MCP runtime readiness/lifecycle authority so later implementation slices can
reuse one vocabulary without inventing a shadow runtime controller.
"""

from __future__ import annotations

from dataclasses import dataclass, is_dataclass
from enum import StrEnum
from typing import Any

from factory_runtime.agents.tooling.llm_quota_policy import LLMQuotaPolicy


class QuotaAuthorityScope(StrEnum):
    """Deployment scope for the quota-governance authority."""

    WORKSPACE_SCOPED = "workspace-scoped"
    SHARED_CAPABLE = "shared-capable"


class QuotaBudgetScope(StrEnum):
    """Hierarchical budget levels for provider-facing quota inheritance."""

    PROVIDER = "provider"
    MODEL_FAMILY = "model-family"
    WORKSPACE = "workspace"
    RUN = "run"
    REQUESTER = "requester"


class QuotaDimension(StrEnum):
    """Budget dimensions governed by the quota authority."""

    REQUESTS_PER_SECOND = "requests-per-second"
    TOKENS_PER_MINUTE = "tokens-per-minute"
    CONCURRENCY_LEASES = "concurrency-leases"


class QuotaLane(StrEnum):
    """Shared scheduling lanes inside one delegated budget envelope."""

    FOREGROUND = "foreground"
    RESERVE = "reserve"


class RequesterClass(StrEnum):
    """Requester classes that consume delegated quota."""

    INTERACTIVE = "interactive"
    PARENT_RUN = "parent-run"
    SUBAGENT = "subagent"
    BACKGROUND = "background"


_DEFAULT_QUOTA_DIMENSIONS = (
    QuotaDimension.REQUESTS_PER_SECOND,
    QuotaDimension.TOKENS_PER_MINUTE,
    QuotaDimension.CONCURRENCY_LEASES,
)


@dataclass(frozen=True, slots=True)
class QuotaAuthorityBoundary:
    """Authority boundary for quota governance versus runtime governance."""

    authority_name: str
    authority_scope: QuotaAuthorityScope
    runtime_truth_owner: str
    runtime_readiness_owner: str
    shared_rollout_requires_isolation_proof: bool = True
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProviderQuotaEnvelope:
    """Provider/model-family ceiling representation for shared requester budgets."""

    provider: str
    model: str
    model_family: str
    quota_bucket: str
    quota_source: str
    requests_per_second_ceiling: float
    token_quota_per_minute: int | None = None
    concurrency_lease_limit: int | None = None


@dataclass(frozen=True, slots=True)
class QuotaBudgetLevel:
    """One level in the hierarchical delegated budget model."""

    scope: QuotaBudgetScope
    parent_scope: QuotaBudgetScope | None
    governed_dimensions: tuple[QuotaDimension, ...]
    description: str


@dataclass(frozen=True, slots=True)
class QuotaLaneAllocation:
    """Shared lane allocation inside a delegated budget envelope."""

    lane: QuotaLane
    share: float
    request_rate_rps: float
    receives_reserved_capacity: bool
    description: str


@dataclass(frozen=True, slots=True)
class RequesterQuotaPolicy:
    """How one requester class consumes delegated quota."""

    requester_class: RequesterClass
    parent_budget_scope: QuotaBudgetScope
    default_lane: QuotaLane
    inherits_parent_budget: bool
    may_open_independent_provider_budget: bool
    description: str


@dataclass(frozen=True, slots=True)
class QuotaGovernanceContract:
    """Long-term quota-governance contract for provider-facing LLM access."""

    version: str
    authority_boundary: QuotaAuthorityBoundary
    quota_dimensions: tuple[QuotaDimension, ...]
    provider_budget: ProviderQuotaEnvelope
    budget_hierarchy: tuple[QuotaBudgetLevel, ...]
    lane_allocations: tuple[QuotaLaneAllocation, ...]
    requester_policies: tuple[RequesterQuotaPolicy, ...]
    notes: tuple[str, ...] = ()

    def get_lane_allocation(
        self,
        lane: QuotaLane | str,
    ) -> QuotaLaneAllocation:
        candidate = lane if isinstance(lane, QuotaLane) else QuotaLane(str(lane))
        for allocation in self.lane_allocations:
            if allocation.lane == candidate:
                return allocation
        raise KeyError(f"Unknown quota lane: {candidate}")

    def get_requester_policy(
        self,
        requester_class: RequesterClass | str,
    ) -> RequesterQuotaPolicy:
        candidate = (
            requester_class
            if isinstance(requester_class, RequesterClass)
            else RequesterClass(str(requester_class))
        )
        for policy in self.requester_policies:
            if policy.requester_class == candidate:
                return policy
        raise KeyError(f"Unknown requester class: {candidate}")

    def as_dict(self) -> dict[str, Any]:
        return serialize_quota_contract_value(self)


def build_default_quota_governance_contract(
    policy: LLMQuotaPolicy,
) -> QuotaGovernanceContract:
    """Build the canonical quota-governance contract from the active policy.

    The active `LLMQuotaPolicy` becomes the current provider/model-family budget
    envelope and lane split for one workspace-scoped quota authority. Later
    implementation slices can enrich the provider envelope with real token or
    concurrency limits without changing the contract vocabulary.
    """

    return QuotaGovernanceContract(
        version="1.0",
        authority_boundary=QuotaAuthorityBoundary(
            authority_name="quota-broker",
            authority_scope=QuotaAuthorityScope.WORKSPACE_SCOPED,
            runtime_truth_owner="mcp-runtime-manager",
            runtime_readiness_owner="mcp-runtime-manager",
            notes=(
                "Quota governance owns provider-facing request admission, "
                "shared budget state, and concurrency leasing.",
                "The MCP runtime manager remains authoritative for runtime "
                "lifecycle, readiness, and repair.",
                "Shared-service promotion is not assumed; workspace-scoped "
                "deployment remains the default until ADR-008 isolation proof "
                "exists.",
            ),
        ),
        quota_dimensions=_DEFAULT_QUOTA_DIMENSIONS,
        provider_budget=ProviderQuotaEnvelope(
            provider=policy.provider,
            model=policy.model,
            model_family=policy.model_family,
            quota_bucket=policy.quota_bucket,
            quota_source=policy.quota_source,
            requests_per_second_ceiling=policy.quota_ceiling_rps,
            concurrency_lease_limit=policy.concurrency_lease_limit,
        ),
        budget_hierarchy=(
            QuotaBudgetLevel(
                scope=QuotaBudgetScope.PROVIDER,
                parent_scope=None,
                governed_dimensions=_DEFAULT_QUOTA_DIMENSIONS,
                description=(
                    "Provider-wide ceiling across the upstream provider "
                    "surface before any workspace-specific allocation occurs."
                ),
            ),
            QuotaBudgetLevel(
                scope=QuotaBudgetScope.MODEL_FAMILY,
                parent_scope=QuotaBudgetScope.PROVIDER,
                governed_dimensions=_DEFAULT_QUOTA_DIMENSIONS,
                description=(
                    "Provider/model-family envelope that carries "
                    "model-specific request, token, and concurrency ceilings."
                ),
            ),
            QuotaBudgetLevel(
                scope=QuotaBudgetScope.WORKSPACE,
                parent_scope=QuotaBudgetScope.MODEL_FAMILY,
                governed_dimensions=_DEFAULT_QUOTA_DIMENSIONS,
                description=(
                    "Workspace-owned quota authority that coordinates one "
                    "repository/runtime identity without becoming runtime "
                    "authority."
                ),
            ),
            QuotaBudgetLevel(
                scope=QuotaBudgetScope.RUN,
                parent_scope=QuotaBudgetScope.WORKSPACE,
                governed_dimensions=_DEFAULT_QUOTA_DIMENSIONS,
                description=(
                    "Delegated execution-lineage budget for one parent run "
                    "inside the workspace envelope."
                ),
            ),
            QuotaBudgetLevel(
                scope=QuotaBudgetScope.REQUESTER,
                parent_scope=QuotaBudgetScope.RUN,
                governed_dimensions=_DEFAULT_QUOTA_DIMENSIONS,
                description=(
                    "Leaf requester budget for an interactive step, parent "
                    "agent action, or subagent action that must not reopen "
                    "provider entitlement."
                ),
            ),
        ),
        lane_allocations=(
            QuotaLaneAllocation(
                lane=QuotaLane.FOREGROUND,
                share=policy.foreground_share,
                request_rate_rps=policy.foreground_lane_rps,
                receives_reserved_capacity=False,
                description=(
                    "Primary shared lane for interactive work and active "
                    "parent execution progress."
                ),
            ),
            QuotaLaneAllocation(
                lane=QuotaLane.RESERVE,
                share=policy.reserve_share,
                request_rate_rps=policy.reserve_lane_rps,
                receives_reserved_capacity=True,
                description=(
                    "Protected reserve capacity for starvation avoidance, "
                    "retries, recovery, and background work."
                ),
            ),
        ),
        requester_policies=(
            RequesterQuotaPolicy(
                requester_class=RequesterClass.INTERACTIVE,
                parent_budget_scope=QuotaBudgetScope.WORKSPACE,
                default_lane=QuotaLane.FOREGROUND,
                inherits_parent_budget=True,
                may_open_independent_provider_budget=False,
                description=(
                    "Interactive requests consume workspace budget directly "
                    "when no parent execution lineage exists."
                ),
            ),
            RequesterQuotaPolicy(
                requester_class=RequesterClass.PARENT_RUN,
                parent_budget_scope=QuotaBudgetScope.WORKSPACE,
                default_lane=QuotaLane.FOREGROUND,
                inherits_parent_budget=True,
                may_open_independent_provider_budget=False,
                description=(
                    "A parent run receives delegated workspace budget and "
                    "becomes the lineage root for child work."
                ),
            ),
            RequesterQuotaPolicy(
                requester_class=RequesterClass.SUBAGENT,
                parent_budget_scope=QuotaBudgetScope.RUN,
                default_lane=QuotaLane.FOREGROUND,
                inherits_parent_budget=True,
                may_open_independent_provider_budget=False,
                description=(
                    "Subagents consume budget through their parent run and "
                    "must not receive an independent provider entitlement."
                ),
            ),
            RequesterQuotaPolicy(
                requester_class=RequesterClass.BACKGROUND,
                parent_budget_scope=QuotaBudgetScope.WORKSPACE,
                default_lane=QuotaLane.RESERVE,
                inherits_parent_budget=True,
                may_open_independent_provider_budget=False,
                description=(
                    "Background maintenance or retry work defaults to the "
                    "reserve lane unless a higher-priority policy overrides "
                    "it."
                ),
            ),
        ),
        notes=(
            "This contract defines authority and inheritance only; fairness "
            "and feedback behavior layer on top in later implementation "
            "slices.",
            "Foreground and reserve lanes are shared budget partitions, not "
            "per-process or per-client entitlements.",
            "The existing workspace-global throttle remains a bounded "
            "near-term baseline and is not the complete long-term broker "
            "architecture.",
        ),
    )


def serialize_quota_contract_value(value: Any) -> Any:
    """Convert quota-governance contract values into JSON-friendly structures."""

    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value):
        return {
            field_name: serialize_quota_contract_value(getattr(value, field_name))
            for field_name in value.__dataclass_fields__
        }
    if isinstance(value, dict):
        return {
            str(key): serialize_quota_contract_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [serialize_quota_contract_value(item) for item in value]
    return value
