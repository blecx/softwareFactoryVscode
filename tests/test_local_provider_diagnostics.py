import os
from unittest.mock import patch

import pytest

from factory_runtime.agents.llm_client import LLMClientFactory


def test_startup_report_github_provider():
    with patch.dict(os.environ, {"FACTORY_RUNTIME_MODE": "production"}):
        with patch.object(
            LLMClientFactory, "load_config", return_value={"provider": "github"}
        ):
            report = LLMClientFactory.get_startup_report()
            assert report["provider_diagnostic"]["status"] == "production-ready"


def test_startup_report_unregistered_provider():
    with patch.dict(os.environ, {"FACTORY_RUNTIME_MODE": "development"}):
        with patch.object(
            LLMClientFactory, "load_config", return_value={"provider": "unknown"}
        ):
            report = LLMClientFactory.get_startup_report()
            assert report["provider_diagnostic"]["status"] == "unavailable"
            assert "unregistered" in report["provider_diagnostic"]["reason"].lower()


def test_startup_report_local_provider_development():
    with patch.dict(os.environ, {"FACTORY_RUNTIME_MODE": "development"}):
        with patch.object(
            LLMClientFactory, "load_config", return_value={"provider": "localOllama"}
        ):
            LLMClientFactory.register_provider("localollama", lambda **k: "mock")
            report = LLMClientFactory.get_startup_report()
            assert report["provider_diagnostic"]["status"] == "development-only"
            del LLMClientFactory._llm_provider_registry["localollama"]


def test_startup_report_local_provider_blocked_production():
    with patch.dict(os.environ, {"FACTORY_RUNTIME_MODE": "production"}):
        with patch.object(
            LLMClientFactory, "load_config", return_value={"provider": "localOllama"}
        ):
            LLMClientFactory.register_provider("localollama", lambda **k: "mock")
            report = LLMClientFactory.get_startup_report()
            assert report["provider_diagnostic"]["status"] == "blocked-in-production"
            del LLMClientFactory._llm_provider_registry["localollama"]
