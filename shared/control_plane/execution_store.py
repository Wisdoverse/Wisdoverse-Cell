"""PostgreSQL dispatch ledger. Locks are released before calling an executor."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .approval_store import SqlAlchemyControlPlaneApprovalStore
from .audit_event_store import SqlAlchemyControlPlaneAuditEventStore
from .budget_store import SqlAlchemyControlPlaneBudgetStore
from .domain.agent_wakeup_adapter import AgentWakeupAdapterConfig
from .domain.audit_retention import audit_detail_for_storage
from .domain.execution_policy import ExecutionDenied, authorize_adapter, intent_hash, period_start
from .domain.work_item import WorkItem as WorkItemAggregate
from .domain_event_audit import DomainEventAuditContext, append_control_plane_domain_event_audits
from .domain_records import agent_role_record, work_item_record
from .execution_control_use_cases import validate_execution_control
from .execution_models import ExecutionLeaseTable, ExecutionReservationTable
from .execution_ports import ExecutionTicket
from .models import ApprovalCategory, ApprovalRequest, AuditEvent, BudgetUsage
from .tables import (
    AgentRoleTable,
    AgentRunTable,
    ApprovalRequestTable,
    BudgetPolicyTable,
    BudgetUsageTable,
    CompanyContextTable,
    WorkItemTable,
)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class SqlAlchemyExecutionGovernanceStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def checkpoint(self) -> None:
        await self._session.commit()

    async def claim(
        self,
        agent: Any,
        *,
        run_id: str,
        payload: dict[str, Any],
        work_item_id: str | None,
        goal_id: str | None,
        actor_id: str,
        idempotency_key: str,
    ) -> ExecutionTicket:
        try:
            return await self._claim(
                agent,
                run_id=run_id,
                payload=payload,
                work_item_id=work_item_id,
                goal_id=goal_id,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
            )
        except ExecutionDenied as exc:
            if await self._session.get(CompanyContextTable, agent.company_id) is not None:
                resource = f"work:{work_item_id}" if work_item_id else f"agent:{agent.agent_id}"
                await self._audit(
                    agent.company_id,
                    resource,
                    "execution.denied",
                    actor_id,
                    {"reason": exc.reason, "external_dispatch": False},
                )
                await self.checkpoint()
            raise

    async def _claim(
        self,
        agent: Any,
        *,
        run_id: str,
        payload: dict[str, Any],
        work_item_id: str | None,
        goal_id: str | None,
        actor_id: str,
        idempotency_key: str,
    ) -> ExecutionTicket:
        now = datetime.now(UTC)
        # A company lock orders claims and multi-policy reservations consistently.
        company = await self._session.scalar(
            select(CompanyContextTable)
            .where(CompanyContextTable.company_id == agent.company_id)
            .with_for_update()
        )
        if company is None:
            raise ExecutionDenied("company_not_found", 404)
        row = await self._session.scalar(
            select(AgentRoleTable)
            .where(
                AgentRoleTable.company_id == agent.company_id,
                AgentRoleTable.agent_id == agent.agent_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise ExecutionDenied("agent_not_found", 404)
        current = agent_role_record(row)
        ceiling = authorize_adapter(current)
        digest = intent_hash(current, payload, work_item_id)
        if digest != intent_hash(agent, payload, work_item_id):
            raise ExecutionDenied("execution_configuration_changed")
        digest = hashlib.sha256(f"{digest}:{idempotency_key}:{actor_id}".encode()).hexdigest()
        execution_id = hashlib.sha256(f"{agent.company_id}:{idempotency_key}".encode()).hexdigest()
        existing = await self._session.get(ExecutionLeaseTable, execution_id)
        if existing:
            if existing.intent_hash != digest:
                raise ExecutionDenied("idempotency_key_conflict")
            if existing.state in {"succeeded", "failed"}:
                return ExecutionTicket(
                    execution_id, existing.run_id, existing.owner_id, ceiling, True
                )
            await self._mark_abandoned(existing, now)
            raise ExecutionDenied(
                "execution_recovery_required"
                if existing.state == "recovery_required"
                else "execution_in_progress"
            )
        resource = f"work:{work_item_id}" if work_item_id else f"agent:{agent.agent_id}"
        active = await self._session.scalar(
            select(ExecutionLeaseTable).where(
                ExecutionLeaseTable.company_id == agent.company_id,
                ExecutionLeaseTable.resource_id == resource,
                ExecutionLeaseTable.state.in_(["running", "recovery_required"]),
            )
        )
        if active:
            await self._mark_abandoned(active, now)
            raise ExecutionDenied(
                "execution_recovery_required"
                if active.state == "recovery_required"
                else "execution_in_progress"
            )
        if payload.get("trigger") == "heartbeat":
            latest = await self._session.scalar(
                select(AgentRunTable)
                .where(
                    AgentRunTable.company_id == agent.company_id,
                    AgentRunTable.agent_id == agent.agent_id,
                )
                .order_by(AgentRunTable.started_at.desc(), AgentRunTable.run_id.desc())
                .limit(1)
            )
            interval = AgentWakeupAdapterConfig.from_agent_role(
                current
            ).heartbeat_interval_seconds()
            if (
                latest
                and (now - _utc(latest.completed_at or latest.started_at)).total_seconds()
                < interval
            ):
                raise ExecutionDenied("heartbeat_interval_not_elapsed")
        work = (
            await self._session.get(WorkItemTable, work_item_id, populate_existing=True)
            if work_item_id
            else None
        )
        if work_item_id and (work is None or work.company_id != agent.company_id):
            raise ExecutionDenied("work_item_not_found", 404)
        if work and work.status in {"completed", "cancelled"}:
            raise ExecutionDenied("work_item_closed")
        if work:
            for dependency_id in work.dependencies or []:
                dependency = await self._session.get(WorkItemTable, dependency_id)
                if (
                    dependency is None
                    or dependency.company_id != work.company_id
                    or dependency.status != "completed"
                ):
                    raise ExecutionDenied("work_item_dependency_not_accepted", 403)
        # Approval binds the reviewed configuration and concrete input, not a label.
        requires_approval = (
            bool(work and work.approval_required)
            or current.escalation_policy.get("approval_required") is True
        )
        approved = None
        if requires_approval:
            approvals = (
                await self._session.scalars(
                    select(ApprovalRequestTable).where(
                        ApprovalRequestTable.company_id == agent.company_id,
                        ApprovalRequestTable.source_agent_id == agent.agent_id,
                        ApprovalRequestTable.metadata_json["execution_intent_hash"].as_string()
                        == digest,
                    )
                )
            ).all()
            valid = [a for a in approvals if a.expires_at and _utc(a.expires_at) > now]
            approved = next(
                (
                    a
                    for a in valid
                    if a.status == "approved"
                    and not (a.metadata_json or {}).get("consumed_execution_id")
                ),
                None,
            )
            if approved is None:
                if not any(a.status == "pending" for a in valid):
                    await SqlAlchemyControlPlaneApprovalStore(self._session).request_approval(
                        ApprovalRequest(
                            company_id=agent.company_id,
                            category=ApprovalCategory.TECHNICAL,
                            requested_by=actor_id,
                            source_agent_id=agent.agent_id,
                            proposed_action=f"Execute {resource} using {agent.adapter_type}",
                            reason="Review the bound dispatch intent before any executor call.",
                            risk="The executor can produce external effects and incur the declared cost ceiling.",
                            rollback_note="Pause the role; uncertain external effects require reconciliation.",
                            affected_resources=[resource],
                            work_item_id=work_item_id,
                            goal_id=goal_id,
                            expires_at=now + timedelta(hours=24),
                            metadata={
                                "execution_intent_hash": digest,
                                "execution_key": idempotency_key,
                                "reviewed_parameters": audit_detail_for_storage(payload),
                                "reviewed_adapter_type": agent.adapter_type,
                                "cost_ceiling_usd": str(ceiling),
                            },
                        )
                    )
                if work:
                    await self._transition_work(work, "awaiting_approval", actor_id)
                await self._audit(
                    agent.company_id,
                    resource,
                    "execution.approval_required",
                    actor_id,
                    {"intent_hash": digest},
                )
                await self.checkpoint()
                raise ExecutionDenied("execution_approval_required", 403)
        lease = ExecutionLeaseTable(
            execution_id=execution_id,
            company_id=agent.company_id,
            resource_id=resource,
            intent_hash=digest,
            run_id=run_id,
            owner_id=uuid4().hex,
            state="running",
            expires_at=now + timedelta(seconds=1000),
            created_at=now,
        )
        policies = (
            await self._session.scalars(
                select(BudgetPolicyTable)
                .where(
                    BudgetPolicyTable.company_id == agent.company_id,
                    BudgetPolicyTable.status == "active",
                )
                .order_by(BudgetPolicyTable.budget_id)
                .with_for_update()
            )
        ).all()
        selected = [
            p
            for p in policies
            if p.scope == "company"
            or (p.scope == "agent" and p.scope_id == agent.agent_id)
            or (p.scope == "work_item" and p.scope_id == work_item_id)
            or (p.scope == "goal" and p.scope_id == goal_id)
            or p.budget_id == current.budget_policy_id
        ]
        if ceiling > 0 and not selected:
            raise ExecutionDenied("execution_budget_required", 403)
        if current.budget_policy_id and not any(
            p.budget_id == current.budget_policy_id for p in selected
        ):
            raise ExecutionDenied("execution_budget_inactive", 403)
        reservations = []
        for policy in selected:
            model = str(
                current.adapter_config.get("model")
                or current.adapter_config.get("target_model")
                or ""
            )
            if policy.model_allowlist and model not in policy.model_allowlist:
                raise ExecutionDenied("execution_model_not_allowed", 403)
            start = period_start(policy.period, now)
            consumed = await self._session.scalar(
                select(func.coalesce(func.sum(BudgetUsageTable.cost_usd), 0)).where(
                    BudgetUsageTable.budget_id == policy.budget_id,
                    BudgetUsageTable.created_at >= start,
                )
            )
            reserved = await self._session.scalar(
                select(func.coalesce(func.sum(ExecutionReservationTable.amount_usd), 0)).where(
                    ExecutionReservationTable.budget_id == policy.budget_id,
                    ExecutionReservationTable.state == "reserved",
                )
            )
            if Decimal(str(consumed or 0)) + Decimal(str(reserved or 0)) + ceiling > Decimal(
                str(policy.limit_usd)
            ):
                raise ExecutionDenied("execution_budget_exceeded", 403)
            reservations.append(
                ExecutionReservationTable(
                    execution_id=execution_id,
                    budget_id=policy.budget_id,
                    amount_usd=ceiling,
                    state="reserved",
                    created_at=now,
                )
            )
        self._session.add(lease)
        if approved is not None:
            approved.metadata_json = {
                **approved.metadata_json,
                "consumed_execution_id": execution_id,
            }
            approved.run_id = run_id
        await self._session.flush()
        self._session.add_all(reservations)
        if work:
            await self._transition_work(work, "running", actor_id)
            metadata = dict(work.metadata_json or {})
            metadata.pop("acceptance_id", None)
            metadata.pop("accepted_artifact_id", None)
            work.metadata_json = metadata
        await self._audit(
            agent.company_id,
            resource,
            "execution.claimed",
            actor_id,
            {"execution_id": execution_id, "intent_hash": digest, "ceiling_usd": str(ceiling)},
        )
        return ExecutionTicket(execution_id, run_id, lease.owner_id, ceiling)

    async def control_action(self, ticket: ExecutionTicket) -> str:
        value = await self._session.scalar(
            select(ExecutionLeaseTable.control_action).where(
                ExecutionLeaseTable.execution_id == ticket.execution_id,
                ExecutionLeaseTable.owner_id == ticket.owner_id,
            )
        )
        return str(value or "terminate")

    async def mark_uncertain(self, ticket: ExecutionTicket) -> None:
        lease = await self._session.get(ExecutionLeaseTable, ticket.execution_id)
        if lease is None or lease.owner_id != ticket.owner_id:
            raise ExecutionDenied("execution_owner_lost")
        lease.state = "recovery_required"
        lease.expires_at = datetime.now(UTC)
        await self._audit(
            lease.company_id,
            lease.resource_id,
            "execution.effects_uncertain",
            "system",
            {"run_id": ticket.run_id, "automatic_replay": False},
        )
        await self.checkpoint()

    async def request_control(
        self, *, run_id: str, company_id: str, action: str, reason: str, actor_id: str
    ) -> dict[str, Any]:
        lease = await self._session.scalar(
            select(ExecutionLeaseTable)
            .where(
                ExecutionLeaseTable.company_id == company_id, ExecutionLeaseTable.run_id == run_id
            )
            .with_for_update()
        )
        run = await self._session.get(AgentRunTable, run_id)
        if lease is None or run is None:
            raise ExecutionDenied("execution_not_found", 404)
        agent = await self._session.scalar(
            select(AgentRoleTable).where(
                AgentRoleTable.company_id == company_id, AgentRoleTable.agent_id == run.agent_id
            )
        )
        if agent is None:
            raise ExecutionDenied("agent_not_found", 404)
        validate_execution_control(agent.adapter_type, action, lease.state)
        lease.control_action = action
        await self._audit(
            company_id,
            lease.resource_id,
            f"execution.{action}_requested",
            actor_id,
            {"run_id": run_id, "reason": reason},
        )
        return {"run_id": run_id, "requested_action": action, "state": "requested"}

    async def recover(
        self, *, run_id: str, company_id: str, reason: str, actor_id: str
    ) -> dict[str, Any]:
        lease = await self._session.scalar(
            select(ExecutionLeaseTable)
            .where(
                ExecutionLeaseTable.company_id == company_id, ExecutionLeaseTable.run_id == run_id
            )
            .with_for_update()
        )
        if lease is None:
            raise ExecutionDenied("execution_not_found", 404)
        if lease.state not in {"running", "recovery_required"} or _utc(
            lease.expires_at
        ) > datetime.now(UTC):
            raise ExecutionDenied("execution_not_abandoned")
        lease.state = "running"
        reservations = (
            await self._session.scalars(
                select(ExecutionReservationTable).where(
                    ExecutionReservationTable.execution_id == lease.execution_id
                )
            )
        ).all()
        ceiling = max((r.amount_usd for r in reservations), default=Decimal(0))
        await self.settle(
            ExecutionTicket(lease.execution_id, lease.run_id, lease.owner_id, ceiling),
            cost_usd=ceiling,
            failed=True,
            estimated=True,
        )
        run = await self._session.get(AgentRunTable, run_id)
        if run and run.status == "running":
            from .agent_operation_store import SqlAlchemyControlPlaneAgentOperationStore
            from .domain.lifecycle.agent_run_lifecycle import fail_agent_wakeup_run

            agent = await self._session.scalar(
                select(AgentRoleTable).where(
                    AgentRoleTable.company_id == company_id, AgentRoleTable.agent_id == run.agent_id
                )
            )
            if agent is None:
                raise ExecutionDenied("recovery_agent_required")
            await fail_agent_wakeup_run(
                SqlAlchemyControlPlaneAgentOperationStore(self._session),
                agent_role_record(agent),
                run_id=run_id,
                input_event=run.input_event or {},
                actor_id=actor_id,
                trace_id=run.trace_id,
                goal_id=run.goal_id,
                work_item_id=run.work_item_id,
                trigger="operator_reconciliation",
                error_category="operator_reconciled_abandoned_execution",
                error_message="external_effects_reviewed",
            )
        if lease.resource_id.startswith("work:"):
            work = await self._session.get(WorkItemTable, lease.resource_id.removeprefix("work:"))
            if work:
                await self._transition_work(work, "failed", actor_id)
        await self._audit(
            company_id,
            lease.resource_id,
            "execution.reconciled",
            actor_id,
            {"run_id": run_id, "reason": reason, "automatic_replay": False},
        )
        return {"run_id": run_id, "state": "failed", "handoff": "operator_reviewed_retry"}

    async def _mark_abandoned(self, lease: ExecutionLeaseTable, now: datetime) -> None:
        if lease.state == "running" and _utc(lease.expires_at) <= now:
            lease.state = "recovery_required"
            await self._audit(
                lease.company_id,
                lease.resource_id,
                "execution.recovery_required",
                "system",
                {"execution_id": lease.execution_id, "automatic_replay": False},
            )
            await self.checkpoint()

    async def settle(
        self, ticket: ExecutionTicket, *, cost_usd: Decimal, failed: bool, estimated: bool = False
    ) -> None:
        lease = await self._session.scalar(
            select(ExecutionLeaseTable)
            .where(ExecutionLeaseTable.execution_id == ticket.execution_id)
            .with_for_update()
        )
        if lease is None or lease.owner_id != ticket.owner_id or lease.state != "running":
            raise ExecutionDenied("execution_owner_lost")
        reservations = (
            await self._session.scalars(
                select(ExecutionReservationTable)
                .where(ExecutionReservationTable.execution_id == ticket.execution_id)
                .with_for_update()
            )
        ).all()
        for reservation in reservations:
            if reservation.state != "reserved":
                raise ExecutionDenied("execution_already_settled")
            reservation.state = "settled"
            await SqlAlchemyControlPlaneBudgetStore(self._session).record_budget_usage(
                BudgetUsage(
                    company_id=lease.company_id,
                    budget_id=reservation.budget_id,
                    cost_usd=float(cost_usd),
                    model="executor",
                    run_id=ticket.run_id,
                    metadata={
                        "execution_id": ticket.execution_id,
                        "failed_attempt": failed,
                        "charged_ceiling": estimated,
                    },
                )
            )
        run = await self._session.scalar(
            select(AgentRunTable).where(AgentRunTable.run_id == ticket.run_id,
                AgentRunTable.company_id == lease.company_id).with_for_update()
        )
        if run is None:
            raise ExecutionDenied("execution_run_not_found")
        run.cost_usd = float(cost_usd)
        run.metadata_json = {**(run.metadata_json or {}), "cost_is_estimate": estimated}
        lease.state = "failed" if failed else "succeeded"
        await self._session.flush()

    async def _audit(
        self, company_id: str, resource: str, action: str, actor_id: str, detail: dict[str, Any]
    ) -> None:
        await SqlAlchemyControlPlaneAuditEventStore(self._session).append_audit_event(
            AuditEvent(
                company_id=company_id,
                target_type="execution",
                target_id=resource,
                action=action,
                actor_type="operator",
                actor_id=actor_id,
                detail=detail,
            )
        )

    async def _transition_work(self, work: WorkItemTable, state: str, actor_id: str) -> None:
        aggregate = WorkItemAggregate.from_record(work_item_record(work))
        aggregate.transition_to(state)
        work.status = aggregate.status.value
        work.updated_at = datetime.now(UTC)
        await append_control_plane_domain_event_audits(
            SqlAlchemyControlPlaneAuditEventStore(self._session),
            aggregate.pull_events(),
            DomainEventAuditContext(
                actor_type="operator",
                actor_id=actor_id,
                work_item_id=work.work_item_id,
                detail={"status": state},
            ),
        )
