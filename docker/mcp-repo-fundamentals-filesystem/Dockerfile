FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FILESYSTEM_MCP_PORT=3014 \
    REPO_FUNDAMENTALS_REPO_ROOT=/target

WORKDIR /factory
COPY factory_runtime/apps/__init__.py apps/__init__.py
COPY factory_runtime/apps/mcp/__init__.py apps/mcp/__init__.py
COPY factory_runtime/apps/mcp/repo_fundamentals/ apps/mcp/repo_fundamentals/

RUN pip install --no-cache-dir \
    mcp==1.12.4 \
    uvicorn[standard]==0.27.0

EXPOSE 3014

CMD ["python", "-m", "apps.mcp.repo_fundamentals.filesystem_server"]
