"""Test ConfirmSkill - Confirm a requirement."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.infra.skill.models import Permission, SkillContext, SkillError
from shared.messaging.inbound.models import Platform, UnifiedMessage
from shared.models.user import User


class TestConfirmSkillMetadata:
    """Test ConfirmSkill metadata."""

    def test_skill_name(self):
        from agents.capabilities.requirements.skills.confirm_requirement import ConfirmSkill
        skill = ConfirmSkill()
        assert skill.name == "confirm"

    def test_skill_commands(self):
        from agents.capabilities.requirements.skills.confirm_requirement import ConfirmSkill
        skill = ConfirmSkill()
        assert "/confirm" in skill.commands

    def test_skill_permissions(self):
        from agents.capabilities.requirements.skills.confirm_requirement import ConfirmSkill
        skill = ConfirmSkill()
        assert Permission.DB_WRITE in skill.permissions
        assert Permission.GATEWAY_REPLY in skill.permissions


class TestConfirmSkillExecute:
    """Test ConfirmSkill execution."""

    @pytest.fixture
    def mock_context(self):
        """Create mock context."""
        message = UnifiedMessage(
            platform=Platform.FEISHU,
            message_id="msg_001",
            chat_id="chat_001",
            sender_id="user_001",
            timestamp=datetime.now(UTC),
            content="/confirm req_001",
        )
        user = User(id="user_001", name="Test User")
        db = AsyncMock()
        return SkillContext(
            message=message,
            user=user,
            parameters={"requirement_id": "req_001"},
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
        """Test successful confirmation."""
        from agents.capabilities.requirements.skills.confirm_requirement import ConfirmSkill

        skill = ConfirmSkill()

        with pytest.MonkeyPatch.context() as mp:
            mock_repo = AsyncMock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_requirement)
            mock_repo.confirm = AsyncMock(return_value=mock_requirement)

            mp.setattr(
                "agents.capabilities.requirements.skills.confirm_requirement.RequirementRepository",
                lambda db: mock_repo
            )

            result = await skill.execute(mock_context)

        assert result.success is True
        assert "已确认" in result.response.card.title

    @pytest.mark.asyncio
    async def test_execute_missing_id(self, mock_context):
        """Test error when requirement ID not provided."""
        from agents.capabilities.requirements.skills.confirm_requirement import ConfirmSkill

        mock_context.parameters = {}
        skill = ConfirmSkill()

        with pytest.raises(SkillError) as exc_info:
            await skill.execute(mock_context)

        assert "请提供需求ID" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_not_found(self, mock_context):
        """Test error when requirement not found."""
        from agents.capabilities.requirements.skills.confirm_requirement import ConfirmSkill

        skill = ConfirmSkill()

        with pytest.MonkeyPatch.context() as mp:
            mock_repo = AsyncMock()
            mock_repo.get_by_id = AsyncMock(return_value=None)

            mp.setattr(
                "agents.capabilities.requirements.skills.confirm_requirement.RequirementRepository",
                lambda db: mock_repo
            )

            with pytest.raises(SkillError) as exc_info:
                await skill.execute(mock_context)

        assert "找不到需求" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_already_confirmed(self, mock_context, mock_requirement):
        """Test error when requirement already confirmed."""
        from agents.capabilities.requirements.skills.confirm_requirement import ConfirmSkill

        mock_requirement.status = "confirmed"
        skill = ConfirmSkill()

        with pytest.MonkeyPatch.context() as mp:
            mock_repo = AsyncMock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_requirement)

            mp.setattr(
                "agents.capabilities.requirements.skills.confirm_requirement.RequirementRepository",
                lambda db: mock_repo
            )

            with pytest.raises(SkillError) as exc_info:
                await skill.execute(mock_context)

        assert "已被处理" in str(exc_info.value)
