"""Add AgentRole event contract fields.

Revision ID: 20260503_agentrole_events
Revises: 20260502_reqmgr_tables
Create Date: 2026-05-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260503_agentrole_events"
down_revision: str | None = "20260502_reqmgr_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "control_plane_agent_roles",
        sa.Column(
            "subscribed_events",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "control_plane_agent_roles",
        sa.Column(
            "published_events",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("control_plane_agent_roles", "published_events")
    op.drop_column("control_plane_agent_roles", "subscribed_events")
