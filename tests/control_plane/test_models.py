"""Tests for control-plane Pydantic models."""

import pytest
from pydantic import ValidationError

from shared.control_plane.models import (
    ApprovalCategory,
    ApprovalRequest,
    BudgetPeriod,
    BudgetPolicy,
    BudgetScope,
    CompanyContext,
    Goal,
    GoalStatus,
    WorkItem,
    WorkItemStatus,
)


def test_core_model_defaults_and_prefixes():
    company = CompanyContext(name="Wisdoverse Cell", mission="Operate with agents")
    goal = Goal(company_id=company.company_id, title="Ship control plane")
    work_item = WorkItem(company_id=company.company_id, title="Create run ledger")

    assert company.company_id.startswith("cmp_")
    assert goal.goal_id.startswith("goal_")
    assert work_item.work_item_id.startswith("work_")
    assert goal.status == GoalStatus.DRAFT
    assert work_item.status == WorkItemStatus.QUEUED
    assert goal.metadata == {}
    assert work_item.dependencies == []


def test_approval_requires_decision_context():
    company = CompanyContext(name="Wisdoverse Cell")

    with pytest.raises(ValidationError):
        ApprovalRequest(
            company_id=company.company_id,
            category=ApprovalCategory.TECHNICAL,
            requested_by="agent:dev-agent",
            source_agent_id="dev-agent",
            proposed_action="",
            reason="Need migration",
            risk="Schema change",
            rollback_note="Rollback migration",
            affected_resources=["postgres"],
        )


def test_approval_requires_affected_resources():
    company = CompanyContext(name="Wisdoverse Cell")

    with pytest.raises(ValidationError):
        ApprovalRequest(
            company_id=company.company_id,
            category=ApprovalCategory.TECHNICAL,
            requested_by="agent:dev-agent",
            source_agent_id="dev-agent",
            proposed_action="Apply migration",
            reason="Need migration",
            risk="Schema change",
            rollback_note="Rollback migration",
        )


def test_budget_limit_must_be_positive():
    company = CompanyContext(name="Wisdoverse Cell")

    with pytest.raises(ValidationError):
        BudgetPolicy(
            company_id=company.company_id,
            scope=BudgetScope.COMPANY,
            period=BudgetPeriod.MONTHLY,
            limit_usd=0,
        )
