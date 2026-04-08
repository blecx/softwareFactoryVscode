FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MEMORY_MCP_PORT=3030 \
    MEMORY_DB_PATH=/data/memory.db

RUN mkdir -p /data

WORKDIR /factory

RUN pip install --no-cache-dir \
    mcp==1.25.0 \
    uvicorn[standard]==0.44.0

COPY factory_runtime/apps/__init__.py apps/__init__.py
COPY factory_runtime/apps/mcp/__init__.py apps/mcp/__init__.py
COPY factory_runtime/apps/mcp/memory/ apps/mcp/memory/

VOLUME ["/data"]

EXPOSE 3030

CMD ["python", "-m", "apps.mcp.memory.mcp_server"]
