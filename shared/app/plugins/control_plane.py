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
from shared.control_plane.runtime_plugin_store import (
    SqlAlchemyControlPlaneRuntimePluginStore,
)
from shared.control_plane.runtime_plugin_use_cases import (
    bootstrap_core_agent_roles,
    complete_event_run,
    fail_event_run,
    start_event_run,
)
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event
from shared.utils.logger import get_logger

logger = get_logger("plugin.control-plane")

SessionProvider = Callable[[], AbstractAsyncContextManager[AsyncSession]]


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
                return await start_event_run(
                    SqlAlchemyControlPlaneRuntimePluginStore(session),
                    agent_id=agent_id,
                    event=event,
                    default_company_id=self._default_company_id,
                    default_company_name=self._default_company_name,
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
                completed = await complete_event_run(
                    SqlAlchemyControlPlaneRuntimePluginStore(session),
                    run_id=run_id,
                    agent_id=agent_id,
                    event=event,
                    output_events=output_events,
                )
                if not completed:
                    logger.warning("control_plane_run_missing_on_complete", run_id=run_id)
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
                failed = await fail_event_run(
                    SqlAlchemyControlPlaneRuntimePluginStore(session),
                    run_id=run_id,
                    agent_id=agent_id,
                    event=event,
                    error=error,
                    default_company_id=self._default_company_id,
                )
                if not failed:
                    logger.warning("control_plane_run_missing_on_fail", run_id=run_id)
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
            async with self._resolve_session_provider()() as session:
                created = await bootstrap_core_agent_roles(
                    SqlAlchemyControlPlaneRuntimePluginStore(session),
                    company_id=self._default_company_id,
                    company_name=self._default_company_name,
                )
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
