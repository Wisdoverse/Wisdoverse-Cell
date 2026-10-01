"""Production-safe heartbeat scheduler for persisted agent definitions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from shared.control_plane.agent_operation_ports import ControlPlaneAgentOperationStore
from shared.control_plane.agent_runner import AgentWakeupError, ControlPlaneAgentRunner
from shared.control_plane.domain.agent_wakeup_adapter import AgentWakeupAdapterConfig
from shared.control_plane.models import AgentRunStatus
from shared.core.ids import generate_ulid

_SCHEDULER_ACTOR_ID = "control-plane:scheduler"


@dataclass(frozen=True)
class AgentHeartbeatResult:
    company_id: str
    agent_id: str
    status: str
    run_id: str | None = None
    skipped_reason: str | None = None
    error: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ControlPlaneHeartbeatScheduler:
    """Runs due heartbeats for active frontend/operator-created agent roles."""

    def __init__(
        self,
        repo: ControlPlaneAgentOperationStore,
        *,
        runner: ControlPlaneAgentRunner | None = None,
    ) -> None:
        self._repo = repo
        self._runner = runner or ControlPlaneAgentRunner(repo)

    async def run_due_once(
        self,
        *,
        company_id: str,
        limit: int = 500,
        now: datetime | None = None,
    ) -> list[AgentHeartbeatResult]:
        checked_at = _as_utc(now or _now())
        agents = await self._repo.list_agent_roles(
            company_id=company_id,
            status="active",
            limit=limit,
        )
        results: list[AgentHeartbeatResult] = []
        for agent in agents:
            adapter_config = AgentWakeupAdapterConfig.from_agent_role(agent)
            if not adapter_config.heartbeat_enabled():
                continue

            interval_seconds = adapter_config.heartbeat_interval_seconds()
            due, skipped_reason = await self._is_due(
                agent_id=agent.agent_id,
                company_id=company_id,
                interval_seconds=interval_seconds,
                now=checked_at,
            )
            if not due:
                results.append(
                    AgentHeartbeatResult(
                        company_id=company_id,
                        agent_id=agent.agent_id,
                        status="skipped",
                        skipped_reason=skipped_reason,
                    )
                )
                continue

            try:
                wakeup = await self._runner.wake(
                    agent,
                    input_payload={
                        "trigger": "heartbeat",
                        "scheduled_at": datetime.fromtimestamp(
                            int(checked_at.timestamp()) // interval_seconds * interval_seconds, UTC).isoformat(),
                        "heartbeat_interval_seconds": interval_seconds,
                    },
                    actor_id=_SCHEDULER_ACTOR_ID,
                    trace_id=f"trace_{generate_ulid().lower()}",
                    trigger="scheduled_heartbeat",
                    idempotency_key=f"heartbeat:{agent.agent_id}:{int(checked_at.timestamp()) // interval_seconds}",
                )
            except AgentWakeupError as exc:
                results.append(
                    AgentHeartbeatResult(
                        company_id=company_id,
                        agent_id=agent.agent_id,
                        status="failed",
                        error=exc.detail,
                    )
                )
                continue
            except Exception as exc:
                results.append(
                    AgentHeartbeatResult(
                        company_id=company_id,
                        agent_id=agent.agent_id,
                        status="failed",
                        error=str(exc),
                    )
                )
                continue

            results.append(
                AgentHeartbeatResult(
                    company_id=company_id,
                    agent_id=agent.agent_id,
                    status="succeeded",
                    run_id=wakeup.run_id,
                )
            )
        return results

    async def _is_due(
        self,
        *,
        agent_id: str,
        company_id: str,
        interval_seconds: int,
        now: datetime,
    ) -> tuple[bool, str | None]:
        runs = await self._repo.list_agent_runs(
            company_id=company_id,
            agent_id=agent_id,
            limit=1,
        )
        if not runs:
            return True, None

        latest = runs[0]
        if latest.status == AgentRunStatus.RUNNING.value:
            return False, "already_running"

        last_at = latest.completed_at or latest.started_at
        if last_at is None:
            return True, None
        elapsed_seconds = (now - _as_utc(last_at)).total_seconds()
        if elapsed_seconds < interval_seconds:
            return False, "interval_not_elapsed"
        return True, None
