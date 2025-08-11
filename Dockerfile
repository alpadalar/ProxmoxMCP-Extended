# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install uv

# Copy project files
COPY . .

# Create virtual environment and install dependencies
RUN uv venv && \
    . .venv/bin/activate && \
    uv pip install -e ".[dev]" && \
    uv pip install fastmcp asgiref

# Expose port
EXPOSE 8812

# Set environment variables
ENV PROXMOX_MCP_CONFIG="/app/proxmox-config/config.json"
ENV HTTP_HOST="0.0.0.0"
ENV HTTP_PORT="8812"
ENV HTTP_PATH="/mcp"

# Startup command - HTTP MCP Server
CMD ["/bin/bash", "-c", "cd /app && source .venv/bin/activate && python -m proxmox_mcp.server_http --host ${HTTP_HOST} --port ${HTTP_PORT} --path ${HTTP_PATH}"]