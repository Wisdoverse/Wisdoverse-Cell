#!/usr/bin/env bash
# Run Alembic migrations through a full upgrade -> downgrade -> upgrade
# cycle against a test database. Stage 5 item 5 per
# docs/architecture/migration-plan.md ("CI runs Alembic up + down on
# every PR that touches migrations/").
#
# Usage:
#   make migration-test
# Or:
#   scripts/migration_round_trip.sh
#
# Requires:
#   - PostgreSQL reachable at $TEST_DATABASE_URL (default below).
#   - Active virtualenv with alembic + the project dependencies.
#
# Exit codes:
#   0 = full round trip succeeded
#   1 = upgrade head failed
#   2 = downgrade base failed
#   3 = re-upgrade head failed
#
# Safety:
#   This script runs against a dedicated test database. It will create
#   tables, then DROP them via downgrade. Do NOT point it at production.

set -euo pipefail

: "${TEST_DATABASE_URL:=postgresql+asyncpg://wisdoverse_cell:wisdoverse_cell@127.0.0.1:5433/wisdoverse_cell_migration_test}"

export DATABASE_URL="$TEST_DATABASE_URL"
export POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"
export POSTGRES_PORT="${POSTGRES_PORT:-5433}"
export POSTGRES_USER="${POSTGRES_USER:-wisdoverse_cell}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-wisdoverse_cell}"
export POSTGRES_DB="${POSTGRES_DB:-wisdoverse_cell_migration_test}"
export CONTROL_PLANE_ENABLED="${CONTROL_PLANE_ENABLED:-true}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Migration round-trip starts"
echo "    DATABASE_URL=$DATABASE_URL"

echo "==> alembic upgrade head"
if ! alembic upgrade head; then
    echo "FAIL: alembic upgrade head" >&2
    exit 1
fi

echo "==> alembic downgrade base"
if ! alembic downgrade base; then
    echo "FAIL: alembic downgrade base" >&2
    exit 2
fi

echo "==> alembic upgrade head (re-run)"
if ! alembic upgrade head; then
    echo "FAIL: re-upgrade head after downgrade" >&2
    exit 3
fi

echo "==> Migration round-trip OK"
