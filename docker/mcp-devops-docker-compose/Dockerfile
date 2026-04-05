FROM docker:27.4.1-cli

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DOCKER_COMPOSE_MCP_PORT=3015 \
    DOCKER_COMPOSE_MCP_REPO_ROOT=/target

WORKDIR /factory
COPY factory_runtime/apps/__init__.py apps/__init__.py
COPY factory_runtime/apps/mcp/__init__.py apps/mcp/__init__.py
COPY factory_runtime/apps/mcp/devops/ apps/mcp/devops/

RUN apk add --no-cache python3 py3-pip && \
    pip install --no-cache-dir --break-system-packages \
      mcp==1.12.4 \
      uvicorn[standard]==0.27.0

EXPOSE 3015

CMD ["python3", "-m", "apps.mcp.devops.docker_compose_server"]
