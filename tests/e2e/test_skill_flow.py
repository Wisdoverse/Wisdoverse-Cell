"""
End-to-end tests for skill execution flow.

Tests the complete flow from command input to response generation.
"""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.infra.skill import SkillContext, SkillError
from shared.messaging.inbound import Platform, UnifiedCard, UnifiedMessage
from skills import ConfirmSkill, ListSkill, RejectSkill


def create_message(content: str, platform: Platform = Platform.FEISHU, chat_id: str = "chat_e2e_001") -> UnifiedMessage:
    """Create a test message."""
    return UnifiedMessage(
        platform=platform,
        message_id="msg_e2e_001",
        chat_id=chat_id,
        sender_id="sender_e2e_001",
        sender_name="E2E Test User",
        content=content,
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def mock_db():
    """Create a mock async database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def mock_user():
    """Create a mock user context."""
    user = MagicMock()
    user.id = "user_e2e_001"
    user.name = "E2E Test User"
    user.platform = "feishu"
    return user


@pytest.fixture
def mock_requirement():
    """Create a mock requirement model."""
    req = MagicMock()
    req.id = "req_e2e_001"
    req.title = "E2E Test Requirement"
    req.description = "Created for E2E testing"
    req.status = "pending"
    req.priority = "high"
    req.category = "feature"
    return req


class TestListSkillE2E:
    """E2E tests for ListSkill."""

    @pytest.mark.asyncio
    async def test_full_list_flow_with_requirements(self, mock_db, mock_user, mock_requirement):
        """Test complete flow: /list command with requirements."""
        # Setup mock repository
        mock_repo_class = MagicMock()
        mock_repo = MagicMock()
        mock_repo.list_all = AsyncMock(return_value=([mock_requirement], 1))
        mock_repo_class.return_value = mock_repo

        # Create context
        message = create_message("/list")
        context = SkillContext(
            message=message,
            user=mock_user,
            parameters={},
            db=mock_db,
        )

        # Execute skill with patched repository
        skill = ListSkill()
        with patch("agents.requirement_manager.skills.list_requirements.RequirementRepository", mock_repo_class):
            result = await skill.execute(context)

        # Verify result
        assert result.success is True
        assert result.response is not None
        assert result.response.card is not None

    @pytest.mark.asyncio
    async def test_full_list_flow_empty(self, mock_db, mock_user):
        """Test complete flow: /list command with no requirements."""
        mock_repo_class = MagicMock()
        mock_repo = MagicMock()
        mock_repo.list_all = AsyncMock(return_value=([], 0))
        mock_repo_class.return_value = mock_repo

        message = create_message("/list")
        context = SkillContext(
            message=message,
            user=mock_user,
            parameters={},
            db=mock_db,
        )

        skill = ListSkill()
        with patch("agents.requirement_manager.skills.list_requirements.RequirementRepository", mock_repo_class):
            result = await skill.execute(context)

        assert result.success is True
        # Should have an empty-state message.
        assert result.response.card is not None


class TestConfirmSkillE2E:
    """E2E tests for ConfirmSkill."""

    @pytest.mark.asyncio
    async def test_full_confirm_flow_success(self, mock_db, mock_user, mock_requirement):
        """Test complete flow: /confirm command success."""
        mock_requirement.status = "pending"

        mock_repo_class = MagicMock()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=mock_requirement)
        mock_repo.confirm = AsyncMock()
        mock_repo_class.return_value = mock_repo

        message = create_message("/confirm req_e2e_001")
        context = SkillContext(
            message=message,
            user=mock_user,
            parameters={"requirement_id": "req_e2e_001"},
            db=mock_db,
        )

        skill = ConfirmSkill()
        with patch("agents.requirement_manager.skills.confirm_requirement.RequirementRepository", mock_repo_class):
            result = await skill.execute(context)

        assert result.success is True
        mock_repo.confirm.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_confirm_flow_not_found(self, mock_db, mock_user):
        """Test complete flow: /confirm command with non-existent requirement."""
        mock_repo_class = MagicMock()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)
        mock_repo_class.return_value = mock_repo

        message = create_message("/confirm nonexistent")
        context = SkillContext(
            message=message,
            user=mock_user,
            parameters={"requirement_id": "nonexistent"},
            db=mock_db,
        )

        skill = ConfirmSkill()
        with patch("agents.requirement_manager.skills.confirm_requirement.RequirementRepository", mock_repo_class):
            with pytest.raises(SkillError) as exc_info:
                await skill.execute(context)

        assert "找不到需求" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_full_confirm_flow_already_processed(self, mock_db, mock_user, mock_requirement):
        """Test complete flow: /confirm on already confirmed requirement."""
        mock_requirement.status = "confirmed"  # Already confirmed

        mock_repo_class = MagicMock()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=mock_requirement)
        mock_repo_class.return_value = mock_repo

        message = create_message("/confirm req_e2e_001")
        context = SkillContext(
            message=message,
            user=mock_user,
            parameters={"requirement_id": "req_e2e_001"},
            db=mock_db,
        )

        skill = ConfirmSkill()
        with patch("agents.requirement_manager.skills.confirm_requirement.RequirementRepository", mock_repo_class):
            with pytest.raises(SkillError) as exc_info:
                await skill.execute(context)

        assert "已被处理" in str(exc_info.value)


class TestRejectSkillE2E:
    """E2E tests for RejectSkill."""

    @pytest.mark.asyncio
    async def test_full_reject_flow_with_reason(self, mock_db, mock_user, mock_requirement):
        """Test complete flow: /reject command with reason."""
        mock_requirement.status = "pending"

        mock_repo_class = MagicMock()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=mock_requirement)
        mock_repo.reject = AsyncMock()
        mock_repo_class.return_value = mock_repo

        message = create_message("/reject req_e2e_001 Not aligned with current roadmap")
        context = SkillContext(
            message=message,
            user=mock_user,
            parameters={
                "requirement_id": "req_e2e_001",
                "reason": "Not aligned with current roadmap"
            },
            db=mock_db,
        )

        skill = RejectSkill()
        with patch("agents.requirement_manager.skills.reject_requirement.RequirementRepository", mock_repo_class):
            result = await skill.execute(context)

        assert result.success is True
        mock_repo.reject.assert_called_once()
        # Verify reason was passed
        call_args = mock_repo.reject.call_args
        assert call_args[0][1] == "Not aligned with current roadmap"

    @pytest.mark.asyncio
    async def test_full_reject_flow_without_reason(self, mock_db, mock_user, mock_requirement):
        """Test complete flow: /reject command without reason."""
        mock_requirement.status = "pending"

        mock_repo_class = MagicMock()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=mock_requirement)
        mock_repo.reject = AsyncMock()
        mock_repo_class.return_value = mock_repo

        message = create_message("/reject req_e2e_001")
        context = SkillContext(
            message=message,
            user=mock_user,
            parameters={"requirement_id": "req_e2e_001"},
            db=mock_db,
        )

        skill = RejectSkill()
        with patch("agents.requirement_manager.skills.reject_requirement.RequirementRepository", mock_repo_class):
            result = await skill.execute(context)

        assert result.success is True
        mock_repo.reject.assert_called_once()


class TestSkillChainE2E:
    """E2E tests for skill chains (multiple skills in sequence)."""

    @pytest.mark.asyncio
    async def test_list_then_confirm_flow(self, mock_db, mock_user, mock_requirement):
        """Test flow: /list then /confirm from card button."""
        mock_requirement.status = "pending"

        mock_repo_class = MagicMock()
        mock_repo = MagicMock()
        mock_repo.list_all = AsyncMock(return_value=([mock_requirement], 1))
        mock_repo.get_by_id = AsyncMock(return_value=mock_requirement)
        mock_repo.confirm = AsyncMock()
        mock_repo_class.return_value = mock_repo

        # Step 1: List requirements
        list_message = create_message("/list")
        list_context = SkillContext(
            message=list_message,
            user=mock_user,
            parameters={},
            db=mock_db,
        )

        list_skill = ListSkill()
        with patch("agents.requirement_manager.skills.list_requirements.RequirementRepository", mock_repo_class):
            list_result = await list_skill.execute(list_context)

        assert list_result.success is True

        # Step 2: Confirm from card button click
        confirm_message = create_message("confirm req_e2e_001")
        confirm_context = SkillContext(
            message=confirm_message,
            user=mock_user,
            parameters={
                "action": "confirm",
                "requirement_id": "req_e2e_001"
            },
            db=mock_db,
        )

        confirm_skill = ConfirmSkill()
        with patch("agents.requirement_manager.skills.confirm_requirement.RequirementRepository", mock_repo_class):
            confirm_result = await confirm_skill.execute(confirm_context)

        assert confirm_result.success is True

    @pytest.mark.asyncio
    async def test_list_pagination_flow(self, mock_db, mock_user, mock_requirement):
        """Test flow: /list then pagination (next page)."""
        # Create multiple requirements
        requirements = [
            MagicMock(id=f"req_{i:03d}", title=f"Requirement {i}", description="",
                     status="pending", priority="medium", category="feature")
            for i in range(15)
        ]

        mock_repo_class = MagicMock()
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo

        # Page 1
        mock_repo.list_all = AsyncMock(return_value=(requirements[:5], 15))

        page1_message = create_message("/list")
        context_page1 = SkillContext(
            message=page1_message,
            user=mock_user,
            parameters={"page": 1},
            db=mock_db,
        )

        skill = ListSkill()
        with patch("agents.requirement_manager.skills.list_requirements.RequirementRepository", mock_repo_class):
            result1 = await skill.execute(context_page1)

        assert result1.success is True

        # Page 2 (from card button)
        mock_repo.list_all = AsyncMock(return_value=(requirements[5:10], 15))

        page2_message = create_message("list_page 2")
        context_page2 = SkillContext(
            message=page2_message,
            user=mock_user,
            parameters={"action": "list_page", "page": 2},
            db=mock_db,
        )

        with patch("agents.requirement_manager.skills.list_requirements.RequirementRepository", mock_repo_class):
            result2 = await skill.execute(context_page2)

        assert result2.success is True


class TestCrossPlatformE2E:
    """E2E tests for cross-platform skill execution."""

    @pytest.mark.asyncio
    async def test_feishu_platform_card_format(self, mock_db, mock_requirement):
        """Test that Feishu platform returns correct card format."""
        user = MagicMock()
        user.id = "feishu_user_001"
        user.name = "Feishu User"
        user.platform = "feishu"

        mock_requirement.status = "pending"

        mock_repo_class = MagicMock()
        mock_repo = MagicMock()
        mock_repo.list_all = AsyncMock(return_value=([mock_requirement], 1))
        mock_repo_class.return_value = mock_repo

        message = create_message("/list", platform=Platform.FEISHU, chat_id="oc_xxx")
        context = SkillContext(
            message=message,
            user=user,
            parameters={},
            db=mock_db,
        )

        skill = ListSkill()
        with patch("agents.requirement_manager.skills.list_requirements.RequirementRepository", mock_repo_class):
            result = await skill.execute(context)

        assert result.success is True
        assert isinstance(result.response.card, UnifiedCard)

    @pytest.mark.asyncio
    async def test_wecom_platform_card_format(self, mock_db, mock_requirement):
        """Test that WeCom platform returns correct card format."""
        user = MagicMock()
        user.id = "wecom_user_001"
        user.name = "WeCom User"
        user.platform = "wecom"

        mock_requirement.status = "pending"

        mock_repo_class = MagicMock()
        mock_repo = MagicMock()
        mock_repo.list_all = AsyncMock(return_value=([mock_requirement], 1))
        mock_repo_class.return_value = mock_repo

        message = create_message("/list", platform=Platform.WECOM, chat_id="wecom_chat_001")
        context = SkillContext(
            message=message,
            user=user,
            parameters={},
            db=mock_db,
        )

        skill = ListSkill()
        with patch("agents.requirement_manager.skills.list_requirements.RequirementRepository", mock_repo_class):
            result = await skill.execute(context)

        assert result.success is True
        # UnifiedCard should work for both platforms
        assert isinstance(result.response.card, UnifiedCard)


class TestErrorHandlingE2E:
    """E2E tests for error handling scenarios."""

    @pytest.mark.asyncio
    async def test_db_connection_error(self, mock_user):
        """Test handling of database connection error."""
        message = create_message("/list")
        context = SkillContext(
            message=message,
            user=mock_user,
            parameters={},
            db=None,  # No DB connection
        )

        skill = ListSkill()
        with pytest.raises(SkillError) as exc_info:
            await skill.execute(context)

        assert "数据库不可用" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_missing_required_parameter(self, mock_db, mock_user):
        """Test handling of missing required parameter."""
        message = create_message("/confirm")
        context = SkillContext(
            message=message,
            user=mock_user,
            parameters={},  # Missing requirement_id
            db=mock_db,
        )

        skill = ConfirmSkill()
        with pytest.raises(SkillError) as exc_info:
            await skill.execute(context)

        assert "请提供需求ID" in str(exc_info.value)
