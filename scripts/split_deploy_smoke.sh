#!/usr/bin/env bash
# Split-deployment smoke test. Brings up infra + one runtime as an
# independent container (using the `split-agents` Compose profile),
# polls its /ready endpoint, then runs a wakeup against /agent/request.
#
# Stage 4 pre-condition #4 per docs/architecture/migration-plan.md:
# "Non-prod deployment proves the split under realistic load."
# This script satisfies the smoke half of that pre-condition; the
# load half (k6) lives in make load-smoke.
#
# Usage:
#   RUNTIME=dev-agent scripts/split_deploy_smoke.sh
#   RUNTIME=qa-agent  scripts/split_deploy_smoke.sh
#
# Or via make:
#   make split-deploy-dev    # RUNTIME=dev-agent
#   make split-deploy-qa     # RUNTIME=qa-agent
#
# Requires:
#   - Docker + Compose v2.
#   - `make up-infra` already brought up Postgres/Redis/NATS/Milvus,
#     or this script brings them up itself.
#   - PM_API_KEY env (or .env entry) so /ready can be polled.
#
# Exit codes:
#   0 = smoke succeeded
#   1 = compose up failed
#   2 = /ready did not return 200 within the timeout
#   3 = /agent/request smoke failed

set -euo pipefail

: "${RUNTIME:=dev-agent}"
: "${SMOKE_TIMEOUT_SECONDS:=120}"
: "${PM_API_KEY:=}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

case "$RUNTIME" in
    dev-agent)   PORT=8015 ;;
    qa-agent)    PORT=8014 ;;
    pjm-agent)   PORT=8012 ;;
    requirement-manager) PORT=8000 ;;
    *)
        echo "FAIL: unsupported RUNTIME=$RUNTIME" >&2
        exit 1
        ;;
esac

echo "==> Split-deployment smoke for $RUNTIME on port $PORT"

echo "==> docker compose --profile split-agents up -d $RUNTIME"
if ! docker compose --profile split-agents up -d "$RUNTIME"; then
    echo "FAIL: compose up" >&2
    exit 1
fi

echo "==> Wait for /ready"
deadline=$(( $(date +%s) + SMOKE_TIMEOUT_SECONDS ))
while true; do
    if curl --silent --fail \
         -H "X-Internal-Key: ${PM_API_KEY:-unused}" \
         "http://localhost:${PORT}/health/ready" > /dev/null; then
        echo "    /ready OK"
        break
    fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
        echo "FAIL: /ready did not return 200 within ${SMOKE_TIMEOUT_SECONDS}s" >&2
        docker compose logs --tail=80 "$RUNTIME" >&2 || true
        exit 2
    fi
    sleep 3
done

echo "==> Wakeup smoke against /agent/request"
if ! curl --silent --fail \
        -H "X-Internal-Key: ${PM_API_KEY:-unused}" \
        -H "Content-Type: application/json" \
        -d '{"action": "ping"}' \
        "http://localhost:${PORT}/agent/request" > /dev/null; then
    # `ping` may not be a known action — the runtime is expected to
    # return a structured error with X-Error-Code, not a connection
    # failure. We accept any HTTP 4xx response here because it proves
    # the runtime is reachable and parsing requests.
    HTTP_CODE=$(curl --silent --output /dev/null --write-out "%{http_code}" \
                -H "X-Internal-Key: ${PM_API_KEY:-unused}" \
                -H "Content-Type: application/json" \
                -d '{"action": "ping"}' \
                "http://localhost:${PORT}/agent/request")
    case "$HTTP_CODE" in
        2*|4*) echo "    /agent/request returned ${HTTP_CODE} (acceptable)" ;;
        *)
            echo "FAIL: /agent/request returned ${HTTP_CODE}" >&2
            exit 3
            ;;
    esac
fi

echo "==> Split-deployment smoke OK for $RUNTIME"
