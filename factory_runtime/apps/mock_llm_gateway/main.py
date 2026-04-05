from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Mock LLM Gateway")

_DEFAULT_MOCKS = [
    {
        "id": "todo-smoke-default",
        "prompt": "Create a todo app",
        "response": "Mock response: create a tiny todo app.",
    }
]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "mock-llm-gateway"}


@app.get("/admin/mocks")
def list_mocks() -> dict[str, list[dict[str, str]]]:
    return {"mocks": _DEFAULT_MOCKS}
