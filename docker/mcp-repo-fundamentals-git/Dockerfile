FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GIT_MCP_PORT=3012 \
    REPO_FUNDAMENTALS_REPO_ROOT=/target

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /factory
COPY factory_runtime/apps/__init__.py apps/__init__.py
COPY factory_runtime/apps/mcp/__init__.py apps/mcp/__init__.py
COPY factory_runtime/apps/mcp/repo_fundamentals/ apps/mcp/repo_fundamentals/

RUN pip install --no-cache-dir \
    mcp==1.25.0 \
    uvicorn[standard]==0.44.0

EXPOSE 3012

CMD ["python", "-m", "apps.mcp.repo_fundamentals.git_server"]
