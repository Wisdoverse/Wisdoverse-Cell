"""Unit tests for QANotifier."""

from unittest.mock import AsyncMock

import pytest

from agents.qa_agent.core.config import QACoreConfig
from agents.qa_agent.core.notifier import QANotifier


class FakeQualityCardRenderer:
    def __init__(self):
        self.calls = []

    def build_acceptance_alert_message(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": "QA alert"},
                    "template": "red",
                },
                "elements": [],
            },
        }


@pytest.fixture
def mock_event_publisher():
    publisher = AsyncMock()
    publisher.publish = AsyncMock()
    return publisher


@pytest.fixture
def mock_gitlab():
    gl = AsyncMock()
    gl.upsert_mr_note = AsyncMock(return_value=True)
    return gl


@pytest.fixture
def mock_feishu_webhook():
    webhook = AsyncMock()
    webhook.send_interactive_card = AsyncMock(return_value=True)
    return webhook


@pytest.fixture
def card_renderer():
    return FakeQualityCardRenderer()


@pytest.fixture
def notifier(mock_event_publisher, mock_gitlab, mock_feishu_webhook, card_renderer):
    return QANotifier(
        event_publisher=mock_event_publisher,
        gitlab=mock_gitlab,
        feishu_webhook=mock_feishu_webhook,
        card_renderer=card_renderer,
    )


def _make_summary(l0: str = "PASS", l1: str = "PASS") -> dict:
    return {
        "l0_gate": l0,
        "l1_check": l1,
        "l2_report": "INFO",
        "total_checks": 10,
        "l0_failures": 1 if l0 == "FAIL" else 0,
        "l1_warnings": 1 if l1 == "WARN" else 0,
    }


class TestEventBusPublish:
    @pytest.mark.asyncio
    async def test_always_publishes_completed(self, notifier, mock_event_publisher):
        result = await notifier.notify_all(
            run_id="run1",
            agent_name="pjm_agent",
            summary=_make_summary(),
            findings=[],
            duration_seconds=5.0,
        )
        assert result["eventbus"]["sent"] is True
        assert mock_event_publisher.publish.call_count == 1

    @pytest.mark.asyncio
    async def test_publishes_gate_failed_on_l0_fail(self, notifier, mock_event_publisher):
        findings = [{"level": "L0", "status": "FAIL", "check": "secrets", "category": "security"}]
        await notifier.notify_all(
            run_id="run2",
            agent_name="pjm_agent",
            summary=_make_summary(l0="FAIL"),
            findings=findings,
            duration_seconds=3.0,
        )
        # 2 events: completed + gate_failed
        assert mock_event_publisher.publish.call_count == 2

    @pytest.mark.asyncio
    async def test_uses_supplied_eventbus_summary_without_publishing(self, notifier, mock_event_publisher):
        result = await notifier.notify_all(
            run_id="run-outbox",
            agent_name="pjm_agent",
            summary=_make_summary(),
            findings=[],
            duration_seconds=5.0,
            eventbus_summary={"sent": True, "published": 1, "failed": 0},
        )

        assert result["eventbus"] == {"sent": True, "published": 1, "failed": 0}
        mock_event_publisher.publish.assert_not_called()


class TestFeishuNotification:
    @pytest.mark.asyncio
    async def test_skips_feishu_when_passing(self, notifier):
        result = await notifier.notify_all(
            run_id="run3",
            agent_name="pjm_agent",
            summary=_make_summary(),
            findings=[],
            duration_seconds=1.0,
        )
        assert result["feishu"]["sent"] is False
        assert result["feishu"]["reason"] == "below_threshold"

    @pytest.mark.asyncio
    async def test_sends_feishu_on_l0_fail(
        self,
        mock_event_publisher,
        mock_gitlab,
        mock_feishu_webhook,
    ):
        card_renderer = FakeQualityCardRenderer()
        notifier = QANotifier(
            event_publisher=mock_event_publisher,
            gitlab=mock_gitlab,
            feishu_webhook=mock_feishu_webhook,
            card_renderer=card_renderer,
            config=QACoreConfig.from_values(
                qa_feishu_webhook_url="https://hook.example.com",
            ),
        )

        result = await notifier.notify_all(
            run_id="run4",
            agent_name="pjm_agent",
            summary=_make_summary(l0="FAIL"),
            findings=[{"level": "L0", "status": "FAIL", "check": "secrets"}],
            duration_seconds=2.0,
        )

        assert result["feishu"]["sent"] is True
        mock_feishu_webhook.send_interactive_card.assert_called_once()
        assert card_renderer.calls[0]["agent_name"] == "pjm_agent"


class TestGitLabComment:
    @pytest.mark.asyncio
    async def test_posts_comment_when_mr_exists(self, notifier, mock_gitlab):
        result = await notifier.notify_all(
            run_id="run5",
            agent_name="pjm_agent",
            summary=_make_summary(),
            findings=[],
            duration_seconds=1.0,
            mr_iid=42,
            report_markdown="## Report\nAll passed.",
        )
        assert result["gitlab"]["sent"] is True
        mock_gitlab.upsert_mr_note.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_gitlab_when_no_mr(self, notifier):
        result = await notifier.notify_all(
            run_id="run6",
            agent_name="pjm_agent",
            summary=_make_summary(),
            findings=[],
            duration_seconds=1.0,
        )
        assert result["gitlab"]["sent"] is False
        assert result["gitlab"]["reason"] == "no_mr"
