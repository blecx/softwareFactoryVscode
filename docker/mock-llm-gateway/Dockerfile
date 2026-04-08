FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /factory

RUN pip install --no-cache-dir \
    fastapi==0.109.1 \
    uvicorn==0.27.0 \
    pydantic==2.5.3

COPY factory_runtime/ /factory/factory_runtime/
ENV PYTHONPATH="/factory"

EXPOSE 9090

CMD ["uvicorn", "factory_runtime.apps.mock_llm_gateway.main:app", "--host", "0.0.0.0", "--port", "9090"]
