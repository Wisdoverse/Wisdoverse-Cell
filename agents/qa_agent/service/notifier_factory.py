"""Service-layer wiring for QA notification adapters."""
from __future__ import annotations

from shared.infra.event_bus import EventBus
from shared.integrations.feishu import FeishuWebhookClient
from shared.integrations.feishu.cards import FeishuQualityCardRenderer
from shared.integrations.gitlab import GitLabClient

from ..core.notifier import QANotifier


def build_qa_notifier(bus: EventBus | None = None) -> QANotifier:
    """Build the QA notifier with concrete adapters at the service edge."""
    return QANotifier(
        bus=bus,
        gitlab=GitLabClient(),
        feishu_webhook=FeishuWebhookClient(),
        card_renderer=FeishuQualityCardRenderer(),
    )
