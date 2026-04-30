"""Feishu event handlers"""

# Handlers are imported lazily to avoid circular imports
# and to handle the case where not all handlers are implemented yet

__all__ = ["EventHandler", "BotHandler", "CardHandler", "MessageRecorder"]


def __getattr__(name):
    """Lazy import handlers"""
    if name == "EventHandler":
        from .event import EventHandler
        return EventHandler
    elif name == "BotHandler":
        from .bot import BotHandler
        return BotHandler
    elif name == "CardHandler":
        from .card import CardHandler
        return CardHandler
    elif name == "MessageRecorder":
        from .message import MessageRecorder
        return MessageRecorder
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
