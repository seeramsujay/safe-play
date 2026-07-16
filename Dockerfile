# Stage 1: Build stage for compiling Cython extensions
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build essential tools for Cython compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY setup.py .
COPY src/routing.pyx ./src/routing.pyx

# Compile the Cython extension module (ensuring setuptools is installed)
RUN pip install --no-cache-dir setuptools && python setup.py build_ext --inplace

# Stage 2: Production runtime stage
FROM python:3.12-slim

WORKDIR /app

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Default environment variables for Google Cloud Run
ENV PORT=8080
ENV MQTT_BROKER_URL=127.0.0.1
ENV LLAMA_SERVER_URL=http://localhost:8080/completion

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy environment configurations if present
COPY .env* ./

# Copy application source code and schema configuration
COPY src/ ./src/
COPY config/ ./config/

# Inject the compiled Cython binary from the builder stage
COPY --from=builder /app/routing*.so ./src/

# Expose the configured port (informative only, Cloud Run overrides this dynamically)
EXPOSE 8080

# Command to execute the core asynchronous middleware engine
CMD ["python", "-m", "src.orchestrator", "--config", "config/schema.json"]
