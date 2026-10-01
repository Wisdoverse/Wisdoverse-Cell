"""Durable, evidence-bound L1 evolution release lifecycle tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.approval_store import SqlAlchemyControlPlaneApprovalStore
from shared.control_plane.domain.execution_policy import ExecutionDenied
from shared.control_plane.evolution_deployment_gateway import HttpEvolutionDeploymentGateway
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
from shared.control_plane.tables import ApprovalRequestTable, AuditEventTable
from shared.evolution.evaluation_batch import (
    EvalCase,
    EvalResult,
    EvaluationBatch,
    EvaluationPolicy,
)


def _batch(
    *, evaluation_id: str, revision: str, quality: float, cases: int = 50
) -> EvaluationBatch:
    case_list = tuple(
        EvalCase(case_id=f"case-{index}", case_revision="1") for index in range(cases)
    )
    results = tuple(
        EvalResult(
            result_id=f"{evaluation_id}-result-{index}",
            case_id=f"case-{index}",
            config_revision=revision,
            accepted=True,
            quality=quality,
            total_attempt_cost_usd=0.01,
            latency_ms=100,
            human_interventions=0,
        )
        for index in range(cases)
    )
    return EvaluationBatch(
        evaluation_id=evaluation_id,
        dataset_revision="fixed-v1",
        config_revision=revision,
        budget_usd=10,
        cases=case_list,
        results=results,
    )


async def _seed_release(
    session: AsyncSession,
    *,
    company_id: str = "cmp_release",
    proposal_id: str = "evo_release",
    tier: EvolutionTier = EvolutionTier.L1,
    cases: int = 50,
    candidate_quality: float = 0.9,
) -> str:
    proposals = SqlAlchemyControlPlaneEvolutionProposalStore(session)
    await proposals.create_company(CompanyContext(company_id=company_id, name="Release Test"))
    proposal = await proposals.create_evolution_proposal(
        EvolutionProposal(
            proposal_id=proposal_id,
            company_id=company_id,
            tier=tier,
            scope="agent:writer/skill:editor",
            expected_benefit="Improve accepted quality",
            risk="Candidate may regress output quality",
        )
    )
    report = await record_evaluation_comparison(
        SqlAlchemyControlPlaneEvolutionEvaluationStore(session),
        company_id=company_id,
        proposal_id=proposal.proposal_id,
        baseline=_batch(
            evaluation_id=f"{proposal_id}-baseline", revision="editor@1", quality=0.8, cases=cases
        ),
        candidate=_batch(
            evaluation_id=f"{proposal_id}-candidate",
            revision="editor@2",
            quality=candidate_quality,
            cases=cases,
        ),
        policy=EvaluationPolicy(
            minimum_sample_count=1,
            minimum_candidate_accepted_quality=0.7,
            maximum_cost_per_accepted_outcome_usd=1,
        ),
        actor_id="test-reviewer",
    )
    return report.evaluation_report_id


def _release_kwargs(report_id: str, *, action: str = "shadow") -> dict:
    return {
        "company_id": "cmp_release",
        "proposal_id": "evo_release",
        "evaluation_report_id": report_id,
        "skill_id": "editor",
        "agent_id": "writer",
        "baseline_version": 1,
        "candidate_version": 2,
        "baseline_config_hash": "a" * 64,
        "candidate_config_hash": "b" * 64,
        "action": action,
        "actor_id": "release-operator",
    }


@pytest.mark.asyncio
async def test_shadow_prepare_checkpoint_and_ack_link_durable_proposal(
    db_session: AsyncSession,
) -> None:
    report_id = await _seed_release(db_session)
    store = SqlAlchemyEvolutionDeploymentStore(db_session)

    command = await store.prepare(**_release_kwargs(report_id))
    await store.checkpoint()
    persisted = await db_session.get(EvolutionDeploymentTable, command.deployment_id)
    assert persisted is not None
    assert persisted.state == "pending"
    assert persisted.command["command_id"] == command.command_id

    response = {"deployment_id": command.deployment_id, "state": "shadow", "active_version": 1}
    await store.acknowledge(command, response, actor_id="release-operator")
    await db_session.commit()

    proposal = await SqlAlchemyControlPlaneEvolutionProposalStore(
        db_session
    ).get_evolution_proposal("evo_release")
    persisted = await db_session.get(EvolutionDeploymentTable, command.deployment_id)
    assert proposal is not None
    assert proposal.rollout_state == "shadow"
    assert proposal.metadata["evaluation_report_id"] == report_id
    assert persisted is not None and persisted.acknowledgement == response


@pytest.mark.asyncio
async def test_canary_and_promotion_need_distinct_bound_approvals(db_session: AsyncSession) -> None:
    report_id = await _seed_release(db_session)
    store = SqlAlchemyEvolutionDeploymentStore(db_session)
    shadow = await store.prepare(**_release_kwargs(report_id))
    await store.acknowledge(
        shadow,
        {"deployment_id": shadow.deployment_id, "state": "shadow"},
        actor_id="release-operator",
    )
    await db_session.commit()

    with pytest.raises(ExecutionDenied, match="skill_release_approval_required"):
        await store.prepare(**_release_kwargs(report_id, action="canary"))
    canary_approval = (
        await db_session.scalars(
            select(ApprovalRequestTable).where(ApprovalRequestTable.company_id == "cmp_release")
        )
    ).one()
    assert canary_approval.status == "pending"
    assert canary_approval.metadata_json["action"] == "canary"
    assert canary_approval.metadata_json["release_snapshot"]["evaluation_report_id"] == report_id

    approvals = SqlAlchemyControlPlaneApprovalStore(db_session)
    await approvals.resolve_approval(
        canary_approval.approval_id, status=ApprovalStatus.APPROVED, resolved_by="board"
    )
    canary = await store.prepare(**_release_kwargs(report_id, action="canary"))
    assert canary.approval_id == canary_approval.approval_id
    await store.acknowledge(
        canary,
        {"deployment_id": canary.deployment_id, "state": "canary", "experiment_id": "exp-1"},
        actor_id="release-operator",
    )
    await db_session.commit()

    with pytest.raises(ExecutionDenied, match="skill_release_approval_required"):
        await store.prepare(**_release_kwargs(report_id, action="promote"))
    promotion = (
        await db_session.scalars(
            select(ApprovalRequestTable).where(
                ApprovalRequestTable.company_id == "cmp_release",
                ApprovalRequestTable.metadata_json["action"].as_string() == "promote",
            )
        )
    ).one()
    assert promotion.status == "pending"
    assert promotion.approval_id != canary_approval.approval_id


@pytest.mark.asyncio
async def test_frozen_configuration_and_report_cannot_change_after_prepare(
    db_session: AsyncSession,
) -> None:
    report_id = await _seed_release(db_session)
    store = SqlAlchemyEvolutionDeploymentStore(db_session)
    command = await store.prepare(**_release_kwargs(report_id))
    changed_config = _release_kwargs(report_id)
    changed_config["candidate_config_hash"] = "c" * 64
    with pytest.raises(ExecutionDenied, match="frozen_release_configuration_changed"):
        await store.prepare(**changed_config)
    alternate = await record_evaluation_comparison(
        SqlAlchemyControlPlaneEvolutionEvaluationStore(db_session),
        company_id="cmp_release",
        proposal_id="evo_release",
        baseline=_batch(evaluation_id="alternate-baseline", revision="editor@1", quality=0.8),
        candidate=_batch(evaluation_id="alternate-candidate", revision="editor@2", quality=0.9),
        policy=EvaluationPolicy(maximum_cost_per_accepted_outcome_usd=1),
    )
    changed_report = _release_kwargs(alternate.evaluation_report_id)
    with pytest.raises(ExecutionDenied, match="frozen_release_configuration_changed"):
        await store.prepare(**changed_report)
    assert command.command_id == (await store.prepare(**_release_kwargs(report_id))).command_id


@pytest.mark.parametrize(
    ("tier", "cases", "candidate_quality", "action", "reason"),
    [
        (EvolutionTier.L1, 2, 0.9, "canary", "live_release_sample_count_required"),
        (EvolutionTier.L1, 50, 0.1, "canary", "evaluation_release_gates_failed"),
        (EvolutionTier.L2, 50, 0.9, "shadow", "only_l1_skill_release_supported"),
    ],
)
@pytest.mark.asyncio
async def test_release_rejects_low_sample_ineligible_and_non_l1_evidence(
    db_session: AsyncSession,
    tier: EvolutionTier,
    cases: int,
    candidate_quality: float,
    action: str,
    reason: str,
) -> None:
    report_id = await _seed_release(
        db_session,
        company_id=f"cmp_{tier.value}_{cases}_{candidate_quality}",
        proposal_id=f"evo_{tier.value}_{cases}_{candidate_quality}",
        tier=tier,
        cases=cases,
        candidate_quality=candidate_quality,
    )
    kwargs = _release_kwargs(report_id, action=action)
    kwargs["company_id"] = f"cmp_{tier.value}_{cases}_{candidate_quality}"
    kwargs["proposal_id"] = f"evo_{tier.value}_{cases}_{candidate_quality}"
    store = SqlAlchemyEvolutionDeploymentStore(db_session)
    if tier == EvolutionTier.L1:
        shadow = await store.prepare(**{**kwargs, "action": "shadow"})
        await store.acknowledge(
            shadow,
            {"deployment_id": shadow.deployment_id, "state": "shadow"},
            actor_id="release-operator",
        )
    with pytest.raises(ExecutionDenied, match=reason):
        await store.prepare(**kwargs)


@pytest.mark.asyncio
async def test_other_company_report_is_rejected_before_deployment_or_approval(
    db_session: AsyncSession,
) -> None:
    report_id = await _seed_release(
        db_session, company_id="cmp_evidence_owner", proposal_id="evo_owner"
    )
    await _seed_release(db_session, company_id="cmp_requester", proposal_id="evo_requester")
    kwargs = _release_kwargs(report_id, action="canary")
    kwargs.update(company_id="cmp_requester", proposal_id="evo_requester")
    with pytest.raises(ExecutionDenied, match="evolution_evidence_not_found"):
        await SqlAlchemyEvolutionDeploymentStore(db_session).prepare(**kwargs)
    assert await db_session.get(EvolutionDeploymentTable, "dep_nonexistent") is None
    assert (
        await db_session.scalars(
            select(ApprovalRequestTable).where(ApprovalRequestTable.company_id == "cmp_requester")
        )
    ).all() == []


@pytest.mark.asyncio
async def test_acknowledgement_must_match_fresh_command(db_session: AsyncSession) -> None:
    report_id = await _seed_release(db_session)
    store = SqlAlchemyEvolutionDeploymentStore(db_session)
    command = await store.prepare(**_release_kwargs(report_id))
    with pytest.raises(ExecutionDenied, match="evolution_receiver_state_mismatch"):
        await store.acknowledge(
            command,
            {"deployment_id": command.deployment_id, "state": "active"},
            actor_id="release-operator",
        )
    stale = command.model_copy(update={"command_id": "cmd_stale"})
    with pytest.raises(ExecutionDenied, match="evolution_release_owner_lost"):
        await store.acknowledge(
            stale,
            {"deployment_id": stale.deployment_id, "state": "shadow"},
            actor_id="release-operator",
        )


@pytest.mark.asyncio
async def test_timeout_retries_same_pending_command_without_new_approval(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_id = await _seed_release(db_session)
    commands = []
    lookups = []
    responses = []

    async def apply(_gateway, command):
        commands.append(command)
        raise httpx.ReadTimeout("receiver timed out")

    ack = {"deployment_id": "placeholder", "state": "canary"}

    async def lookup(_gateway, command):
        lookups.append(command)
        if len(lookups) == 1:
            return None
        response = {**ack, "deployment_id": command.deployment_id}
        responses.append(response)
        return response

    monkeypatch.setattr(HttpEvolutionDeploymentGateway, "apply", apply)
    monkeypatch.setattr(HttpEvolutionDeploymentGateway, "lookup", lookup)
    store = SqlAlchemyEvolutionDeploymentStore(db_session)
    shadow = await store.prepare(**_release_kwargs(report_id))
    await store.acknowledge(
        shadow, {"deployment_id": shadow.deployment_id, "state": "shadow"}, actor_id="operator"
    )
    await db_session.commit()
    with pytest.raises(ExecutionDenied, match="skill_release_approval_required"):
        await store.prepare(**_release_kwargs(report_id, action="canary"))
    approval = (
        await db_session.scalars(
            select(ApprovalRequestTable).where(ApprovalRequestTable.company_id == "cmp_release")
        )
    ).one()
    await SqlAlchemyControlPlaneApprovalStore(db_session).resolve_approval(
        approval.approval_id, status=ApprovalStatus.APPROVED, resolved_by="board"
    )
    await db_session.commit()

    command = await store.prepare(**_release_kwargs(report_id, action="canary"))
    await store.checkpoint()
    with pytest.raises(httpx.ReadTimeout):
        if await HttpEvolutionDeploymentGateway().lookup(command) is None:
            await HttpEvolutionDeploymentGateway().apply(command)
    pending_row = await db_session.get(EvolutionDeploymentTable, command.deployment_id)
    assert pending_row is not None and pending_row.state == "pending"
    replay = await store.prepare(**_release_kwargs(report_id, action="canary"))
    assert replay.command_id == command.command_id
    response = await HttpEvolutionDeploymentGateway().lookup(replay)
    assert response is not None
    await store.acknowledge(replay, response, actor_id="release-operator")
    await db_session.commit()

    assert len(commands) == 1
    assert commands[0].command_id == replay.command_id
    assert [item.command_id for item in lookups] == [command.command_id, replay.command_id]
    assert responses == [{"deployment_id": command.deployment_id, "state": "canary"}]
    approvals = (
        await db_session.scalars(
            select(ApprovalRequestTable).where(ApprovalRequestTable.company_id == "cmp_release")
        )
    ).all()
    assert len(approvals) == 1


@pytest.mark.asyncio
async def test_revoked_approval_blocks_redispatch_of_pending_command(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_id = await _seed_release(db_session)
    commands = []
    lookups = []

    async def timeout(_gateway, command):
        commands.append(command)
        raise httpx.ReadTimeout("receiver timed out")

    async def missing(_gateway, command):
        lookups.append(command)
        return None

    monkeypatch.setattr(HttpEvolutionDeploymentGateway, "apply", timeout)
    monkeypatch.setattr(HttpEvolutionDeploymentGateway, "lookup", missing)
    store = SqlAlchemyEvolutionDeploymentStore(db_session)
    shadow = await store.prepare(**_release_kwargs(report_id))
    await store.acknowledge(
        shadow, {"deployment_id": shadow.deployment_id, "state": "shadow"}, actor_id="operator"
    )
    await db_session.commit()
    with pytest.raises(ExecutionDenied, match="skill_release_approval_required"):
        await store.prepare(**_release_kwargs(report_id, action="canary"))
    approval = (
        await db_session.scalars(
            select(ApprovalRequestTable).where(ApprovalRequestTable.company_id == "cmp_release")
        )
    ).one()
    await SqlAlchemyControlPlaneApprovalStore(db_session).resolve_approval(
        approval.approval_id, status=ApprovalStatus.APPROVED, resolved_by="board"
    )
    await db_session.commit()

    command = await store.prepare(**_release_kwargs(report_id, action="canary"))
    await store.checkpoint()
    with pytest.raises(httpx.ReadTimeout):
        if await HttpEvolutionDeploymentGateway().lookup(command) is None:
            await HttpEvolutionDeploymentGateway().apply(command)
    approval.status = "rejected"
    await db_session.flush()
    await db_session.commit()
    with pytest.raises(ExecutionDenied, match="skill_release_approval_revoked"):
        await store.prepare(**_release_kwargs(report_id, action="canary"))
    assert len(commands) == 1
    assert len(lookups) == 1


@pytest.mark.asyncio
async def test_release_reconcile_route_persists_receiver_acknowledgement(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from collections.abc import AsyncGenerator

    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from shared.control_plane.api_routes.evolution_releases import create_evolution_release_router
    from shared.control_plane.unit_of_work import ControlPlaneUnitOfWork

    report_id = await _seed_release(db_session)
    store = SqlAlchemyEvolutionDeploymentStore(db_session)
    shadow = await store.prepare(**_release_kwargs(report_id))
    await store.acknowledge(
        shadow, {"deployment_id": shadow.deployment_id, "state": "shadow"}, actor_id="operator"
    )
    await db_session.commit()
    with pytest.raises(ExecutionDenied, match="skill_release_approval_required"):
        await store.prepare(**_release_kwargs(report_id, action="canary"))
    approval = (
        await db_session.scalars(
            select(ApprovalRequestTable).where(ApprovalRequestTable.company_id == "cmp_release")
        )
    ).one()
    await SqlAlchemyControlPlaneApprovalStore(db_session).resolve_approval(
        approval.approval_id, status=ApprovalStatus.APPROVED, resolved_by="board"
    )
    await db_session.commit()
    command = await store.prepare(**_release_kwargs(report_id, action="canary"))
    await store.checkpoint()

    async def lookup(_gateway, requested):
        assert requested.command_id == command.command_id
        return {"deployment_id": requested.deployment_id, "state": "canary"}

    monkeypatch.setattr(HttpEvolutionDeploymentGateway, "lookup", lookup)

    async def get_uow() -> AsyncGenerator[ControlPlaneUnitOfWork, None]:
        yield ControlPlaneUnitOfWork(db_session)

    app = FastAPI()
    app.include_router(
        create_evolution_release_router(get_uow=get_uow), prefix="/api/v1/control-plane"
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        reconciled = await client.post(
            "/api/v1/control-plane/evolution-proposals/evo_release/release/reconcile",
            params={"company_id": "cmp_release"},
        )

    assert reconciled.status_code == 200
    assert reconciled.json()["state"] == "canary"
    deployment = await db_session.get(EvolutionDeploymentTable, command.deployment_id)
    assert deployment is not None and deployment.state == "canary"


@pytest.mark.asyncio
async def test_expired_unapplied_pending_command_renews_with_new_id_and_audit(
    db_session: AsyncSession,
) -> None:
    report_id = await _seed_release(db_session)
    store = SqlAlchemyEvolutionDeploymentStore(db_session)
    original = await store.prepare(**_release_kwargs(report_id))
    expired = original.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    deployment = await db_session.get(EvolutionDeploymentTable, original.deployment_id)
    assert deployment is not None
    deployment.command = expired.model_dump(mode="json")
    await db_session.commit()

    replacement = await store.recover_expired_pending(expired, actor_id="release-operator")
    assert replacement.command_id != expired.command_id
    assert replacement.deployment_id == expired.deployment_id
    assert replacement.action == expired.action == "shadow"
    row = await db_session.get(EvolutionDeploymentTable, original.deployment_id)
    assert row is not None and row.state == "pending"
    assert row.command["command_id"] == replacement.command_id
    audit = await db_session.scalar(
        select(AuditEventTable).where(
            AuditEventTable.action == "evolution.release_expired_command_recovered"
        )
    )
    assert audit is not None
    assert audit.detail["superseded_command"]["command_id"] == expired.command_id
    assert audit.detail["receiver_lookup"] == "not_found"


@pytest.mark.asyncio
async def test_expired_pending_reconcile_acknowledges_original_command(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from collections.abc import AsyncGenerator

    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from shared.control_plane.api_routes.evolution_releases import create_evolution_release_router
    from shared.control_plane.unit_of_work import ControlPlaneUnitOfWork

    report_id = await _seed_release(db_session)
    store = SqlAlchemyEvolutionDeploymentStore(db_session)
    original = await store.prepare(**_release_kwargs(report_id))
    expired = original.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    deployment = await db_session.get(EvolutionDeploymentTable, original.deployment_id)
    assert deployment is not None
    deployment.command = expired.model_dump(mode="json")
    await db_session.commit()
    calls: list[str] = []

    async def lookup(_gateway, command):
        calls.append(command.command_id)
        return {"deployment_id": command.deployment_id, "state": "shadow"}

    async def apply(_gateway, command):
        raise AssertionError("expired applied command must not be replayed")

    monkeypatch.setattr(HttpEvolutionDeploymentGateway, "lookup", lookup)
    monkeypatch.setattr(HttpEvolutionDeploymentGateway, "apply", apply)

    async def get_uow() -> AsyncGenerator[ControlPlaneUnitOfWork, None]:
        yield ControlPlaneUnitOfWork(db_session)

    app = FastAPI()
    app.include_router(
        create_evolution_release_router(get_uow=get_uow), prefix="/api/v1/control-plane"
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/control-plane/evolution-proposals/evo_release/release/recover",
            params={"company_id": "cmp_release"},
        )
    assert response.status_code == 200
    assert calls == [expired.command_id]
    row = await db_session.get(EvolutionDeploymentTable, original.deployment_id)
    assert row is not None and row.state == "shadow"
    assert row.command["command_id"] == expired.command_id


@pytest.mark.asyncio
async def test_recovery_transport_unknown_leaves_pending_command_unchanged(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from collections.abc import AsyncGenerator

    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from shared.control_plane.api_routes.evolution_releases import create_evolution_release_router
    from shared.control_plane.unit_of_work import ControlPlaneUnitOfWork

    report_id = await _seed_release(db_session)
    store = SqlAlchemyEvolutionDeploymentStore(db_session)
    original = await store.prepare(**_release_kwargs(report_id))
    expired = original.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    deployment = await db_session.get(EvolutionDeploymentTable, original.deployment_id)
    assert deployment is not None
    deployment.command = expired.model_dump(mode="json")
    await db_session.commit()

    async def lookup(_gateway, _command):
        raise httpx.ReadTimeout("receipt status unknown")

    monkeypatch.setattr(HttpEvolutionDeploymentGateway, "lookup", lookup)

    async def get_uow() -> AsyncGenerator[ControlPlaneUnitOfWork, None]:
        yield ControlPlaneUnitOfWork(db_session)

    app = FastAPI()
    app.include_router(
        create_evolution_release_router(get_uow=get_uow), prefix="/api/v1/control-plane"
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/control-plane/evolution-proposals/evo_release/release/recover",
            params={"company_id": "cmp_release"},
        )
    assert response.status_code == 502
    row = await db_session.get(EvolutionDeploymentTable, original.deployment_id)
    assert row is not None and row.command["command_id"] == expired.command_id
    audits = (
        await db_session.scalars(
            select(AuditEventTable).where(
                AuditEventTable.action == "evolution.release_expired_command_recovered"
            )
        )
    ).all()
    assert audits == []


@pytest.mark.asyncio
async def test_expired_command_recovery_rejects_stale_current_owner(
    db_session: AsyncSession,
) -> None:
    report_id = await _seed_release(db_session)
    store = SqlAlchemyEvolutionDeploymentStore(db_session)
    original = await store.prepare(**_release_kwargs(report_id))
    expired = original.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    deployment = await db_session.get(EvolutionDeploymentTable, original.deployment_id)
    assert deployment is not None
    deployment.command = expired.model_dump(mode="json")
    await db_session.commit()
    deployment.command = {**expired.model_dump(mode="json"), "command_id": "cmd_new_owner"}
    await db_session.commit()

    with pytest.raises(ExecutionDenied, match="evolution_release_owner_lost"):
        await store.recover_expired_pending(expired, actor_id="release-operator")


@pytest.mark.asyncio
async def test_recovery_refreshes_locked_row_before_owner_cas(
    db_session: AsyncSession,
) -> None:
    report_id = await _seed_release(db_session)
    store = SqlAlchemyEvolutionDeploymentStore(db_session)
    original = await store.prepare(**_release_kwargs(report_id))
    stale_pending = await store.pending(company_id="cmp_release", proposal_id="evo_release")
    await db_session.commit()

    async with AsyncSession(bind=db_session.bind, expire_on_commit=False) as writer:
        row = await writer.get(EvolutionDeploymentTable, original.deployment_id)
        assert row is not None
        row.command = {**row.command, "command_id": "cmd_concurrent_recovery"}
        await writer.commit()

    with pytest.raises(ExecutionDenied, match="evolution_release_owner_lost"):
        await store.recover_expired_pending(stale_pending, actor_id="release-operator")
    row = await db_session.get(EvolutionDeploymentTable, original.deployment_id)
    assert row is not None and row.command["command_id"] == "cmd_concurrent_recovery"
    assert row.state == "pending"


@pytest.mark.asyncio
async def test_acknowledge_refreshes_locked_row_before_owner_cas(
    db_session: AsyncSession,
) -> None:
    report_id = await _seed_release(db_session)
    store = SqlAlchemyEvolutionDeploymentStore(db_session)
    original = await store.prepare(**_release_kwargs(report_id))
    await db_session.commit()

    async with AsyncSession(bind=db_session.bind, expire_on_commit=False) as writer:
        row = await writer.get(EvolutionDeploymentTable, original.deployment_id)
        assert row is not None
        row.command = {**row.command, "command_id": "cmd_concurrent_ack"}
        await writer.commit()

    with pytest.raises(ExecutionDenied, match="evolution_release_owner_lost"):
        await store.acknowledge(
            original,
            {"deployment_id": original.deployment_id, "state": "shadow"},
            actor_id="release-operator",
        )
    row = await db_session.get(EvolutionDeploymentTable, original.deployment_id)
    assert row is not None and row.command["command_id"] == "cmd_concurrent_ack"
    assert row.state == "pending"
