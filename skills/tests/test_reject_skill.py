"""Test RejectSkill - Reject a requirement."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.infra.skill.models import Permission, SkillContext, SkillError
from shared.messaging.inbound.models import Platform, UnifiedMessage
from shared.models.user import User


class TestRejectSkillMetadata:
    """Test RejectSkill metadata."""

    def test_skill_name(self):
        from skills.reject_requirement import RejectSkill
        skill = RejectSkill()
        assert skill.name == "reject"

    def test_skill_commands(self):
        from skills.reject_requirement import RejectSkill
        skill = RejectSkill()
        assert "/reject" in skill.commands

    def test_skill_permissions(self):
        from skills.reject_requirement import RejectSkill
        skill = RejectSkill()
        assert Permission.DB_WRITE in skill.permissions
        assert Permission.GATEWAY_REPLY in skill.permissions


class TestRejectSkillExecute:
    """Test RejectSkill execution."""

    @pytest.fixture
    def mock_context(self):
        """Create mock context."""
        message = UnifiedMessage(
            platform=Platform.FEISHU,
            message_id="msg_001",
            chat_id="chat_001",
            sender_id="user_001",
            timestamp=datetime.now(UTC),
            content="/reject req_001 不符合规划",
        )
        user = User(id="user_001", name="Test User")
        db = AsyncMock()
        return SkillContext(
            message=message,
            user=user,
            parameters={"requirement_id": "req_001", "reason": "不符合规划"},
            db=db,
        )

    @pytest.fixture
    def mock_requirement(self):
        """Create mock requirement."""
        req = MagicMock()
        req.id = "req_001"
        req.title = "Test Requirement"
        req.status = "pending"
        return req

    @pytest.mark.asyncio
    async def test_execute_success(self, mock_context, mock_requirement):
        """Test successful rejection."""
        from skills.reject_requirement import RejectSkill

        skill = RejectSkill()

        with pytest.MonkeyPatch.context() as mp:
            mock_repo = AsyncMock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_requirement)
            mock_repo.reject = AsyncMock(return_value=mock_requirement)

            mp.setattr(
                "agents.capabilities.requirements.skills.reject_requirement.RequirementRepository",
                lambda db: mock_repo
            )

            result = await skill.execute(mock_context)

        assert result.success is True
        assert "已拒绝" in result.response.card.title

    @pytest.mark.asyncio
    async def test_execute_missing_id(self, mock_context):
        """Test error when requirement ID not provided."""
        from skills.reject_requirement import RejectSkill

        mock_context.parameters = {}
        skill = RejectSkill()

        with pytest.raises(SkillError) as exc_info:
            await skill.execute(mock_context)

        assert "请提供需求ID" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_not_found(self, mock_context):
        """Test error when requirement not found."""
        from skills.reject_requirement import RejectSkill

        skill = RejectSkill()

        with pytest.MonkeyPatch.context() as mp:
            mock_repo = AsyncMock()
            mock_repo.get_by_id = AsyncMock(return_value=None)

            mp.setattr(
                "agents.capabilities.requirements.skills.reject_requirement.RequirementRepository",
                lambda db: mock_repo
            )

            with pytest.raises(SkillError) as exc_info:
                await skill.execute(mock_context)

        assert "找不到需求" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_without_reason(self, mock_context, mock_requirement):
        """Test rejection without reason (should still work)."""
        from skills.reject_requirement import RejectSkill

        mock_context.parameters = {"requirement_id": "req_001"}
        skill = RejectSkill()

        with pytest.MonkeyPatch.context() as mp:
            mock_repo = AsyncMock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_requirement)
            mock_repo.reject = AsyncMock(return_value=mock_requirement)

            mp.setattr(
                "agents.capabilities.requirements.skills.reject_requirement.RequirementRepository",
                lambda db: mock_repo
            )

            result = await skill.execute(mock_context)

        assert result.success is True
        mock_repo.reject.assert_called_once()
