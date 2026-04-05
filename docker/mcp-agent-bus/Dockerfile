FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AGENT_BUS_PORT=3031 \
    AGENT_BUS_DB_PATH=/data/agent_bus.db

RUN mkdir -p /data

WORKDIR /factory

RUN pip install --no-cache-dir \
    mcp==1.12.4 \
    uvicorn[standard]==0.27.0

COPY factory_runtime/apps/__init__.py apps/__init__.py
COPY factory_runtime/apps/mcp/__init__.py apps/mcp/__init__.py
COPY factory_runtime/apps/mcp/agent_bus/ apps/mcp/agent_bus/

VOLUME ["/data"]

EXPOSE 3031

CMD ["python", "-m", "apps.mcp.agent_bus.mcp_server"]
