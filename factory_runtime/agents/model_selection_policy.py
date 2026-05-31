from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class ModelProfile:
    name: str
    file_cap: int
    diff_budget: int
    domain_cap: int
    context_class: str
    fallback_actions: list[str]
    tool_subset: list[str]


@dataclass
class ExecutionFitResult:
    is_fit: bool
    reason: str
    action_required: str  # "fits-selected-model", "split-issue-required", "upgrade-model-recommended", "blocked-by-authority-contract"
    fallback_recommendation: list[str] = __import__("dataclasses").field(
        default_factory=list
    )
    compact_tool_subset: list[str] = __import__("dataclasses").field(
        default_factory=list
    )


class ModelSelectionPolicy:
    """Evaluates whether an execution slice fits within a chosen model profile."""

    def __init__(self, profiles_path: Optional[str] = None):
        self.profiles: dict[str, ModelProfile] = {}
        if profiles_path:
            self.load_profiles(Path(profiles_path))

    def load_profiles(self, path: Path) -> None:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            for k, v in data.items():
                self.profiles[k] = ModelProfile(
                    name=k,
                    file_cap=v.get("file_cap", 5),
                    diff_budget=v.get("diff_budget", 250),
                    domain_cap=v.get("domain_cap", 1),
                    context_class=v.get("context_class", "narrow"),
                    fallback_actions=v.get("fallback_actions", []),
                    tool_subset=v.get("tool_subset", []),
                )

    def evaluate(
        self,
        profile_name: str,
        file_count: int,
        domain_count: int,
        violates_authority: bool = False,
    ) -> ExecutionFitResult:
        if violates_authority:
            return ExecutionFitResult(
                is_fit=False,
                reason="Execution slice violates authority contract",
                action_required="blocked-by-authority-contract",
                fallback_recommendation=[],
                compact_tool_subset=[],
            )

        profile = self.profiles.get(profile_name)
        if not profile:
            # Fallback if profile not found: assume strict ADR-018 limits
            if file_count > 5 or domain_count > 1:
                return ExecutionFitResult(
                    is_fit=False,
                    reason="Exceeds ADR-018 fallback limits",
                    action_required="split-issue-required",
                    fallback_recommendation=[],
                    compact_tool_subset=[],
                )
            return ExecutionFitResult(
                is_fit=True,
                reason="Fits fallback limits",
                action_required="fits-selected-model",
                fallback_recommendation=[],
                compact_tool_subset=[],
            )

        if file_count > profile.file_cap or domain_count > profile.domain_cap:
            if "escalate-to-full" in profile.fallback_actions:
                return ExecutionFitResult(
                    is_fit=False,
                    reason=f"Exceeds cap for {profile_name}, upgrade recommended",
                    action_required="upgrade-model-recommended",
                    fallback_recommendation=profile.fallback_actions,
                    compact_tool_subset=profile.tool_subset,
                )
            return ExecutionFitResult(
                is_fit=False,
                reason=f"Exceeds cap for {profile_name}",
                action_required="split-issue-required",
                fallback_recommendation=profile.fallback_actions,
                compact_tool_subset=profile.tool_subset,
            )

        return ExecutionFitResult(
            is_fit=True,
            reason="Fits selected model",
            action_required="fits-selected-model",
            fallback_recommendation=profile.fallback_actions,
            compact_tool_subset=profile.tool_subset,
        )
