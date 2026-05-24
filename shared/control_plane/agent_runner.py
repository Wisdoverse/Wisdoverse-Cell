"""Run frontend-created agent definitions through explicit adapters."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import httpx

from shared.config import settings
from shared.control_plane.adapter_registry import DEFAULT_ADAPTER_REGISTRY
from shared.control_plane.agent_operation_ports import ControlPlaneAgentOperationStore
from shared.control_plane.domain.agent_role import (
    AgentRole as AgentRoleAggregate,
)
from shared.control_plane.domain.agent_role import InvalidAgentRoleStatusError
from shared.control_plane.domain.agent_wakeup_adapter import AgentWakeupAdapterConfig
from shared.control_plane.domain.lifecycle.agent_run_lifecycle import (
    complete_agent_wakeup_run,
    fail_agent_wakeup_run,
    start_agent_wakeup_run,
)
from shared.utils.logger import get_logger

logger = get_logger("control_plane.agent_runner")

_MAX_STDIO_CHARS = 20_000
_MAX_PROCESS_TIMEOUT_SECONDS = 900


class AgentWakeupError(Exception):
    """Raised when a control-plane agent definition cannot be woken."""

    def __init__(
        self,
        detail: str,
        *,
        status_code: int = 400,
        error_category: str = "wakeup_error",
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.error_category = error_category


@dataclass(frozen=True)
class AgentWakeupResult:
    run_id: str
    output: dict[str, Any]
    evidence_artifact_id: str | None = None


def _truncate(value: str) -> str:
    if len(value) <= _MAX_STDIO_CHARS:
        return value
    return value[:_MAX_STDIO_CHARS] + "\n...[truncated]"


class ControlPlaneAgentRunner:
    """Executes a persisted AgentRole through its configured adapter."""

    def __init__(self, repo: ControlPlaneAgentOperationStore) -> None:
        self._repo = repo

    async def wake(
        self,
        agent: Any,
        *,
        input_payload: dict[str, Any] | None = None,
        actor_id: str = "api",
        trace_id: str | None = None,
        goal_id: str | None = None,
        work_item_id: str | None = None,
        trigger: str = "manual_wakeup",
    ) -> AgentWakeupResult:
        try:
            role = AgentRoleAggregate.from_record(agent)
            is_runnable = role.is_runnable
        except InvalidAgentRoleStatusError as exc:
            raise AgentWakeupError(
                "invalid_agent_status",
                status_code=409,
                error_category="invalid_agent_status",
            ) from exc
        if not is_runnable:
            raise AgentWakeupError("agent_not_runnable", status_code=409)

        run_record = await start_agent_wakeup_run(
            self._repo,
            agent,
            input_payload=input_payload,
            actor_id=actor_id,
            trace_id=trace_id,
            goal_id=goal_id,
            work_item_id=work_item_id,
            trigger=trigger,
        )
        run = run_record.run

        try:
            output = await self._execute_adapter(
                agent,
                run_id=run.run_id,
                input_payload=input_payload or {},
                trace_id=trace_id,
                goal_id=goal_id,
                work_item_id=work_item_id,
            )
        except Exception as exc:
            error_category = (
                exc.error_category
                if isinstance(exc, AgentWakeupError)
                else type(exc).__name__
            )
            error_message = exc.detail if isinstance(exc, AgentWakeupError) else str(exc)
            await fail_agent_wakeup_run(
                self._repo,
                agent,
                run_id=run.run_id,
                input_event=run_record.input_event,
                actor_id=actor_id,
                trace_id=trace_id,
                goal_id=goal_id,
                work_item_id=work_item_id,
                trigger=trigger,
                error_category=error_category,
                error_message=error_message,
            )
            if isinstance(exc, AgentWakeupError):
                raise
            raise AgentWakeupError(
                "agent_wakeup_failed",
                status_code=502,
                error_category=error_category,
            ) from exc

        evidence_artifact_id = await complete_agent_wakeup_run(
            self._repo,
            agent,
            run_id=run.run_id,
            input_event=run_record.input_event,
            output=output,
            actor_id=actor_id,
            trace_id=trace_id,
            goal_id=goal_id,
            work_item_id=work_item_id,
            trigger=trigger,
        )
        return AgentWakeupResult(
            run_id=run.run_id,
            output=output,
            evidence_artifact_id=evidence_artifact_id,
        )

    async def _execute_adapter(
        self,
        agent: Any,
        *,
        run_id: str,
        input_payload: dict[str, Any],
        trace_id: str | None,
        goal_id: str | None,
        work_item_id: str | None,
    ) -> dict[str, Any]:
        adapter_config = AgentWakeupAdapterConfig.from_agent_role(agent)
        if not DEFAULT_ADAPTER_REGISTRY.is_registered(adapter_config.adapter_type):
            raise AgentWakeupError(
                "unsupported_adapter_type",
                status_code=400,
                error_category="unsupported_adapter",
            )

        request = {
            "action": adapter_config.action(),
            "agent_id": agent.agent_id,
            "run_id": run_id,
            "trace_id": trace_id,
            "goal_id": goal_id,
            "work_item_id": work_item_id,
            "input": input_payload,
        }

        if adapter_config.adapter_type == "builtin":
            return {
                "status": "recorded",
                "summary": (
                    f"{agent.display_name} wakeup was recorded by the control plane."
                ),
                "agent_kind": agent.agent_kind,
                "role": agent.role,
                "title": agent.title,
                "capabilities": list(agent.capabilities or []),
                "responsibilities": list(agent.responsibilities or []),
            }
        if adapter_config.adapter_type == "http":
            return await self._execute_http(adapter_config, request)
        if DEFAULT_ADAPTER_REGISTRY.is_local(adapter_config.adapter_type):
            if not settings.control_plane_local_adapter_enabled:
                raise AgentWakeupError(
                    "local_adapter_disabled",
                    status_code=403,
                    error_category="adapter_disabled",
                )
            if (
                adapter_config.allowlist_key()
                not in settings.control_plane_local_adapter_allowlist_entries
            ):
                raise AgentWakeupError(
                    "local_adapter_not_allowlisted",
                    status_code=403,
                    error_category="adapter_not_allowlisted",
                )
            return await self._execute_process(adapter_config, request)
        raise AgentWakeupError("unsupported_adapter_type", status_code=400)

    async def _execute_http(
        self,
        adapter_config: AgentWakeupAdapterConfig,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        base_url = adapter_config.string_value("base_url", "url", "endpoint")
        if not base_url:
            raise AgentWakeupError(
                "http_adapter_base_url_required",
                status_code=400,
                error_category="adapter_config_error",
            )
        path = adapter_config.string_value("path") or "/agent/request"
        url = base_url.rstrip("/") + (path if path.startswith("/") else f"/{path}")
        timeout = adapter_config.http_timeout_seconds()
        headers = {}
        if settings.internal_service_key:
            headers["X-Internal-Key"] = settings.internal_service_key
        if request.get("trace_id"):
            headers["X-Trace-ID"] = str(request["trace_id"])
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=request, headers=headers)
            response.raise_for_status()
            if "application/json" in response.headers.get("content-type", ""):
                body = response.json()
            else:
                body = {"text": response.text}
        return {
            "status": "ok",
            "adapter": "http",
            "response": body,
            "summary": body.get("status") if isinstance(body, dict) else "ok",
        }

    async def _execute_process(
        self,
        adapter_config: AgentWakeupAdapterConfig,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        command = adapter_config.command()
        if not command:
            raise AgentWakeupError(
                "local_adapter_command_required",
                status_code=400,
                error_category="adapter_config_error",
            )
        cwd = adapter_config.string_value("cwd", "working_directory")
        timeout = adapter_config.process_timeout_seconds(
            max_seconds=_MAX_PROCESS_TIMEOUT_SECONDS,
        )
        stdin_payload = json.dumps(request, ensure_ascii=False).encode()
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(stdin_payload),
                timeout=timeout,
            )
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.wait()
            raise AgentWakeupError(
                "local_adapter_timeout",
                status_code=504,
                error_category="timeout",
            ) from exc

        output = {
            "status": "ok" if process.returncode == 0 else "failed",
            "adapter": "process",
            "exit_code": process.returncode,
            "stdout": _truncate(stdout.decode(errors="replace")),
            "stderr": _truncate(stderr.decode(errors="replace")),
        }
        if process.returncode != 0:
            raise AgentWakeupError(
                "local_adapter_failed",
                status_code=502,
                error_category="process_failed",
            )
        output["summary"] = (
            output["stdout"].strip().splitlines()[-1]
            if output["stdout"].strip()
            else "ok"
        )
        return output
