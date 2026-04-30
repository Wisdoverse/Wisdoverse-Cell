"""
Shared Database - 共享数据库组件
"""
from .base_database import BaseDatabaseManager
from .repository import UserRepository

__all__ = [
    "BaseDatabaseManager",
    "UserRepository",
]
