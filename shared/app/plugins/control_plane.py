"""ControlPlanePlugin — records agent runs and audit events in the shared ledger."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from shared.app.runtime import RuntimePlugin
from shared.control_plane.context import (
    ControlPlaneRunContext,
    reset_current_run_context,
    set_current_run_context,
)
from shared.control_plane.models import (
    AgentRun,
    AgentRunStatus,
    AuditEvent,
    CompanyContext,
)
from shared.control_plane.repository import ControlPlaneRepository
from shared.control_plane.run_evidence import create_run_evidence_artifact
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

logger = get_logger("plugin.control-plane")

SessionProvider = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def _lookup_context_value(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value:
        return value
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _event_to_dict(event: Event) -> dict[str, Any]:
    return event.model_dump(mode="json")


def _events_to_dict(events: list[Event]) -> list[dict[str, Any]]:
    return [event.model_dump(mode="json") for event in events]


class ControlPlaneRecorder:
    """Small service object that writes run and audit evidence."""

    def __init__(
        self,
        *,
        session_provider: SessionProvider,
        default_company_id: str,
        default_company_name: str,
        fail_closed: bool = False,
    ) -> None:
        self._session_provider = session_provider
        self._default_company_id = default_company_id
        self._default_company_name = default_company_name
        self._fail_closed = fail_closed

    async def start_event_run(
        self,
        *,
        agent_id: str,
        event: Event,
    ) -> ControlPlaneRunContext | None:
        try:
            async with self._session_provider() as session:
                repo = ControlPlaneRepository(session)
                company_id = self._company_id_from_payload(event.payload)
                await self._ensure_company(repo, company_id)
                run = await repo.create_agent_run(
                    AgentRun(
                        company_id=company_id,
                        agent_id=agent_id,
                        status=AgentRunStatus.RUNNING,
                        trace_id=event.metadata.trace_id,
                        goal_id=_lookup_context_value(event.payload, "goal_id"),
                        work_item_id=_lookup_context_value(event.payload, "work_item_id"),
                        trigger_event_id=event.event_id,
                        input_event=_event_to_dict(event),
                    )
                )
                await repo.append_audit_event(
                    AuditEvent(
                        company_id=company_id,
                        action=EventTypes.AGENT_RUN_STARTED,
                        target_type="agent_run",
                        target_id=run.run_id,
                        actor_type="agent",
                        actor_id=agent_id,
                        trace_id=event.metadata.trace_id,
                        run_id=run.run_id,
                        work_item_id=run.work_item_id,
                        detail={
                            "event_id": event.event_id,
                            "event_type": event.event_type,
                        },
                    )
                )
                return ControlPlaneRunContext(
                    company_id=company_id,
                    run_id=run.run_id,
                    agent_id=agent_id,
                    trace_id=event.metadata.trace_id,
                    goal_id=run.goal_id,
                    work_item_id=run.work_item_id,
                )
        except Exception as exc:
            logger.error(
                "control_plane_run_start_failed",
                agent_id=agent_id,
                event_id=event.event_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            if self._fail_closed:
                raise
            return None

    async def complete_event_run(
        self,
        *,
        run_id: str,
        agent_id: str,
        event: Event,
        output_events: list[Event],
    ) -> None:
        try:
            async with self._session_provider() as session:
                repo = ControlPlaneRepository(session)
                run = await repo.update_agent_run_status(
                    run_id,
                    AgentRunStatus.SUCCEEDED,
                    output_events=_events_to_dict(output_events),
                )
                if run is None:
                    logger.warning("control_plane_run_missing_on_complete", run_id=run_id)
                    return
                await repo.append_audit_event(
                    AuditEvent(
                        company_id=run.company_id,
                        action=EventTypes.AGENT_RUN_SUCCEEDED,
                        target_type="agent_run",
                        target_id=run_id,
                        actor_type="agent",
                        actor_id=agent_id,
                        trace_id=event.metadata.trace_id,
                        run_id=run_id,
                        work_item_id=run.work_item_id,
                        detail={
                            "event_id": event.event_id,
                            "event_type": event.event_type,
                            "output_event_count": len(output_events),
                        },
                    )
                )
                await create_run_evidence_artifact(
                    repo,
                    company_id=run.company_id,
                    agent_id=agent_id,
                    run_id=run_id,
                    actor_type="agent",
                    actor_id=agent_id,
                    trigger=event.event_type,
                    trace_id=event.metadata.trace_id,
                    goal_id=run.goal_id,
                    work_item_id=run.work_item_id,
                    adapter_type="agent_runtime",
                    status="succeeded",
                    input_event=_event_to_dict(event),
                    output_events=_events_to_dict(output_events),
                    output_summary=f"{len(output_events)} output event(s)",
                    generated_by="control_plane_runtime_plugin",
                )
        except Exception as exc:
            logger.error(
                "control_plane_run_complete_failed",
                agent_id=agent_id,
                run_id=run_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            if self._fail_closed:
                raise

    async def fail_event_run(
        self,
        *,
        run_id: str,
        agent_id: str,
        event: Event,
        error: BaseException,
    ) -> None:
        try:
            async with self._session_provider() as session:
                repo = ControlPlaneRepository(session)
                failure_event = Event.create(
                    event_type=EventTypes.AGENT_RUN_FAILED,
                    source_agent=agent_id,
                    payload={
                        "company_id": self._company_id_from_payload(event.payload),
                        "run_id": run_id,
                        "status": "failed",
                        "error_category": type(error).__name__,
                        "error_message": str(error),
                    },
                    trace_id=event.metadata.trace_id,
                )
                output_events = [_event_to_dict(failure_event)]
                run = await repo.update_agent_run_status(
                    run_id,
                    AgentRunStatus.FAILED,
                    error_category=type(error).__name__,
                    error_message=str(error),
                    last_successful_step="handler_started",
                    output_events=output_events,
                )
                if run is None:
                    logger.warning("control_plane_run_missing_on_fail", run_id=run_id)
                    return
                await repo.append_audit_event(
                    AuditEvent(
                        company_id=run.company_id,
                        action=EventTypes.AGENT_RUN_FAILED,
                        target_type="agent_run",
                        target_id=run_id,
                        actor_type="agent",
                        actor_id=agent_id,
                        trace_id=event.metadata.trace_id,
                        run_id=run_id,
                        work_item_id=run.work_item_id,
                        detail={
                            "event_id": event.event_id,
                            "event_type": event.event_type,
                            "error_type": type(error).__name__,
                            "error": str(error),
                        },
                    )
                )
                await create_run_evidence_artifact(
                    repo,
                    company_id=run.company_id,
                    agent_id=agent_id,
                    run_id=run_id,
                    actor_type="agent",
                    actor_id=agent_id,
                    trigger=event.event_type,
                    trace_id=event.metadata.trace_id,
                    goal_id=run.goal_id,
                    work_item_id=run.work_item_id,
                    adapter_type="agent_runtime",
                    status="failed",
                    input_event=_event_to_dict(event),
                    output_events=output_events,
                    output_summary=None,
                    error_category=type(error).__name__,
                    error_message=str(error),
                    generated_by="control_plane_runtime_plugin",
                )
        except Exception as exc:
            logger.error(
                "control_plane_run_fail_record_failed",
                agent_id=agent_id,
                run_id=run_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            if self._fail_closed:
                raise

    def _company_id_from_payload(self, payload: dict[str, Any]) -> str:
        return _lookup_context_value(payload, "company_id") or self._default_company_id

    async def _ensure_company(self, repo: ControlPlaneRepository, company_id: str) -> None:
        if await repo.get_company(company_id) is not None:
            return
        await repo.create_company(
            CompanyContext(
                company_id=company_id,
                name=self._default_company_name,
            )
        )


class _ControlPlaneAgentWrapper(BaseAgent):
    """BaseAgent wrapper that records event-run lifecycle evidence."""

    def __init__(self, inner: BaseAgent, recorder: ControlPlaneRecorder):
        super().__init__(
            agent_id=inner.agent_id,
            agent_name=inner.agent_name,
            subscribed_events=inner.subscribed_events,
            published_events=inner.published_events,
            a2a_enabled=inner.a2a_enabled,
            mcp_enabled=inner.mcp_enabled,
        )
        self._inner = inner
        self._recorder = recorder

    async def handle_event(self, event: Event) -> list[Event]:
        run_context = await self._recorder.start_event_run(
            agent_id=self.agent_id,
            event=event,
        )
        context_token = (
            set_current_run_context(run_context) if run_context is not None else None
        )
        try:
            output_events = await self._inner.handle_event(event)
        except Exception as exc:
            if run_context:
                await self._recorder.fail_event_run(
                    run_id=run_context.run_id,
                    agent_id=self.agent_id,
                    event=event,
                    error=exc,
                )
            raise
        finally:
            if context_token is not None:
                reset_current_run_context(context_token)

        if run_context:
            await self._recorder.complete_event_run(
                run_id=run_context.run_id,
                agent_id=self.agent_id,
                event=event,
                output_events=output_events,
            )
        return output_events

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        result = await self.handle_standard_request(request)
        if result is not None:
            return result
        return await self._inner.handle_request(request)

    async def handle_standard_request(
        self, request: dict[str, Any]
    ) -> dict[str, Any] | None:
        return await self._inner.handle_standard_request(request)

    async def startup(self) -> None:
        await self._inner.startup()

    async def shutdown(self) -> None:
        await self._inner.shutdown()

    async def health_check(self) -> dict[str, bool]:
        return await self._inner.health_check()


class ControlPlanePlugin(RuntimePlugin):
    """Runtime plugin that records every handled event as an AgentRun."""

    name = "control-plane"

    def __init__(
        self,
        *,
        session_provider: SessionProvider | None = None,
        default_company_id: str = "cmp_wisdoverse_cell",
        default_company_name: str = "Wisdoverse Cell",
        fail_closed: bool = False,
    ) -> None:
        self._session_provider = session_provider
        self._default_company_id = default_company_id
        self._default_company_name = default_company_name
        self._fail_closed = fail_closed

    def wrap_agent(self, agent: BaseAgent) -> BaseAgent:
        recorder = ControlPlaneRecorder(
            session_provider=self._resolve_session_provider(),
            default_company_id=self._default_company_id,
            default_company_name=self._default_company_name,
            fail_closed=self._fail_closed,
        )
        return _ControlPlaneAgentWrapper(agent, recorder)

    async def startup(self, runtime) -> None:
        try:
            from shared.control_plane.bootstrap import (
                ensure_core_organization_role_agents,
                ensure_core_runtime_agent_roles,
            )

            async with self._resolve_session_provider()() as session:
                repo = ControlPlaneRepository(session)
                created_role_agents = await ensure_core_organization_role_agents(
                    repo,
                    company_id=self._default_company_id,
                    company_name=self._default_company_name,
                )
                created_runtime_agents = await ensure_core_runtime_agent_roles(
                    repo,
                    company_id=self._default_company_id,
                    company_name=self._default_company_name,
                )
            created = created_role_agents + created_runtime_agents
            if created:
                logger.info(
                    "control_plane_agents_bootstrapped",
                    agent_id=runtime.agent_id,
                    company_id=self._default_company_id,
                    agent_ids=created,
                )
        except Exception as exc:
            logger.error(
                "control_plane_agent_bootstrap_failed",
                agent_id=runtime.agent_id,
                company_id=self._default_company_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            if self._fail_closed:
                raise

    def _resolve_session_provider(self) -> SessionProvider:
        if self._session_provider is not None:
            return self._session_provider

        from shared.control_plane.database import control_plane_db_manager

        return control_plane_db_manager.session
