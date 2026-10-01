"""Internal HTTP adapter for governed native executor requests and receipts."""

from fastapi import Depends, FastAPI, Request
from pydantic import ValidationError

from shared.api import raise_api_error
from shared.config import settings
from shared.core.native_executor import NativeExecutorError, NativeExecutorLedger
from shared.middleware.internal_auth import verify_internal_key
from shared.protocols.executor import (
    ExecutorCapabilities,
    ExecutorReceipt,
    ExecutorRequest,
    ExecutorResponse,
)

from .native_executor import MAX_EXECUTOR_BYTES, NativeExecutorUseCase
from .runtime import AgentRuntime


def install_native_executor_api(
    app: FastAPI,
    runtime: AgentRuntime,
    ledger: NativeExecutorLedger | None,
    allowed_actions: frozenset[str],
) -> None:
    def require_enabled() -> NativeExecutorLedger:
        if not settings.native_executor_enabled or ledger is None:
            raise_api_error(
                status_code=503, code="executor.disabled", message="native_executor_disabled"
            )
        return ledger

    async def dispatch(request: Request) -> ExecutorResponse:
        store = require_enabled()
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_EXECUTOR_BYTES:
                raise_api_error(
                    status_code=413,
                    code="executor.input_too_large",
                    message="executor_input_too_large",
                )
        try:
            command = ExecutorRequest.model_validate_json(data)
        except (ValidationError, ValueError):
            raise_api_error(
                status_code=422, code="executor.request_invalid", message="executor_request_invalid"
            )
        if request.headers.get("X-Executor-Contract") != "1.0":
            raise_api_error(
                status_code=422,
                code="executor.version_required",
                message="executor_contract_version_required",
            )
        trace = request.headers.get("X-Trace-ID")
        if trace is not None and trace != command.trace_id:
            raise_api_error(
                status_code=422,
                code="executor.trace_mismatch",
                message="executor_trace_id_conflict",
            )
        use_case = NativeExecutorUseCase(
            store,
            runtime.agent.handle_request,
            runtime_id=runtime.agent_id,
            company_id=settings.control_plane_company_id,
            allowed_actions=allowed_actions,
            timeout_seconds=settings.native_executor_timeout_seconds,
        )
        try:
            return await use_case.execute(command, request.headers.get("Idempotency-Key", ""))
        except NativeExecutorError as exc:
            raise_api_error(
                status_code=exc.status_code, code=f"executor.{exc.code}", message=exc.code
            )

    app.state.native_executor_dispatch = dispatch
    if ledger is None:
        return

    @app.get(
        "/api/v1/executor/capabilities",
        dependencies=[Depends(verify_internal_key)],
        tags=["executor"],
    )
    async def capabilities() -> ExecutorCapabilities:
        return ExecutorCapabilities(
            runtime_id=runtime.agent_id,
            company_id=settings.control_plane_company_id,
            enabled=settings.native_executor_enabled and ledger is not None,
            actions=sorted(allowed_actions),
            timeout_seconds=settings.native_executor_timeout_seconds,
        )

    @app.post(
        "/api/v1/executor/requests",
        response_model=ExecutorResponse,
        dependencies=[Depends(verify_internal_key)],
        tags=["executor"],
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": ExecutorRequest.model_json_schema()}},
            }
        },
    )
    async def execute(request: Request) -> ExecutorResponse:
        return await dispatch(request)

    @app.get(
        "/api/v1/executor/requests/{run_id}",
        dependencies=[Depends(verify_internal_key)],
        tags=["executor"],
    )
    async def receipt(run_id: str, company_id: str) -> ExecutorReceipt:
        store = require_enabled()
        if company_id != settings.control_plane_company_id:
            raise_api_error(
                status_code=403,
                code="executor.company_not_owned",
                message="executor_company_not_owned",
            )
        result = await store.lookup(company_id, run_id)
        if result is None:
            raise_api_error(
                status_code=404,
                code="executor.receipt_not_found",
                message="executor_receipt_not_found",
            )
        return ExecutorReceipt(
            runtime_id=runtime.agent_id,
            company_id=company_id,
            run_id=run_id,
            state=result.state,
            response=result.response,
        )
