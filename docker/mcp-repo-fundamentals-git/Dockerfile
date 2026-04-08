FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GIT_MCP_PORT=3012 \
    REPO_FUNDAMENTALS_REPO_ROOT=/target

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /factory
COPY factory_runtime/ /factory/factory_runtime/
ENV PYTHONPATH="/factory"

RUN pip install --no-cache-dir \
    mcp==1.25.0 \
    uvicorn[standard]==0.44.0

EXPOSE 3012

CMD ["python", "-m", "factory_runtime.apps.mcp.repo_fundamentals.git_server"]
