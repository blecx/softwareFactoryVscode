FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir fastapi uvicorn pydantic

COPY apps/mock_llm_gateway /app/apps/mock_llm_gateway

EXPOSE 9090

CMD ["uvicorn", "apps.mock_llm_gateway.main:app", "--host", "0.0.0.0", "--port", "9090"]
