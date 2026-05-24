"""Tests for control-plane budget application use cases."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.audit_event_store import SqlAlchemyControlPlaneAuditEventStore
from shared.control_plane.budget_store import SqlAlchemyControlPlaneBudgetStore
from shared.control_plane.budget_use_cases import (
    ActiveBudgetPolicyConflictError,
    create_budget_policy_with_audit,
    update_budget_policy_with_audit,
)
from shared.control_plane.domain.budget_policy import (
    BUDGET_POLICY_STATUS_ACTIVE,
    BUDGET_POLICY_STATUS_PAUSED,
)
from shared.control_plane.models import BudgetPeriod, BudgetPolicy, BudgetScope
from shared.schemas.event import EventTypes


@pytest.mark.asyncio
async def test_budget_policy_use_cases_apply_active_conflict_vocabulary(
    db_session: AsyncSession,
) -> None:
    store = SqlAlchemyControlPlaneBudgetStore(db_session)
    active = await create_budget_policy_with_audit(
        store,
        BudgetPolicy(
            company_id="cmp_budget_policy_use_case",
            scope=BudgetScope.AGENT,
            scope_id="dev-agent",
            period=BudgetPeriod.DAILY,
            limit_usd=20,
            status=BUDGET_POLICY_STATUS_ACTIVE,
        ),
        created_by="human:finance",
    )
    paused = await create_budget_policy_with_audit(
        store,
        BudgetPolicy(
            company_id="cmp_budget_policy_use_case",
            scope=BudgetScope.AGENT,
            scope_id="dev-agent",
            period=BudgetPeriod.DAILY,
            limit_usd=30,
            status=BUDGET_POLICY_STATUS_PAUSED,
        ),
        created_by="human:finance",
    )

    with pytest.raises(ActiveBudgetPolicyConflictError) as exc:
        await update_budget_policy_with_audit(
            store,
            company_id="cmp_budget_policy_use_case",
            budget_id=paused.budget_id,
            status=BUDGET_POLICY_STATUS_ACTIVE,
            actor_id="human:finance",
            changed_fields=["status"],
        )

    assert str(exc.value) == active.budget_id

    audits = await SqlAlchemyControlPlaneAuditEventStore(db_session).list_audit_events(
        company_id="cmp_budget_policy_use_case",
        target_type="budget_policy",
    )
    created_details = [
        audit.detail
        for audit in audits
        if audit.action == EventTypes.BUDGET_POLICY_CREATED
    ]
    assert len(created_details) == 2
    assert {detail["domain_event"] for detail in created_details} == {
        "BudgetPolicyCreated"
    }
    assert {detail["status"] for detail in created_details} == {
        BUDGET_POLICY_STATUS_ACTIVE,
        BUDGET_POLICY_STATUS_PAUSED,
    }


@pytest.mark.asyncio
async def test_budget_policy_update_uses_budget_value_objects(
    db_session: AsyncSession,
) -> None:
    store = SqlAlchemyControlPlaneBudgetStore(db_session)
    policy = await create_budget_policy_with_audit(
        store,
        BudgetPolicy(
            company_id="cmp_budget_amount_use_case",
            scope=BudgetScope.COMPANY,
            period=BudgetPeriod.DAILY,
            limit_usd=20,
        ),
        created_by="human:finance",
    )

    with pytest.raises(ValueError, match="positive"):
        await update_budget_policy_with_audit(
            store,
            company_id="cmp_budget_amount_use_case",
            budget_id=policy.budget_id,
            limit_usd=0,
            actor_id="human:finance",
            changed_fields=["limit_usd"],
        )

    with pytest.raises(ValueError, match="within"):
        await update_budget_policy_with_audit(
            store,
            company_id="cmp_budget_amount_use_case",
            budget_id=policy.budget_id,
            warning_threshold=1.01,
            actor_id="human:finance",
            changed_fields=["warning_threshold"],
        )


@pytest.mark.asyncio
async def test_budget_policy_update_uses_aggregate_domain_event_audit(
    db_session: AsyncSession,
) -> None:
    store = SqlAlchemyControlPlaneBudgetStore(db_session)
    policy = await create_budget_policy_with_audit(
        store,
        BudgetPolicy(
            company_id="cmp_budget_event_use_case",
            scope=BudgetScope.COMPANY,
            period=BudgetPeriod.DAILY,
            limit_usd=20,
        ),
        created_by="human:finance",
    )

    await update_budget_policy_with_audit(
        store,
        company_id="cmp_budget_event_use_case",
        budget_id=policy.budget_id,
        limit_usd=30,
        status=BUDGET_POLICY_STATUS_PAUSED,
        actor_id="human:finance",
        changed_fields=["limit_usd", "status"],
    )

    audits = await SqlAlchemyControlPlaneAuditEventStore(db_session).list_audit_events(
        company_id="cmp_budget_event_use_case",
        target_type="budget_policy",
    )

    update_audit = next(
        audit for audit in audits if audit.action == EventTypes.BUDGET_POLICY_UPDATED
    )
    assert update_audit.detail["domain_event"] == "BudgetPolicyUpdated"
    assert update_audit.detail["from_status"] == BUDGET_POLICY_STATUS_ACTIVE
    assert update_audit.detail["to_status"] == BUDGET_POLICY_STATUS_PAUSED
    assert update_audit.detail["changed_fields"] == ["limit_usd", "status"]
