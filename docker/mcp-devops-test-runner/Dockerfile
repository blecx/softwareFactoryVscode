FROM node:20-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TEST_RUNNER_MCP_PORT=3016 \
    TEST_RUNNER_MCP_REPO_ROOT=/target

WORKDIR /factory
COPY factory_runtime/apps/__init__.py apps/__init__.py
COPY factory_runtime/apps/mcp/__init__.py apps/mcp/__init__.py
COPY factory_runtime/apps/mcp/devops/ apps/mcp/devops/

RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 python3-pip && \
    rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir --break-system-packages \
      mcp==1.25.0 \
    uvicorn[standard]==0.44.0

EXPOSE 3016

CMD ["python3", "-m", "apps.mcp.devops.test_runner_server"]
