"""
Unit Test Fixtures - analysis_agent

提供单元测试所需的数据库会话和其他 fixtures。
"""
import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中（必须在其他导入之前）
_project_root = Path(__file__).parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import os
from typing import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# 测试环境配置
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5433")
os.environ.setdefault("POSTGRES_DB", "projectcell_test")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")

# 导入所有 model 以便 SQLAlchemy 注册它们
from shared.capabilities.analysis.models.base import Base
from shared.capabilities.analysis.models.report import ReportLog  # noqa: F401


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    测试用数据库会话

    每个测试使用独立的事务，测试结束后回滚。
    """
    pg_host = os.environ.get("POSTGRES_HOST", "localhost")
    pg_port = os.environ.get("POSTGRES_PORT", "5433")
    pg_db = os.environ.get("POSTGRES_DB", "projectcell_test")
    pg_user = os.environ.get("POSTGRES_USER", "test")
    pg_password = os.environ.get("POSTGRES_PASSWORD", "test")
    database_url = f"postgresql+asyncpg://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"
    engine = create_async_engine(database_url, echo=False)

    # 创建表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 创建会话
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        # 测试后回滚
        await session.rollback()

    # 清理表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
def mock_event_bus():
    """模拟 EventBus 实例"""
    bus = AsyncMock()
    bus.connect = AsyncMock()
    bus.disconnect = AsyncMock()
    bus.publish = AsyncMock()
    bus.subscribe = AsyncMock()
    return bus


@pytest.fixture
def mock_bitable():
    """模拟 bitable_service 实例"""
    bitable = AsyncMock()
    bitable.list_all_records = AsyncMock(return_value=[])
    return bitable
