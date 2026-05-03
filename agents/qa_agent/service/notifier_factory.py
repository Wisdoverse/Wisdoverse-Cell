"""Service-layer wiring for QA notification adapters."""
from __future__ import annotations

from shared.config import settings as app_settings
from shared.infra.event_bus import EventBus
from shared.integrations.feishu import FeishuWebhookClient
from shared.integrations.feishu.cards import FeishuQualityCardRenderer
from shared.integrations.gitlab import GitLabClient

from ..core.config import QACoreConfig
from ..core.notifier import QANotifier


def build_qa_core_config() -> QACoreConfig:
    """Build explicit QA core config from process settings at the service edge."""
    return QACoreConfig.from_values(
        runner_timeout_seconds=app_settings.qa_runner_timeout_seconds,
        qa_feishu_webhook_url=app_settings.qa_feishu_webhook_url,
        feishu_webhook_url=app_settings.feishu_webhook_url,
        high_severity_check_list=app_settings.qa_high_severity_check_list,
        gitlab_api_url=app_settings.gitlab_api_url,
        gitlab_project_id=app_settings.gitlab_project_id,
    )


def build_qa_notifier(
    bus: EventBus | None = None,
    config: QACoreConfig | None = None,
) -> QANotifier:
    """Build the QA notifier with concrete adapters at the service edge."""
    return QANotifier(
        bus=bus,
        gitlab=GitLabClient(),
        feishu_webhook=FeishuWebhookClient(),
        card_renderer=FeishuQualityCardRenderer(),
        config=config or build_qa_core_config(),
    )
