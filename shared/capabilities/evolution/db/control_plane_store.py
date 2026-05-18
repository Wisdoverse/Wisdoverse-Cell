"""Control-plane persistence adapter for Evolution proposals."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane import EvolutionTier
from shared.control_plane.evolution_proposal_store import (
    SqlAlchemyControlPlaneEvolutionProposalStore,
)
from shared.control_plane.evolution_proposal_use_cases import (
    ensure_evolution_proposal_company,
    record_evolution_proposal_with_audit,
)

from ..core.control_plane_ports import EvolutionControlPlaneProposalStore

ControlPlaneSessionProvider = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def default_control_plane_session_provider() -> ControlPlaneSessionProvider:
    """Return the default Control Plane database session provider."""
    from shared.control_plane.database import control_plane_db_manager

    return control_plane_db_manager.session


class SqlAlchemyEvolutionControlPlaneProposalStore(EvolutionControlPlaneProposalStore):
    """SQLAlchemy-backed control-plane proposal store."""

    def __init__(self, session_provider: ControlPlaneSessionProvider):
        self._session_provider = session_provider

    async def ensure_company(self, company_id: str) -> None:
        async with self._session_provider() as session:
            await ensure_evolution_proposal_company(
                SqlAlchemyControlPlaneEvolutionProposalStore(session),
                company_id=company_id,
            )

    async def record_proposal(
        self,
        *,
        company_id: str,
        tier: EvolutionTier,
        scope: str,
        evidence: dict[str, Any],
        expected_benefit: str,
        risk: str,
        approval_state: str,
        approval_id: str | None,
        metadata: dict[str, Any],
        actor_id: str,
        trace_id: str | None,
    ) -> str:
        async with self._session_provider() as session:
            row = await record_evolution_proposal_with_audit(
                SqlAlchemyControlPlaneEvolutionProposalStore(session),
                company_id=company_id,
                tier=tier,
                scope=scope,
                evidence=evidence,
                expected_benefit=expected_benefit,
                risk=risk,
                approval_state=approval_state,
                approval_id=approval_id,
                metadata=metadata,
                actor_id=actor_id,
                trace_id=trace_id,
            )
            return row.proposal_id
