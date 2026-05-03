"""In-process registry for configured channel adapters."""

from threading import Lock

from .base import MessageChannel


class ChannelRegistry:
    """Registry for channel adapters wired by service entry points."""

    _channels: dict[str, MessageChannel] = {}
    _lock = Lock()

    @classmethod
    def register(cls, channel: MessageChannel) -> None:
        """Register or replace a channel adapter by its channel name."""
        with cls._lock:
            cls._channels[channel.channel_name] = channel

    @classmethod
    def get(cls, name: str) -> MessageChannel | None:
        """Return a registered channel adapter by name."""
        with cls._lock:
            return cls._channels.get(name)

    @classmethod
    def all(cls) -> dict[str, MessageChannel]:
        """Return a copy of the registered channel map."""
        with cls._lock:
            return cls._channels.copy()

    @classmethod
    def list_channels(cls) -> dict[str, MessageChannel]:
        """Return a copy of the registered channel map for health checks."""
        return cls.all()

    @classmethod
    def clear(cls) -> None:
        """Clear all registered channels, primarily for tests."""
        with cls._lock:
            cls._channels.clear()
