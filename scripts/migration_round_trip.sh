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
#   4 = post-upgrade insert probe failed (server defaults missing/incorrect)
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

# INSERT probes — catches the class of bug where a migration declares
# columns as NOT NULL without a server default, so an insert that omits the
# column relies on an ORM-level default that the bare SQL probe does not
# emit. The current probe covers qa_acceptance_runs (per migration
# 20260517). Extend with additional table/column combinations as new
# NOT-NULL-with-default columns appear.
echo "==> Post-upgrade INSERT probe: qa_acceptance_runs JSONB defaults"
PROBE_PSQL_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
PROBE_ID="probe_$(date +%s%N)"
if ! PGPASSWORD="$POSTGRES_PASSWORD" psql "$PROBE_PSQL_URL" -v ON_ERROR_STOP=1 -q <<SQL
    INSERT INTO qa_acceptance_runs (
        id, agent_name, target_path, trigger, level,
        l0_status, l1_status, l2_status,
        total_checks, l0_failure_count, l1_warning_count,
        duration_seconds, runner_exit_code,
        raw_report, created_at
    ) VALUES (
        '${PROBE_ID}', 'qa-agent', '/tmp/round-trip-probe', 'manual', 'l0',
        'PASS', 'PASS', 'PASS', 0, 0, 0,
        0.0, 0,
        '{}'::jsonb, NOW()
    );
    DO \$\$
    DECLARE
        files_changed_val jsonb;
        notification_summary_val jsonb;
    BEGIN
        SELECT files_changed, notification_summary
          INTO files_changed_val, notification_summary_val
          FROM qa_acceptance_runs
         WHERE id = '${PROBE_ID}';
        IF files_changed_val IS DISTINCT FROM '[]'::jsonb THEN
            RAISE EXCEPTION 'files_changed default missing or wrong: %', files_changed_val;
        END IF;
        IF notification_summary_val IS DISTINCT FROM '{}'::jsonb THEN
            RAISE EXCEPTION 'notification_summary default missing or wrong: %', notification_summary_val;
        END IF;
    END
    \$\$;
    DELETE FROM qa_acceptance_runs WHERE id = '${PROBE_ID}';
SQL
then
    echo "FAIL: qa_acceptance_runs JSONB default probe" >&2
    exit 4
fi

echo "==> Migration round-trip OK"
