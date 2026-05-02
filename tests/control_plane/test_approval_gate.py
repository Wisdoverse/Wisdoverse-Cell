"""Tests for shared approval enforcement."""

from contextlib import asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.approval_gate import (
    ApprovalGate,
    ApprovalGateService,
    ApprovalRequiredError,
)
from shared.control_plane.models import ApprovalCategory, CompanyContext
from shared.control_plane.repository import ControlPlaneRepository


@pytest.mark.asyncio
async def test_approval_gate_blocks_until_approved(db_session: AsyncSession):
    repo = ControlPlaneRepository(db_session)
    company = await repo.create_company(CompanyContext(name="Wisdoverse Cell"))
    gate = ApprovalGate(repo)

    approval = await gate.request_approval(
        company_id=company.company_id,
        category=ApprovalCategory.TECHNICAL,
        requested_by="agent:dev-agent",
        source_agent_id="dev-agent",
        proposed_action="Run production migration",
        reason="Control-plane ledger is required",
        risk="Schema change",
        rollback_note="Run downgrade migration",
        affected_resources=["postgres"],
        artifact_links=["https://gitlab.example/mr/1"],
        trace_id="trace_approval",
    )

    with pytest.raises(ApprovalRequiredError):
        await gate.ensure_approved(approval.approval_id)

    decision = await gate.approve(approval.approval_id, resolved_by="human:cto")
    assert decision.approved is True

    allowed = await gate.ensure_approved(approval.approval_id)
    assert allowed.approved is True
    assert allowed.status == "approved"


def _session_provider(db_session: AsyncSession):
    @asynccontextmanager
    async def _provider():
        yield db_session
        await db_session.flush()

    return _provider


@pytest.mark.asyncio
async def test_approval_gate_service_requests_and_approves(db_session: AsyncSession):
    service = ApprovalGateService(
        source_agent_id="dev-agent",
        session_provider=_session_provider(db_session),
        default_company_id="cmp_test",
        enabled=True,
        enforced=True,
    )

    approval = await service.request_approval(
        category=ApprovalCategory.TECHNICAL,
        proposed_action="Run high-risk workflow",
        reason="High risk dev task",
        risk="External workflow execution",
        rollback_note="Cancel before execution",
    )

    assert approval is not None
    assert approval.company_id == "cmp_test"
    assert approval.source_agent_id == "dev-agent"
    with pytest.raises(ApprovalRequiredError):
        await ApprovalGate(ControlPlaneRepository(db_session)).ensure_approved(
            approval.approval_id
        )

    decision = await service.approve_for_sensitive_action(
        approval.approval_id,
        resolved_by="human:lead",
    )

    assert decision is not None
    assert decision.approved is True


@pytest.mark.asyncio
async def test_approval_gate_service_enforced_requires_id(db_session: AsyncSession):
    service = ApprovalGateService(
        source_agent_id="dev-agent",
        session_provider=_session_provider(db_session),
        default_company_id="cmp_test",
        enabled=True,
        enforced=True,
    )

    with pytest.raises(ApprovalRequiredError, match="control_plane_approval_required"):
        await service.approve_for_sensitive_action(None, resolved_by="human:lead")


@pytest.mark.asyncio
async def test_approval_gate_rejects(db_session: AsyncSession):
    repo = ControlPlaneRepository(db_session)
    company = await repo.create_company(CompanyContext(name="Wisdoverse Cell"))
    gate = ApprovalGate(repo)

    approval = await gate.request_approval(
        company_id=company.company_id,
        category=ApprovalCategory.FINANCE,
        requested_by="agent:analysis-agent",
        source_agent_id="analysis-agent",
        proposed_action="Increase monthly LLM budget",
        reason="Higher analysis volume",
        risk="Spend increase",
        rollback_note="Restore previous budget limit",
    )

    decision = await gate.reject(approval.approval_id, resolved_by="human:cfo")
    assert decision.approved is False

    with pytest.raises(ApprovalRequiredError):
        await gate.ensure_approved(approval.approval_id)
