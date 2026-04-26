"""LLM Client for GitHub Models.

This project standardizes on GitHub Models (Copilot) for all agent roles.
Configuration is loaded from the active config (see LLMClientFactory.get_config_path).
"""

import asyncio
import json
import os
import random
import subprocess
import time
from pathlib import Path
from typing import Awaitable, Callable, Dict, Optional

import httpx
from openai import AsyncOpenAI

from factory_runtime.agents.tooling import api_throttle
from factory_runtime.agents.tooling.llm_quota_policy import (
    LLMQuotaPolicy,
    get_llm_config_path,
    get_llm_role_config,
    load_llm_config,
    resolve_role_quota_policy,
)
from factory_runtime.secret_safety import (
    is_blank_or_placeholder,
    production_runtime_mode_enabled,
)


def _production_runtime_mode_enabled() -> bool:
    return production_runtime_mode_enabled()


def _load_dynamic_override_api_key() -> str:
    override_path = os.getenv("LLM_OVERRIDE_PATH", "configs/runtime_override.json")
    if not os.path.exists(override_path):
        return ""

    if _production_runtime_mode_enabled():
        raise ValueError(
            "Dynamic LLM override files via LLM_OVERRIDE_PATH are disabled when "
            "FACTORY_RUNTIME_MODE=production. Remove the override file or switch "
            "to development mode."
        )

    try:
        with open(override_path, encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return ""

    candidate = str(data.get("api_key", "")).strip() if isinstance(data, dict) else ""
    return candidate


def _normalize_throttle_lane(lane: str) -> str:
    normalized = (lane or "foreground").strip().lower()
    return "reserve" if normalized == "reserve" else "foreground"


def _build_shared_throttle_channel(role: str, lane: str = "foreground") -> str:
    normalized_role = (role or "coding").strip().lower() or "coding"
    channel = f"llm:{normalized_role}"
    if _normalize_throttle_lane(lane) == "reserve":
        return f"{channel}.reserve"
    return channel


def _extract_retry_after_seconds(response: httpx.Response) -> float | None:
    retry_after = (response.headers.get("retry-after") or "").strip()
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            parsed = api_throttle.extract_retry_after_seconds(retry_after)
            if parsed is not None:
                return parsed

    if response.status_code != 429:
        return None

    try:
        return api_throttle.extract_retry_after_seconds(response.text)
    except (httpx.ResponseNotRead, UnicodeDecodeError):
        return None


class _LLMRequestThrottle:
    """Process-local async request throttle for outbound LLM calls."""

    def __init__(
        self,
        *,
        max_rps: float,
        jitter_ratio: float,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter_fn: Callable[[float, float], float] = random.uniform,
    ):
        self.max_rps = max_rps
        self.min_interval = 1.0 / max_rps
        self.jitter_ratio = jitter_ratio
        self._clock = clock
        self._sleeper = sleeper
        self._jitter_fn = jitter_fn
        self._lock = asyncio.Lock()
        self._last_request_time: Optional[float] = None

    async def acquire(self) -> None:
        """Wait until the next request slot is available."""
        async with self._lock:
            now = self._clock()
            if self._last_request_time is None:
                self._last_request_time = now
                return

            elapsed = now - self._last_request_time
            remaining = max(0.0, self.min_interval - elapsed)
            jitter_cap = self.min_interval * self.jitter_ratio
            jitter = self._jitter_fn(0.0, jitter_cap) if jitter_cap > 0 else 0.0
            wait_seconds = remaining + jitter

            if wait_seconds > 0:
                await self._sleeper(wait_seconds)
                now = self._clock()

            self._last_request_time = now


class _RateLimitedAsyncHTTPClient(httpx.AsyncClient):
    """httpx client wrapper that throttles before each outbound request."""

    def __init__(
        self,
        *,
        throttle: _LLMRequestThrottle,
        role: str,
        lane: str = "foreground",
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
        **client_kwargs,
    ):
        super().__init__(**client_kwargs)
        self._throttle = throttle
        self._role = (role or "coding").strip().lower() or "coding"
        self._lane = _normalize_throttle_lane(lane)
        self._shared_channel = _build_shared_throttle_channel(self._role, self._lane)
        self._sleeper = sleeper

    async def _acquire_request_slot(self) -> None:
        if api_throttle.shared_throttle_supported():
            wait_seconds = api_throttle.reserve_api_slot(
                channel=self._shared_channel,
                role=self._role,
            )
            if wait_seconds > 0:
                await self._sleeper(wait_seconds)
            return

        await self._throttle.acquire()

    def _apply_shared_penalty(self, response: httpx.Response) -> None:
        retry_after_seconds = _extract_retry_after_seconds(response)
        if response.status_code != 429 and retry_after_seconds is None:
            return

        api_throttle.apply_rate_limit_penalty(
            channel=self._shared_channel,
            penalty_seconds=retry_after_seconds,
            role=self._role,
        )

    async def send(self, request, **kwargs):
        await self._acquire_request_slot()
        response = await super().send(request, **kwargs)
        self._apply_shared_penalty(response)
        return response


class LLMClientFactory:
    """Factory for creating LLM clients based on configuration."""

    _cached_github_token: Optional[str] = None
    _shared_request_throttles: Dict[
        tuple[str, str, float, float], _LLMRequestThrottle
    ] = {}
    _default_role_models = {
        # gpt-5.2 does not exist on GitHub Models; use gpt-4o as the capable default.
        "planning": "openai/gpt-4o",
        "coding": "openai/gpt-4o-mini",
        "review": "openai/gpt-4o-mini",
    }

    @staticmethod
    def _parse_positive_float(value: str, fallback: float) -> float:
        try:
            parsed = float(value)
            if parsed > 0:
                return parsed
        except (TypeError, ValueError):
            pass
        return fallback

    @staticmethod
    def _get_rps_settings() -> tuple[float, float]:
        """Return max-RPS and jitter ratio for LLM requests."""
        policy = LLMClientFactory._get_request_policy("coding")
        return policy.foreground_lane_rps, policy.jitter_ratio

    @staticmethod
    def _get_request_policy(
        role: str,
        role_config: Optional[dict] = None,
    ) -> LLMQuotaPolicy:
        return resolve_role_quota_policy(role, config=role_config)

    @staticmethod
    def _get_lane_rps(policy: LLMQuotaPolicy, lane: str) -> float:
        if _normalize_throttle_lane(lane) == "reserve":
            return policy.reserve_lane_rps
        return policy.foreground_lane_rps

    @staticmethod
    def _get_shared_request_throttle(
        role: str,
        role_config: Optional[dict] = None,
        lane: str = "foreground",
    ) -> _LLMRequestThrottle:
        policy = LLMClientFactory._get_request_policy(role, role_config=role_config)
        normalized_role = (role or "coding").strip().lower() or "coding"
        normalized_lane = _normalize_throttle_lane(lane)
        lane_rps = LLMClientFactory._get_lane_rps(policy, normalized_lane)
        key = (normalized_role, normalized_lane, lane_rps, policy.jitter_ratio)
        throttle = LLMClientFactory._shared_request_throttles.get(key)
        if throttle is None:
            throttle = _LLMRequestThrottle(
                max_rps=lane_rps,
                jitter_ratio=policy.jitter_ratio,
            )
            LLMClientFactory._shared_request_throttles[key] = throttle
        return throttle

    @staticmethod
    def _create_rate_limited_http_client(
        role: str,
        role_config: Optional[dict] = None,
        lane: str = "foreground",
    ) -> httpx.AsyncClient:
        throttle = LLMClientFactory._get_shared_request_throttle(
            role,
            role_config=role_config,
            lane=lane,
        )
        return _RateLimitedAsyncHTTPClient(
            throttle=throttle,
            role=role,
            lane=lane,
        )

    @staticmethod
    def _looks_like_placeholder(key: str) -> bool:
        return is_blank_or_placeholder(key)

    @staticmethod
    def _get_github_token_from_env() -> str:
        return (
            os.environ.get("GITHUB_TOKEN")
            or os.environ.get("GITHUB_PAT")
            or os.environ.get("GH_TOKEN")
            or ""
        )

    @staticmethod
    def _get_github_token_from_gh_cli() -> str:
        if LLMClientFactory._cached_github_token is not None:
            return LLMClientFactory._cached_github_token

        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            token = (result.stdout or "").strip() if result.returncode == 0 else ""
            if token:
                LLMClientFactory._cached_github_token = token
                return token
        except Exception:
            pass

        LLMClientFactory._cached_github_token = ""
        return ""

    @staticmethod
    def resolve_github_api_key(config_key: str = "") -> str:
        """Resolve GitHub Models API key from config/env/gh-cli in that order."""
        if not LLMClientFactory._looks_like_placeholder(config_key):
            return config_key

        env_token = LLMClientFactory._get_github_token_from_env()
        if env_token:
            return env_token

        cli_token = LLMClientFactory._get_github_token_from_gh_cli()
        if cli_token:
            os.environ.setdefault("GH_TOKEN", cli_token)
            return cli_token

        return config_key

    @staticmethod
    def get_config_path() -> Path:
        """Return the active LLM config path.

        Resolution order:
        1) LLM_CONFIG_PATH env var (recommended; keeps secrets out of git)
        2) /config/llm.json (Docker convention)
        3) configs/llm.json (local override; should remain gitignored)
        4) configs/llm.default.json (repo default)
        """
        return get_llm_config_path()

    @staticmethod
    def load_config() -> dict:
        """Load LLM configuration from configs/llm.json or default."""
        return load_llm_config()

    @staticmethod
    def get_model_roles() -> Dict[str, str]:
        """Return configured model IDs for planning/coding/review.

        Supports either a single `model` or per-role keys:
        - `planning_model`
        - `coding_model`
        - `review_model`
        """
        try:
            return {
                "planning": LLMClientFactory.get_model_id_for_role("planning"),
                "coding": LLMClientFactory.get_model_id_for_role("coding"),
                "review": LLMClientFactory.get_model_id_for_role("review"),
            }
        except Exception:
            return {
                "planning": LLMClientFactory._default_role_models["planning"],
                "coding": LLMClientFactory._default_role_models["coding"],
                "review": LLMClientFactory._default_role_models["review"],
            }

    @staticmethod
    def get_startup_report() -> dict:
        """Safe, non-secret model/config info suitable for printing at startup."""
        try:
            config_path = str(LLMClientFactory.get_config_path())
        except Exception:
            config_path = "(missing)"

        try:
            config = LLMClientFactory.load_config()
        except Exception:
            config = {}

        models = LLMClientFactory.get_model_roles()

        role_endpoints = {}
        role_request_policies = {}
        for role in ["planning", "coding", "review"]:
            try:
                role_cfg = LLMClientFactory.get_role_config(role)
                role_endpoints[role] = {
                    "provider": role_cfg.get("provider", ""),
                    "base_url": role_cfg.get("base_url", role_cfg.get("api_base", "")),
                    "azure_endpoint": role_cfg.get("azure_endpoint", ""),
                }
                role_request_policies[role] = LLMClientFactory._get_request_policy(
                    role,
                    role_config=role_cfg,
                ).to_dict()
            except Exception:
                role_endpoints[role] = {}
                role_request_policies[role] = {}
        coding_policy = role_request_policies.get("coding") or {}
        max_rps = coding_policy.get("foreground_lane_rps", 0.0)
        jitter_ratio = coding_policy.get("jitter_ratio", 0.0)
        return {
            "config_path": config_path,
            "provider": config.get("provider", ""),
            "configured_base_url": config.get("base_url", config.get("api_base", "")),
            "models": models,
            "request_throttle": {
                "max_rps": max_rps,
                "jitter_ratio": jitter_ratio,
            },
            "request_quota_policy": coding_policy,
            "role_endpoints": role_endpoints,
            "role_request_policies": role_request_policies,
        }

    @staticmethod
    def get_role_config(role: str) -> dict:
        """Return the merged config dict for a given role.

        Supported shapes:
        - roles: { planning: {...}, coding: {...}, review: {...} }
        - prefixed keys: planning_model, planning_provider, planning_base_url, ...
        - fallback to top-level keys.
        """
        return get_llm_role_config(role)

    @staticmethod
    def get_model_id_for_role(role: str) -> str:
        role_config = LLMClientFactory.get_role_config(role)
        model = role_config.get("model", "")
        if model:
            return model
        return LLMClientFactory._default_role_models.get(role, "openai/gpt-4o-mini")

    @staticmethod
    def create_client_for_role(role: str, lane: str = "foreground") -> AsyncOpenAI:
        """Create an OpenAI-compatible async client for a given role.

        Supported:
        - GitHub Models: provider=github OR base_url contains models.github.ai
        """
        role_config = LLMClientFactory.get_role_config(role)
        provider = (role_config.get("provider") or "").lower()
        base_url = role_config.get("base_url") or role_config.get("api_base") or ""
        api_key = role_config.get("api_key") or ""

        # Allow secrets via environment variables (preferred; avoids writing configs/llm.json).
        # Only override when config is missing/placeholder.
        if LLMClientFactory._looks_like_placeholder(api_key) and (
            provider == "github" or "models.github.ai" in base_url
        ):
            api_key = LLMClientFactory.resolve_github_api_key(api_key)

        # --- Check Dynamic Overrides ---
        override_api_key = _load_dynamic_override_api_key()
        if override_api_key:
            api_key = override_api_key
        # -------------------------------

        # GitHub Models
        if provider == "github" or "models.github.ai" in base_url:
            if LLMClientFactory._looks_like_placeholder(api_key):
                if _production_runtime_mode_enabled():
                    raise ValueError(
                        "GitHub Models credentials are required when "
                        "FACTORY_RUNTIME_MODE=production; mock fallback is disabled. "
                        "Set GITHUB_TOKEN, GH_TOKEN, GITHUB_PAT, or a non-placeholder api_key."
                    )
                # Fallback to Mock LLM Gateway
                return AsyncOpenAI(
                    base_url=os.getenv("MOCK_LLM_URL", "http://localhost:9090/v1"),
                    api_key="sk-dummy-test",
                    http_client=LLMClientFactory._create_rate_limited_http_client(
                        role,
                        role_config=role_config,
                        lane=lane,
                    ),
                )
            return AsyncOpenAI(
                base_url="https://models.github.ai/inference",
                api_key=api_key,
                http_client=LLMClientFactory._create_rate_limited_http_client(
                    role,
                    role_config=role_config,
                    lane=lane,
                ),
            )

        # Everything else is intentionally unsupported in this repo.
        raise ValueError(
            "Unsupported LLM provider/config. This project only supports GitHub Models (provider=github)."
        )

    @staticmethod
    def create_github_client(
        api_key: Optional[str] = None,
        lane: str = "foreground",
    ) -> AsyncOpenAI:
        """
        Create OpenAI client configured for GitHub Models.

        Args:
            api_key: GitHub PAT token. If None, loads from config.

        Returns:
            Configured AsyncOpenAI client
        """
        if api_key is None:
            config = LLMClientFactory.load_config()
            api_key = LLMClientFactory.resolve_github_api_key(config.get("api_key", ""))

            if LLMClientFactory._looks_like_placeholder(api_key):
                raise ValueError(
                    "GitHub PAT token required. Set in configs/llm.json, export GITHUB_TOKEN/GH_TOKEN, or run `gh auth login`.\n"  # noqa: E501
                    "Get your token at: https://github.com/settings/tokens"
                )

        return AsyncOpenAI(
            base_url="https://models.github.ai/inference",
            api_key=api_key,
            http_client=LLMClientFactory._create_rate_limited_http_client(
                "coding",
                lane=lane,
            ),
        )

    @staticmethod
    def get_recommended_model() -> str:
        """
        Get recommended model for autonomous agent work.

        For planning/execution split:
        - planning: capable model (default: openai/gpt-4o)
        - coding/review: free-tier capable smaller models (default: openai/gpt-4o-mini)

        Returns:
            Model ID string
        """
        # Try to load from config first
        try:
            config = LLMClientFactory.load_config()
            model = config.get("model", "")
            if model and model != "your-model-name":
                return model
        except Exception:
            pass

        return LLMClientFactory._default_role_models["planning"]
