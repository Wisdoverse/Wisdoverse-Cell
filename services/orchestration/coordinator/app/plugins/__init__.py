"""Coordinator app runtime plugins."""

from .outbox_dispatcher import CoordinatorOutboxDispatcherPlugin

__all__ = ["CoordinatorOutboxDispatcherPlugin"]
