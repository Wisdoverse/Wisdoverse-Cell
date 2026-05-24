"""Tests for BudgetPolicy domain aggregate and vocabulary."""

import pytest

from shared.control_plane.domain.budget_policy import (
    BUDGET_POLICY_STATUS_ACTIVE,
    BUDGET_POLICY_STATUS_ARCHIVED,
    BUDGET_POLICY_STATUS_PAUSED,
    BUDGET_POLICY_STATUSES,
    TERMINAL_STATUSES,
    BudgetPolicy,
    BudgetPolicyConflictError,
    BudgetPolicyConflictPolicy,
    BudgetPolicyCreated,
    BudgetPolicyStatus,
    BudgetPolicyUpdated,
    InvalidBudgetPolicyError,
    InvalidBudgetPolicyTransitionError,
    budget_policy_status,
    is_active_budget_policy_status,
    is_budget_policy_status,
    normalize_budget_policy_status,
)
from shared.control_plane.domain.services import ControlPlaneDomainService
from shared.control_plane.models import BudgetPeriod, BudgetScope
from shared.control_plane.models import BudgetPolicy as BudgetPolicyRecord


def test_budget_policy_status_vocabulary_is_canonical() -> None:
    assert BUDGET_POLICY_STATUSES == frozenset(
        {
            BUDGET_POLICY_STATUS_ACTIVE,
            BUDGET_POLICY_STATUS_PAUSED,
            BUDGET_POLICY_STATUS_ARCHIVED,
        }
    )
    assert normalize_budget_policy_status(" ACTIVE ") == BUDGET_POLICY_STATUS_ACTIVE
    assert budget_policy_status(" paused ") == BudgetPolicyStatus.PAUSED
    assert is_budget_policy_status(" Paused ")
    assert not is_budget_policy_status("disabled")
    assert TERMINAL_STATUSES == frozenset({BudgetPolicyStatus.ARCHIVED})


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (BUDGET_POLICY_STATUS_ACTIVE, True),
        (" ACTIVE ", True),
        (BUDGET_POLICY_STATUS_PAUSED, False),
        (BUDGET_POLICY_STATUS_ARCHIVED, False),
        (None, False),
    ],
)
def test_only_active_budget_policy_status_participates_in_conflicts(
    status: str | None,
    expected: bool,
) -> None:
    assert is_active_budget_policy_status(status) is expected


def test_budget_policy_conflict_policy_implements_domain_service_contract() -> None:
    policy = BudgetPolicyConflictPolicy()

    assert isinstance(policy, ControlPlaneDomainService)
    assert policy.service_name == "BudgetPolicyConflictPolicy"
    assert policy.requires_unique_active_policy(BudgetPolicyStatus.ACTIVE)
    assert policy.requires_unique_active_policy(" ACTIVE ")
    assert not policy.requires_unique_active_policy(BudgetPolicyStatus.PAUSED)


def test_budget_policy_conflict_policy_rejects_other_active_policy() -> None:
    policy = BudgetPolicyConflictPolicy()
    existing = BudgetPolicyRecord(
        budget_id="bud_existing",
        company_id="cmp_budget_domain",
        scope=BudgetScope.COMPANY,
        period=BudgetPeriod.MONTHLY,
        limit_usd=20,
    )

    with pytest.raises(BudgetPolicyConflictError) as exc:
        policy.ensure_no_active_conflict(
            existing=existing,
            current_budget_id="bud_current",
        )

    assert exc.value.budget_id == "bud_existing"
    policy.ensure_no_active_conflict(
        existing=existing,
        current_budget_id="bud_existing",
    )


def test_budget_policy_for_creation_normalizes_record_and_raises_created_event() -> None:
    aggregate = BudgetPolicy.for_creation(
        BudgetPolicyRecord(
            budget_id="bud_policy_domain",
            company_id="cmp_budget_domain",
            scope=BudgetScope.AGENT,
            scope_id=" dev-agent ",
            period=BudgetPeriod.DAILY,
            limit_usd=20,
            warning_threshold=0.75,
            status=" ACTIVE ",
            model_allowlist=[" claude-sonnet ", "", "gpt-5"],
            metadata={"source": "test"},
        )
    )

    assert aggregate.record.scope_id == "dev-agent"
    assert aggregate.record.status == BUDGET_POLICY_STATUS_ACTIVE
    assert aggregate.record.model_allowlist == ["claude-sonnet", "gpt-5"]

    aggregate.mark_created()

    events = aggregate.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, BudgetPolicyCreated)
    assert event.company_id == "cmp_budget_domain"
    assert event.status == BudgetPolicyStatus.ACTIVE
    assert event.model_allowlist == ("claude-sonnet", "gpt-5")
    assert aggregate.pull_events() == []


def test_budget_policy_company_scope_forbids_scope_id() -> None:
    with pytest.raises(InvalidBudgetPolicyError, match="company_scope_id_forbidden"):
        BudgetPolicy.for_creation(
            BudgetPolicyRecord(
                company_id="cmp_budget_domain",
                scope=BudgetScope.COMPANY,
                scope_id="company",
                period=BudgetPeriod.MONTHLY,
                limit_usd=20,
            )
        )


def test_budget_policy_non_company_scope_requires_scope_id() -> None:
    with pytest.raises(InvalidBudgetPolicyError, match="scope_id_required"):
        BudgetPolicy.for_creation(
            BudgetPolicyRecord(
                company_id="cmp_budget_domain",
                scope=BudgetScope.WORK_ITEM,
                period=BudgetPeriod.MONTHLY,
                limit_usd=20,
            )
        )


def test_budget_policy_apply_update_validates_transition_and_raises_event() -> None:
    aggregate = BudgetPolicy.for_creation(
        BudgetPolicyRecord(
            budget_id="bud_policy_domain",
            company_id="cmp_budget_domain",
            scope=BudgetScope.COMPANY,
            period=BudgetPeriod.MONTHLY,
            limit_usd=20,
        )
    )

    aggregate.apply_update(
        limit_usd=30,
        warning_threshold=0.7,
        status=BUDGET_POLICY_STATUS_PAUSED,
        model_allowlist=[" gpt-5 "],
        metadata={"source": "update"},
        changed_fields=[
            "metadata",
            "model_allowlist",
            "status",
            "warning_threshold",
            "limit_usd",
        ],
    )

    assert aggregate.record.limit_usd == 30
    assert aggregate.record.warning_threshold == 0.7
    assert aggregate.record.status == BUDGET_POLICY_STATUS_PAUSED
    assert aggregate.record.model_allowlist == ["gpt-5"]

    events = aggregate.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, BudgetPolicyUpdated)
    assert event.from_status == BudgetPolicyStatus.ACTIVE
    assert event.to_status == BudgetPolicyStatus.PAUSED
    assert event.changed_fields == (
        "limit_usd",
        "metadata",
        "model_allowlist",
        "status",
        "warning_threshold",
    )


def test_archived_budget_policy_is_terminal() -> None:
    aggregate = BudgetPolicy.for_creation(
        BudgetPolicyRecord(
            budget_id="bud_policy_domain",
            company_id="cmp_budget_domain",
            scope=BudgetScope.COMPANY,
            period=BudgetPeriod.MONTHLY,
            limit_usd=20,
            status=BUDGET_POLICY_STATUS_ARCHIVED,
        )
    )

    assert aggregate.is_terminal
    with pytest.raises(InvalidBudgetPolicyTransitionError):
        aggregate.apply_update(
            status=BUDGET_POLICY_STATUS_ACTIVE,
            changed_fields=["status"],
        )
