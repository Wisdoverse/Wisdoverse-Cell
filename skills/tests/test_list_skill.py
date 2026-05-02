"""Test ListSkill - List pending requirements."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.infra.skill.models import Permission, SkillContext
from shared.messaging.inbound.models import Platform, UnifiedMessage
from shared.models.user import User


class TestListSkillMetadata:
    """Test ListSkill metadata and configuration."""

    def test_skill_name(self):
        from skills.list_requirements import ListSkill
        skill = ListSkill()
        assert skill.name == "list"

    def test_skill_commands(self):
        from skills.list_requirements import ListSkill
        skill = ListSkill()
        assert "/list" in skill.commands
        assert "/需求" in skill.commands

    def test_skill_patterns(self):
        from skills.list_requirements import ListSkill
        skill = ListSkill()
        assert any("待确认" in p for p in skill.patterns)

    def test_skill_permissions(self):
        from skills.list_requirements import ListSkill
        skill = ListSkill()
        assert Permission.DB_READ in skill.permissions
        assert Permission.GATEWAY_REPLY in skill.permissions


class TestListSkillExecute:
    """Test ListSkill execution."""

    @pytest.fixture
    def mock_context(self):
        """Create mock context with DB."""
        message = UnifiedMessage(
            platform=Platform.FEISHU,
            message_id="msg_001",
            chat_id="chat_001",
            sender_id="user_001",
            timestamp=datetime.now(UTC),
            content="/list",
        )
        user = User(id="user_001", name="Test User")
        db = AsyncMock()
        return SkillContext(
            message=message,
            user=user,
            parameters={},
            db=db,
        )

    @pytest.fixture
    def mock_requirement(self):
        """Create mock requirement."""
        req = MagicMock()
        req.id = "req_001"
        req.title = "Test Requirement"
        req.description = "A test requirement description"
        req.priority = "high"
        req.category = "功能"
        req.status = "pending"
        return req

    @pytest.mark.asyncio
    async def test_execute_returns_card(self, mock_context, mock_requirement):
        """Test execute returns card with requirements."""
        from skills.list_requirements import ListSkill

        skill = ListSkill()

        with pytest.MonkeyPatch.context() as mp:
            mock_repo = AsyncMock()
            mock_repo.list_all = AsyncMock(return_value=([mock_requirement], 1))

            mp.setattr(
                "agents.capabilities.requirements.skills.list_requirements.RequirementRepository",
                lambda db: mock_repo
            )

            result = await skill.execute(mock_context)

        assert result.success is True
        assert result.response is not None
        assert result.response.card is not None
        assert "待确认需求" in result.response.card.title

    @pytest.mark.asyncio
    async def test_execute_empty_list(self, mock_context):
        """Test execute with no requirements."""
        from skills.list_requirements import ListSkill

        skill = ListSkill()

        with pytest.MonkeyPatch.context() as mp:
            mock_repo = AsyncMock()
            mock_repo.list_all = AsyncMock(return_value=([], 0))

            mp.setattr(
                "agents.capabilities.requirements.skills.list_requirements.RequirementRepository",
                lambda db: mock_repo
            )

            result = await skill.execute(mock_context)

        assert result.success is True
        assert "暂无" in result.response.card.content

    @pytest.mark.asyncio
    async def test_execute_pagination(self, mock_context, mock_requirement):
        """Test pagination parameter handling."""
        from skills.list_requirements import ListSkill

        mock_context.parameters = {"page": "2"}
        skill = ListSkill()

        with pytest.MonkeyPatch.context() as mp:
            mock_repo = AsyncMock()
            mock_repo.list_all = AsyncMock(return_value=([mock_requirement], 10))

            mp.setattr(
                "agents.capabilities.requirements.skills.list_requirements.RequirementRepository",
                lambda db: mock_repo
            )

            await skill.execute(mock_context)

        mock_repo.list_all.assert_called_once()
        call_kwargs = mock_repo.list_all.call_args[1]
        assert call_kwargs["skip"] == 5

    @pytest.mark.asyncio
    async def test_execute_no_db_raises_error(self, mock_context):
        """Test execute raises error when DB not available."""
        from shared.infra.skill.models import SkillError
        from skills.list_requirements import ListSkill

        mock_context.db = None
        skill = ListSkill()

        with pytest.raises(SkillError) as exc_info:
            await skill.execute(mock_context)

        assert "数据库不可用" in str(exc_info.value)
