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

COPY factory_runtime/ /factory/factory_runtime/
ENV PYTHONPATH="/factory"

VOLUME ["/data"]

EXPOSE 3030

CMD ["python", "-m", "factory_runtime.apps.mcp.memory.mcp_server"]
