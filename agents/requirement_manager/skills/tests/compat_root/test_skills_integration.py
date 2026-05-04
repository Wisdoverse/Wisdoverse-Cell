"""Integration tests for P0 skills with database."""
import sys
from pathlib import Path

# Ensure project root in Python path
_project_root = next(
    parent for parent in Path(__file__).resolve().parents
    if (parent / "pyproject.toml").exists()
)
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import os
from datetime import UTC, datetime
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Test environment config
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5433")
os.environ.setdefault("POSTGRES_DB", "projectcell_test")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")

from agents.requirement_manager.db.repository import RequirementRepository
from agents.requirement_manager.models import Base, Requirement, RequirementStatus
from shared.infra.skill.models import SkillContext
from shared.messaging.inbound.models import Platform, UnifiedMessage
from shared.models.user import User


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    pg_host = os.environ.get("POSTGRES_HOST", "localhost")
    pg_port = os.environ.get("POSTGRES_PORT", "5433")
    pg_db = os.environ.get("POSTGRES_DB", "projectcell_test")
    pg_user = os.environ.get("POSTGRES_USER", "test")
    pg_password = os.environ.get("POSTGRES_PASSWORD", "test")
    database_url = f"postgresql+asyncpg://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"
    engine = create_async_engine(database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with async_session() as session:
        yield session
        await session.rollback()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def sample_requirement(db_session) -> Requirement:
    """Create sample requirement in DB."""
    req = Requirement(
        id="req_test_001",
        title="Test Requirement",
        description="A test requirement for integration testing",
        status=RequirementStatus.PENDING.value,
        priority="high",
        category="功能",
    )
    db_session.add(req)
    await db_session.commit()
    await db_session.refresh(req)
    return req


class TestListSkillIntegration:
    """Integration tests for ListSkill."""

    @pytest.mark.asyncio
    async def test_list_with_real_db(self, db_session, sample_requirement):
        """Test ListSkill with real database."""
        from skills.list_requirements import ListSkill

        message = UnifiedMessage(
            platform=Platform.FEISHU,
            message_id="msg_001",
            chat_id="chat_001",
            sender_id="user_001",
            timestamp=datetime.now(UTC),
            content="/list",
        )
        user = User(id="user_001", name="Test User")
        context = SkillContext(
            message=message,
            user=user,
            parameters={},
            db=db_session,
        )

        skill = ListSkill()
        result = await skill.execute(context)

        assert result.success is True
        assert "Test Requirement" in result.response.card.content


class TestConfirmSkillIntegration:
    """Integration tests for ConfirmSkill."""

    @pytest.mark.asyncio
    async def test_confirm_with_real_db(self, db_session, sample_requirement):
        """Test ConfirmSkill with real database."""
        from skills.confirm_requirement import ConfirmSkill

        message = UnifiedMessage(
            platform=Platform.FEISHU,
            message_id="msg_001",
            chat_id="chat_001",
            sender_id="user_001",
            timestamp=datetime.now(UTC),
            content="/confirm req_test_001",
        )
        user = User(id="user_001", name="Test User")
        context = SkillContext(
            message=message,
            user=user,
            parameters={"requirement_id": "req_test_001"},
            db=db_session,
        )

        skill = ConfirmSkill()
        result = await skill.execute(context)

        assert result.success is True

        # Verify DB state
        repo = RequirementRepository(db_session)
        req = await repo.get_by_id("req_test_001")
        assert req.status == RequirementStatus.CONFIRMED.value


class TestRejectSkillIntegration:
    """Integration tests for RejectSkill."""

    @pytest.mark.asyncio
    async def test_reject_with_real_db(self, db_session, sample_requirement):
        """Test RejectSkill with real database."""
        from skills.reject_requirement import RejectSkill

        message = UnifiedMessage(
            platform=Platform.FEISHU,
            message_id="msg_001",
            chat_id="chat_001",
            sender_id="user_001",
            timestamp=datetime.now(UTC),
            content="/reject req_test_001 Not in scope",
        )
        user = User(id="user_001", name="Test User")
        context = SkillContext(
            message=message,
            user=user,
            parameters={"requirement_id": "req_test_001", "reason": "Not in scope"},
            db=db_session,
        )

        skill = RejectSkill()
        result = await skill.execute(context)

        assert result.success is True

        # Verify DB state
        repo = RequirementRepository(db_session)
        req = await repo.get_by_id("req_test_001")
        assert req.status == RequirementStatus.REJECTED.value
        assert req.rejection_reason == "Not in scope"
