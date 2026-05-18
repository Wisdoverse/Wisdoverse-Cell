"""Per-request store factory for control-plane HTTP handlers.

Closes part of Phase 1 audit H5 / P1-3: route handlers should not depend
on `AsyncSession` directly. They depend on a `ControlPlaneStores`
factory that exposes per-aggregate stores. The factory hides the
session inside, which keeps the SQLAlchemy concern out of the
interface layer.

Adoption is gradual. Migration Plan §Stage 1 item 3 says to hide
``AsyncSession`` from route handlers; this module provides the seam.
Existing routes that still receive ``AsyncSession`` directly remain
correct — new routes (and future PRs that touch existing ones) should
prefer this factory.

Stores are instantiated lazily on first attribute access so that
routes that touch only one aggregate do not pay for unrelated store
construction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from .agent_operation_store import SqlAlchemyControlPlaneAgentOperationStore
    from .agent_registry_store import SqlAlchemyControlPlaneAgentRegistryStore
    from .agent_run_store import SqlAlchemyControlPlaneAgentRunStore
    from .approval_store import SqlAlchemyControlPlaneApprovalStore
    from .artifact_store import SqlAlchemyControlPlaneArtifactStore
    from .audit_timeline_store import SqlAlchemyControlPlaneAuditTimelineStore
    from .budget_store import SqlAlchemyControlPlaneBudgetStore
    from .company_store import SqlAlchemyControlPlaneCompanyStore
    from .decision_store import SqlAlchemyControlPlaneDecisionStore
    from .evolution_proposal_store import SqlAlchemyControlPlaneEvolutionProposalStore
    from .goal_store import SqlAlchemyControlPlaneGoalStore
    from .prompt_config_store import SqlAlchemyControlPlanePromptConfigStore
    from .work_item_store import SqlAlchemyControlPlaneWorkItemStore


class ControlPlaneStores:
    """Per-request factory of control-plane SqlAlchemy stores.

    Route handlers receive an instance of this class instead of a raw
    ``AsyncSession``. The session stays internal; handlers reach
    per-aggregate stores by attribute access.
    """

    __slots__ = ("_session",)

    def __init__(self, session: "AsyncSession") -> None:
        self._session = session

    @property
    def companies(self) -> "SqlAlchemyControlPlaneCompanyStore":
        from .company_store import SqlAlchemyControlPlaneCompanyStore

        return SqlAlchemyControlPlaneCompanyStore(self._session)

    @property
    def goals(self) -> "SqlAlchemyControlPlaneGoalStore":
        from .goal_store import SqlAlchemyControlPlaneGoalStore

        return SqlAlchemyControlPlaneGoalStore(self._session)

    @property
    def work_items(self) -> "SqlAlchemyControlPlaneWorkItemStore":
        from .work_item_store import SqlAlchemyControlPlaneWorkItemStore

        return SqlAlchemyControlPlaneWorkItemStore(self._session)

    @property
    def agent_runs(self) -> "SqlAlchemyControlPlaneAgentRunStore":
        from .agent_run_store import SqlAlchemyControlPlaneAgentRunStore

        return SqlAlchemyControlPlaneAgentRunStore(self._session)

    @property
    def agent_operations(self) -> "SqlAlchemyControlPlaneAgentOperationStore":
        from .agent_operation_store import SqlAlchemyControlPlaneAgentOperationStore

        return SqlAlchemyControlPlaneAgentOperationStore(self._session)

    @property
    def agent_registry(self) -> "SqlAlchemyControlPlaneAgentRegistryStore":
        from .agent_registry_store import SqlAlchemyControlPlaneAgentRegistryStore

        return SqlAlchemyControlPlaneAgentRegistryStore(self._session)

    @property
    def approvals(self) -> "SqlAlchemyControlPlaneApprovalStore":
        from .approval_store import SqlAlchemyControlPlaneApprovalStore

        return SqlAlchemyControlPlaneApprovalStore(self._session)

    @property
    def artifacts(self) -> "SqlAlchemyControlPlaneArtifactStore":
        from .artifact_store import SqlAlchemyControlPlaneArtifactStore

        return SqlAlchemyControlPlaneArtifactStore(self._session)

    @property
    def audit_timeline(self) -> "SqlAlchemyControlPlaneAuditTimelineStore":
        from .audit_timeline_store import SqlAlchemyControlPlaneAuditTimelineStore

        return SqlAlchemyControlPlaneAuditTimelineStore(self._session)

    @property
    def budgets(self) -> "SqlAlchemyControlPlaneBudgetStore":
        from .budget_store import SqlAlchemyControlPlaneBudgetStore

        return SqlAlchemyControlPlaneBudgetStore(self._session)

    @property
    def decisions(self) -> "SqlAlchemyControlPlaneDecisionStore":
        from .decision_store import SqlAlchemyControlPlaneDecisionStore

        return SqlAlchemyControlPlaneDecisionStore(self._session)

    @property
    def evolution_proposals(self) -> "SqlAlchemyControlPlaneEvolutionProposalStore":
        from .evolution_proposal_store import (
            SqlAlchemyControlPlaneEvolutionProposalStore,
        )

        return SqlAlchemyControlPlaneEvolutionProposalStore(self._session)

    @property
    def prompt_configs(self) -> "SqlAlchemyControlPlanePromptConfigStore":
        from .prompt_config_store import SqlAlchemyControlPlanePromptConfigStore

        return SqlAlchemyControlPlanePromptConfigStore(self._session)


__all__ = ["ControlPlaneStores"]
