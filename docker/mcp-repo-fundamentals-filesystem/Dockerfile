FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FILESYSTEM_MCP_PORT=3014 \
    REPO_FUNDAMENTALS_REPO_ROOT=/target

WORKDIR /factory
COPY factory_runtime/ /factory/factory_runtime/
ENV PYTHONPATH="/factory"

RUN pip install --no-cache-dir \
    black==24.4.2 \
    mcp==1.25.0 \
    uvicorn[standard]==0.44.0

EXPOSE 3014

CMD ["python", "-m", "factory_runtime.apps.mcp.repo_fundamentals.filesystem_server"]
