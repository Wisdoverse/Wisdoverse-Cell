"""
Alembic environment — async migration runner for Wisdoverse Cell.
"""
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import all models so metadata is populated for Alembic autogenerate checks.
from agents.dev_agent.models.base import Base as DevAgentBase
from agents.dev_agent.models.dev import (  # noqa: F401
    DevAgentEventOutbox,
    DevAgentTask,
    DevAgentWorkflowLog,
)
from agents.pjm_agent.models import (  # noqa: F401
    AlertLog,
    DecompositionRecord,
    PJMEventOutbox,
    PMConfigCache,
)
from agents.pjm_agent.models.base import Base as PJMAgentBase
from agents.qa_agent.models import (  # noqa: F401
    QAAcceptanceResult,
    QAAcceptanceRun,
    QAEventOutbox,
)
from agents.qa_agent.models.base import Base as QAAgentBase
from agents.requirement_manager.models import (  # noqa: F401
    ChatMessage,
    FeedbackRecord,
    LLMUsage,
    Meeting,
    OpenQuestion,
    Requirement,
)
from agents.requirement_manager.models.base import Base as RequirementManagerBase
from services.gateways.channel.models import ChannelGatewayEventOutbox  # noqa: F401
from services.gateways.channel.models.base import Base as ChannelGatewayBase
from services.gateways.user_interaction.models import (  # noqa: F401
    CardOperation,
    ConversationHistory,
    DailyProgress,
    UserInteractionEventOutbox,
)
from services.gateways.user_interaction.models.base import Base as UserInteractionBase
from services.orchestration.coordinator.db.base import Base as CoordinatorBase
from services.orchestration.coordinator.db.event_outbox import (  # noqa: F401
    CoordinatorEventOutbox,
)
from shared.capabilities.analysis.models import (  # noqa: F401
    AnalysisEventOutbox,
    ReportLog,
)
from shared.capabilities.analysis.models.base import Base as AnalysisBase
from shared.capabilities.sync.models import (  # noqa: F401
    SubtaskMapping,
    SyncEventOutbox,
    SyncLock,
    SyncLog,
    SyncMapping,
)
from shared.capabilities.sync.models.base import Base as SyncBase
from shared.config import settings
from shared.control_plane.tables import control_plane_metadata
from shared.evolution.db.tables import evolution_metadata
from shared.models.user import User  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = [
    RequirementManagerBase.metadata,
    control_plane_metadata,
    PJMAgentBase.metadata,
    QAAgentBase.metadata,
    DevAgentBase.metadata,
    UserInteractionBase.metadata,
    ChannelGatewayBase.metadata,
    CoordinatorBase.metadata,
    SyncBase.metadata,
    AnalysisBase.metadata,
    evolution_metadata,
]


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL to stdout."""
    url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with an async engine."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = settings.database_url
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
