import pytest

from shared.infra.llm_gateway import LLMGateway


class TestCostCap:
    def test_estimate_cost_returns_float(self):
        gw = LLMGateway(api_key="test-key")
        cost = gw.estimate_cost(100_000, 10_000, "claude-opus-4-6")
        assert isinstance(cost, float)
        assert cost > 0

    def test_preflight_cost_check_raises_on_expensive_call(self):
        gw = LLMGateway(api_key="test-key")
        # 500K input tokens on opus = ~$7.50 input alone
        with pytest.raises(ValueError, match="estimated_cost_exceeds_cap"):
            gw.preflight_cost_check(
                max_tokens=100_000,
                model="claude-opus-4-6",
                estimated_input_tokens=500_000,
                cost_cap_usd=2.0,
            )

    def test_preflight_cost_check_passes_for_cheap_call(self):
        gw = LLMGateway(api_key="test-key")
        # 1K input tokens on haiku = ~$0.00025
        gw.preflight_cost_check(
            max_tokens=1000,
            model="claude-haiku-4-5-20251001",
            estimated_input_tokens=1000,
            cost_cap_usd=2.0,
        )  # should not raise

    def test_preflight_cost_check_at_boundary(self):
        gw = LLMGateway(api_key="test-key")
        # Exactly at cap should pass
        cost = gw.estimate_cost(10_000, 1000, "claude-sonnet-4-20250514")
        gw.preflight_cost_check(
            max_tokens=1000,
            model="claude-sonnet-4-20250514",
            estimated_input_tokens=10_000,
            cost_cap_usd=cost + 0.01,
        )
