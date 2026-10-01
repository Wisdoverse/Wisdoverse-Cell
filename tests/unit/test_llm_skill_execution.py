from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shared.config import settings
from shared.evolution.config import evolution_settings
from shared.evolution.release_contract import canonical_hash
from shared.evolution.skill_execution_contract import (
    SkillSelection,
    current_evolution_trace,
    selection_signature,
)
from shared.infra import llm_gateway as llm_gateway_module
from shared.infra.llm_gateway import LLMGateway

_SECRET = "llm-gateway-frozen-skill-key-that-is-long-enough"


def _selection() -> SkillSelection:
    values = {
        "company_id": "company-1",
        "agent_id": "agent-1",
        "skill_id": "agent-1:review",
        "trace_id": "trace-1",
        "schema_version": "1.0",
        "deployment_id": "deployment-1",
        "experiment_id": "experiment-1",
        "version": 7,
        "configuration": {
            "skill_id": "agent-1:review",
            "version": "7",
            "system_prompt": "frozen system",
            "parameters": {"temperature": 0.7, "max_tokens": 123},
            "few_shot_examples": [{"input": "example input", "output": "example output"}],
            "output_format": "structured json",
            "target_model": "openai/frozen-model",
        },
        "configuration_hash": "0" * 64,
        "expires_at": datetime.now(UTC) + timedelta(minutes=10),
    }
    values["configuration_hash"] = canonical_hash(values["configuration"])
    values["signature"] = "0" * 64
    provisional = SkillSelection.model_validate(values)
    values["signature"] = selection_signature(provisional.model_dump(mode="json"), _SECRET)
    return SkillSelection.model_validate(values)


def _response():
    return SimpleNamespace(
        usage=SimpleNamespace(input_tokens=12, output_tokens=8),
        content=[SimpleNamespace(type="text", text="gateway result")],
    )


@pytest.mark.asyncio
async def test_complete_uses_frozen_skill_and_records_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selection = _selection()
    monkeypatch.setattr(evolution_settings, "skill_execution_enabled", True)
    monkeypatch.setattr(settings, "control_plane_company_id", "company-1")
    resolve = AsyncMock(return_value=selection)
    monkeypatch.setattr(
        "shared.evolution.skill_execution_gateway.HttpSkillExecutionGateway.resolve", resolve
    )

    gateway = LLMGateway(api_key="unit-test-key")
    gateway._check_control_plane_budget = AsyncMock(return_value=None)
    gateway._record_control_plane_budget_usage = AsyncMock()
    provider_call = AsyncMock(return_value=_response())
    gateway._provider_messages_create = provider_call
    gateway._record_llm_success_metrics = lambda **kwargs: None
    trace = SimpleNamespace(
        trace_id="trace-1", skill_used=None, skill_version=None, skill_selections={}
    )
    token = current_evolution_trace.set(trace)
    try:
        result = await gateway.complete(
            "user prompt",
            agent_id="agent-1",
            task_type="review",
            system_prompt="caller prompt",
            model="openai/default",
            max_tokens=99,
            temperature=0.2,
        )
    finally:
        current_evolution_trace.reset(token)

    assert result == "gateway result"
    resolve.assert_awaited_once()
    provider_call.assert_awaited_once()
    kwargs = provider_call.await_args.args[0]
    assert kwargs["model"] == "openai/frozen-model"
    assert kwargs["max_tokens"] == 123
    assert kwargs["temperature"] == 0.7
    assert kwargs["system"][0]["text"] == (
        'frozen system\nExamples:\n[{"input": "example input", "output": "example output"}]'
        "\nRequired output format: structured json"
    )
    assert trace.skill_used == selection.skill_id
    assert trace.skill_version == selection.version
    assert trace.skill_selections == {selection.skill_id: selection}
    gateway._check_control_plane_budget.assert_awaited_once()
    assert gateway._check_control_plane_budget.await_args.kwargs["model"] == "openai/frozen-model"


@pytest.mark.asyncio
async def test_disabled_skill_execution_does_not_resolve_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(evolution_settings, "skill_execution_enabled", False)
    resolve = AsyncMock()
    monkeypatch.setattr(
        "shared.evolution.skill_execution_gateway.HttpSkillExecutionGateway.resolve", resolve
    )
    gateway = LLMGateway(api_key="unit-test-key")
    gateway._check_control_plane_budget = AsyncMock(return_value=None)
    gateway._record_control_plane_budget_usage = AsyncMock()
    gateway._provider_messages_create = AsyncMock(return_value=_response())
    gateway._record_llm_success_metrics = lambda **kwargs: None
    trace = SimpleNamespace(
        trace_id="trace-1", skill_used=None, skill_version=None, skill_selections={}
    )
    token = current_evolution_trace.set(trace)
    try:
        assert (
            await gateway.complete("prompt", agent_id="agent-1", task_type="review")
            == "gateway result"
        )
    finally:
        current_evolution_trace.reset(token)
    resolve.assert_not_awaited()
    assert not trace.skill_selections


