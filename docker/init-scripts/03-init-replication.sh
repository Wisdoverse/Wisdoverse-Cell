#!/bin/bash
set -e

# =============================================================================
# Initialize PostgreSQL Streaming Replication
# =============================================================================
# Runs on the primary during first startup (docker-entrypoint-initdb.d).
# Creates a replication role and allows replication connections.

echo "Setting up replication user..."

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'replicator') THEN
            CREATE ROLE replicator WITH REPLICATION LOGIN PASSWORD '${POSTGRES_REPLICATION_PASSWORD:-replicator}';
        END IF;
    END
    \$\$;
EOSQL

# Allow replication connections from Docker network.
echo "host replication replicator all md5" >> "$PGDATA/pg_hba.conf"

# Reload config to pick up pg_hba change.
pg_ctl reload -D "$PGDATA"

echo "Replication setup complete."
