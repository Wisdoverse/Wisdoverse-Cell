"""Run frontend-created agent definitions through explicit adapters."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import tempfile
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
from shared.control_plane.domain.execution_policy import ExecutionDenied, bounded_cost
from shared.control_plane.domain.executor_contract import ExecutorResponse
from shared.control_plane.domain.lifecycle.agent_run_lifecycle import (
    complete_agent_wakeup_run,
    fail_agent_wakeup_run,
    start_agent_wakeup_run,
)
from shared.control_plane.execution_ports import ExecutionGovernanceStore, ExecutionTicket
from shared.control_plane.operator_auth import current_operator
from shared.core.ids import IDPrefix, generate_id
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
        self._governance: ExecutionGovernanceStore | None = getattr(
            repo, "execution_governance", None
        )
        self._ticket: ExecutionTicket | None = None

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
        idempotency_key: str | None = None,
    ) -> AgentWakeupResult:
        principal = current_operator()
        if principal is not None:
            actor_id = principal.actor_id
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

        run_id = generate_id(IDPrefix.AGENT_RUN)
        ticket: ExecutionTicket | None = None
        if self._governance is not None:
            try:
                ticket = await self._governance.claim(
                    agent,
                    run_id=run_id,
                    payload=input_payload or {},
                    work_item_id=work_item_id,
                    goal_id=goal_id,
                    actor_id=actor_id,
                    idempotency_key=idempotency_key or run_id,
                )
            except ExecutionDenied as exc:
                raise AgentWakeupError(
                    exc.reason, status_code=exc.status_code, error_category="execution_denied"
                ) from exc
            if ticket.replay:
                existing = await self._repo.get_agent_run(ticket.run_id)
                if existing is None:
                    raise AgentWakeupError("execution_recovery_required", status_code=409)
                if existing.status != "succeeded":
                    raise AgentWakeupError("previous_attempt_failed", status_code=409)
                events = existing.output_events or []
                output = events[-1].get("payload", {}).get("output", {}) if events else {}
                return AgentWakeupResult(run_id=ticket.run_id, output=output)
        self._ticket = ticket

        run_record = await start_agent_wakeup_run(
            self._repo,
            agent,
            input_payload=input_payload,
            actor_id=actor_id,
            trace_id=trace_id,
            goal_id=goal_id,
            work_item_id=work_item_id,
            trigger=trigger,
            run_id=run_id,
        )
        run = run_record.run
        if self._governance is not None:
            # Persist both intent and RUNNING before any external side effect.
            await self._governance.checkpoint()

        settled = False
        try:
            output = await self._execute_adapter(
                agent,
                run_id=run.run_id,
                input_payload=input_payload or {},
                trace_id=trace_id,
                goal_id=goal_id,
                work_item_id=work_item_id,
            )
            if ticket is not None and self._governance is not None:
                estimated = "cost_usd" not in output or output.get("cost_is_estimate") is True
                cost = bounded_cost(output.get("cost_usd", ticket.ceiling_usd))
                if estimated:
                    cost = max(cost, ticket.ceiling_usd)
                await self._governance.settle(
                    ticket,
                    cost_usd=cost,
                    failed=cost > ticket.ceiling_usd,
                    estimated=estimated,
                )
                settled = True
                if cost > ticket.ceiling_usd:
                    raise AgentWakeupError(
                        "executor_cost_ceiling_exceeded",
                        status_code=502,
                        error_category="executor_contract",
                    )
        except Exception as exc:
            error_category = (
                exc.error_category if isinstance(exc, AgentWakeupError) else type(exc).__name__
            )
            error_message = exc.detail if isinstance(exc, AgentWakeupError) else str(exc)
            if (
                error_category == "uncertain_effects"
                and ticket is not None
                and self._governance is not None
            ):
                await self._governance.mark_uncertain(ticket)
                raise
            if ticket is not None and self._governance is not None and not settled:
                # Unknown/failed work is conservatively charged its reserved ceiling.
                await self._governance.settle(
                    ticket, cost_usd=ticket.ceiling_usd, failed=True, estimated=True
                )
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
                cancelled=error_category == "cancelled",
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
            "schema_version": "1.0",
            "company_id": agent.company_id,
            "action": adapter_config.action(),
            "agent_id": agent.agent_id,
            "run_id": run_id,
            "trace_id": trace_id,
            "goal_id": goal_id,
            "work_item_id": work_item_id,
            "input": input_payload,
            "max_cost_usd": float(self._ticket.ceiling_usd) if self._ticket else 0,
        }

        if adapter_config.adapter_type == "builtin":
            return {
                "status": "recorded",
                "summary": (f"{agent.display_name} wakeup was recorded by the control plane."),
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
        allowlist = {
            value.strip().rstrip("/")
            for value in settings.control_plane_http_adapter_allowlist.split(",")
            if value.strip()
        }
        if base_url.rstrip("/") not in allowlist:
            raise AgentWakeupError(
                "http_adapter_endpoint_not_allowlisted",
                status_code=403,
                error_category="adapter_not_allowlisted",
            )
        path = adapter_config.string_value("path") or "/agent/request"
        url = base_url.rstrip("/") + (path if path.startswith("/") else f"/{path}")
        timeout = adapter_config.http_timeout_seconds()
        headers = {}
        headers["Idempotency-Key"] = str(request["run_id"])
        if adapter_config.config.get("contract_version") == "1.0":
            headers["X-Executor-Contract"] = "1.0"
        if settings.internal_service_key:
            headers["X-Internal-Key"] = settings.internal_service_key
        if request.get("trace_id"):
            headers["X-Trace-ID"] = str(request["trace_id"])
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                async with client.stream("POST", url, json=request, headers=headers) as response:
                    if response.status_code >= 500:
                        raise AgentWakeupError(
                            "executor_effects_uncertain",
                            status_code=409,
                            error_category="uncertain_effects",
                        )
                    response.raise_for_status()
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > 1_000_000:
                            raise AgentWakeupError(
                                "executor_output_limit_exceeded",
                                status_code=409,
                                error_category="uncertain_effects",
                            )
                    try:
                        body = (
                            json.loads(content)
                            if "application/json" in response.headers.get("content-type", "")
                            else {"text": content.decode(errors="replace")}
                        )
                    except ValueError as exc:
                        raise AgentWakeupError(
                            "executor_contract_invalid",
                            status_code=409,
                            error_category="uncertain_effects",
                        ) from exc
        except httpx.TransportError as exc:
            raise AgentWakeupError(
                "executor_effects_uncertain", status_code=409, error_category="uncertain_effects"
            ) from exc
        if adapter_config.config.get("contract_version") == "1.0":
            try:
                result = ExecutorResponse.model_validate(body)
            except ValueError as exc:
                raise AgentWakeupError(
                    "executor_contract_invalid", status_code=409, error_category="uncertain_effects"
                ) from exc
            if result.status == "failed":
                raise AgentWakeupError("http_executor_failed", status_code=502)
            return {
                "status": "ok" if result.status == "succeeded" else "recorded",
                "adapter": "http",
                "cost_usd": result.cost_usd,
                "cost_is_estimate": result.cost_is_estimate,
                "summary": result.summary,
                "response": result.output,
                "artifact_references": result.artifact_references,
            }
        return {
            "status": "recorded",
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
        if cwd:
            raise AgentWakeupError("local_adapter_custom_workspace_forbidden", status_code=403)
        workspace = tempfile.TemporaryDirectory(prefix="cell-execution-")
        cwd = workspace.name
        timeout = adapter_config.process_timeout_seconds(
            max_seconds=_MAX_PROCESS_TIMEOUT_SECONDS,
        )
        stdin_payload = json.dumps(request, ensure_ascii=False).encode()
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=cwd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={"PATH": os.defpath, "LANG": "C.UTF-8", "HOME": cwd},
                start_new_session=True,
            )
        except BaseException:
            workspace.cleanup()
            raise
        communication: asyncio.Task[tuple[bytes, bytes]] | None = None
        try:

            async def communicate_bounded() -> tuple[bytes, bytes]:
                assert process.stdin and process.stdout and process.stderr
                process.stdin.write(stdin_payload)
                await process.stdin.drain()
                process.stdin.close()

                async def read_bounded(stream: asyncio.StreamReader) -> bytes:
                    chunks = bytearray()
                    while chunk := await stream.read(8192):
                        chunks.extend(chunk)
                        if len(chunks) > 1_000_000:
                            raise AgentWakeupError(
                                "executor_output_limit_exceeded", status_code=502
                            )
                    return bytes(chunks)

                stdout, stderr = await asyncio.gather(
                    read_bounded(process.stdout), read_bounded(process.stderr)
                )
                await process.wait()
                return stdout, stderr

            communication = asyncio.create_task(communicate_bounded())
            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout
            paused = False
            while not communication.done():
                if loop.time() >= deadline:
                    raise asyncio.TimeoutError
                if self._ticket and self._governance:
                    action = await self._governance.control_action(self._ticket)
                    if action == "terminate":
                        raise AgentWakeupError(
                            "execution_terminated", status_code=409, error_category="cancelled"
                        )
                    if action == "pause" and not paused:
                        os.killpg(process.pid, signal.SIGSTOP)
                        paused = True
                    elif action == "resume" and paused:
                        os.killpg(process.pid, signal.SIGCONT)
                        paused = False
                await asyncio.wait({communication}, timeout=0.25)
            stdout, stderr = await communication
        except asyncio.TimeoutError as exc:
            if process.returncode is None:
                os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
            raise AgentWakeupError(
                "local_adapter_timeout",
                status_code=504,
                error_category="timeout",
            ) from exc
        except asyncio.CancelledError:
            if process.returncode is None:
                os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
            raise
        except Exception:
            if process.returncode is None:
                os.killpg(process.pid, signal.SIGKILL)
                await process.wait()
            raise
        finally:
            if communication is not None and not communication.done():
                communication.cancel()
                await asyncio.gather(communication, return_exceptions=True)
            workspace.cleanup()

        output: dict[str, Any] = {
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
        if adapter_config.config.get("contract_version") == "1.0":
            try:
                result = ExecutorResponse.model_validate_json(stdout)
            except ValueError as exc:
                raise AgentWakeupError("executor_contract_invalid", status_code=502) from exc
            if result.status == "failed":
                raise AgentWakeupError("process_executor_failed", status_code=502)
            return {
                "status": "ok" if result.status == "succeeded" else "recorded",
                "adapter": "process",
                "cost_usd": result.cost_usd,
                "cost_is_estimate": result.cost_is_estimate,
                "summary": result.summary,
                "response": result.output,
                "artifact_references": result.artifact_references,
            }
        if not stdout.strip():
            output["status"] = "recorded"
        output["summary"] = (
            output["stdout"].strip().splitlines()[-1] if output["stdout"].strip() else "ok"
        )
        return output
