"""Tests for analysis core configuration."""

from shared.capabilities.analysis.core.config import AnalysisCoreConfig


def test_analysis_core_config_parses_project_ids_from_string() -> None:
    config = AnalysisCoreConfig.from_values(decompose_project_ids="1, 2,,abc")

    assert config.decompose_project_ids == ("1", "2", "abc")


def test_analysis_core_config_parses_project_ids_from_iterable() -> None:
    config = AnalysisCoreConfig.from_values(decompose_project_ids=[1, "2", ""])

    assert config.decompose_project_ids == ("1", "2")
