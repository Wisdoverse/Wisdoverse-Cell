# ==============================================================================
# DEPRECATED — Use docker/Dockerfile.agents (target: dev-agent) instead.
# This file is kept for standalone builds only.
# ==============================================================================
#
# Preferred:
#   docker build --target dev-agent -f docker/Dockerfile.agents .
#   docker compose build dev-agent
#
# Legacy standalone:
#   docker build -t wisdoverse/cell-dev-agent:latest \
#     -f agents/dev_agent/Dockerfile .
#
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Builder - Install dependencies and compile
# ------------------------------------------------------------------------------
FROM python:3.14-slim AS builder

ARG PIP_NO_CACHE_DIR=1
ARG PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ------------------------------------------------------------------------------
# Stage 2: Runtime - Minimal production image
# ------------------------------------------------------------------------------
FROM python:3.14-slim AS runtime

# =============================================================================
# Metadata (OCI Image Spec)
# =============================================================================
LABEL org.opencontainers.image.title="Dev Agent" \
      org.opencontainers.image.description="AI development agent for code generation and review" \
      org.opencontainers.image.vendor="Wisdoverse Cell" \
      org.opencontainers.image.source="https://github.com/Wisdoverse/Wisdoverse-Cell" \
      org.opencontainers.image.documentation="https://github.com/Wisdoverse/Wisdoverse-Cell/docs" \
      org.opencontainers.image.licenses="LicenseRef-Wisdoverse-Cell-BSL-1.1"

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
    libpq5 tini curl \
    && rm -rf /var/lib/apt/lists/* && apt-get clean

# =============================================================================
# Application Setup
# =============================================================================
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY --chown=appuser:appgroup shared/ /app/shared/
COPY --chown=appuser:appgroup agents/dev_agent/ /app/agents/dev_agent/

# =============================================================================
# Environment Configuration
# =============================================================================
ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_ENV=production \
    DEBUG=false \
    API_HOST=0.0.0.0 \
    API_PORT=8015

# =============================================================================
# Runtime Configuration
# =============================================================================
USER appuser
EXPOSE 8015

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl --fail --silent http://localhost:8015/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["gunicorn", \
     "agents.dev_agent.app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "1", \
     "--bind", "0.0.0.0:8015", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--keep-alive", "5", \
     "--access-logfile", "-", \
     "--access-logformat", "%(h)s %(l)s %(u)s %(t)s \"%(r)s\" %(s)s %(b)s %(D)s"]
