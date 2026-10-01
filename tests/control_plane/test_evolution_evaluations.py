"""Tests for immutable proposal-linked evolution evaluation reports."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.api_routes.evolution_evaluations import (
    create_evolution_evaluation_router,
)
from shared.control_plane.company_store import SqlAlchemyControlPlaneCompanyStore
from shared.control_plane.evolution_evaluation_models import EvolutionEvaluationReportTable
from shared.control_plane.evolution_evaluation_store import (
    SqlAlchemyControlPlaneEvolutionEvaluationStore,
)
from shared.control_plane.evolution_evaluation_use_cases import (
    EvolutionEvaluationCompatibilityError,
    EvolutionEvaluationProposalNotFoundError,
    list_evaluation_comparisons,
    record_evaluation_comparison,
)
from shared.control_plane.evolution_proposal_store import (
    SqlAlchemyControlPlaneEvolutionProposalStore,
)
from shared.control_plane.models import (
    AuditEvent,
    CompanyContext,
    EvolutionProposal,
    EvolutionTier,
)
from shared.control_plane.tables import AuditEventTable
from shared.evolution.evaluation_batch import (
    EvalCase,
    EvalResult,
    EvaluationBatch,
    EvaluationPolicy,
)


def _batch(
    *,
    evaluation_id: str,
    config_revision: str,
    cost: float = 1.0,
    budget_usd: float = 10.0,
    dataset_revision: str = "dataset-v1",
    case_revision: str = "1",
) -> EvaluationBatch:
    return EvaluationBatch(
        evaluation_id=evaluation_id,
        dataset_revision=dataset_revision,
        config_revision=config_revision,
        budget_usd=budget_usd,
        cases=(EvalCase(case_id="case-1", case_revision=case_revision),),
        results=(
            EvalResult(
                result_id=f"result-{evaluation_id}",
                case_id="case-1",
                config_revision=config_revision,
                accepted=True,
                quality=0.9,
                total_attempt_cost_usd=cost,
                latency_ms=100,
                human_interventions=0,
            ),
        ),
    )


def _policy() -> EvaluationPolicy:
    return EvaluationPolicy(maximum_cost_per_accepted_outcome_usd=5)


async def _create_proposal(session: AsyncSession, company_id: str) -> EvolutionProposal:
    await SqlAlchemyControlPlaneCompanyStore(session).create_company(
        CompanyContext(company_id=company_id, name="Evaluation Test Co")
    )
    return await SqlAlchemyControlPlaneEvolutionProposalStore(session).create_evolution_proposal(
        EvolutionProposal(
            proposal_id="evo_eval_test",
            company_id=company_id,
            tier=EvolutionTier.L1,
            scope="agent:test-agent/skill:test-skill",
            expected_benefit="Improve accepted quality",
            risk="Candidate can regress quality",
        )
    )


@pytest.mark.asyncio
async def test_store_persists_immutable_snapshot_and_audit_link(db_session: AsyncSession) -> None:
    proposal = await _create_proposal(db_session, "cmp_eval_test")
    store = SqlAlchemyControlPlaneEvolutionEvaluationStore(db_session)

    report = await record_evaluation_comparison(
        store,
        company_id=proposal.company_id,
        proposal_id=proposal.proposal_id,
        baseline=_batch(evaluation_id="baseline-1", config_revision="skill-v1"),
        candidate=_batch(evaluation_id="candidate-1", config_revision="skill-v2", cost=1.5),
        policy=_policy(),
        actor_id="reviewer",
    )
    await db_session.commit()

    listed = await list_evaluation_comparisons(
        store, company_id=proposal.company_id, proposal_id=proposal.proposal_id
    )
    persisted_row = await db_session.get(
        EvolutionEvaluationReportTable, report.evaluation_report_id
    )
    audit_result = await db_session.execute(
        select(AuditEventTable).where(AuditEventTable.target_id == report.evaluation_report_id)
    )
    audit = audit_result.scalar_one()

    assert len(listed) == 1
    assert listed[0].baseline_skill_version_id == "skill-v1"
    assert listed[0].candidate_skill_version_id == "skill-v2"
    assert listed[0].evaluator_version == "fixed-case-evaluation-v1"
    assert len(listed[0].baseline_batch_hash) == 64
    assert persisted_row is not None
    assert audit.action == "evolution_evaluation.recorded"
    assert audit.detail["proposal_id"] == proposal.proposal_id
    assert audit.detail["evaluation_report_id"] == report.evaluation_report_id
    persisted_row.policy = {"mutated": True}
    with pytest.raises(ValueError, match="reports are immutable"):
        await db_session.flush()


@pytest.mark.asyncio
async def test_company_mismatch_is_rejected_before_report_write(db_session: AsyncSession) -> None:
    proposal = await _create_proposal(db_session, "cmp_eval_test")
    store = SqlAlchemyControlPlaneEvolutionEvaluationStore(db_session)

    with pytest.raises(EvolutionEvaluationProposalNotFoundError):
        await record_evaluation_comparison(
            store,
            company_id="cmp_other_company",
            proposal_id=proposal.proposal_id,
            baseline=_batch(evaluation_id="baseline-1", config_revision="skill-v1"),
            candidate=_batch(evaluation_id="candidate-1", config_revision="skill-v2"),
            policy=_policy(),
        )

    assert (
        await store.list_evaluation_reports(
            company_id="cmp_eval_test", proposal_id=proposal.proposal_id
        )
        == []
    )


@pytest.mark.parametrize(
    "baseline_kwargs,candidate_kwargs",
    [
        ({}, {"budget_usd": 9.0}),
        ({}, {"case_revision": "2"}),
        ({}, {"dataset_revision": "dataset-v2"}),
    ],
)
@pytest.mark.asyncio
async def test_incompatible_arms_are_rejected_before_write(
    db_session: AsyncSession,
    baseline_kwargs: dict,
    candidate_kwargs: dict,
) -> None:
    proposal = await _create_proposal(db_session, "cmp_eval_test")
    store = SqlAlchemyControlPlaneEvolutionEvaluationStore(db_session)

    with pytest.raises(EvolutionEvaluationCompatibilityError):
        await record_evaluation_comparison(
            store,
            company_id=proposal.company_id,
            proposal_id=proposal.proposal_id,
            baseline=_batch(
                evaluation_id="baseline-1",
                config_revision="skill-v1",
                **baseline_kwargs,
            ),
            candidate=_batch(
                evaluation_id="candidate-1",
                config_revision="skill-v2",
                **candidate_kwargs,
            ),
            policy=_policy(),
        )

    assert (
        await store.list_evaluation_reports(
            company_id=proposal.company_id, proposal_id=proposal.proposal_id
        )
        == []
    )


def test_api_post_and_get_expose_fixed_case_reports() -> None:
    proposal = EvolutionProposal(
        proposal_id="evo_api_test",
        company_id="cmp_api_test",
        tier=EvolutionTier.L1,
        scope="agent:test-agent/skill:test-skill",
        expected_benefit="Improve accepted quality",
        risk="Candidate can regress quality",
    )

    class FakeStore:
        reports = []
        audits: list[AuditEvent] = []

        async def get_evolution_proposal(self, proposal_id: str):
            return proposal if proposal_id == proposal.proposal_id else None

        async def create_evaluation_report(self, report):
            self.reports.append(report)
            return report

        async def list_evaluation_reports(self, *, company_id: str, proposal_id: str):
            return list(self.reports)

        async def append_audit_event(self, event: AuditEvent):
            self.audits.append(event)
            return event

    class FakeUnitOfWork:
        committed = False

        async def commit(self):
            self.committed = True

    store = FakeStore()
    uow = FakeUnitOfWork()

    async def get_store() -> AsyncGenerator[FakeStore, None]:
        yield store

    async def get_uow() -> AsyncGenerator[FakeUnitOfWork, None]:
        yield uow

    app = FastAPI()
    app.include_router(
        create_evolution_evaluation_router(
            get_store=get_store,
            get_uow=get_uow,
            resolve_company=lambda company_id: company_id or "cmp_api_test",
        ),
        prefix="/api/v1/control-plane",
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/control-plane/evolution-proposals/evo_api_test/evaluations",
            json={
                "company_id": "cmp_api_test",
                "baseline": _batch(
                    evaluation_id="baseline-api", config_revision="skill-v1"
                ).model_dump(mode="json"),
                "candidate": _batch(
                    evaluation_id="candidate-api", config_revision="skill-v2"
                ).model_dump(mode="json"),
                "policy": _policy().model_dump(mode="json"),
            },
        )
        listed = client.get("/api/v1/control-plane/evolution-proposals/evo_api_test/evaluations")

    assert response.status_code == 201
    assert response.json()["proposal_id"] == proposal.proposal_id
    assert response.json()["comparison_report"]["is_live_model_benchmark"] is False
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["report_kind"] == "fixed_evaluation_case_comparison"
    assert uow.committed
    assert store.audits[0].target_id == response.json()["evaluation_report_id"]
