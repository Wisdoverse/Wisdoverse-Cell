"""Bounded native dispatch with durable intent, exact replay and honest receipts."""

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Any

from shared.core.native_executor import NativeExecutorError, NativeExecutorLedger
from shared.protocols.executor import ExecutorRequest, ExecutorResponse
from shared.utils.logger import get_logger

logger = get_logger("native.executor")
MAX_EXECUTOR_BYTES = 1000000


def request_digest(request: ExecutorRequest) -> str:
    return hashlib.sha256(
        json.dumps(
            request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


class NativeExecutorUseCase:
    def __init__(
        self,
        ledger: NativeExecutorLedger,
        handler: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
        *,
        runtime_id: str,
        company_id: str,
        allowed_actions: frozenset[str],
        timeout_seconds: float = 90,
    ) -> None:
        self._ledger = ledger
        self._handler = handler
        self._runtime_id = runtime_id
        self._company_id = company_id
        self._allowed_actions = allowed_actions
        self._timeout = timeout_seconds

    async def execute(self, request: ExecutorRequest, idempotency_key: str) -> ExecutorResponse:
        if request.company_id != self._company_id:
            raise NativeExecutorError("executor_company_not_owned", 403)
        if idempotency_key != request.run_id:
            raise NativeExecutorError("executor_idempotency_key_mismatch", 422)
        action = request.input.get("action") if request.action == "wakeup" else request.action
        if not isinstance(action, str) or action not in self._allowed_actions:
            raise NativeExecutorError("executor_action_not_supported", 422)
        if request.input.get("action", action) != action or "_executor_context" in request.input:
            raise NativeExecutorError("executor_input_context_conflict", 422)
        if request.input.get("trace_id", request.trace_id) != request.trace_id:
            raise NativeExecutorError("executor_trace_id_conflict", 422)
        digest = request_digest(request)
        claim = await self._ledger.claim(request, digest)
        if not claim.acquired:
            if claim.response is not None:
                return claim.response
            raise NativeExecutorError("executor_effects_uncertain", 503)
        context = {
            "runtime_id": self._runtime_id,
            "company_id": request.company_id,
            "agent_id": request.agent_id,
            "run_id": request.run_id,
            "goal_id": request.goal_id,
            "work_item_id": request.work_item_id,
            "trace_id": request.trace_id,
            "request_hash": digest,
        }
        native = {
            **request.input,
            "action": action,
            "trace_id": request.trace_id,
            "_executor_context": context,
        }
        logger.info("native_executor_started", **context)
        try:
            async with asyncio.timeout(self._timeout):
                result = await self._handler(native)
            if not isinstance(result, dict):
                raise ValueError("native_executor_result_not_object")
            failed = bool(result.get("error")) or result.get("status") in {"error", "failed"}
            response = ExecutorResponse(
                schema_version="1.0",
                status="failed" if failed else "recorded",
                summary="Native request failed."
                if failed
                else "Native request recorded; business outcome acceptance is separate.",
                cost_usd=request.max_cost_usd,
                cost_is_estimate=True,
                output={"native_result": result, "executor_receipt": context},
            )
            encoded = json.dumps(
                response.model_dump(mode="python"),
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
            if len(encoded) > MAX_EXECUTOR_BYTES:
                raise ValueError("native_executor_output_too_large")
            await self._ledger.complete(request.run_id, digest, response)
        except BaseException as exc:
            # Cancellation, timeout and persistence failure can follow business effects.
            # Keep the committed dispatch intent; never replay the handler automatically.
            try:
                async with asyncio.timeout(5):
                    await self._ledger.mark_uncertain(request.run_id, digest)
            except (Exception, asyncio.CancelledError):
                pass
            logger.warning("native_executor_uncertain", **context)
            if not isinstance(exc, Exception):
                raise
            raise NativeExecutorError("executor_effects_uncertain", 503) from None
        logger.info("native_executor_recorded", **context)
        return response
