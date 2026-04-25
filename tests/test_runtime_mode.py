from __future__ import annotations

import json

import pytest

import factory_runtime.agents.llm_client as llm_client_module
from factory_runtime.agents.llm_client import LLMClientFactory
from factory_runtime.agents.tooling.openai_images_client import (
    OpenAIAPIKeyMissingError,
    OpenAIImagesClient,
)


def test_llm_client_uses_mock_fallback_in_development_mode(monkeypatch) -> None:
    created: dict[str, object] = {}

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            created.update(kwargs)

    monkeypatch.delenv("FACTORY_RUNTIME_MODE", raising=False)
    monkeypatch.setattr(llm_client_module, "AsyncOpenAI", FakeAsyncOpenAI)
    monkeypatch.setattr(
        LLMClientFactory,
        "resolve_github_api_key",
        staticmethod(lambda config_key="": config_key),
    )
    monkeypatch.setattr(
        LLMClientFactory,
        "get_role_config",
        staticmethod(
            lambda role: {
                "provider": "github",
                "base_url": "https://models.github.ai/inference",
                "api_key": "your-token-here",
            }
        ),
    )

    LLMClientFactory.create_client_for_role("coding")

    assert created["base_url"] == "http://localhost:9090/v1"
    assert created["api_key"] == "sk-dummy-test"


def test_llm_client_fails_closed_in_production_mode(monkeypatch) -> None:
    monkeypatch.setenv("FACTORY_RUNTIME_MODE", "production")
    monkeypatch.setattr(
        LLMClientFactory,
        "resolve_github_api_key",
        staticmethod(lambda config_key="": config_key),
    )
    monkeypatch.setattr(
        LLMClientFactory,
        "get_role_config",
        staticmethod(
            lambda role: {
                "provider": "github",
                "base_url": "https://models.github.ai/inference",
                "api_key": "your-token-here",
            }
        ),
    )

    with pytest.raises(ValueError, match="mock fallback is disabled"):
        LLMClientFactory.create_client_for_role("coding")


def test_openai_images_client_fails_closed_in_production_mode(monkeypatch) -> None:
    monkeypatch.setenv("FACTORY_RUNTIME_MODE", "production")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(OpenAIAPIKeyMissingError, match="mock fallback is disabled"):
        OpenAIImagesClient()


def test_llm_client_rejects_override_file_in_production_mode(
    monkeypatch,
    tmp_path,
) -> None:
    override_path = tmp_path / "runtime_override.json"
    override_path.write_text(
        json.dumps({"api_key": "live-override-key"}),
        encoding="utf-8",
    )

    monkeypatch.setenv("FACTORY_RUNTIME_MODE", "production")
    monkeypatch.setenv("LLM_OVERRIDE_PATH", str(override_path))
    monkeypatch.setattr(
        LLMClientFactory,
        "get_role_config",
        staticmethod(
            lambda role: {
                "provider": "github",
                "base_url": "https://models.github.ai/inference",
                "api_key": "your-token-here",
            }
        ),
    )

    with pytest.raises(
        ValueError, match="override files via LLM_OVERRIDE_PATH are disabled"
    ):
        LLMClientFactory.create_client_for_role("coding")


def test_openai_images_client_rejects_placeholder_key_in_production_mode(
    monkeypatch,
) -> None:
    monkeypatch.setenv("FACTORY_RUNTIME_MODE", "production")
    monkeypatch.setenv("OPENAI_API_KEY", "your-api-key-here")

    with pytest.raises(OpenAIAPIKeyMissingError, match="mock fallback is disabled"):
        OpenAIImagesClient()


def test_openai_images_client_rejects_override_file_in_production_mode(
    monkeypatch,
    tmp_path,
) -> None:
    override_path = tmp_path / "runtime_override.json"
    override_path.write_text(
        json.dumps({"api_key": "live-override-key"}),
        encoding="utf-8",
    )

    monkeypatch.setenv("FACTORY_RUNTIME_MODE", "production")
    monkeypatch.setenv("LLM_OVERRIDE_PATH", str(override_path))

    with pytest.raises(
        OpenAIAPIKeyMissingError,
        match="override files via LLM_OVERRIDE_PATH are disabled",
    ):
        OpenAIImagesClient()
