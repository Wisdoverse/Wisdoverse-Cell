"""Production-safe heartbeat scheduler for persisted agent definitions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from shared.control_plane.agent_runner import AgentWakeupError, ControlPlaneAgentRunner
from shared.control_plane.models import AgentRunStatus
from shared.control_plane.repository import ControlPlaneRepository
from shared.core.ids import generate_ulid

_DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 300
_MIN_HEARTBEAT_INTERVAL_SECONDS = 60
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


def _heartbeat_enabled(config: dict[str, Any]) -> bool:
    return config.get("heartbeat_enabled") is True


def _heartbeat_interval_seconds(config: dict[str, Any]) -> int:
    raw = config.get("heartbeat_interval_seconds", _DEFAULT_HEARTBEAT_INTERVAL_SECONDS)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = _DEFAULT_HEARTBEAT_INTERVAL_SECONDS
    return max(value, _MIN_HEARTBEAT_INTERVAL_SECONDS)


class ControlPlaneHeartbeatScheduler:
    """Runs due heartbeats for active frontend/operator-created agent roles."""

    def __init__(
        self,
        repo: ControlPlaneRepository,
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
            config = dict(agent.adapter_config or {})
            if not _heartbeat_enabled(config):
                continue

            interval_seconds = _heartbeat_interval_seconds(config)
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
                        "scheduled_at": checked_at.isoformat(),
                        "heartbeat_interval_seconds": interval_seconds,
                    },
                    actor_id=_SCHEDULER_ACTOR_ID,
                    trace_id=f"trace_{generate_ulid().lower()}",
                    trigger="scheduled_heartbeat",
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
