FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BASH_GATEWAY_MCP_PORT=3011 \
    BASH_GATEWAY_REPO_ROOT=/target \
    BASH_GATEWAY_POLICY_PATH=/target/configs/bash_gateway_policy.default.yml

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /factory
COPY factory_runtime/ /factory/factory_runtime/
ENV PYTHONPATH="/factory"

RUN pip install --no-cache-dir \
    mcp==1.25.0 \
    uvicorn[standard]==0.44.0 \
    pyyaml==6.0.1

EXPOSE 3011

CMD ["python", "-m", "factory_runtime.apps.mcp.bash_gateway.mcp_server"]
