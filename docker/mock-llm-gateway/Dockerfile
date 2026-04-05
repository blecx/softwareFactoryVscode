FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn pydantic

COPY factory_runtime/apps/mock_llm_gateway /app/apps/mock_llm_gateway

EXPOSE 9090

CMD ["uvicorn", "apps.mock_llm_gateway.main:app", "--host", "0.0.0.0", "--port", "9090"]
