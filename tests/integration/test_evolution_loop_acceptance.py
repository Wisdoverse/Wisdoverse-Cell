"""Synthetic acceptance of the durable L1 evidence-to-release loop.

This exercises the Control Plane and evolution runtime SQL stores together. The
50 paired cases are fixed fixtures; no model/provider call is made or implied.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.config import settings
from shared.control_plane.approval_store import SqlAlchemyControlPlaneApprovalStore
from shared.control_plane.domain.execution_policy import ExecutionDenied
from shared.control_plane.evolution_deployment_models import EvolutionDeploymentTable
from shared.control_plane.evolution_deployment_store import SqlAlchemyEvolutionDeploymentStore
from shared.control_plane.evolution_evaluation_store import (
    SqlAlchemyControlPlaneEvolutionEvaluationStore,
)
from shared.control_plane.evolution_evaluation_use_cases import record_evaluation_comparison
from shared.control_plane.evolution_proposal_store import (
    SqlAlchemyControlPlaneEvolutionProposalStore,
)
from shared.control_plane.models import (
    ApprovalStatus,
    CompanyContext,
    EvolutionProposal,
    EvolutionTier,
)
from shared.control_plane.tables import (
    ApprovalRequestTable,
    AuditEventTable,
    control_plane_metadata,
)
from shared.evolution.db.release_store import SqlAlchemySkillReleaseStore
from shared.evolution.db.release_tables import EvolutionSkillRelease
from shared.evolution.db.repository import EvolutionRepository
from shared.evolution.db.tables import (
    EvolutionExperiment,
    EvolutionSkillConfig,
    evolution_metadata,
)
from shared.evolution.evaluation_batch import (
    EvalCase,
    EvalResult,
    EvaluationBatch,
    EvaluationPolicy,
)
from shared.evolution.release_contract import skill_config_hash


@asynccontextmanager
async def _postgres_schema_factory() -> AsyncIterator[
    tuple[async_sessionmaker[AsyncSession], async_sessionmaker[AsyncSession]]
]:
    raw_url = os.getenv("TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("Set TEST_DATABASE_URL for PostgreSQL evolution loop acceptance")
    url = make_url(raw_url)
    if not url.drivername.startswith("postgresql"):
        pytest.skip("TEST_DATABASE_URL must use PostgreSQL for isolated-schema acceptance")
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+asyncpg")

    schema = f"test_evolution_loop_{uuid4().hex}"
    root_engine = create_async_engine(url)
    async with root_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped_engine = root_engine.execution_options(schema_translate_map={None: schema})
    try:
        async with scoped_engine.begin() as connection:
            await connection.run_sync(control_plane_metadata.create_all)
            await connection.run_sync(evolution_metadata.create_all)
        yield (
            async_sessionmaker(scoped_engine, expire_on_commit=False),
            async_sessionmaker(scoped_engine, expire_on_commit=False),
        )
    finally:
        async with scoped_engine.begin() as connection:
            await connection.run_sync(evolution_metadata.drop_all)
            await connection.run_sync(control_plane_metadata.drop_all)
        async with root_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await root_engine.dispose()


def _batch(evaluation_id: str, revision: str, quality: float) -> EvaluationBatch:
    cases = tuple(EvalCase(case_id=f"frozen-{index:02d}", case_revision="frozen-v1") for index in range(50))
    results = tuple(
        EvalResult(
            result_id=f"{evaluation_id}-{index:02d}",
            case_id=case.case_id,
            config_revision=revision,
            accepted=True,
            quality=quality,
            total_attempt_cost_usd=0.02,
            latency_ms=100,
            human_interventions=0,
        )
        for index, case in enumerate(cases)
    )
    return EvaluationBatch(
        evaluation_id=evaluation_id,
        dataset_revision="frozen-dataset-v1",
        config_revision=revision,
        budget_usd=5,
        cases=cases,
        results=results,
    )


def _skill(version: int, status: str, prompt: str) -> EvolutionSkillConfig:
    return EvolutionSkillConfig(
        skill_id="acceptance-editor",
        version=str(version),
        status=status,
        system_prompt=prompt,
        parameters={"temperature": 0},
        few_shot_examples=[{"input": "fixture", "output": "deterministic"}],
        output_format="json",
        target_model="synthetic-fixture",
    )


@pytest.mark.asyncio
async def test_synthetic_50_case_evolution_release_and_regression_rollback() -> None:
    async with _postgres_schema_factory() as (control_plane_factory, evolution_factory):
        company_id = settings.control_plane_company_id
        proposal_id = f"evo_accept_{uuid4().hex[:12]}"
        skill_id = "acceptance-editor"
        actor = "synthetic-acceptance-operator"

        async with control_plane_factory() as control_session:
            proposals = SqlAlchemyControlPlaneEvolutionProposalStore(control_session)
            await proposals.create_company(CompanyContext(company_id=company_id, name="Acceptance"))
            proposal = await proposals.create_evolution_proposal(
                EvolutionProposal(
                    proposal_id=proposal_id,
                    company_id=company_id,
                    tier=EvolutionTier.L1,
                    scope=f"agent:writer/skill:{skill_id}",
                    expected_benefit="Improve deterministic fixture quality",
                    risk="Synthetic regression may require restoring baseline",
                )
            )
            report = await record_evaluation_comparison(
                SqlAlchemyControlPlaneEvolutionEvaluationStore(control_session),
                company_id=company_id,
                proposal_id=proposal.proposal_id,
                baseline=_batch(f"{proposal_id}-base", f"{skill_id}@1", 0.80),
                candidate=_batch(f"{proposal_id}-candidate", f"{skill_id}@2", 0.92),
                policy=EvaluationPolicy(
                    minimum_sample_count=50,
                    minimum_candidate_accepted_quality=0.70,
                    maximum_cost_per_accepted_outcome_usd=1.0,
                ),
                actor_id=actor,
            )
            await control_session.commit()

            baseline = _skill(1, "active", "baseline frozen prompt")
            candidate = _skill(2, "candidate", "candidate frozen prompt")
            async with evolution_factory() as evolution_session:
                evolution_session.add_all([baseline, candidate])
                await evolution_session.commit()

                async def apply_and_ack(action: str) -> dict:
                    deployment_store = SqlAlchemyEvolutionDeploymentStore(control_session)
                    try:
                        await deployment_store.prepare(
                            company_id=company_id,
                            proposal_id=proposal_id,
                            evaluation_report_id=report.evaluation_report_id,
                            skill_id=skill_id,
                            agent_id="writer",
                            baseline_version=1,
                            candidate_version=2,
                            baseline_config_hash=skill_config_hash(baseline),
                            candidate_config_hash=skill_config_hash(candidate),
                            action=action,
                            actor_id=actor,
                        )
                    except ExecutionDenied as exc:
                        if "skill_release_approval_required" not in str(exc):
                            raise
                        pending = await control_session.scalar(
                            select(ApprovalRequestTable).where(
                                ApprovalRequestTable.company_id == company_id,
                                ApprovalRequestTable.metadata_json["action"].as_string() == action,
                            ).order_by(ApprovalRequestTable.created_at.desc())
                        )
                        assert pending is not None and pending.status == "pending"
                        await SqlAlchemyControlPlaneApprovalStore(control_session).resolve_approval(
                            pending.approval_id,
                            status=ApprovalStatus.APPROVED,
                            resolved_by="synthetic-review-board",
                        )
                        await control_session.commit()
                    command = await deployment_store.prepare(
                        company_id=company_id,
                        proposal_id=proposal_id,
                        evaluation_report_id=report.evaluation_report_id,
                        skill_id=skill_id,
                        agent_id="writer",
                        baseline_version=1,
                        candidate_version=2,
                        baseline_config_hash=skill_config_hash(baseline),
                        candidate_config_hash=skill_config_hash(candidate),
                        action=action,
                        actor_id=actor,
                    )
                    response = await SqlAlchemySkillReleaseStore(evolution_session).apply(command)
                    await evolution_session.commit()
                    await deployment_store.acknowledge(command, response, actor_id=actor)
                    await control_session.commit()
                    return response

                shadow = await apply_and_ack("shadow")
                assert shadow["state"] == "shadow"
                canary = await apply_and_ack("canary")
                assert canary["state"] == "canary"

                # Simulated observations pass the canary gate, permitting the
                # synthetic promotion. This is fixed data, not a live experiment.
                experiment = await evolution_session.scalar(
                    select(EvolutionExperiment).where(
                        EvolutionExperiment.experiment_id == canary["experiment_id"]
                    )
                )
                assert experiment is not None
                experiment.control_results = [0.80] * 50
                experiment.candidate_results = [0.92] * 50
                await evolution_session.commit()
                promoted = await apply_and_ack("promote")
                assert promoted["state"] == "active"

                # Inject a post-promotion regression observation, then apply the
                # approved rollback command. The frozen baseline row is restored.
                experiment = await evolution_session.scalar(
                    select(EvolutionExperiment).where(
                        EvolutionExperiment.experiment_id == canary["experiment_id"]
                    )
                )
                assert experiment is not None
                experiment.control_results = [0.80] * 50
                experiment.candidate_results = [0.20] * 50
                await evolution_session.commit()
                rolled_back = await apply_and_ack("rollback")
                assert rolled_back["state"] == "rolled_back"

                restored = await EvolutionRepository(evolution_session).get_active_skill(skill_id)
                retired_candidate = await EvolutionRepository(evolution_session).get_skill_by_version(
                    skill_id, "2"
                )
                release = await evolution_session.get(EvolutionSkillRelease, promoted["deployment_id"])
                assert restored is not None
                assert (restored.version, restored.system_prompt, restored.parameters) == (
                    "1",
                    "baseline frozen prompt",
                    {"temperature": 0},
                )
                assert retired_candidate is not None and retired_candidate.status == "retired"
                assert release is not None and release.state == "rolled_back"

            audit_rows = (
                await control_session.scalars(
                    select(AuditEventTable).where(
                        AuditEventTable.target_id == proposal_id,
                        AuditEventTable.action == "evolution.release_applied",
                    )
                )
            ).all()
            assert len(audit_rows) == 4
            assert all(row.detail.get("deployment_id") == shadow["deployment_id"] for row in audit_rows)
            deployment = await control_session.scalar(
                select(EvolutionDeploymentTable).where(
                    EvolutionDeploymentTable.deployment_id == shadow["deployment_id"]
                )
            )
            assert deployment is not None
            assert deployment.state == "rolled_back"
            assert deployment.evaluation_report_id == report.evaluation_report_id
            requested = await control_session.scalar(
                select(AuditEventTable).where(
                    AuditEventTable.target_id == proposal_id,
                    AuditEventTable.action == "evolution.release_requested",
                ).order_by(AuditEventTable.created_at.desc())
            )
            assert requested is not None
            assert requested.detail["evaluation_report_id"] == report.evaluation_report_id