@pytest.mark.asyncio
async def test_budget_denial_does_not_call_provider_or_attach_skill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(evolution_settings, "skill_execution_enabled", True)
    monkeypatch.setattr(settings, "control_plane_company_id", "company-1")
    resolve = AsyncMock(return_value=_selection())
    monkeypatch.setattr(
        "shared.evolution.skill_execution_gateway.HttpSkillExecutionGateway.resolve", resolve
    )
    provider_call = AsyncMock(return_value=_response())
    gateway = LLMGateway(api_key="unit-test-key")
    gateway._check_control_plane_budget = AsyncMock(side_effect=PermissionError("budget denied"))
    gateway._provider_messages_create = provider_call
    trace = SimpleNamespace(
        trace_id="trace-1", skill_used=None, skill_version=None, skill_selections={}
    )
    token = current_evolution_trace.set(trace)
    try:
        with pytest.raises(PermissionError, match="budget denied"):
            await gateway.complete("prompt", agent_id="agent-1", task_type="review")
    finally:
        current_evolution_trace.reset(token)
    provider_call.assert_not_awaited()
    assert not trace.skill_selections


@pytest.mark.asyncio
async def test_frozen_model_overload_never_falls_back_to_another_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shared.infra.llm_errors import LLMErrorCategory, RetryStrategy, default_retry_config

    monkeypatch.setattr(evolution_settings, "skill_execution_enabled", True)
    monkeypatch.setattr(settings, "control_plane_company_id", "company-1")
    monkeypatch.setattr(
        "shared.evolution.skill_execution_gateway.HttpSkillExecutionGateway.resolve",
        AsyncMock(return_value=_selection()),
    )
    retry_config = default_retry_config()
    retry_config.strategies[LLMErrorCategory.OVERLOADED] = RetryStrategy(
        max_attempts=2,
        base_delay_s=0,
        max_delay_s=0,
        use_jitter=False,
        fallback_model="openai/alternate-model",
    )
    monkeypatch.setattr(llm_gateway_module, "default_retry_config", lambda: retry_config)

    class ProviderOverloaded(Exception):
        status_code = 503

    models: list[str] = []

    async def overloaded(kwargs):
        models.append(kwargs["model"])
        raise ProviderOverloaded("provider busy")

    gateway = LLMGateway(api_key="unit-test-key")
    gateway._check_control_plane_budget = AsyncMock(return_value=None)
    gateway._provider_messages_create = overloaded
    trace = SimpleNamespace(
        trace_id="trace-1", skill_used=None, skill_version=None, skill_selections={}
    )
    token = current_evolution_trace.set(trace)
    try:
        with pytest.raises(ProviderOverloaded):
            await gateway.complete("prompt", agent_id="agent-1", task_type="review")
    finally:
        current_evolution_trace.reset(token)
    assert models == ["openai/frozen-model", "openai/frozen-model"]
    assert trace.skill_selections["agent-1:review"].version == 7


@pytest.mark.asyncio
async def test_concurrent_execution_contexts_keep_skill_selections_isolated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(evolution_settings, "skill_execution_enabled", True)
    monkeypatch.setattr(settings, "control_plane_company_id", "company-1")
    selections = {
        f"trace-{n}": _selection().model_copy(update={"trace_id": f"trace-{n}"}) for n in (1, 2)
    }
    # Re-sign the changed trace subject, so the fixture remains a valid signed selection.
    for trace_id, selection in list(selections.items()):
        raw = selection.model_dump(mode="json")
        raw["signature"] = "0" * 64
        raw["signature"] = selection_signature(raw, _SECRET)
        selections[trace_id] = SkillSelection.model_validate(raw)
    resolve = AsyncMock(side_effect=lambda request: selections[request.trace_id])
    monkeypatch.setattr(
        "shared.evolution.skill_execution_gateway.HttpSkillExecutionGateway.resolve", resolve
    )
    gateway = LLMGateway(api_key="unit-test-key")
    gateway._check_control_plane_budget = AsyncMock(return_value=None)
    gateway._record_control_plane_budget_usage = AsyncMock()
    provider_call = AsyncMock(return_value=_response())
    gateway._provider_messages_create = provider_call
    gateway._record_llm_success_metrics = lambda **kwargs: None
    traces = [
        SimpleNamespace(
            trace_id=f"trace-{n}", skill_used=None, skill_version=None, skill_selections={}
        )
        for n in (1, 2)
    ]

    async def run(trace):
        token = current_evolution_trace.set(trace)
        try:
            await gateway.complete("prompt", agent_id="agent-1", task_type="review")
        finally:
            current_evolution_trace.reset(token)

    await __import__("asyncio").gather(*(run(trace) for trace in traces))
    assert provider_call.await_count == 2
    assert traces[0].skill_selections["agent-1:review"].trace_id == "trace-1"
    assert traces[1].skill_selections["agent-1:review"].trace_id == "trace-2"
