"""Tests for Dev task value objects."""

import pytest

from agents.dev_agent.core.domain.task_values import RiskLevel, risk_level_value
from agents.dev_agent.models.schemas import RiskLevel as SchemaRiskLevel


def test_risk_level_is_owned_by_domain_and_reexported_for_schemas() -> None:
    assert SchemaRiskLevel is RiskLevel
    assert RiskLevel.HIGH.value == "HIGH"


def test_risk_level_value_normalizes_enum_string_and_none() -> None:
    assert risk_level_value(RiskLevel.LOW) == "LOW"
    assert risk_level_value("MEDIUM") == "MEDIUM"
    assert risk_level_value(None) == "MEDIUM"


def test_risk_level_value_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        risk_level_value("urgent")
