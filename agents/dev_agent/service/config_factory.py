"""Service-layer wiring for dev core configuration."""

from __future__ import annotations

from shared.config import settings as app_settings

from ..core.config import DevCoreConfig


def build_dev_core_config() -> DevCoreConfig:
    """Build explicit dev core config from process settings at the service edge."""
    return DevCoreConfig.from_values(
        decompose_model=app_settings.decompose_model,
        gitlab_project_id=app_settings.dev_gitlab_project_id,
    )
