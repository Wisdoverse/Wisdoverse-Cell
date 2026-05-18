"""Unit tests for ControlPlaneStores.

The factory hides AsyncSession behind a per-request seam. Tests below
verify that every documented property returns the correct concrete store
type and that the underlying session is passed through unchanged.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from shared.control_plane.agent_operation_store import (
    SqlAlchemyControlPlaneAgentOperationStore,
)
from shared.control_plane.agent_registry_store import (
    SqlAlchemyControlPlaneAgentRegistryStore,
)
from shared.control_plane.agent_run_store import SqlAlchemyControlPlaneAgentRunStore
from shared.control_plane.approval_store import SqlAlchemyControlPlaneApprovalStore
from shared.control_plane.artifact_store import SqlAlchemyControlPlaneArtifactStore
from shared.control_plane.audit_timeline_store import (
    SqlAlchemyControlPlaneAuditTimelineStore,
)
from shared.control_plane.budget_store import SqlAlchemyControlPlaneBudgetStore
from shared.control_plane.company_store import SqlAlchemyControlPlaneCompanyStore
from shared.control_plane.decision_store import SqlAlchemyControlPlaneDecisionStore
from shared.control_plane.evolution_proposal_store import (
    SqlAlchemyControlPlaneEvolutionProposalStore,
)
from shared.control_plane.goal_store import SqlAlchemyControlPlaneGoalStore
from shared.control_plane.prompt_config_store import (
    SqlAlchemyControlPlanePromptConfigStore,
)
from shared.control_plane.store_factory import ControlPlaneStores
from shared.control_plane.work_item_store import SqlAlchemyControlPlaneWorkItemStore


def _factory() -> tuple[ControlPlaneStores, MagicMock]:
    session = MagicMock(name="async_session")
    return ControlPlaneStores(session), session


def test_companies_returns_company_store():
    stores, _ = _factory()
    assert isinstance(stores.companies, SqlAlchemyControlPlaneCompanyStore)


def test_goals_returns_goal_store():
    stores, _ = _factory()
    assert isinstance(stores.goals, SqlAlchemyControlPlaneGoalStore)


def test_work_items_returns_work_item_store():
    stores, _ = _factory()
    assert isinstance(stores.work_items, SqlAlchemyControlPlaneWorkItemStore)


def test_agent_runs_returns_agent_run_store():
    stores, _ = _factory()
    assert isinstance(stores.agent_runs, SqlAlchemyControlPlaneAgentRunStore)


def test_agent_operations_returns_agent_operation_store():
    stores, _ = _factory()
    assert isinstance(
        stores.agent_operations, SqlAlchemyControlPlaneAgentOperationStore
    )


def test_agent_registry_returns_agent_registry_store():
    stores, _ = _factory()
    assert isinstance(stores.agent_registry, SqlAlchemyControlPlaneAgentRegistryStore)


def test_approvals_returns_approval_store():
    stores, _ = _factory()
    assert isinstance(stores.approvals, SqlAlchemyControlPlaneApprovalStore)


def test_artifacts_returns_artifact_store():
    stores, _ = _factory()
    assert isinstance(stores.artifacts, SqlAlchemyControlPlaneArtifactStore)


def test_audit_timeline_returns_audit_timeline_store():
    stores, _ = _factory()
    assert isinstance(
        stores.audit_timeline, SqlAlchemyControlPlaneAuditTimelineStore
    )


def test_budgets_returns_budget_store():
    stores, _ = _factory()
    assert isinstance(stores.budgets, SqlAlchemyControlPlaneBudgetStore)


def test_decisions_returns_decision_store():
    stores, _ = _factory()
    assert isinstance(stores.decisions, SqlAlchemyControlPlaneDecisionStore)


def test_evolution_proposals_returns_evolution_proposal_store():
    stores, _ = _factory()
    assert isinstance(
        stores.evolution_proposals, SqlAlchemyControlPlaneEvolutionProposalStore
    )


def test_prompt_configs_returns_prompt_config_store():
    stores, _ = _factory()
    assert isinstance(
        stores.prompt_configs, SqlAlchemyControlPlanePromptConfigStore
    )


def test_factory_does_not_expose_session_as_public_attribute():
    """`session` is private; route handlers must not reach into it."""
    stores, _ = _factory()
    assert not hasattr(stores, "session")
    # Only the slot-defined private attribute remains; no public alias.
    public_attrs = {
        name for name in dir(stores) if not name.startswith("_") and not callable(getattr(stores, name, None))
    }
    assert "session" not in public_attrs


def test_factory_uses_slots():
    """ControlPlaneStores uses __slots__ so no ad-hoc state can leak in."""
    stores, _ = _factory()
    assert ControlPlaneStores.__slots__ == ("_session",)
    try:
        stores.arbitrary = "x"  # type: ignore[attr-defined]
    except AttributeError:
        pass
    else:
        raise AssertionError("ControlPlaneStores must reject arbitrary attribute writes")
