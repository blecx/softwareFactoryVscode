"""LLM Client for GitHub Models.

This project standardizes on GitHub Models (Copilot) for all agent roles.
Configuration is loaded from the active config (see LLMClientFactory.get_config_path).
"""

import json
import os
import subprocess
import asyncio
import random
import time
from pathlib import Path
from typing import Optional, Dict, Callable, Awaitable

import httpx
from openai import AsyncOpenAI


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

    def __init__(self, *, throttle: _LLMRequestThrottle):
        super().__init__()
        self._throttle = throttle

    async def send(self, request, **kwargs):
        await self._throttle.acquire()
        return await super().send(request, **kwargs)


class LLMClientFactory:
    """Factory for creating LLM clients based on configuration."""

    _cached_github_token: Optional[str] = None
    _shared_request_throttle: Optional[_LLMRequestThrottle] = None
    _shared_request_throttle_key: Optional[tuple[float, float]] = None
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
        max_rps = LLMClientFactory._parse_positive_float(
            os.environ.get("WORK_ISSUE_MAX_RPS", "0.2"),
            0.2,
        )
        jitter_ratio = LLMClientFactory._parse_positive_float(
            os.environ.get("WORK_ISSUE_RPS_JITTER", "0.1"),
            0.1,
        )
        jitter_ratio = min(max(jitter_ratio, 0.0), 1.0)
        return max_rps, jitter_ratio

    @staticmethod
    def _get_shared_request_throttle() -> _LLMRequestThrottle:
        key = LLMClientFactory._get_rps_settings()
        if (
            LLMClientFactory._shared_request_throttle is None
            or LLMClientFactory._shared_request_throttle_key != key
        ):
            max_rps, jitter_ratio = key
            LLMClientFactory._shared_request_throttle = _LLMRequestThrottle(
                max_rps=max_rps,
                jitter_ratio=jitter_ratio,
            )
            LLMClientFactory._shared_request_throttle_key = key
        return LLMClientFactory._shared_request_throttle

    @staticmethod
    def _create_rate_limited_http_client() -> httpx.AsyncClient:
        throttle = LLMClientFactory._get_shared_request_throttle()
        return _RateLimitedAsyncHTTPClient(throttle=throttle)

    @staticmethod
    def _looks_like_placeholder(key: str) -> bool:
        if not key:
            return True
        lowered = key.lower().strip()
        return (
            lowered in {"your-api-key-here", "your-token-here", "changeme"}
            or "your_token_here" in lowered
            or "your token here" in lowered
        )

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
        env_path = (
            Path(str(p)).expanduser()
            if (p := (os.environ.get("LLM_CONFIG_PATH") or "").strip())
            else None
        )
        if env_path is not None:
            resolved = env_path if env_path.is_absolute() else Path.cwd() / env_path
            if resolved.exists():
                return resolved
            raise FileNotFoundError(
                f"LLM_CONFIG_PATH was set but file does not exist: {resolved}"
            )

        docker_path = Path("/config/llm.json")
        if docker_path.exists():
            return docker_path

        config_path = Path("configs/llm.json")
        if config_path.exists():
            return config_path

        config_path = Path("configs/llm.default.json")
        if config_path.exists():
            return config_path

        raise FileNotFoundError(
            "No LLM configuration found. Set LLM_CONFIG_PATH, create configs/llm.json, or use configs/llm.default.json"
        )

    @staticmethod
    def load_config() -> dict:
        """Load LLM configuration from configs/llm.json or default."""
        config_path = LLMClientFactory.get_config_path()

        with open(config_path) as f:
            return json.load(f)

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
        for role in ["planning", "coding", "review"]:
            try:
                role_cfg = LLMClientFactory.get_role_config(role)
                role_endpoints[role] = {
                    "provider": role_cfg.get("provider", ""),
                    "base_url": role_cfg.get("base_url", ""),
                    "azure_endpoint": role_cfg.get("azure_endpoint", ""),
                }
            except Exception:
                role_endpoints[role] = {}
        max_rps, jitter_ratio = LLMClientFactory._get_rps_settings()
        return {
            "config_path": config_path,
            "provider": config.get("provider", ""),
            "configured_base_url": config.get("base_url", ""),
            "models": models,
            "request_throttle": {
                "max_rps": max_rps,
                "jitter_ratio": jitter_ratio,
            },
            "role_endpoints": role_endpoints,
        }

    @staticmethod
    def get_role_config(role: str) -> dict:
        """Return the merged config dict for a given role.

        Supported shapes:
        - roles: { planning: {...}, coding: {...}, review: {...} }
        - prefixed keys: planning_model, planning_provider, planning_base_url, ...
        - fallback to top-level keys.
        """
        config = LLMClientFactory.load_config()

        roles = config.get("roles")
        if isinstance(roles, dict) and isinstance(roles.get(role), dict):
            merged = dict(config)
            merged.update(roles.get(role, {}))
            merged.pop("roles", None)
            return merged

        prefix = f"{role}_"
        role_overrides = {
            k[len(prefix) :]: v
            for k, v in config.items()
            if isinstance(k, str) and k.startswith(prefix)
        }
        merged = dict(config)
        merged.update(role_overrides)
        return merged

    @staticmethod
    def get_model_id_for_role(role: str) -> str:
        role_config = LLMClientFactory.get_role_config(role)
        model = role_config.get("model", "")
        if model:
            return model
        return LLMClientFactory._default_role_models.get(role, "openai/gpt-4o-mini")

    @staticmethod
    def create_client_for_role(role: str) -> AsyncOpenAI:
        """Create an OpenAI-compatible async client for a given role.

        Supported:
        - GitHub Models: provider=github OR base_url contains models.github.ai
        """
        role_config = LLMClientFactory.get_role_config(role)
        provider = (role_config.get("provider") or "").lower()
        base_url = role_config.get("base_url") or ""
        api_key = role_config.get("api_key") or ""

        # Allow secrets via environment variables (preferred; avoids writing configs/llm.json).
        # Only override when config is missing/placeholder.
        if LLMClientFactory._looks_like_placeholder(api_key) and (
            provider == "github" or "models.github.ai" in base_url
        ):
            api_key = LLMClientFactory.resolve_github_api_key(api_key)

        # --- Check Dynamic Overrides ---
        override_path = os.getenv("LLM_OVERRIDE_PATH", "configs/runtime_override.json")
        if os.path.exists(override_path):
            try:
                import json

                with open(override_path, "r") as f:
                    data = json.load(f)
                    if data.get("api_key"):
                        api_key = data["api_key"]
            except Exception:
                pass
        # -------------------------------

        # GitHub Models
        if provider == "github" or "models.github.ai" in base_url:
            if LLMClientFactory._looks_like_placeholder(api_key):
                # Fallback to Mock LLM Gateway
                return AsyncOpenAI(
                    base_url=os.getenv("MOCK_LLM_URL", "http://localhost:9090/v1"),
                    api_key="sk-dummy-test",
                    http_client=LLMClientFactory._create_rate_limited_http_client(),
                )
            return AsyncOpenAI(
                base_url="https://models.github.ai/inference",
                api_key=api_key,
                http_client=LLMClientFactory._create_rate_limited_http_client(),
            )

        # Everything else is intentionally unsupported in this repo.
        raise ValueError(
            "Unsupported LLM provider/config. This project only supports GitHub Models (provider=github)."
        )

    @staticmethod
    def create_github_client(api_key: Optional[str] = None) -> AsyncOpenAI:
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
                    "GitHub PAT token required. Set in configs/llm.json, export GITHUB_TOKEN/GH_TOKEN, or run `gh auth login`.\n"
                    "Get your token at: https://github.com/settings/tokens"
                )

        return AsyncOpenAI(
            base_url="https://models.github.ai/inference",
            api_key=api_key,
            http_client=LLMClientFactory._create_rate_limited_http_client(),
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
