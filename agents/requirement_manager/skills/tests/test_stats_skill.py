"""Tests for StatsSkill."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.requirement_manager.skills.stats import StatsSkill
from shared.infra.skill import SkillContext, SkillError
from shared.messaging.inbound import Platform, UnifiedMessage


def create_message(content: str) -> UnifiedMessage:
    """Create a test message."""
    return UnifiedMessage(
        platform=Platform.FEISHU,
        message_id="msg_test",
        chat_id="chat_test",
        sender_id="sender_test",
        content=content,
        timestamp=datetime.now(UTC),
    )


class TestStatsSkillMetadata:
    """Test StatsSkill metadata."""

    def test_skill_name(self):
        skill = StatsSkill()
        assert skill.name == "stats"

    def test_skill_commands(self):
        skill = StatsSkill()
        assert "/stats" in skill.commands
        assert "/统计" in skill.commands


class TestStatsSkillExecute:
    """Test StatsSkill execution."""

    @pytest.mark.asyncio
    async def test_execute_returns_card(self):
        """Test stats returns a card with statistics."""
        mock_db = AsyncMock()
        mock_user = MagicMock(id="user_001")

        mock_store_class = MagicMock()
        mock_store = MagicMock()
        mock_store.count_by_status = AsyncMock(return_value={
            "pending": 5,
            "confirmed": 10,
            "rejected": 2,
        })
        mock_store.count_by_priority = AsyncMock(return_value={
            "high": 3,
            "medium": 8,
            "low": 6,
        })
        mock_store.count_by_category = AsyncMock(return_value={
            "feature": 10,
            "bug": 5,
            "enhancement": 2,
        })
        mock_store.get_daily_counts = AsyncMock(return_value=[
            {"date": "01/25", "count": 3},
            {"date": "01/26", "count": 5},
            {"date": "01/27", "count": 2},
        ])
        mock_store.count_today = AsyncMock(return_value=2)
        mock_store.meeting_counts = AsyncMock(return_value=(10, 2))
        mock_store_class.return_value = mock_store

        message = create_message("/stats")
        context = SkillContext(
            message=message,
            user=mock_user,
            parameters={},
            db=mock_db,
        )

        skill = StatsSkill()
        with patch(
            "agents.requirement_manager.skills.stats.build_requirement_skill_store",
            mock_store_class,
        ):
            result = await skill.execute(context)

        assert result.success is True
        assert result.response.card is not None
        assert "需求概览" in result.response.card.content
        assert "17" in result.response.card.content  # Total: 5+10+2

    @pytest.mark.asyncio
    async def test_execute_no_db_raises_error(self):
        """Test stats without DB raises error."""
        mock_user = MagicMock(id="user_001")

        message = create_message("/stats")
        context = SkillContext(
            message=message,
            user=mock_user,
            parameters={},
            db=None,
        )

        skill = StatsSkill()
        with pytest.raises(SkillError) as exc_info:
            await skill.execute(context)

        assert "数据库不可用" in str(exc_info.value)
