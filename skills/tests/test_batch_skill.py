"""Tests for BatchConfirmSkill and BatchRejectSkill."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.infra.skill import SkillContext, SkillError
from shared.messaging.inbound import Platform, UnifiedMessage
from skills.batch_operations import BatchConfirmSkill, BatchRejectSkill


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


def create_mock_requirement(req_id: str, status: str = "pending"):
    """Create a mock requirement."""
    req = MagicMock()
    req.id = req_id
    req.title = f"Test Requirement {req_id}"
    req.status = status
    return req


class TestBatchConfirmSkillMetadata:
    """Test BatchConfirmSkill metadata."""

    def test_skill_name(self):
        skill = BatchConfirmSkill()
        assert skill.name == "batch_confirm"

    def test_skill_commands(self):
        skill = BatchConfirmSkill()
        assert "/batch-confirm" in skill.commands


class TestBatchConfirmSkillExecute:
    """Test BatchConfirmSkill execution."""

    @pytest.mark.asyncio
    async def test_execute_success(self):
        """Test batch confirm success."""
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_user = MagicMock(id="user_001")

        mock_repo_class = MagicMock()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(side_effect=[
            create_mock_requirement("req_001"),
            create_mock_requirement("req_002"),
        ])
        mock_repo.confirm = AsyncMock()
        mock_repo_class.return_value = mock_repo

        message = create_message("/batch-confirm req_001,req_002")
        context = SkillContext(
            message=message,
            user=mock_user,
            parameters={"requirement_ids": "req_001,req_002"},
            db=mock_db,
        )

        skill = BatchConfirmSkill()
        with patch("agents.capabilities.requirements.skills.batch_operations.RequirementRepository", mock_repo_class):
            result = await skill.execute(context)

        assert result.success is True
        assert mock_repo.confirm.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_missing_ids(self):
        """Test batch confirm with missing IDs."""
        mock_db = AsyncMock()
        mock_user = MagicMock(id="user_001")

        message = create_message("/batch-confirm")
        context = SkillContext(
            message=message,
            user=mock_user,
            parameters={},
            db=mock_db,
        )

        skill = BatchConfirmSkill()
        with pytest.raises(SkillError) as exc_info:
            await skill.execute(context)

        assert "请提供需求ID列表" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_partial_success(self):
        """Test batch confirm with some failures."""
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_user = MagicMock(id="user_001")

        mock_repo_class = MagicMock()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(side_effect=[
            create_mock_requirement("req_001"),
            None,  # Not found
        ])
        mock_repo.confirm = AsyncMock()
        mock_repo_class.return_value = mock_repo

        message = create_message("/batch-confirm req_001,req_002")
        context = SkillContext(
            message=message,
            user=mock_user,
            parameters={"requirement_ids": "req_001,req_002"},
            db=mock_db,
        )

        skill = BatchConfirmSkill()
        with patch("agents.capabilities.requirements.skills.batch_operations.RequirementRepository", mock_repo_class):
            result = await skill.execute(context)

        assert result.success is True
        assert "partial" in result.response.card.status


class TestBatchRejectSkillExecute:
    """Test BatchRejectSkill execution."""

    @pytest.mark.asyncio
    async def test_execute_success_with_reason(self):
        """Test batch reject with reason."""
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_user = MagicMock(id="user_001")

        mock_repo_class = MagicMock()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=create_mock_requirement("req_001"))
        mock_repo.reject = AsyncMock()
        mock_repo_class.return_value = mock_repo

        message = create_message("/batch-reject req_001 Not needed")
        context = SkillContext(
            message=message,
            user=mock_user,
            parameters={"requirement_ids": "req_001", "reason": "Not needed"},
            db=mock_db,
        )

        skill = BatchRejectSkill()
        with patch("agents.capabilities.requirements.skills.batch_operations.RequirementRepository", mock_repo_class):
            result = await skill.execute(context)

        assert result.success is True
        mock_repo.reject.assert_called_once()
