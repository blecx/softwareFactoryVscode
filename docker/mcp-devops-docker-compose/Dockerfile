FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DOCKER_COMPOSE_MCP_PORT=3015 \
    DOCKER_COMPOSE_MCP_REPO_ROOT=/target

WORKDIR /factory
COPY factory_runtime/ /factory/factory_runtime/
ENV PYTHONPATH="/factory"

RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
  && install -m 0755 -d /etc/apt/keyrings \
  && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
  && chmod a+r /etc/apt/keyrings/docker.asc \
  && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" > /etc/apt/sources.list.d/docker.list \
  && apt-get update \
  && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
  && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    mcp==1.25.0 \
  uvicorn[standard]==0.44.0

EXPOSE 3015

CMD ["python", "-m", "factory_runtime.apps.mcp.devops.docker_compose_server"]
