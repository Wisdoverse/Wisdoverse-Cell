"""
Shared Database components.
"""
from .base import Base
from .base_database import BaseDatabaseManager

__all__ = [
    "Base",
    "BaseDatabaseManager",
    "UserRepository",
]


def __getattr__(name: str):
    """Lazily expose repositories without importing shared models during package init."""
    if name == "UserRepository":
        from .repository import UserRepository

        return UserRepository
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
