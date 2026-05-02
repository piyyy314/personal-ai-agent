# Production-grade container image for the personal AI agent
# Multi-stage build for security and minimal image size
FROM python:3.10-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.10-slim

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r agent && useradd -r -g agent agent

# Create application directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/agent/.local

# Copy application code
COPY --chown=agent:agent . .

# Create log directory
RUN mkdir -p /var/log/agent && chown -R agent:agent /var/log/agent

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/home/agent/.local/bin:$PATH \
    HEALTH_PORT=8080

# Switch to non-root user
USER agent

# Expose health check port
EXPOSE 8080

# Health check configuration
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Readiness probe (for Kubernetes)
# Use: curl http://localhost:8080/ready

# Labels for metadata
LABEL org.opencontainers.image.title="Personal AI Agent" \
      org.opencontainers.image.description="Production-ready AI agent with monitoring and compliance" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.vendor="Personal AI Agent Project"

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
