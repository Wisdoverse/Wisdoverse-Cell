"""Candidate migration surface: only accepts a rehearsal-owned connection."""

from alembic import context

from agents.dev_agent.migrations.contracts import verify_inherited_schema, verify_scope
from agents.dev_agent.models import Base

connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError("Dev migrations are rehearsal-only; use make migration-rehearse-dev")

verify_scope(context.config, connection)
expected = context.config.attributes.get("inherited_inventory")
if expected is not None:
    verify_inherited_schema(connection, expected)

context.configure(
    connection=connection,
    target_metadata=Base.metadata,
    version_table="alembic_version_dev_agent",
)
with context.begin_transaction():
    context.run_migrations()
