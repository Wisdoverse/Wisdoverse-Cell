"""
User repository tests.
"""
import sys
from pathlib import Path

# Ensure the project root is on the Python path.
_project_root = Path(__file__).parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Test environment configuration.
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5433")
os.environ.setdefault("POSTGRES_DB", "wisdoverse-cell_test")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")

from shared.db.base import Base
from shared.db.repository import UserRepository
from shared.models.platform import Platform
from shared.models.user import User


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Database session for tests."""
    pg_host = os.environ.get("POSTGRES_HOST", "localhost")
    pg_port = os.environ.get("POSTGRES_PORT", "5433")
    pg_db = os.environ.get("POSTGRES_DB", "wisdoverse-cell_test")
    pg_user = os.environ.get("POSTGRES_USER", "test")
    pg_password = os.environ.get("POSTGRES_PASSWORD", "test")
    database_url = f"postgresql+asyncpg://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"
    engine = create_async_engine(database_url, echo=False)

    # Create tables.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session.
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with async_session() as session:
        yield session
        await session.rollback()

    # Clean up tables.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_and_get_by_id(db_session: AsyncSession):
    """Create a user and fetch it by ID."""
    repo = UserRepository(db_session)

    # Create user.
    user = User(
        name="Test User",
        email="test@example.com",
        feishu_open_id="ou_test123"
    )
    created_user = await repo.create(user)

    # Validate returned user.
    assert created_user.id is not None
    assert created_user.id.startswith("usr_")
    assert created_user.name == "Test User"
    assert created_user.email == "test@example.com"

    # Fetch by ID.
    fetched_user = await repo.get_by_id(created_user.id)
    assert fetched_user is not None
    assert fetched_user.id == created_user.id
    assert fetched_user.name == "Test User"


@pytest.mark.asyncio
async def test_get_by_email(db_session: AsyncSession):
    """Fetch a user by email."""
    repo = UserRepository(db_session)

    # Create user.
    user = User(
        name="Email User",
        email="email@example.com"
    )
    await repo.create(user)

    # Fetch by email.
    fetched_user = await repo.get_by_email("email@example.com")
    assert fetched_user is not None
    assert fetched_user.name == "Email User"

    # Missing email.
    not_found = await repo.get_by_email("notfound@example.com")
    assert not_found is None


@pytest.mark.asyncio
async def test_get_by_phone(db_session: AsyncSession):
    """Fetch a user by phone number."""
    repo = UserRepository(db_session)

    # Create user.
    user = User(
        name="Phone User",
        phone="13800138000"
    )
    await repo.create(user)

    # Fetch by phone number.
    fetched_user = await repo.get_by_phone("13800138000")
    assert fetched_user is not None
    assert fetched_user.name == "Phone User"

    # Missing phone number.
    not_found = await repo.get_by_phone("10000000000")
    assert not_found is None


@pytest.mark.asyncio
async def test_get_by_platform_id_feishu(db_session: AsyncSession):
    """Fetch a user by Feishu open_id."""
    repo = UserRepository(db_session)

    # Create user.
    user = User(
        name="Feishu User",
        feishu_open_id="ou_feishu123",
        feishu_user_id="user_feishu123"
    )
    await repo.create(user)

    # Fetch by Feishu ID.
    fetched_user = await repo.get_by_platform_id(Platform.FEISHU, "ou_feishu123")
    assert fetched_user is not None
    assert fetched_user.name == "Feishu User"
    assert fetched_user.feishu_user_id == "user_feishu123"

    # Missing ID.
    not_found = await repo.get_by_platform_id(Platform.FEISHU, "ou_notfound")
    assert not_found is None


@pytest.mark.asyncio
async def test_get_by_platform_id_wecom(db_session: AsyncSession):
    """Fetch a user by WeCom user_id."""
    repo = UserRepository(db_session)

    # Create user.
    user = User(
        name="Wecom User",
        wecom_user_id="wecom_user123"
    )
    await repo.create(user)

    # Fetch by WeCom ID.
    fetched_user = await repo.get_by_platform_id(Platform.WECOM, "wecom_user123")
    assert fetched_user is not None
    assert fetched_user.name == "Wecom User"

    # Missing ID.
    not_found = await repo.get_by_platform_id(Platform.WECOM, "wecom_notfound")
    assert not_found is None


@pytest.mark.asyncio
async def test_get_by_platform_id_web(db_session: AsyncSession):
    """Fetch a user by web user_id."""
    repo = UserRepository(db_session)

    # Create user.
    user = User(
        name="Web User",
        web_user_id="web_user123"
    )
    await repo.create(user)

    # Fetch by web ID.
    fetched_user = await repo.get_by_platform_id(Platform.WEB, "web_user123")
    assert fetched_user is not None
    assert fetched_user.name == "Web User"

    # Missing ID.
    not_found = await repo.get_by_platform_id(Platform.WEB, "web_notfound")
    assert not_found is None


@pytest.mark.asyncio
async def test_update(db_session: AsyncSession):
    """Update a user."""
    repo = UserRepository(db_session)

    # Create user.
    user = User(
        name="Original Name",
        email="update@example.com"
    )
    created_user = await repo.create(user)

    # Update user.
    created_user.name = "Updated Name"
    created_user.last_active_platform = "feishu"
    updated_user = await repo.update(created_user)

    # Validate update result.
    assert updated_user.name == "Updated Name"
    assert updated_user.last_active_platform == "feishu"

    # Fetch again to validate persistence.
    fetched_user = await repo.get_by_id(created_user.id)
    assert fetched_user is not None
    assert fetched_user.name == "Updated Name"
    assert fetched_user.last_active_platform == "feishu"


@pytest.mark.asyncio
async def test_user_with_multiple_platforms(db_session: AsyncSession):
    """User can be linked to multiple platforms."""
    repo = UserRepository(db_session)

    # Create a user linked to multiple platforms.
    user = User(
        name="Multi Platform User",
        email="multi@example.com",
        phone="13900139000",
        feishu_open_id="ou_multi123",
        feishu_user_id="user_multi123",
        wecom_user_id="wecom_multi123",
        web_user_id="web_multi123"
    )
    await repo.create(user)

    # Every lookup method returns the same user.
    by_email = await repo.get_by_email("multi@example.com")
    by_phone = await repo.get_by_phone("13900139000")
    by_feishu = await repo.get_by_platform_id(Platform.FEISHU, "ou_multi123")
    by_wecom = await repo.get_by_platform_id(Platform.WECOM, "wecom_multi123")
    by_web = await repo.get_by_platform_id(Platform.WEB, "web_multi123")

    # All query results should point to the same user.
    assert by_email is not None
    assert by_email.id == by_phone.id == by_feishu.id == by_wecom.id == by_web.id
    assert by_email.name == "Multi Platform User"
