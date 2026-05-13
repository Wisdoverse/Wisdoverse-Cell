#!/usr/bin/env sh
set -eu

# Create per-agent PostgreSQL roles before 02-agent-users.sql applies grants.
# The SQL file keeps the table and sequence grants; this shell layer owns
# passwords because the official Postgres entrypoint does not expand
# environment variables inside .sql files.

APP_ENV="${APP_ENV:-development}"

psql_cmd() {
    if [ -n "${POSTGRES_HOST:-}" ]; then
        PGPASSWORD="${POSTGRES_PASSWORD:-}" psql \
            -v ON_ERROR_STOP=1 \
            --host "${POSTGRES_HOST}" \
            --port "${POSTGRES_PORT:-5432}" \
            --username "${POSTGRES_USER:-wisdoverse-cell}" \
            --dbname "${POSTGRES_DB:-wisdoverse-cell}" \
            "$@"
        return
    fi

    PGPASSWORD="${POSTGRES_PASSWORD:-}" psql \
        -v ON_ERROR_STOP=1 \
        --username "${POSTGRES_USER:-wisdoverse-cell}" \
        --dbname "${POSTGRES_DB:-wisdoverse-cell}" \
        "$@"
}

agent_password() {
    env_name="$1"
    dev_default="$2"
    value="$(eval "printf '%s' \"\${${env_name}:-}\"")"
    if [ -n "$value" ]; then
        printf '%s' "$value"
        return
    fi
    if [ "$APP_ENV" = "production" ]; then
        echo "ERROR: ${env_name} is required when APP_ENV=production" >&2
        exit 1
    fi
    printf '%s' "$dev_default"
}

create_or_update_role() {
    role="$1"
    env_name="$2"
    dev_default="$3"
    password="$(agent_password "$env_name" "$dev_default")"

    exists="$(psql_cmd -v role="$role" --tuples-only --no-align <<'EOSQL'
SELECT 1 FROM pg_roles WHERE rolname = :'role';
EOSQL
)"

    if [ "$exists" = "1" ]; then
        psql_cmd -v role="$role" -v password="$password" <<'EOSQL'
ALTER ROLE :"role" WITH LOGIN PASSWORD :'password';
EOSQL
    else
        psql_cmd -v role="$role" -v password="$password" <<'EOSQL'
CREATE ROLE :"role" WITH LOGIN PASSWORD :'password';
EOSQL
    fi
}

create_or_update_role "chat_agent" "CHAT_AGENT_DB_PASSWORD" "chat_agent_dev"
create_or_update_role "pjm_agent" "PM_AGENT_DB_PASSWORD" "pjm_agent_dev"
create_or_update_role "sync_agent" "SYNC_MODULE_DB_PASSWORD" "sync_agent_dev"
create_or_update_role "analysis_agent" "ANALYSIS_MODULE_DB_PASSWORD" "analysis_agent_dev"
create_or_update_role "qa_agent" "QA_AGENT_DB_PASSWORD" "qa_agent_dev"
create_or_update_role "dev_agent" "DEV_AGENT_DB_PASSWORD" "dev_agent_dev"
create_or_update_role "evolution_agent" "EVOLUTION_MODULE_DB_PASSWORD" "evolution_agent_dev"

echo "Per-runtime DB role passwords initialized for APP_ENV=${APP_ENV}"
