"""
User Model - 统一用户表

跨平台身份映射，支持 Feishu、Wecom、Web 等平台账号关联。
"""
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from agents.requirement_manager.models.base import Base
from shared.utils.id_generator import IDPrefix, generate_id


class User(Base):
    """统一用户表 - 跨平台身份映射"""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        default=lambda: generate_id(IDPrefix.USER)
    )

    # 身份标识
    email: Mapped[Optional[str]] = mapped_column(
        String(128), unique=True, nullable=True, index=True
    )
    phone: Mapped[Optional[str]] = mapped_column(
        String(32), unique=True, nullable=True, index=True
    )

    # 基本信息
    name: Mapped[str] = mapped_column(String(64))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # 平台账号映射
    feishu_open_id: Mapped[Optional[str]] = mapped_column(
        String(64), unique=True, nullable=True, index=True
    )
    feishu_user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    wecom_user_id: Mapped[Optional[str]] = mapped_column(
        String(64), unique=True, nullable=True, index=True
    )
    web_user_id: Mapped[Optional[str]] = mapped_column(
        String(64), unique=True, nullable=True, index=True
    )

    # 活跃信息
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC)
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC)
    )
    last_active_platform: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} name={self.name}>"
