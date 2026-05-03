"""Tests for LLM usage metrics emission."""

from unittest.mock import MagicMock, patch

from shared.infra.llm_gateway import LLMGateway


def test_record_llm_success_metrics_emits_duration_tokens_and_cost() -> None:
    gateway = LLMGateway(api_key="test-key")
    duration_metric = MagicMock()
    token_metric = MagicMock()
    cost_metric = MagicMock()

    with (
        patch("shared.infra.llm_gateway.LLM_REQUEST_DURATION", duration_metric),
        patch("shared.infra.llm_gateway.LLM_TOKEN_TOTAL", token_metric),
        patch("shared.infra.llm_gateway.LLM_COST_DOLLARS_TOTAL", cost_metric),
    ):
        gateway._record_llm_success_metrics(
            model="claude-test",
            agent_id="agent-a",
            input_tokens=11,
            output_tokens=7,
            cost_usd=0.0123,
            latency_ms=2500,
        )

    duration_metric.labels.assert_called_once_with(model="claude-test", agent_id="agent-a")
    duration_metric.labels.return_value.observe.assert_called_once_with(2.5)
    token_metric.labels.assert_any_call(
        model="claude-test",
        agent_id="agent-a",
        token_type="input",
    )
    token_metric.labels.assert_any_call(
        model="claude-test",
        agent_id="agent-a",
        token_type="output",
    )
    assert token_metric.labels.return_value.inc.call_args_list[0].args == (11,)
    assert token_metric.labels.return_value.inc.call_args_list[1].args == (7,)
    cost_metric.labels.assert_called_once_with(model="claude-test", agent_id="agent-a")
    cost_metric.labels.return_value.inc.assert_called_once_with(0.0123)
