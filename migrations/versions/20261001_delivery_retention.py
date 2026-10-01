"""Requirement delivery mapping and Control Plane physical retention receipts."""

import sqlalchemy as sa
from alembic import op

revision = "20261001_delivery_retention"
down_revision = "20261001_native_executor_receipts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "requirement_delivery_handoffs",
        sa.Column(
            "requirement_id", sa.String(32), sa.ForeignKey("requirements.id"), primary_key=True
        ),
        sa.Column("company_id", sa.String(48), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("wp_id", sa.Integer(), nullable=False),
        sa.Column("receipt", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "project_id", "wp_id", name="uq_requirement_delivery_wp"),
    )
    op.create_index(
        "ix_requirement_delivery_handoffs_company_id",
        "requirement_delivery_handoffs",
        ["company_id"],
    )
    op.create_table(
        "control_plane_audit_retention_tombstones",
        sa.Column("audit_event_id", sa.String(48), primary_key=True),
        sa.Column("company_id", sa.String(48), nullable=False),
        sa.Column("idempotency_hash", sa.String(64), nullable=True),
        sa.Column("receipt", sa.JSON(), nullable=False),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_control_plane_audit_retention_tombstones_company_id",
        "control_plane_audit_retention_tombstones",
        ["company_id"],
    )
    op.create_index(
        "uq_control_audit_retention_key",
        "control_plane_audit_retention_tombstones",
        ["company_id", "idempotency_hash"],
        unique=True,
    )
    op.create_table(
        "control_plane_retention_runs",
        sa.Column("company_id", sa.String(48), primary_key=True),
        sa.Column("request_id", sa.String(48), primary_key=True),
        sa.Column("command_hash", sa.String(64), nullable=False),
        sa.Column("receipt", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_control_artifact_audit_pins ON control_plane_artifacts USING gin ((CAST(metadata -> 'evidence' -> 'audit_events' AS jsonb)))"
        )


def downgrade():
    tables = (
        "requirement_delivery_handoffs",
        "control_plane_audit_retention_tombstones",
        "control_plane_retention_runs",
    )
    for table in tables:
        if op.get_bind().scalar(sa.text(f'SELECT COUNT(*) FROM "{table}"')):
            raise RuntimeError("Delivery/retention downgrade requires empty durable receipt tables")
    if op.get_bind().dialect.name == "postgresql":
        op.drop_index("ix_control_artifact_audit_pins", table_name="control_plane_artifacts")
    for table in reversed(tables):
        op.drop_table(table)
