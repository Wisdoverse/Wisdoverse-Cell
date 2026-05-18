"""Ports for Evolution control-plane persistence."""

from typing import Any, Protocol

from shared.control_plane import EvolutionTier


class EvolutionControlPlaneProposalStore(Protocol):
    """Persistence port for Evolution control-plane records."""

    async def ensure_company(self, company_id: str) -> None:
        """Ensure the target company context exists."""

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
        """Create an evolution proposal and matching audit event."""
