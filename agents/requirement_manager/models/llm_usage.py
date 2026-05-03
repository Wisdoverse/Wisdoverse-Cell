"""
LLM usage persistence model.

Records agent LLM calls for cost tracking and analysis.
"""
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.core.ids import generate_ulid

from .base import Base


class LLMUsage(Base):
    """
    LLM usage table.

    Stores detailed information for each LLM call, including:
    - Token usage
    - Cost estimates
    - Latency metrics
    - Success/failure state
    """
    __tablename__ = "llm_usage"

    id: Mapped[str] = mapped_column(
        String(26),
        primary_key=True,
        default=generate_ulid
    )

    # Caller metadata
    agent_id: Mapped[str] = mapped_column(String(50), index=True)
    task_type: Mapped[str] = mapped_column(String(50), index=True)  # extraction/generation/analysis

    # Model metadata
    model: Mapped[str] = mapped_column(String(100))

    # Token statistics
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)

    # Cost in USD
    cost_usd: Mapped[float] = mapped_column(Float)

    # Performance metrics
    latency_ms: Mapped[int] = mapped_column(Integer)

    # State
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Optional tracing metadata
    trace_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True
    )

    # Composite indexes optimize common queries.
    __table_args__ = (
        Index('ix_llm_usage_agent_date', 'agent_id', 'created_at'),
        Index('ix_llm_usage_date_success', 'created_at', 'success'),
    )

    def __repr__(self) -> str:
        return f"<LLMUsage id={self.id} agent={self.agent_id} tokens={self.input_tokens}+{self.output_tokens}>"
