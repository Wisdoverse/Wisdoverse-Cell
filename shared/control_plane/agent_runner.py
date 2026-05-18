"""Run frontend-created agent definitions through explicit adapters."""

from __future__ import annotations

import asyncio
import json
import shlex
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from shared.config import settings
from shared.control_plane.adapter_registry import DEFAULT_ADAPTER_REGISTRY
from shared.control_plane.agent_operation_ports import ControlPlaneAgentOperationStore
from shared.control_plane.agent_run_lifecycle import (
    complete_agent_wakeup_run,
    fail_agent_wakeup_run,
    start_agent_wakeup_run,
)
from shared.utils.logger import get_logger

logger = get_logger("control_plane.agent_runner")

_TERMINAL_ROLE_STATUSES = {"paused", "terminated"}
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


def _config_string(config: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _command_from_config(config: dict[str, Any]) -> list[str]:
    command = config.get("command")
    if isinstance(command, str):
        return shlex.split(command)
    if isinstance(command, Sequence) and not isinstance(command, (bytes, bytearray)):
        return [str(part) for part in command if str(part)]
    return []


def _local_adapter_allowlist_key(
    *,
    agent_id: str,
    adapter_type: str,
    config: dict[str, Any],
) -> str:
    configured = _config_string(config, "allowlist_key", "registry_key")
    return configured or f"{adapter_type}:{agent_id}"


def _local_adapter_allowed(
    *,
    agent_id: str,
    adapter_type: str,
    config: dict[str, Any],
) -> bool:
    return (
        _local_adapter_allowlist_key(
            agent_id=agent_id,
            adapter_type=adapter_type,
            config=config,
        )
        in settings.control_plane_local_adapter_allowlist_entries
    )


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
        status = str(agent.status or "").lower()
        if status in _TERMINAL_ROLE_STATUSES:
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
        adapter_type = str(agent.adapter_type or "builtin")
        config = dict(agent.adapter_config or {})
        if not DEFAULT_ADAPTER_REGISTRY.is_registered(adapter_type):
            raise AgentWakeupError(
                "unsupported_adapter_type",
                status_code=400,
                error_category="unsupported_adapter",
            )

        request = {
            "action": config.get("action", "wakeup"),
            "agent_id": agent.agent_id,
            "run_id": run_id,
            "trace_id": trace_id,
            "goal_id": goal_id,
            "work_item_id": work_item_id,
            "input": input_payload,
        }

        if adapter_type == "builtin":
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
        if adapter_type == "http":
            return await self._execute_http(config, request)
        if DEFAULT_ADAPTER_REGISTRY.is_local(adapter_type):
            if not settings.control_plane_local_adapter_enabled:
                raise AgentWakeupError(
                    "local_adapter_disabled",
                    status_code=403,
                    error_category="adapter_disabled",
                )
            if not _local_adapter_allowed(
                agent_id=agent.agent_id,
                adapter_type=adapter_type,
                config=config,
            ):
                raise AgentWakeupError(
                    "local_adapter_not_allowlisted",
                    status_code=403,
                    error_category="adapter_not_allowlisted",
                )
            return await self._execute_process(config, request)
        raise AgentWakeupError("unsupported_adapter_type", status_code=400)

    async def _execute_http(
        self,
        config: dict[str, Any],
        request: dict[str, Any],
    ) -> dict[str, Any]:
        base_url = _config_string(config, "base_url", "url", "endpoint")
        if not base_url:
            raise AgentWakeupError(
                "http_adapter_base_url_required",
                status_code=400,
                error_category="adapter_config_error",
            )
        path = _config_string(config, "path") or "/agent/request"
        url = base_url.rstrip("/") + (path if path.startswith("/") else f"/{path}")
        timeout = min(float(config.get("timeout_sec", 30)), 120.0)
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
        config: dict[str, Any],
        request: dict[str, Any],
    ) -> dict[str, Any]:
        command = _command_from_config(config)
        if not command:
            raise AgentWakeupError(
                "local_adapter_command_required",
                status_code=400,
                error_category="adapter_config_error",
            )
        cwd = _config_string(config, "cwd", "working_directory")
        timeout = min(
            int(config.get("timeout_sec", 300)),
            _MAX_PROCESS_TIMEOUT_SECONDS,
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
