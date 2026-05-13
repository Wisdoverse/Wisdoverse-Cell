#!/bin/sh
# Wisdoverse Cell — unified Python runtime entrypoint.
#
# The image bundles every Python agent and capability module so a single
# tagged release artifact (`ghcr.io/wisdoverse/cell-agents:<version>`) can
# back every container in the compose topology. The first positional
# argument selects which agent or capability to launch; alternatively set
# the `WISDOVERSE_AGENT` environment variable. Any unrecognised argument
# is exec'd as-is so `docker run ... bash` and similar continue to work.
#
# Each entry maps to a (port, ASGI app path) pair. Override the bind port
# with `WISDOVERSE_BIND_PORT`; override the ASGI app with
# `WISDOVERSE_APP_PATH`. Extra gunicorn flags are taken verbatim from
# `GUNICORN_EXTRA_ARGS`.

set -eu

agent="${WISDOVERSE_AGENT:-${1:-}}"
if [ -n "${1:-}" ] && [ "${WISDOVERSE_AGENT:-}" = "" ]; then
  shift
fi

case "${agent}" in
  ai-core|requirement-manager)
    : "${WISDOVERSE_BIND_PORT:=8000}"
    : "${WISDOVERSE_APP_PATH:=agents.requirement_manager.app.main:app}"
    ;;
  sync-module)
    : "${WISDOVERSE_BIND_PORT:=8010}"
    : "${WISDOVERSE_APP_PATH:=shared.capabilities.sync.app.main:app}"
    ;;
  analysis-module)
    : "${WISDOVERSE_BIND_PORT:=8011}"
    : "${WISDOVERSE_APP_PATH:=shared.capabilities.analysis.app.main:app}"
    ;;
  evolution-module)
    : "${WISDOVERSE_BIND_PORT:=8016}"
    : "${WISDOVERSE_APP_PATH:=shared.capabilities.evolution.app.main:app}"
    ;;
  pjm-agent)
    : "${WISDOVERSE_BIND_PORT:=8012}"
    : "${WISDOVERSE_APP_PATH:=agents.pjm_agent.app.main:app}"
    ;;
  qa-agent)
    : "${WISDOVERSE_BIND_PORT:=8014}"
    : "${WISDOVERSE_APP_PATH:=agents.qa_agent.app.main:app}"
    ;;
  dev-agent)
    : "${WISDOVERSE_BIND_PORT:=8015}"
    : "${WISDOVERSE_APP_PATH:=agents.dev_agent.app.main:app}"
    ;;
  chat-agent|user-interaction-gateway)
    : "${WISDOVERSE_BIND_PORT:=8013}"
    : "${WISDOVERSE_APP_PATH:=services.gateways.user_interaction.app.main:app}"
    ;;
  cell)
    exec python /usr/local/bin/wisdoverse-cell-supervisor "$@"
    ;;
  ""|"-h"|"--help"|"help")
    cat <<'USAGE'
Usage: wisdoverse-agent <service> [extra gunicorn args]

Services (also accepted via WISDOVERSE_AGENT env):
  cell                            full local Cell runtime
  ai-core | requirement-manager   port 8000
  sync-module                     port 8010
  analysis-module                 port 8011
  evolution-module                port 8016
  pjm-agent                       port 8012
  qa-agent                        port 8014
  dev-agent                       port 8015
  chat-agent | user-interaction-gateway  port 8013

Environment overrides:
  WISDOVERSE_BIND_PORT    bind port (default per service above)
  WISDOVERSE_APP_PATH     ASGI app import path (default per service above)
  GUNICORN_WORKERS        worker count (default 1)
  GUNICORN_EXTRA_ARGS     extra gunicorn flags (verbatim)
USAGE
    exit 0
    ;;
  *)
    # Fall through: treat unrecognised first arg as a raw command (bash, alembic, ...).
    exec "${agent}" "$@"
    ;;
esac

: "${GUNICORN_WORKERS:=1}"
: "${GUNICORN_EXTRA_ARGS:=}"

# shellcheck disable=SC2086
exec gunicorn \
  "${WISDOVERSE_APP_PATH}" \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers "${GUNICORN_WORKERS}" \
  --bind "0.0.0.0:${WISDOVERSE_BIND_PORT}" \
  --timeout 120 \
  --graceful-timeout 30 \
  --keep-alive 5 \
  --access-logfile - \
  --access-logformat '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s %(D)s' \
  ${GUNICORN_EXTRA_ARGS} \
  "$@"
