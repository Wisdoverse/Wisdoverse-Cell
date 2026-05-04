# ==============================================================================
# DEPRECATED — Use docker/Dockerfile.agents (target: qa-agent) instead.
# This file is kept for standalone builds only.
# ==============================================================================
#
# Preferred:
#   docker build --target qa-agent -f docker/Dockerfile.agents .
#   docker compose build qa-agent
#
# ==============================================================================

FROM python:3.13-slim AS builder

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

FROM python:3.13-slim AS runtime

LABEL org.opencontainers.image.title="QA Agent" \
      org.opencontainers.image.description="Automated acceptance verification for AI-generated code" \
      org.opencontainers.image.vendor="Wisdoverse Cell" \
      org.opencontainers.image.source="https://github.com/Wisdoverse/project-cell" \
      org.opencontainers.image.licenses="LicenseRef-Wisdoverse-Cell-BSL-1.1"

RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 tini curl \
    && rm -rf /var/lib/apt/lists/* && apt-get clean

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY --chown=appuser:appgroup shared/ /app/shared/
COPY --chown=appuser:appgroup agents/qa_agent/ /app/agents/qa_agent/
COPY --chown=appuser:appgroup .acceptance/ /app/.acceptance/

ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    DEBUG=false \
    API_HOST=0.0.0.0 \
    API_PORT=8014

USER appuser
EXPOSE 8014

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl --fail --silent http://localhost:8014/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["gunicorn", \
     "agents.qa_agent.app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "1", \
     "--bind", "0.0.0.0:8014", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--keep-alive", "5", \
     "--access-logfile", "-", \
     "--access-logformat", "%(h)s %(l)s %(u)s %(t)s \"%(r)s\" %(s)s %(b)s %(D)s"]
