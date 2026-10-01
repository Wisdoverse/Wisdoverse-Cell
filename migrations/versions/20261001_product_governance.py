"""Frozen product governance, evaluation, knowledge and skill-release ledger.

Only the existing shared migration chain is active; runtime cutovers remain gated.
"""

from alembic import op

revision = "20261001_product_governance"
down_revision = "20260527_identity_event_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE control_plane_company_template_names (
            normalized_name VARCHAR(256) NOT NULL,
            company_id VARCHAR(48) NOT NULL,
            PRIMARY KEY (normalized_name),
            UNIQUE (company_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE control_plane_knowledge_tombstones (
            knowledge_id VARCHAR(64) NOT NULL,
            company_id VARCHAR(48) NOT NULL,
            actor_id VARCHAR(128) NOT NULL,
            version INTEGER NOT NULL,
            deleted_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (knowledge_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_control_plane_knowledge_tombstones_company_id ON control_plane_knowledge_tombstones (company_id)"
    )
    op.execute(
        """
        CREATE TABLE control_plane_execution_leases (
            execution_id VARCHAR(64) NOT NULL,
            company_id VARCHAR(48) NOT NULL,
            resource_id VARCHAR(128) NOT NULL,
            intent_hash VARCHAR(64) NOT NULL,
            run_id VARCHAR(48) NOT NULL,
            owner_id VARCHAR(48) NOT NULL,
            state VARCHAR(32) NOT NULL,
            control_action VARCHAR(16) NOT NULL,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (execution_id),
            CONSTRAINT ck_execution_state CHECK (state IN ('running','recovery_required','succeeded','failed')),
            CONSTRAINT ck_execution_control CHECK (control_action IN ('pause','resume','terminate')),
            FOREIGN KEY(company_id) REFERENCES control_plane_companies (company_id),
            UNIQUE (run_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_control_plane_execution_leases_company_id ON control_plane_execution_leases (company_id)"
    )
    op.execute(
        "CREATE INDEX ix_control_plane_execution_leases_resource_id ON control_plane_execution_leases (resource_id)"
    )
    op.execute(
        "CREATE INDEX ix_control_plane_execution_leases_state ON control_plane_execution_leases (state)"
    )
    op.execute(
        "CREATE INDEX ix_execution_resource_state ON control_plane_execution_leases (company_id, resource_id, state)"
    )
    op.execute(
        """
        CREATE TABLE control_plane_execution_reservations (
            execution_id VARCHAR(64) NOT NULL,
            budget_id VARCHAR(48) NOT NULL,
            amount_usd NUMERIC(18, 6) NOT NULL,
            state VARCHAR(32) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (execution_id, budget_id),
            CONSTRAINT ck_execution_reservation_amount CHECK (amount_usd >= 0),
            CONSTRAINT ck_execution_reservation_state CHECK (state IN ('reserved','settled')),
            CONSTRAINT uq_execution_budget UNIQUE (execution_id, budget_id),
            FOREIGN KEY(execution_id) REFERENCES control_plane_execution_leases (execution_id),
            FOREIGN KEY(budget_id) REFERENCES control_plane_budget_policies (budget_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_control_plane_execution_reservations_state ON control_plane_execution_reservations (state)"
    )
    op.execute(
        """
        CREATE TABLE control_plane_knowledge (
            knowledge_id VARCHAR(64) NOT NULL,
            company_id VARCHAR(48) NOT NULL,
            source_artifact_id VARCHAR(48) NOT NULL,
            source_company_id VARCHAR(48) NOT NULL,
            owner_actor_id VARCHAR(128) NOT NULL,
            reader_role_ids JSON NOT NULL,
            version INTEGER NOT NULL,
            retention_until TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            deleted_at TIMESTAMP WITH TIME ZONE,
            deleted_by_actor_id VARCHAR(128),
            PRIMARY KEY (knowledge_id),
            FOREIGN KEY(company_id) REFERENCES control_plane_companies (company_id),
            FOREIGN KEY(source_artifact_id) REFERENCES control_plane_artifacts (artifact_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_control_knowledge_company_access ON control_plane_knowledge (company_id, deleted_at, retention_until)"
    )
    op.execute(
        """
        CREATE TABLE control_plane_outcome_acceptances (
            acceptance_id VARCHAR(48) NOT NULL,
            company_id VARCHAR(48) NOT NULL,
            work_item_id VARCHAR(48) NOT NULL,
            artifact_id VARCHAR(48) NOT NULL,
            run_id VARCHAR(48) NOT NULL,
            artifact_hash VARCHAR(128) NOT NULL,
            verdict VARCHAR(16) NOT NULL,
            actor_id VARCHAR(128) NOT NULL,
            reason TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (acceptance_id),
            FOREIGN KEY(company_id) REFERENCES control_plane_companies (company_id),
            FOREIGN KEY(work_item_id) REFERENCES control_plane_work_items (work_item_id),
            FOREIGN KEY(artifact_id) REFERENCES control_plane_artifacts (artifact_id),
            FOREIGN KEY(run_id) REFERENCES control_plane_agent_runs (run_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_control_plane_outcome_acceptances_company_id ON control_plane_outcome_acceptances (company_id)"
    )
    op.execute(
        "CREATE INDEX ix_control_plane_outcome_acceptances_work_item_id ON control_plane_outcome_acceptances (work_item_id)"
    )
    op.execute(
        """
        CREATE TABLE control_plane_evolution_evaluations (
            evaluation_report_id VARCHAR(48) NOT NULL,
            company_id VARCHAR(48) NOT NULL,
            proposal_id VARCHAR(48) NOT NULL,
            baseline_skill_version_id VARCHAR(200) NOT NULL,
            candidate_skill_version_id VARCHAR(200) NOT NULL,
            dataset_revision VARCHAR(200) NOT NULL,
            baseline_batch_hash VARCHAR(64) NOT NULL,
            candidate_batch_hash VARCHAR(64) NOT NULL,
            baseline_batch JSON NOT NULL,
            candidate_batch JSON NOT NULL,
            policy JSON NOT NULL,
            comparison_report JSON NOT NULL,
            evaluator_version VARCHAR(128) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (evaluation_report_id),
            FOREIGN KEY(company_id) REFERENCES control_plane_companies (company_id),
            FOREIGN KEY(proposal_id) REFERENCES control_plane_evolution_proposals (proposal_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_control_evaluations_company_proposal_created ON control_plane_evolution_evaluations (company_id, proposal_id, created_at)"
    )
    op.execute(
        """
        CREATE TABLE control_plane_evolution_deployments (
            deployment_id VARCHAR(64) NOT NULL,
            company_id VARCHAR(48) NOT NULL,
            proposal_id VARCHAR(48) NOT NULL,
            evaluation_report_id VARCHAR(48) NOT NULL,
            state VARCHAR(32) NOT NULL,
            desired_action VARCHAR(16) NOT NULL,
            command JSON NOT NULL,
            acknowledgement JSON NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (deployment_id),
            FOREIGN KEY(company_id) REFERENCES control_plane_companies (company_id),
            UNIQUE (proposal_id),
            FOREIGN KEY(proposal_id) REFERENCES control_plane_evolution_proposals (proposal_id),
            FOREIGN KEY(evaluation_report_id) REFERENCES control_plane_evolution_evaluations (evaluation_report_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_control_plane_evolution_deployments_company_id ON control_plane_evolution_deployments (company_id)"
    )
    op.execute(
        """
        CREATE TABLE evolution_skill_release_commands (
            command_id VARCHAR(64) NOT NULL,
            deployment_id VARCHAR(64) NOT NULL,
            payload_hash VARCHAR(64) NOT NULL,
            response JSON NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (command_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_evolution_skill_release_commands_deployment_id ON evolution_skill_release_commands (deployment_id)"
    )
    op.execute(
        """
        CREATE TABLE evolution_skill_releases (
            deployment_id VARCHAR(64) NOT NULL,
            company_id VARCHAR(48) NOT NULL,
            proposal_id VARCHAR(48) NOT NULL,
            evaluation_report_id VARCHAR(48) NOT NULL,
            evaluation_hash VARCHAR(64) NOT NULL,
            skill_id VARCHAR(128) NOT NULL,
            agent_id VARCHAR(64) NOT NULL,
            baseline_version INTEGER NOT NULL,
            candidate_version INTEGER NOT NULL,
            baseline_config_hash VARCHAR(64) NOT NULL,
            candidate_config_hash VARCHAR(64) NOT NULL,
            state VARCHAR(20) NOT NULL,
            version INTEGER NOT NULL,
            experiment_id VARCHAR(64),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (deployment_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_evolution_skill_releases_agent_id ON evolution_skill_releases (agent_id)"
    )
    op.execute(
        "CREATE INDEX ix_evolution_skill_releases_company_id ON evolution_skill_releases (company_id)"
    )
    op.execute(
        "CREATE INDEX ix_evolution_skill_releases_skill_id ON evolution_skill_releases (skill_id)"
    )


def downgrade() -> None:
    op.drop_table("evolution_skill_releases")
    op.drop_table("evolution_skill_release_commands")
    op.drop_table("control_plane_evolution_deployments")
    op.drop_table("control_plane_evolution_evaluations")
    op.drop_table("control_plane_outcome_acceptances")
    op.drop_table("control_plane_knowledge")
    op.drop_table("control_plane_execution_reservations")
    op.drop_table("control_plane_execution_leases")
    op.drop_table("control_plane_knowledge_tombstones")
    op.drop_table("control_plane_company_template_names")
