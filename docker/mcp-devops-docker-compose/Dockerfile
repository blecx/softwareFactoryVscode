FROM docker:27.4.1-cli

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DOCKER_COMPOSE_MCP_PORT=3015 \
    DOCKER_COMPOSE_MCP_REPO_ROOT=/target

WORKDIR /factory
COPY factory_runtime/ /factory/factory_runtime/
ENV PYTHONPATH="/factory"

RUN apk add --no-cache python3 py3-pip && \
    pip install --no-cache-dir --break-system-packages \
      mcp==1.25.0 \
    uvicorn[standard]==0.44.0

EXPOSE 3015

CMD ["python3", "-m", "factory_runtime.apps.mcp.devops.docker_compose_server"]
