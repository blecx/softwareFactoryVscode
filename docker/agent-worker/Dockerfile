FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /factory

# Install full requirements (includes agents package deps)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY agents/ agents/
COPY apps/__init__.py apps/__init__.py
COPY apps/mcp/ apps/mcp/

# Workspace is mounted at runtime via volume
# CMD runs the orchestrator queue loop
CMD ["python", "-m", "agents.maestro_cli", "run-queue"]
