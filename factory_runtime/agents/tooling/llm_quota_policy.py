from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

_DEFAULT_FOREGROUND_SHARE = 0.70
_DEFAULT_RESERVE_SHARE = 0.30
_DEFAULT_JITTER_RATIO = 0.10
_DEFAULT_MAX_WAIT_SECONDS = 180.0
_DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS = 45.0


@dataclass(frozen=True)
class LLMQuotaPolicy:
    provider: str
    model: str
    model_family: str
    quota_bucket: str
    quota_source: str
    quota_ceiling_rps: float
    foreground_share: float
    reserve_share: float
    foreground_lane_rps: float
    reserve_lane_rps: float
    jitter_ratio: float
    max_wait_seconds: float
    rate_limit_cooldown_seconds: float

    def to_dict(self) -> dict[str, float | str]:
        return asdict(self)


def _parse_positive_float(raw: str | None, default: float) -> float:
    try:
        value = float((raw or "").strip())
    except ValueError:
        return default
    return value if value > 0 else default


def _parse_unit_ratio(raw: str | None, default: float) -> float:
    try:
        value = float((raw or "").strip())
    except ValueError:
        return default
    if value < 0:
        return default
    if value > 1:
        return 1.0
    return value


def _round_quota(value: float) -> float:
    return round(max(0.0, value), 6)


def normalize_provider(provider: str = "", base_url: str = "") -> str:
    normalized_provider = (provider or "").strip().lower()
    normalized_base_url = (base_url or "").strip().lower()
    if normalized_provider:
        return normalized_provider
    if "models.github.ai" in normalized_base_url:
        return "github"
    return "unknown"


def normalize_model_family(model: str = "") -> str:
    normalized = (model or "").strip().lower()
    if not normalized:
        return "unknown"
    return normalized


def _resolve_lane_shares(
    env: Mapping[str, str],
) -> tuple[float, float]:
    foreground_share = _parse_unit_ratio(
        env.get("WORK_ISSUE_FOREGROUND_SHARE"),
        _DEFAULT_FOREGROUND_SHARE,
    )

    reserve_raw = env.get("WORK_ISSUE_RESERVE_SHARE")
    if reserve_raw is None or not reserve_raw.strip():
        reserve_share = max(0.0, 1.0 - foreground_share)
    else:
        reserve_share = _parse_unit_ratio(reserve_raw, _DEFAULT_RESERVE_SHARE)
        total_share = foreground_share + reserve_share
        if total_share <= 0:
            foreground_share = _DEFAULT_FOREGROUND_SHARE
            reserve_share = _DEFAULT_RESERVE_SHARE
        else:
            foreground_share /= total_share
            reserve_share /= total_share

    return _round_quota(foreground_share), _round_quota(reserve_share)


def _select_quota_bucket(provider: str, model_family: str) -> tuple[str, float]:
    if provider == "github":
        if "gpt-4.1-mini" in model_family or "gpt-4o-mini" in model_family:
            return "github-openai-mini", 0.50
        if "gpt-4.1" in model_family or "gpt-4o" in model_family:
            return "github-openai-standard", 0.30
        if (
            model_family.startswith("openai/o1")
            or model_family.startswith("o1")
            or model_family.startswith("openai/o3")
            or model_family.startswith("o3")
            or model_family.startswith("openai/o4")
            or model_family.startswith("o4")
        ):
            return "github-openai-reasoning", 0.15
        if model_family.startswith("openai/"):
            return "github-openai-other", 0.25
        return "github-default", 0.20

    return "generic-default", 0.10


