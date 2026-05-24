"""Tests for approval resolution domain service effects."""

from shared.control_plane.domain.approval_resolution import ApprovalResolutionPolicy
from shared.control_plane.domain.services import ControlPlaneDomainService
from shared.control_plane.models import ApprovalStatus, EvolutionRolloutState


def test_approval_resolution_policy_implements_domain_service_contract() -> None:
    policy = ApprovalResolutionPolicy()

    assert isinstance(policy, ControlPlaneDomainService)
    assert policy.service_name == "ApprovalResolutionPolicy"


def test_approval_resolution_policy_builds_approved_effect() -> None:
    effect = ApprovalResolutionPolicy().resolve(approved=True)

    assert effect.approved is True
    assert effect.approval_status == ApprovalStatus.APPROVED
    assert effect.proposal_update_kwargs() == {
        "approval_state": ApprovalStatus.APPROVED.value,
        "rollout_state": None,
    }
    assert effect.proposal_audit_detail(
        proposal_id="evo_test",
        approval_id="appr_test",
    ) == {
        "proposal_id": "evo_test",
        "approval_state": ApprovalStatus.APPROVED.value,
        "approval_id": "appr_test",
    }


def test_approval_resolution_policy_builds_rejected_effect() -> None:
    effect = ApprovalResolutionPolicy().resolve(approved=False)

    assert effect.approved is False
    assert effect.approval_status == ApprovalStatus.REJECTED
    assert effect.proposal_update_kwargs() == {
        "approval_state": ApprovalStatus.REJECTED.value,
        "rollout_state": EvolutionRolloutState.REJECTED.value,
    }
    assert effect.proposal_audit_detail(
        proposal_id="evo_test",
        approval_id="appr_test",
    ) == {
        "proposal_id": "evo_test",
        "approval_state": ApprovalStatus.REJECTED.value,
        "approval_id": "appr_test",
        "rollout_state": EvolutionRolloutState.REJECTED.value,
    }
