"""
Alembic environment — async migration runner for Wisdoverse Cell.
"""
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
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

# Alembic 1.18 hardcodes `alembic_version.version_num` as `String(32)`
# at table-creation time. Wisdoverse Cell revision IDs are
# date-prefixed and can exceed 32 chars (e.g.
# `20260511_user_interaction_event_outbox` is 38). Widen the column
# unconditionally before the migration chain runs, so a fresh
# database accepts every revision id.
_ALEMBIC_VERSION_PREP_STATEMENTS: tuple[str, ...] = (
    # Create the version table with the wider column on fresh databases
    # so the very first revision_id can be inserted without overflowing
    # the default varchar(32).
    """
    CREATE TABLE IF NOT EXISTS alembic_version (
        version_num VARCHAR(64) NOT NULL,
        CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
    );
    """,
    # On databases that already have alembic_version from an earlier
    # Alembic run (varchar(32)), widen the column so future revision
    # ids fit.
    "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64);",
)


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


def _ensure_version_table_width(connection) -> None:
    """Ensure alembic_version.version_num accepts our long revision ids."""
    for statement in _ALEMBIC_VERSION_PREP_STATEMENTS:
        connection.execute(text(statement))


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
        await connection.run_sync(_ensure_version_table_width)
        await connection.commit()
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
