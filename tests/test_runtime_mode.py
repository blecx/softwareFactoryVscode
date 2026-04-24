from __future__ import annotations

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
