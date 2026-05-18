from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shared.capabilities.evolution.core.proposal_approval_use_cases import (
    EvolutionProposalApprovalUseCase,
)
from shared.control_plane import ApprovalCategory, EvolutionTier


class FakeApprovalService:
    def __init__(self, *, approval=None, enforced: bool = False, error=None):
        self.enforced = enforced
        self.request_approval = AsyncMock(
            side_effect=error,
            return_value=approval,
        )


class FakeProposalStore:
    def __init__(self, *, proposal_id: str = "evo_prop_1", error=None):
        self.company_ids: list[str] = []
        self.proposals: list[dict] = []
        self._proposal_id = proposal_id
        self._error = error

    async def ensure_company(self, company_id: str) -> None:
        self.company_ids.append(company_id)

    async def record_proposal(self, **kwargs) -> str:
        if self._error is not None:
            raise self._error
        self.proposals.append(kwargs)
        return self._proposal_id


def _use_case(
    *,
    approval_service=None,
    proposal_store=None,
    records_enabled: bool = False,
) -> EvolutionProposalApprovalUseCase:
    return EvolutionProposalApprovalUseCase(
        approval_service=approval_service
        or FakeApprovalService(approval=SimpleNamespace(approval_id="appr_evo_1")),
        proposal_store=proposal_store,
        source_agent_id="evolution-module",
        company_id="cmp_wisdoverse_cell",
        records_enabled=records_enabled,
    )


@pytest.mark.asyncio
async def test_attach_approval_adds_control_plane_approval_id() -> None:
    approval_service = FakeApprovalService(
        approval=SimpleNamespace(approval_id="appr_evo_1"),
    )
    use_case = _use_case(approval_service=approval_service)

    result = await use_case.attach_approval(
        {
            "operation": "add_skill",
            "target_agent": "pjm-agent",
            "rationale": "Improve decomposition quality",
        },
        trace_id="trace-evo",
    )

    assert result["control_plane_approval_id"] == "appr_evo_1"
    approval_service.request_approval.assert_awaited_once()
    call = approval_service.request_approval.await_args.kwargs
    assert call["category"] == ApprovalCategory.TECHNICAL
    assert call["affected_resources"] == ["pjm-agent"]
    assert call["trace_id"] == "trace-evo"


@pytest.mark.asyncio
async def test_attach_approval_records_control_plane_proposal_when_enabled() -> None:
    approval_service = FakeApprovalService(
        approval=SimpleNamespace(approval_id="appr_evo_1", status="pending"),
    )
    proposal_store = FakeProposalStore()
    use_case = _use_case(
        approval_service=approval_service,
        proposal_store=proposal_store,
        records_enabled=True,
    )

    result = await use_case.attach_approval(
        {
            "operation": "modify_event_subscription",
            "target_agent": "pjm-agent",
            "description": "Subscribe to QA feedback",
            "rationale": "Improve handoff quality",
        },
        trace_id="trace-evo",
    )

    assert result["control_plane_approval_id"] == "appr_evo_1"
    assert result["control_plane_proposal_id"] == "evo_prop_1"
    assert proposal_store.company_ids == ["cmp_wisdoverse_cell"]
    assert len(proposal_store.proposals) == 1
    proposal = proposal_store.proposals[0]
    assert proposal["tier"] == EvolutionTier.L2
    assert proposal["scope"] == "agent:pjm-agent"
    assert proposal["approval_id"] == "appr_evo_1"
    assert proposal["evidence"]["trace_id"] == "trace-evo"
    assert proposal["actor_id"] == "evolution-module"


@pytest.mark.asyncio
async def test_attach_approval_returns_payload_when_approval_request_fails_softly() -> None:
    approval_service = FakeApprovalService(error=RuntimeError("approval down"))
    proposal_store = FakeProposalStore()
    use_case = _use_case(
        approval_service=approval_service,
        proposal_store=proposal_store,
        records_enabled=True,
    )

    result = await use_case.attach_approval(
        {"operation": "add_skill", "target_agent": "pjm-agent"},
        trace_id="trace-evo",
    )

    assert result == {"operation": "add_skill", "target_agent": "pjm-agent"}
    assert proposal_store.company_ids == ["cmp_wisdoverse_cell"]
    assert proposal_store.proposals == []


def test_infer_tier_and_scope_are_explicit() -> None:
    assert EvolutionProposalApprovalUseCase.infer_proposal_tier(
        {"pattern_id": "pat_1"}
    ) == EvolutionTier.L3
    assert EvolutionProposalApprovalUseCase.infer_proposal_tier(
        {"operation": "modify_event_subscription"}
    ) == EvolutionTier.L2
    assert EvolutionProposalApprovalUseCase.infer_proposal_tier(
        {"operation": "add_skill"}
    ) == EvolutionTier.L1
    assert EvolutionProposalApprovalUseCase.proposal_scope(
        {"pattern_id": "pat_1"},
        EvolutionTier.L3,
    ) == "pattern:pat_1"
    assert EvolutionProposalApprovalUseCase.proposal_scope(
        {"target_agent": "pjm-agent", "target_skill": "decompose"},
        EvolutionTier.L1,
    ) == "agent:pjm-agent/skill:decompose"
