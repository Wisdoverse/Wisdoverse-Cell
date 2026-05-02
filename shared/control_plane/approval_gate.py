"""Shared human-in-the-loop approval gate."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import settings

from .context import get_current_run_context
from .models import ApprovalCategory, ApprovalRequest, ApprovalStatus
from .repository import ControlPlaneRepository
from .tables import ApprovalRequestTable


class ApprovalRequiredError(PermissionError):
    """Raised when a sensitive action has not been approved."""


@dataclass(frozen=True)
class ApprovalDecision:
    approval_id: str
    status: str
    approved: bool


class ApprovalGate:
    """Creates and enforces SPEC approval requests."""

    def __init__(self, repo: ControlPlaneRepository):
        self._repo = repo

    async def request_approval(
        self,
        *,
        company_id: str,
        category: ApprovalCategory,
        requested_by: str,
        source_agent_id: str,
        proposed_action: str,
        reason: str,
        risk: str,
        rollback_note: str,
        affected_resources: list[str] | None = None,
        artifact_links: list[str] | None = None,
        run_id: str | None = None,
        work_item_id: str | None = None,
        goal_id: str | None = None,
        trace_id: str | None = None,
    ) -> ApprovalRequestTable:
        return await self._repo.request_approval(
            ApprovalRequest(
                company_id=company_id,
                category=category,
                requested_by=requested_by,
                source_agent_id=source_agent_id,
                proposed_action=proposed_action,
                reason=reason,
                risk=risk,
                rollback_note=rollback_note,
                affected_resources=affected_resources or [],
                artifact_links=artifact_links or [],
                run_id=run_id,
                work_item_id=work_item_id,
                goal_id=goal_id,
                trace_id=trace_id,
            )
        )

    async def approve(self, approval_id: str, *, resolved_by: str) -> ApprovalDecision:
        row = await self._repo.resolve_approval(
            approval_id,
            status=ApprovalStatus.APPROVED,
            resolved_by=resolved_by,
        )
        if row is None:
            raise ApprovalRequiredError(f"approval_not_found: {approval_id}")
        return ApprovalDecision(
            approval_id=row.approval_id,
            status=row.status,
            approved=True,
        )

    async def reject(self, approval_id: str, *, resolved_by: str) -> ApprovalDecision:
        row = await self._repo.resolve_approval(
            approval_id,
            status=ApprovalStatus.REJECTED,
            resolved_by=resolved_by,
        )
        if row is None:
            raise ApprovalRequiredError(f"approval_not_found: {approval_id}")
        return ApprovalDecision(
            approval_id=row.approval_id,
            status=row.status,
            approved=False,
        )

    async def ensure_approved(self, approval_id: str) -> ApprovalDecision:
        row = await self._repo.get_approval(approval_id)
        if row is None:
            raise ApprovalRequiredError(f"approval_not_found: {approval_id}")
        if row.status != ApprovalStatus.APPROVED.value:
            raise ApprovalRequiredError(
                f"approval_required: {approval_id} status={row.status}"
            )
        return ApprovalDecision(
            approval_id=row.approval_id,
            status=row.status,
            approved=True,
        )


SessionProvider = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class ApprovalGateService:
    """Session-owning approval gate for runtime-sensitive actions."""

    def __init__(
        self,
        *,
        source_agent_id: str,
        session_provider: SessionProvider | None = None,
        default_company_id: str | None = None,
        enabled: bool | None = None,
        enforced: bool | None = None,
    ) -> None:
        self._source_agent_id = source_agent_id
        self._session_provider = session_provider
        self._default_company_id = default_company_id
        self._enabled = enabled
        self._enforced = enforced

    @property
    def enabled(self) -> bool:
        if self._enabled is not None:
            return self._enabled
        return settings.control_plane_enabled or settings.control_plane_approval_enforced

    @property
    def enforced(self) -> bool:
        if self._enforced is not None:
            return self._enforced
        return settings.control_plane_approval_enforced

    async def request_approval(
        self,
        *,
        category: ApprovalCategory,
        requested_by: str | None = None,
        proposed_action: str,
        reason: str,
        risk: str,
        rollback_note: str,
        affected_resources: list[str] | None = None,
        artifact_links: list[str] | None = None,
        company_id: str | None = None,
        run_id: str | None = None,
        work_item_id: str | None = None,
        goal_id: str | None = None,
        trace_id: str | None = None,
    ) -> ApprovalRequestTable | None:
        if not self.enabled:
            return None

        context = get_current_run_context()
        resolved_company_id = (
            company_id
            or (context.company_id if context is not None else None)
            or self._default_company_id
            or settings.control_plane_company_id
        )
        resolved_run_id = run_id or (context.run_id if context is not None else None)
        resolved_work_item_id = work_item_id or (
            context.work_item_id if context is not None else None
        )
        resolved_goal_id = goal_id or (context.goal_id if context is not None else None)
        resolved_trace_id = trace_id or (context.trace_id if context is not None else None)

        async with self._resolve_session_provider()() as session:
            gate = ApprovalGate(ControlPlaneRepository(session))
            return await gate.request_approval(
                company_id=resolved_company_id,
                category=category,
                requested_by=requested_by or f"agent:{self._source_agent_id}",
                source_agent_id=self._source_agent_id,
                proposed_action=proposed_action,
                reason=reason,
                risk=risk,
                rollback_note=rollback_note,
                affected_resources=affected_resources,
                artifact_links=artifact_links,
                run_id=resolved_run_id,
                work_item_id=resolved_work_item_id,
                goal_id=resolved_goal_id,
                trace_id=resolved_trace_id,
            )

    async def approve_for_sensitive_action(
        self,
        approval_id: str | None,
        *,
        resolved_by: str,
    ) -> ApprovalDecision | None:
        if not self.enabled:
            return None
        if not approval_id:
            if self.enforced:
                raise ApprovalRequiredError("control_plane_approval_required")
            return None
        async with self._resolve_session_provider()() as session:
            gate = ApprovalGate(ControlPlaneRepository(session))
            return await gate.approve(approval_id, resolved_by=resolved_by)

    async def reject_for_sensitive_action(
        self,
        approval_id: str | None,
        *,
        resolved_by: str,
    ) -> ApprovalDecision | None:
        if not self.enabled:
            return None
        if not approval_id:
            if self.enforced:
                raise ApprovalRequiredError("control_plane_approval_required")
            return None
        async with self._resolve_session_provider()() as session:
            gate = ApprovalGate(ControlPlaneRepository(session))
            return await gate.reject(approval_id, resolved_by=resolved_by)

    def _resolve_session_provider(self) -> SessionProvider:
        if self._session_provider is not None:
            return self._session_provider

        from shared.control_plane.database import control_plane_db_manager

        return control_plane_db_manager.session
