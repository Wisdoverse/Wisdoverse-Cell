# API
from .admin import router as admin_router
from .health import router as health_router

__all__ = [
    "health_router",
    "admin_router",
]
