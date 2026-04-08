FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GITHUB_OPS_MCP_PORT=3018 \
    GITHUB_OPS_MCP_REPO_ROOT=/target

WORKDIR /factory
COPY factory_runtime/ /factory/factory_runtime/
ENV PYTHONPATH="/factory"

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      | gpg --dearmor -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
  mcp==1.25.0 \
  uvicorn[standard]==0.44.0

EXPOSE 3018

CMD ["python", "-m", "factory_runtime.apps.mcp.github_ops.mcp_server"]