def resolve_quota_policy(
    *,
    provider: str = "",
    model: str = "",
    base_url: str = "",
    env: Mapping[str, str] | None = None,
) -> LLMQuotaPolicy:
    runtime_env = env if env is not None else os.environ
    normalized_provider = normalize_provider(provider, base_url)
    normalized_model = normalize_model_family(model)
    foreground_share, reserve_share = _resolve_lane_shares(runtime_env)

    explicit_ceiling_rps = _parse_positive_float(
        runtime_env.get("WORK_ISSUE_QUOTA_CEILING_RPS"),
        0.0,
    )
    legacy_foreground_rps = _parse_positive_float(
        runtime_env.get("WORK_ISSUE_MAX_RPS"),
        0.0,
    )

    if explicit_ceiling_rps > 0:
        quota_bucket = "env-explicit-ceiling"
        quota_source = "WORK_ISSUE_QUOTA_CEILING_RPS"
        quota_ceiling_rps = explicit_ceiling_rps
    elif legacy_foreground_rps > 0:
        quota_bucket = "legacy-foreground-override"
        quota_source = "WORK_ISSUE_MAX_RPS"
        quota_ceiling_rps = legacy_foreground_rps / max(foreground_share, 0.01)
    else:
        quota_bucket, quota_ceiling_rps = _select_quota_bucket(
            normalized_provider,
            normalized_model,
        )
        quota_source = "model-family-fallback"

    quota_ceiling_rps = _round_quota(quota_ceiling_rps)
    foreground_lane_rps = _round_quota(quota_ceiling_rps * foreground_share)
    reserve_lane_rps = _round_quota(quota_ceiling_rps * reserve_share)
    jitter_ratio = _parse_unit_ratio(
        runtime_env.get("WORK_ISSUE_RPS_JITTER"),
        _DEFAULT_JITTER_RATIO,
    )
    max_wait_seconds = _parse_positive_float(
        runtime_env.get("WORK_ISSUE_MAX_THROTTLE_WAIT_SECONDS"),
        _DEFAULT_MAX_WAIT_SECONDS,
    )
    rate_limit_cooldown_seconds = _parse_positive_float(
        runtime_env.get("WORK_ISSUE_RATE_LIMIT_COOLDOWN_SECONDS"),
        _DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS,
    )

    return LLMQuotaPolicy(
        provider=normalized_provider,
        model=(model or "").strip(),
        model_family=normalized_model,
        quota_bucket=quota_bucket,
        quota_source=quota_source,
        quota_ceiling_rps=quota_ceiling_rps,
        foreground_share=foreground_share,
        reserve_share=reserve_share,
        foreground_lane_rps=foreground_lane_rps,
        reserve_lane_rps=reserve_lane_rps,
        jitter_ratio=_round_quota(jitter_ratio),
        max_wait_seconds=_round_quota(max_wait_seconds),
        rate_limit_cooldown_seconds=_round_quota(rate_limit_cooldown_seconds),
    )


def get_llm_config_path() -> Path:
    env_path = (
        Path(str(candidate)).expanduser()
        if (candidate := (os.environ.get("LLM_CONFIG_PATH") or "").strip())
        else None
    )
    if env_path is not None:
        resolved = env_path if env_path.is_absolute() else Path.cwd() / env_path
        if resolved.exists():
            return resolved
        raise FileNotFoundError(
            f"LLM_CONFIG_PATH was set but file does not exist: {resolved}"
        )

    for candidate in (
        Path("/config/llm.json"),
        Path("configs/llm.json"),
        Path("configs/llm.default.json"),
    ):
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        "No LLM configuration found. Set LLM_CONFIG_PATH, create configs/llm.json, or use configs/llm.default.json"
    )


def load_llm_config() -> dict:
    config_path = get_llm_config_path()
    with open(config_path, encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def get_llm_role_config(
    role: str,
    config: Mapping[str, object] | None = None,
) -> dict[str, object]:
    config_data = dict(config) if config is not None else load_llm_config()

    roles = config_data.get("roles")
    if isinstance(roles, dict) and isinstance(roles.get(role), dict):
        merged = dict(config_data)
        merged.update(roles.get(role, {}))
        merged.pop("roles", None)
        return merged

    prefix = f"{role}_"
    role_overrides = {
        key[len(prefix) :]: value
        for key, value in config_data.items()
        if isinstance(key, str) and key.startswith(prefix)
    }
    merged = dict(config_data)
    merged.update(role_overrides)
    return merged


def resolve_role_quota_policy(
    role: str = "coding",
    *,
    config: Mapping[str, object] | None = None,
    env: Mapping[str, str] | None = None,
) -> LLMQuotaPolicy:
    try:
        role_config = get_llm_role_config(role, config)
    except Exception:
        role_config = {}

    provider = str(role_config.get("provider") or "")
    model = str(role_config.get("model") or "")
    base_url = str(
        role_config.get("base_url")
        or role_config.get("api_base")
        or role_config.get("azure_endpoint")
        or ""
    )
    return resolve_quota_policy(
        provider=provider,
        model=model,
        base_url=base_url,
        env=env,
    )
