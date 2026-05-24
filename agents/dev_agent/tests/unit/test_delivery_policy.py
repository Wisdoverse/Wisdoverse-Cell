"""Tests for Dev delivery workflow policy."""

from agents.dev_agent.core.domain.delivery_policy import DevDeliveryWorkflowPolicy
from agents.dev_agent.core.domain.task_values import RiskLevel


def test_delivery_policy_owns_risk_gate_decisions() -> None:
    policy = DevDeliveryWorkflowPolicy()

    assert policy.rejects_automatic_delivery(RiskLevel.CRITICAL)
    assert not policy.rejects_automatic_delivery(RiskLevel.HIGH)
    assert policy.requires_workflow_approval(RiskLevel.HIGH)
    assert not policy.requires_workflow_approval(RiskLevel.MEDIUM)


def test_delivery_policy_owns_capacity_decision() -> None:
    policy = DevDeliveryWorkflowPolicy()

    available = policy.capacity_decision(active_count=1, max_concurrent_workflows=2)
    full = policy.capacity_decision(active_count=2, max_concurrent_workflows=2)

    assert available.can_start
    assert not full.can_start
    assert full.active_count == 2
    assert full.limit == 2


def test_delivery_policy_owns_qa_retry_decision() -> None:
    policy = DevDeliveryWorkflowPolicy()

    retry = policy.qa_retry_decision(retry_count=0)
    exhausted = policy.qa_retry_decision(retry_count=1)

    assert retry.should_retry
    assert retry.next_retry_count == 1
    assert not exhausted.should_retry
