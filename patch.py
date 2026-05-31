import sys

with open("factory_runtime/agents/llm_client.py", "r") as f:
    text = f.read()

# 1. Add _llm_provider_registry
text = text.replace('    _default_role_models = {',
                    '    _llm_provider_registry = {}\n    _default_role_models = {')

# 2. Add register_provider
text = text.replace('    @staticmethod\n    def _parse_positive_float',
                    '    @classmethod\n    def register_provider(cls, provider: str, factory_method):\n        cls._llm_provider_registry[provider.lower()] = factory_method\n\n    @staticmethod\n    def _parse_positive_float')

# 3. Replace GitHub hardcode with registry lookup
old_github_block = """        # GitHub Models
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
                        requester_class=requester_class,
                        run_id=run_id,
                        parent_run_id=parent_run_id,
                        requester_id=requester_id,
                    ),
                )
            return AsyncOpenAI(
                base_url="https://models.github.ai/inference",
                api_key=api_key,
                http_client=LLMClientFactory._create_rate_limited_http_client(
                    role,
                    role_config=role_config,
                    lane=lane,
                    requester_class=requester_class,
                    run_id=run_id,
                    parent_run_id=parent_run_id,
                    requester_id=requester_id,
                ),
            )

        # Everything else is intentionally unsupported in this repo.
        raise ValueError(
            "Unsupported LLM provider/config. This project only supports GitHub Models (provider=github)."
        )"""

new_github_block = """        if not provider and "models.github.ai" in base_url:
            provider = "github"
        provider = provider or "github"

        if provider in LLMClientFactory._llm_provider_registry:
            return LLMClientFactory._llm_provider_registry[provider](
                api_key=api_key,
                role=role,
                role_config=role_config,
                lane=lane,
                requester_class=requester_class,
                run_id=run_id,
                parent_run_id=parent_run_id,
                requester_id=requester_id,
            )

        # Everything else is intentionally unsupported in this repo.
        raise ValueError(
            f"Unsupported LLM provider/config: '{provider}'. "
            "This project only supports registered providers (default: github)."
        )"""

text = text.replace(old_github_block, new_github_block)

# 4. We need to define the github provider factory method and register it
github_provider_method = """    @classmethod
    def _create_github_provider(
        cls,
        api_key: str,
        role: str,
        role_config: dict,
        lane: str,
        requester_class: str | None,
        run_id: str | None,
        parent_run_id: str | None,
        requester_id: str | None,
    ) -> AsyncOpenAI:
        if cls._looks_like_placeholder(api_key):
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
                http_client=cls._create_rate_limited_http_client(
                    role,
                    role_config=role_config,
                    lane=lane,
                    requester_class=requester_class,
                    run_id=run_id,
                    parent_run_id=parent_run_id,
                    requester_id=requester_id,
                ),
            )
        return AsyncOpenAI(
            base_url="https://models.github.ai/inference",
            api_key=api_key,
            http_client=cls._create_rate_limited_http_client(
                role,
                role_config=role_config,
                lane=lane,
                requester_class=requester_class,
                run_id=run_id,
                parent_run_id=parent_run_id,
                requester_id=requester_id,
            ),
        )"""

text = text.replace('    @staticmethod\n    def get_startup_report()', github_provider_method + '\n\n    @staticmethod\n    def get_startup_report()')

# 5. Add call to register_provider at the end of the file
text += "\nLLMClientFactory.register_provider('github', LLMClientFactory._create_github_provider)\n"

with open("factory_runtime/agents/llm_client.py", "w") as f:
    f.write(text)
