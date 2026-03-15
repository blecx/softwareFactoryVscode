FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install git (required for GitPython)
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
# Copy from repo root: requirements at repo root and apps/api/requirements.txt
COPY requirements.txt .
COPY apps/api/requirements.txt ./apps_api_requirements.txt
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt

# Copy application code and shared templates/configs
# Copy the API app into /app
COPY apps/api/ /app/
# Copy templates and configs into the image so services can access them
COPY templates/ /app/templates/
COPY configs/ /app/configs/

# Create directories for mounted volumes
RUN mkdir -p /projectDocs /config

# Expose port
EXPOSE 8000

# Set environment variables
ENV PROJECT_DOCS_PATH=/projectDocs
ENV LLM_CONFIG_PATH=/config/llm.json
ENV PYTHONUNBUFFERED=1

# Configure git (required for commits)
RUN git config --global user.email "agent@iso21500.local" && \
    git config --global user.name "ISO21500 Agent"

# Run uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
