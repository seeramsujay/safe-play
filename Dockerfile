# Use a lightweight official Python runtime as a parent image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Default environment variables for Google Cloud Run
ENV PORT=8080
ENV MQTT_BROKER_URL=127.0.0.1
ENV LLAMA_SERVER_URL=http://localhost:8080/completion

# Copy requirements file first to leverage Docker layer caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code and schema configuration
COPY src/ ./src/
COPY config/ ./config/

# Expose the configured port (informative only, Cloud Run overrides this dynamically)
EXPOSE 8080

# Command to execute the core asynchronous middleware engine
CMD ["python", "-m", "src.orchestrator", "--config", "config/schema.json"]
