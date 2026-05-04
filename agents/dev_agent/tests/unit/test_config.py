"""Unit tests for dev core configuration values."""

from agents.dev_agent.core.config import DevCoreConfig


def test_dev_core_config_preserves_project_id() -> None:
    config = DevCoreConfig.from_values(
        decompose_model="custom-model",
        gitlab_project_id=42,
    )

    assert config.decompose_model == "custom-model"
    assert config.gitlab_project_id == 42


def test_dev_core_config_uses_planner_fallback_model_when_empty() -> None:
    config = DevCoreConfig.from_values(decompose_model="")

    assert config.decompose_model == "claude-sonnet-4-20250514"
