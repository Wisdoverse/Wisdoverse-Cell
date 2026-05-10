# ==============================================================================
# DEPRECATED — Use docker/Dockerfile.agents (target: ai-core) instead.
# This file is kept for standalone builds only.
# ==============================================================================
#
# Preferred:
#   docker build --target ai-core -f docker/Dockerfile.agents .
#   docker compose build ai-core
#
# Legacy standalone:
#   docker build -t wisdoverse/cell-requirement-manager:latest \
#     --build-arg VERSION=$(git describe --tags --always) \
#     -f agents/requirement_manager/Dockerfile .
#
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Builder - Install dependencies and compile
# ------------------------------------------------------------------------------
FROM python:3.13-slim AS builder

# Build arguments
ARG PIP_NO_CACHE_DIR=1
ARG PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ------------------------------------------------------------------------------
# Stage 2: Runtime - Minimal production image
# ------------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

# =============================================================================
# Metadata (OCI Image Spec)
# =============================================================================
LABEL org.opencontainers.image.title="Requirement Manager Agent" \
      org.opencontainers.image.description="Requirements extraction, confirmation, and PRD generation agent" \
      org.opencontainers.image.vendor="Wisdoverse Cell" \
      org.opencontainers.image.source="https://github.com/Wisdoverse/Wisdoverse-Cell" \
      org.opencontainers.image.documentation="https://github.com/Wisdoverse/Wisdoverse-Cell/docs" \
      org.opencontainers.image.licenses="LicenseRef-Wisdoverse-Cell-BSL-1.1"

# Build arguments for versioning
ARG VERSION=dev
ARG BUILD_DATE
ARG GIT_COMMIT

LABEL org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${GIT_COMMIT}"

# =============================================================================
# Security: Non-root user
# =============================================================================
RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

# =============================================================================
# Runtime Dependencies
# =============================================================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    # PostgreSQL client library (required by asyncpg)
    libpq5 \
    # Process manager for proper signal handling
    tini \
    # Health check utility
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# =============================================================================
# Application Setup
# =============================================================================
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY --chown=appuser:appgroup shared/ /app/shared/
COPY --chown=appuser:appgroup skills/ /app/skills/
COPY --chown=appuser:appgroup agents/requirement_manager/ /app/agents/requirement_manager/

# =============================================================================
# Environment Configuration
# =============================================================================
ENV PYTHONPATH=/app \
    # Prevent Python from writing bytecode
    PYTHONDONTWRITEBYTECODE=1 \
    # Prevent Python from buffering stdout/stderr
    PYTHONUNBUFFERED=1 \
    # Disable pip version warnings
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Application defaults
    APP_ENV=production \
    DEBUG=false \
    API_HOST=0.0.0.0 \
    API_PORT=8000

# =============================================================================
# Runtime Configuration
# =============================================================================
# Switch to non-root user
USER appuser

# Expose ports (HTTP API + gRPC)
EXPOSE 8000 50051

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl --fail --silent http://localhost:8000/health || exit 1

# Use tini as init system for proper signal handling
ENTRYPOINT ["/usr/bin/tini", "--"]

# Run application with Gunicorn managing multiple Uvicorn workers
CMD ["gunicorn", \
     "agents.requirement_manager.app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "4", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--keep-alive", "5", \
     "--access-logfile", "-", \
     "--access-logformat", "%(h)s %(l)s %(u)s %(t)s \"%(r)s\" %(s)s %(b)s %(D)s"]
