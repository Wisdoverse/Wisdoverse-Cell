"""Tests for control-plane Pydantic models."""

import pytest
from pydantic import ValidationError

from shared.control_plane.models import (
    ApprovalCategory,
    ApprovalRequest,
    BudgetPeriod,
    BudgetPolicy,
    BudgetScope,
    BudgetUsage,
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


def test_budget_warning_threshold_must_be_ratio():
    company = CompanyContext(name="Wisdoverse Cell")

    for threshold in (0, -0.1, 1.1):
        with pytest.raises(ValidationError):
            BudgetPolicy(
                company_id=company.company_id,
                scope=BudgetScope.COMPANY,
                period=BudgetPeriod.MONTHLY,
                limit_usd=100,
                warning_threshold=threshold,
            )

    policy = BudgetPolicy(
        company_id=company.company_id,
        scope=BudgetScope.COMPANY,
        period=BudgetPeriod.MONTHLY,
        limit_usd=100,
        warning_threshold=1,
    )
    assert policy.warning_threshold == 1


def test_budget_usage_must_be_non_negative():
    company = CompanyContext(name="Wisdoverse Cell")

    valid = {
        "company_id": company.company_id,
        "budget_id": "bud_test",
        "cost_usd": 0,
        "model": "test-model",
        "input_tokens": 0,
        "output_tokens": 0,
    }
    assert BudgetUsage(**valid).cost_usd == 0

    for field, value in (
        ("cost_usd", -0.01),
        ("input_tokens", -1),
        ("output_tokens", -1),
    ):
        with pytest.raises(ValidationError):
            BudgetUsage(**{**valid, field: value})
