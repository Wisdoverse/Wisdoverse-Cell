"""Add QA run idempotency index.

Revision ID: 20260504_qa_run_idempotency
Revises: 20260503_agentrole_events
Create Date: 2026-05-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260504_qa_run_idempotency"
down_revision: str | None = "20260503_agentrole_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = 'qa_acceptance_runs'
            ) THEN
                BEGIN
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_qa_runs_trigger_event_id
                    ON qa_acceptance_runs (trigger_event_id)
                    WHERE trigger_event_id IS NOT NULL;
                EXCEPTION
                    WHEN undefined_table THEN
                        NULL;
                END;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_qa_runs_trigger_event_id")
