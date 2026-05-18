"""Application use cases for Evolution agent requests."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol


class EvolutionAnalyzerPort(Protocol):
    """Trace-analysis operation required by Evolution request handling."""

    async def analyze(self, days: int) -> list[dict[str, Any]]:
        """Analyze recent traces and produce proposal payloads."""


AttachProposalApproval = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class EvolutionRequestUseCase:
    """Dispatch and execute Evolution agent request actions."""

    def __init__(
        self,
        *,
        analyzer: EvolutionAnalyzerPort,
        attach_proposal_approval: AttachProposalApproval,
    ):
        self._analyzer = analyzer
        self._attach_proposal_approval = attach_proposal_approval

    async def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        if request.get("action") == "trigger_analysis":
            days = request.get("days", 7)
            proposals = await self._analyzer.analyze(days)
            proposals = [
                await self._attach_proposal_approval(proposal)
                for proposal in proposals
            ]
            return {"proposals": proposals}
        return {"status": "ok"}
