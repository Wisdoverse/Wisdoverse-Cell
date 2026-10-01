"""Add native owner-local executor intents and immutable replay receipts.

Revision ID: 20261001_native_executor_receipts
Revises: 20261001_product_governance
"""

import sqlalchemy as sa
from alembic import op

revision = "20261001_native_executor_receipts"
down_revision = "20261001_product_governance"
branch_labels = None
depends_on = None

_TABLES = (
    "requirement_manager_executor_requests",
    "pjm_executor_requests",
    "dev_agent_executor_requests",
    "qa_executor_requests",
)


def upgrade() -> None:
    for name in _TABLES:
        op.create_table(
            name,
            sa.Column("run_id", sa.String(48), primary_key=True),
            sa.Column("company_id", sa.String(48), nullable=False),
            sa.Column("request_hash", sa.String(64), nullable=False),
            sa.Column("state", sa.String(16), nullable=False),
            sa.Column("response", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    # Intents pin uncertain external effects. Dropping a live ledger would reopen
    # old run IDs; require operator reconciliation and a separately reviewed purge.
    connection = op.get_bind()
    if any(connection.scalar(sa.text(f'SELECT COUNT(*) FROM "{name}"')) for name in _TABLES):
        raise RuntimeError("Native executor ledger downgrade requires empty receipt tables")
    for name in reversed(_TABLES):
        op.drop_table(name)
