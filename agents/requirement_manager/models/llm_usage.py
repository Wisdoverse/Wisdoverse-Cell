"""
LLM Usage Model - LLM 调用记录模型

记录所有 Agent 的 LLM 调用，用于成本追踪和分析。
"""
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.core.ids import generate_ulid

from .base import Base


class LLMUsage(Base):
    """
    LLM 调用记录表

    存储每次 LLM 调用的详细信息，包括:
    - Token 使用量
    - 成本估算
    - 延迟统计
    - 成功/失败状态
    """
    __tablename__ = "llm_usage"

    id: Mapped[str] = mapped_column(
        String(26),
        primary_key=True,
        default=generate_ulid
    )

    # 调用方信息
    agent_id: Mapped[str] = mapped_column(String(50), index=True)
    task_type: Mapped[str] = mapped_column(String(50), index=True)  # extraction/generation/analysis

    # 模型信息
    model: Mapped[str] = mapped_column(String(100))

    # Token 统计
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)

    # 成本（美元）
    cost_usd: Mapped[float] = mapped_column(Float)

    # 性能统计
    latency_ms: Mapped[int] = mapped_column(Integer)

    # 状态
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 可选的追踪信息
    trace_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True
    )

    # 复合索引优化查询
    __table_args__ = (
        Index('ix_llm_usage_agent_date', 'agent_id', 'created_at'),
        Index('ix_llm_usage_date_success', 'created_at', 'success'),
    )

    def __repr__(self) -> str:
        return f"<LLMUsage id={self.id} agent={self.agent_id} tokens={self.input_tokens}+{self.output_tokens}>"
