# Multi-stage build
FROM python:3.14-slim AS builder

# Declare the build environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_HTTP_TIMEOUT=120

# Get the necessary build packages and curl
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Get the latest version of UV from the official website
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set the working directory
WORKDIR /app

# Copy project configuration files and lock file (if present) to leverage caching
COPY pyproject.toml uv.lock* README.md* ./

# Copy the rest of the application source code needed for package installation
COPY . .

# Install packages with uv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system --upgrade pip && \
    uv pip install --system .

# Runtime stage
FROM python:3.14-slim AS runtime

# Set the runtime environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Set the user and permissions
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -d /app -s /bin/bash appuser

# Set the runtime working dir
WORKDIR /app

# Copy installed packages and binaries from the build stage
COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Create folders
RUN mkdir -p ./logs ./secrets && \
    chown -R appuser:appuser /app

# Copy application code with assigned permissions
COPY --chown=appuser:appuser . .

# Set the user
USER appuser

# Expose the port
EXPOSE 8000

# Run the python command to create the server
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info", "--reload"]
