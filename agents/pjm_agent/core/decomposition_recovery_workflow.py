"""Recovery and query workflow for PJM decomposition records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from shared.core import request_error
from shared.core.identifiers import OpenProjectProjectId, WorkPackageId
from shared.schemas.event import Event, EventTypes

from .decomposition_ports import PJMDecompositionStore
from .domain.decomposition_policy import DecompositionRetryDecision, DecompositionWorkflowPolicy


class PJMOpenProjectReadPort(Protocol):
    async def get_work_package(self, wp_id: WorkPackageId) -> dict:
        """Fetch one OpenProject work package."""


@dataclass(frozen=True)
class StagedRecoveryEvent:
    """Event staged in the local PJM transaction and ready to publish."""

    event: Event
    wp_id: WorkPackageId | None = None


@dataclass(frozen=True)
class DecompositionRecoveryResult:
    """Recovery workflow response plus post-commit events ready for publish."""

    response: dict
    staged_events: tuple[StagedRecoveryEvent, ...] = ()


class DecompositionRecoveryWorkflow:
    """Owns retry and query behavior for persisted decompositions."""

    def __init__(
        self,
        *,
        decomposition_store: PJMDecompositionStore | None,
        op_client: PJMOpenProjectReadPort | None,
    ) -> None:
        self._decomposition_store = decomposition_store
        self._op = op_client
        self._workflow_policy = DecompositionWorkflowPolicy()

    def _require_decomposition_store(self) -> PJMDecompositionStore:
        if self._decomposition_store is None:
            raise RuntimeError("pjm_decomposition_store_not_configured")
        return self._decomposition_store

    async def retry_decompose(self, wp_id: WorkPackageId | None) -> DecompositionRecoveryResult:
        """Retry a failed/rejected decomposition by re-fetching WP data from OP."""
        if not wp_id:
            return DecompositionRecoveryResult(request_error("wp_id is required", "wp_id_required"))
        async with self._require_decomposition_store().transaction() as decomposition:
            record = await decomposition.get_by_wp_id(wp_id)
            retry_decision = self._workflow_policy.retry_decision(record.status if record else None)
            if not retry_decision.allowed:
                return self._retry_blocked_result(retry_decision)
            project_id: OpenProjectProjectId = record.project_id
            assignee_id = record.assignee_id

        try:
            if self._op is None:
                return DecompositionRecoveryResult(
                    request_error(
                        "openproject port not configured",
                        "openproject_port_not_configured",
                    )
                )
            wp = await self._op.get_work_package(wp_id)
            subject = wp.get("subject", "")
            description_raw = wp.get("description", {})
            description = (
                description_raw.get("raw", "") if isinstance(description_raw, dict) else ""
            )
            wp_type = wp.get("_links", {}).get("type", {}).get("title", "Feature")
            project_name = wp.get("_links", {}).get("project", {}).get("title", "")
            assignee_name = wp.get("_links", {}).get("assignee", {}).get("title", "")
        except Exception as exc:
            return DecompositionRecoveryResult(
                request_error(
                    f"failed to fetch WP from OP: {exc}",
                    "openproject_work_package_fetch_failed",
                    wp_id=wp_id,
                )
            )

        event = Event.create(
            event_type=EventTypes.SYNC_TASK_NEEDS_DECOMPOSE,
            source_agent="pjm-agent",
            payload={
                "wp_id": wp_id,
                "subject": subject,
                "description": description,
                "wp_type": wp_type,
                "project_id": project_id,
                "project_name": project_name,
                "assignee": assignee_name,
                "assignee_id": assignee_id,
            },
        )
        async with self._require_decomposition_store().transaction() as decomposition:
            record = await decomposition.get_by_wp_id(wp_id)
            retry_decision = self._workflow_policy.retry_decision(record.status if record else None)
            if not retry_decision.allowed:
                return self._retry_blocked_result(retry_decision)
            await decomposition.delete_by_wp_id(wp_id)
            await decomposition.stage_event(event)
            await decomposition.commit()

        return DecompositionRecoveryResult(
            {"status": "retrying", "wp_id": wp_id},
            (StagedRecoveryEvent(event, wp_id=wp_id),),
        )

    async def get_decompose(self, wp_id: WorkPackageId | None) -> dict:
        """Retrieve decomposition record for a given work package."""
        if not wp_id:
            return {}
        async with self._require_decomposition_store().transaction() as decomposition:
            record = await decomposition.get_by_wp_id(wp_id)
            if not record:
                return {}
            return {
                "wp_id": record.wp_id,
                "project_id": record.project_id,
                "status": record.status,
                "assignee_id": record.assignee_id,
                "decompose_result": record.decompose_result,
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
                "approved_by": record.approved_by,
            }

    def _retry_blocked_result(
        self, retry_decision: DecompositionRetryDecision
    ) -> DecompositionRecoveryResult:
        extra = {"status": retry_decision.status} if retry_decision.status else {}
        return DecompositionRecoveryResult(
            request_error(
                retry_decision.error_message or "retry not allowed",
                retry_decision.error_code or "pm.decomposition_retry_not_allowed",
                **extra,
            )
        )
