FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APPROVAL_GATE_PORT=8001 \
    AGENT_BUS_URL=http://mcp-agent-bus:3031

WORKDIR /factory

RUN pip install --no-cache-dir \
    fastapi==0.109.1 \
    uvicorn[standard]==0.27.0 \
    httpx==0.27.0 \
    pydantic==2.5.3 \
    websockets==12.0

COPY apps/__init__.py apps/__init__.py
COPY apps/approval_gate/ apps/approval_gate/

EXPOSE 8001

CMD ["python", "-m", "apps.approval_gate.main"]
