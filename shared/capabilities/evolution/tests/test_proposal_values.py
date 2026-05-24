import pytest

from shared.capabilities.evolution.core.domain.proposal import (
    ALLOWED_EVOLUTION_OPERATIONS,
    EVOLUTION_PROPOSAL_RISK,
    EvolutionProposalApprovalContext,
    EvolutionProposalOperation,
)
from shared.control_plane import EvolutionTier


def test_proposal_context_derives_l2_scope_and_approval_copy() -> None:
    context = EvolutionProposalApprovalContext.from_payload(
        {
            "operation": "modify_event_subscription",
            "target_agent": "pjm-agent",
            "target_skill": "decompose",
            "rationale": "Improve handoff quality",
            "expected_benefit": "Fewer handoff misses",
        },
        source_agent_id="evolution-module",
        trace_id="trace-evo",
    )

    assert context.tier == EvolutionTier.L2
    assert context.scope.value == "agent:pjm-agent/skill:decompose"
    assert context.approval_action == (
        "Approve evolution proposal modify_event_subscription"
    )
    assert context.approval_reason == "Improve handoff quality"
    assert context.affected_resources == ["pjm-agent"]
    assert context.expected_benefit == "Fewer handoff misses"
    assert context.risk == EVOLUTION_PROPOSAL_RISK
    assert context.evidence["source_agent"] == "evolution-module"
    assert context.evidence["trace_id"] == "trace-evo"
    assert context.metadata["target_skill"] == "decompose"

    with pytest.raises(TypeError):
        context.payload["operation"] = "add_skill"


def test_proposal_context_derives_l3_pattern_scope() -> None:
    context = EvolutionProposalApprovalContext.from_payload(
        {
            "pattern_id": "pattern_qa_handoff",
            "name": "QA handoff",
            "description": "Coordinate QA after implementation",
        },
        source_agent_id="evolution-module",
        trace_id=None,
    )

    assert context.tier == EvolutionTier.L3
    assert context.scope.value == "pattern:pattern_qa_handoff"
    assert context.scope.pattern_id == "pattern_qa_handoff"
    assert context.approval_action == (
        "Approve evolution proposal pattern_qa_handoff"
    )
    assert context.affected_resources == ["pattern_qa_handoff"]
    assert context.expected_benefit == "Coordinate QA after implementation"


def test_allowed_operations_are_domain_owned() -> None:
    assert EvolutionProposalOperation.ADD_LOOP_LOGIC.value in (
        ALLOWED_EVOLUTION_OPERATIONS
    )
    assert set(ALLOWED_EVOLUTION_OPERATIONS) == {
        "add_skill",
        "adjust_skill_ordering",
        "modify_event_subscription",
        "adjust_sampling_parameters",
        "add_loop_logic",
    }
