"""Tests for durable control-plane LLM budget enforcement."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.control_plane.budget_guard import BudgetExceededError
from shared.control_plane.context import (
    ControlPlaneRunContext,
    reset_current_run_context,
    set_current_run_context,
)
from shared.infra import llm_gateway as llm_gateway_module
from shared.infra.llm_gateway import ControlPlaneBudgetReservation, LLMGateway


def _mock_response(input_tokens: int = 120, output_tokens: int = 40):
    response = MagicMock()
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    response.content = [MagicMock(text="ok")]
    return response


@pytest.fixture
def gateway(monkeypatch):
    monkeypatch.setattr(
        llm_gateway_module.settings,
        "control_plane_llm_budget_enforced",
        True,
    )
    monkeypatch.setattr(
        llm_gateway_module.settings,
        "control_plane_company_id",
        "cmp_test",
    )
    gw = LLMGateway(api_key="test-key")
    monkeypatch.setattr(gw, "_get_redis", AsyncMock(return_value=None))
    return gw


class TestControlPlaneLLMBudget:
    @pytest.mark.asyncio
    async def test_create_messages_checks_budget_before_provider_and_records_usage(
        self,
        gateway,
        monkeypatch,
    ):
        reservation = ControlPlaneBudgetReservation(
            company_id="cmp_test",
            budget_id="bud_test",
        )
        check_budget = AsyncMock(return_value=reservation)
        record_usage = AsyncMock()
        monkeypatch.setattr(gateway, "_check_control_plane_budget", check_budget)
        monkeypatch.setattr(gateway, "_record_control_plane_budget_usage", record_usage)
        gateway.async_client.messages.create = AsyncMock(return_value=_mock_response())

        await gateway.create_messages(
            agent_id="agent-a",
            messages=[{"role": "user", "content": "hello"}],
            trace_id="trace-1",
            run_id="run-1",
        )

        check_budget.assert_awaited_once()
        check_kwargs = check_budget.await_args.kwargs
        assert check_kwargs["agent_id"] == "agent-a"
        assert check_kwargs["model"] == llm_gateway_module.settings.chat_model
        assert check_kwargs["estimated_cost_usd"] > 0
        gateway.async_client.messages.create.assert_awaited_once()
        record_usage.assert_awaited_once()
        record_kwargs = record_usage.await_args.kwargs
        assert record_kwargs["reservation"] == reservation
        assert record_kwargs["run_id"] == "run-1"
        assert record_kwargs["trace_id"] == "trace-1"
        assert record_kwargs["input_tokens"] == 120
        assert record_kwargs["output_tokens"] == 40

    @pytest.mark.asyncio
    async def test_create_messages_budget_rejection_skips_provider(
        self,
        gateway,
        monkeypatch,
    ):
        check_budget = AsyncMock(side_effect=BudgetExceededError("budget_exceeded"))
        monkeypatch.setattr(gateway, "_check_control_plane_budget", check_budget)
        gateway.async_client.messages.create = AsyncMock(return_value=_mock_response())

        with pytest.raises(BudgetExceededError, match="budget_exceeded"):
            await gateway.create_messages(
                agent_id="agent-a",
                messages=[{"role": "user", "content": "hello"}],
            )

        check_budget.assert_awaited_once()
        gateway.async_client.messages.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_complete_checks_budget_and_records_usage(
        self,
        gateway,
        monkeypatch,
    ):
        reservation = ControlPlaneBudgetReservation(
            company_id="cmp_test",
            budget_id="bud_test",
        )
        check_budget = AsyncMock(return_value=reservation)
        record_usage = AsyncMock()
        monkeypatch.setattr(gateway, "_check_control_plane_budget", check_budget)
        monkeypatch.setattr(gateway, "_record_control_plane_budget_usage", record_usage)
        gateway.async_client.messages.create = AsyncMock(return_value=_mock_response())

        result = await gateway.complete(
            prompt="hello",
            agent_id="agent-a",
            trace_id="trace-2",
            run_id="run-2",
        )

        assert result == "ok"
        check_budget.assert_awaited_once()
        gateway.async_client.messages.create.assert_awaited_once()
        record_usage.assert_awaited_once()
        record_kwargs = record_usage.await_args.kwargs
        assert record_kwargs["reservation"] == reservation
        assert record_kwargs["run_id"] == "run-2"
        assert record_kwargs["trace_id"] == "trace-2"

    @pytest.mark.asyncio
    async def test_complete_uses_runtime_context_when_run_id_not_passed(
        self,
        gateway,
        monkeypatch,
    ):
        reservation = ControlPlaneBudgetReservation(
            company_id="cmp_ctx",
            budget_id="bud_ctx",
        )
        check_budget = AsyncMock(return_value=reservation)
        record_usage = AsyncMock()
        monkeypatch.setattr(gateway, "_check_control_plane_budget", check_budget)
        monkeypatch.setattr(gateway, "_record_control_plane_budget_usage", record_usage)
        gateway.async_client.messages.create = AsyncMock(return_value=_mock_response())

        token = set_current_run_context(
            ControlPlaneRunContext(
                company_id="cmp_ctx",
                run_id="run_ctx",
                agent_id="agent-a",
                trace_id="trace-ctx",
            )
        )
        try:
            await gateway.complete(
                prompt="hello",
                agent_id="agent-a",
                trace_id="trace-ctx",
            )
        finally:
            reset_current_run_context(token)

        check_kwargs = check_budget.await_args.kwargs
        assert check_kwargs["company_id"] == "cmp_ctx"
        record_kwargs = record_usage.await_args.kwargs
        assert record_kwargs["run_id"] == "run_ctx"
