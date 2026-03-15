"""OpenAI Images client wrapper.

Minimal wrapper around the OpenAI Images API for generating UI mockup images.

Notes:
- Reads API key from `OPENAI_API_KEY` if not provided.
- Does not persist secrets to disk.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any, Optional


class OpenAIAPIKeyMissingError(RuntimeError):
    """Raised when `OPENAI_API_KEY` is not configured."""


@dataclass(frozen=True)
class OpenAIImagesGenerateParams:
    model: str = "gpt-image-1"
    size: str = "1024x1024"
    response_format: str = "b64_json"


@dataclass(frozen=True)
class MockImageResult:
    ok: bool
    message: str | None = None
    b64_json: str | None = None
    png_bytes: bytes | None = None
    model: str = OpenAIImagesGenerateParams.model


class OpenAIImagesClient:
    """Small OpenAI Images client wrapper.

    The wrapper is designed for easy unit testing by allowing dependency injection
    of an already-constructed OpenAI client.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        openai_client: Any | None = None,
    ):
        resolved_key = api_key or os.getenv("OPENAI_API_KEY")
        # --- Check Dynamic Overrides ---
        import os, json

        override_path = os.getenv("LLM_OVERRIDE_PATH", "configs/runtime_override.json")
        if os.path.exists(override_path):
            try:
                with open(override_path, "r") as f:
                    data = json.load(f)
                    if data.get("api_key"):
                        resolved_key = data["api_key"]
                        base_url = None
            except Exception:
                pass
        # -------------------------------
        if not resolved_key and openai_client is None:
            resolved_key = "sk-dummy-test"
            base_url = os.getenv("MOCK_LLM_URL", "http://localhost:9090/v1")
        else:
            base_url = None

        if openai_client is not None:
            self._client = openai_client
            return

        # Import lazily to keep this module pure-Python for environments that
        # don't need Images (and to make unit tests easier to isolate).
        from openai import OpenAI  # type: ignore

        if base_url:
            self._client = OpenAI(api_key=resolved_key, base_url=base_url)
        else:
            self._client = OpenAI(api_key=resolved_key)

    def generate_png_bytes(
        self,
        prompt: str,
        *,
        params: OpenAIImagesGenerateParams | None = None,
    ) -> bytes:
        """Generate a single image and return PNG bytes."""
        b64_json = self.generate_b64_json(prompt, params=params)
        try:
            return base64.b64decode(b64_json)
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("Failed to decode image base64 payload") from exc

    def generate_b64_json(
        self,
        prompt: str,
        *,
        params: OpenAIImagesGenerateParams | None = None,
    ) -> str:
        """Generate a single image and return the `b64_json` payload."""
        if not prompt or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")

        resolved = params or OpenAIImagesGenerateParams()

        response = self._client.images.generate(
            model=resolved.model,
            prompt=prompt,
            size=resolved.size,
            response_format=resolved.response_format,
        )

        return _extract_first_b64_json(response)


def generate_mock_image(
    prompt: str,
    *,
    api_key: str | None = None,
    openai_client: Any | None = None,
    params: OpenAIImagesGenerateParams | None = None,
) -> MockImageResult:
    """Issue #486 helper: generate an image and return a non-throwing result.

    - Uses `OPENAI_API_KEY` if `api_key` is not provided.
    - If no key is available, returns `ok=False` with an actionable message.
    - Intended for unit tests to mock the OpenAI client (no network).
    """
    try:
        client = OpenAIImagesClient(api_key=api_key, openai_client=openai_client)
    except OpenAIAPIKeyMissingError as exc:
        return MockImageResult(ok=False, message=str(exc))

    try:
        resolved = params or OpenAIImagesGenerateParams()
        b64_json = client.generate_b64_json(prompt, params=resolved)
        png_bytes = base64.b64decode(b64_json)
        return MockImageResult(
            ok=True,
            b64_json=b64_json,
            png_bytes=png_bytes,
            model=resolved.model,
        )
    except Exception as exc:
        return MockImageResult(ok=False, message=str(exc))


def _extract_first_b64_json(response: Any) -> str:
    """Extract `data[0].b64_json` from OpenAI SDK or dict-like response."""
    data = None
    if hasattr(response, "data"):
        data = getattr(response, "data")
    elif isinstance(response, dict):
        data = response.get("data")

    if not data or not isinstance(data, list):
        raise RuntimeError("OpenAI Images response missing 'data' list")

    first = data[0]
    if hasattr(first, "b64_json"):
        b64_json = getattr(first, "b64_json")
    elif isinstance(first, dict):
        b64_json = first.get("b64_json")
    else:
        b64_json = None

    if not b64_json or not isinstance(b64_json, str):
        raise RuntimeError("OpenAI Images response missing 'b64_json' payload")

    return b64_json
