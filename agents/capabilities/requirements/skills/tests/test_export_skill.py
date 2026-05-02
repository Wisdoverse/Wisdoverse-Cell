"""Tests for ExportSkill."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.capabilities.requirements.skills.export import ExportSkill
from shared.infra.skill import SkillContext
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


def create_mock_requirement(req_id: str, category: str = "feature"):
    """Create a mock requirement."""
    req = MagicMock()
    req.id = req_id
    req.title = f"Test Requirement {req_id}"
    req.description = f"Description for {req_id}"
    req.status = "confirmed"
    req.priority = "high"
    req.category = category
    return req


class TestExportSkillMetadata:
    """Test ExportSkill metadata."""

    def test_skill_name(self):
        skill = ExportSkill()
        assert skill.name == "export"

    def test_skill_commands(self):
        skill = ExportSkill()
        assert "/export" in skill.commands
        assert "/prd" in skill.commands


class TestExportSkillExecute:
    """Test ExportSkill execution."""

    @pytest.mark.asyncio
    async def test_execute_summary_format(self):
        """Test export with summary format."""
        mock_db = AsyncMock()
        mock_user = MagicMock(id="user_001")

        mock_repo_class = MagicMock()
        mock_repo = MagicMock()
        mock_repo.list_all = AsyncMock(return_value=([
            create_mock_requirement("req_001", "feature"),
            create_mock_requirement("req_002", "feature"),
            create_mock_requirement("req_003", "bug"),
        ], 3))
        mock_repo_class.return_value = mock_repo

        message = create_message("/export")
        context = SkillContext(
            message=message,
            user=mock_user,
            parameters={},
            db=mock_db,
        )

        skill = ExportSkill()
        with patch(
            "agents.capabilities.requirements.skills.export.RequirementRepository",
            mock_repo_class,
        ):
            result = await skill.execute(context)

        assert result.success is True
        assert "需求摘要" in result.response.card.title
        assert "feature" in result.response.card.content

    @pytest.mark.asyncio
    async def test_execute_detail_format(self):
        """Test export with detail format."""
        mock_db = AsyncMock()
        mock_user = MagicMock(id="user_001")

        mock_repo_class = MagicMock()
        mock_repo = MagicMock()
        mock_repo.list_all = AsyncMock(return_value=([
            create_mock_requirement("req_001"),
        ], 1))
        mock_repo_class.return_value = mock_repo

        message = create_message("/export detail")
        context = SkillContext(
            message=message,
            user=mock_user,
            parameters={"format": "detail"},
            db=mock_db,
        )

        skill = ExportSkill()
        with patch(
            "agents.capabilities.requirements.skills.export.RequirementRepository",
            mock_repo_class,
        ):
            result = await skill.execute(context)

        assert result.success is True
        assert "PRD" in result.response.card.title

    @pytest.mark.asyncio
    async def test_execute_empty_requirements(self):
        """Test export with no requirements."""
        mock_db = AsyncMock()
        mock_user = MagicMock(id="user_001")

        mock_repo_class = MagicMock()
        mock_repo = MagicMock()
        mock_repo.list_all = AsyncMock(return_value=([], 0))
        mock_repo_class.return_value = mock_repo

        message = create_message("/export")
        context = SkillContext(
            message=message,
            user=mock_user,
            parameters={},
            db=mock_db,
        )

        skill = ExportSkill()
        with patch(
            "agents.capabilities.requirements.skills.export.RequirementRepository",
            mock_repo_class,
        ):
            result = await skill.execute(context)

        assert result.success is True
        assert "暂无" in result.response.card.content
