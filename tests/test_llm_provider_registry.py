import os
from unittest.mock import MagicMock, patch

import pytest
from openai import AsyncOpenAI

from factory_runtime.agents.llm_client import LLMClientFactory


def test_github_default_provider():
    with patch.dict(os.environ, {"FACTORY_RUNTIME_MODE": "development"}):
        with patch.object(
            LLMClientFactory, "get_role_config", return_value={"provider": ""}
        ):
            client = LLMClientFactory.create_client_for_role("coding")
            assert isinstance(client, AsyncOpenAI)


def test_unregistered_provider_blocked():
    with patch.dict(os.environ, {"FACTORY_RUNTIME_MODE": "development"}):
        with patch.object(
            LLMClientFactory,
            "get_role_config",
            return_value={"provider": "unknown-provider"},
        ):
            with pytest.raises(
                ValueError, match="Unsupported LLM provider/config: 'unknown-provider'"
            ):
                LLMClientFactory.create_client_for_role("coding")


def test_register_and_use_custom_provider():
    def custom_factory(**kwargs):
        return "custom-client"

    LLMClientFactory.register_provider("custom", custom_factory)

    with patch.object(
        LLMClientFactory, "get_role_config", return_value={"provider": "custom"}
    ):
        client = LLMClientFactory.create_client_for_role("coding")
        assert client == "custom-client"

    # Cleanup
    del LLMClientFactory._llm_provider_registry["custom"]


def test_github_production_mode_enforcement():
    with patch.dict(os.environ, {"FACTORY_RUNTIME_MODE": "production"}, clear=True):
        with patch.object(
            LLMClientFactory, "get_role_config", return_value={"provider": "github"}
        ):
            with patch.object(
                LLMClientFactory, "resolve_github_api_key", return_value=""
            ):
                with patch(
                    "factory_runtime.agents.llm_client._load_dynamic_override_api_key",
                    return_value="",
                ):
                    # Without API key, it should fail
                    with pytest.raises(
                        ValueError, match="GitHub Models credentials are required"
                    ):
                        LLMClientFactory.create_client_for_role("coding")
