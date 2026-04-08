FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AGENT_BUS_PORT=3031 \
    AGENT_BUS_DB_PATH=/data/agent_bus.db

RUN mkdir -p /data

WORKDIR /factory

RUN pip install --no-cache-dir \
    mcp==1.25.0 \
    uvicorn[standard]==0.44.0

COPY factory_runtime/ /factory/factory_runtime/
ENV PYTHONPATH="/factory"

VOLUME ["/data"]

EXPOSE 3031

CMD ["python", "-m", "factory_runtime.apps.mcp.agent_bus.mcp_server"]
