"""Allow PJM decomposition write lifecycle statuses.

Revision ID: 20260504_pjm_decomp_statuses
Revises: 20260504_qa_run_idempotency
Create Date: 2026-05-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260504_pjm_decomp_statuses"
down_revision: str | None = "20260504_qa_run_idempotency"
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
                  AND table_name = 'pjm_agent_decomposition_records'
            ) THEN
                BEGIN
                    ALTER TABLE pjm_agent_decomposition_records
                        DROP CONSTRAINT IF EXISTS ck_decompose_status;
                    ALTER TABLE pjm_agent_decomposition_records
                        ADD CONSTRAINT ck_decompose_status
                        CHECK (
                            status IN (
                                'pending',
                                'writing',
                                'approved',
                                'rejected',
                                'failed',
                                'write_failed'
                            )
                        );
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
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = 'pjm_agent_decomposition_records'
            ) THEN
                BEGIN
                    ALTER TABLE pjm_agent_decomposition_records
                        DROP CONSTRAINT IF EXISTS ck_decompose_status;
                    ALTER TABLE pjm_agent_decomposition_records
                        ADD CONSTRAINT ck_decompose_status
                        CHECK (status IN ('pending', 'approved', 'rejected', 'failed'));
                EXCEPTION
                    WHEN undefined_table THEN
                        NULL;
                END;
            END IF;
        END
        $$;
        """
    )
