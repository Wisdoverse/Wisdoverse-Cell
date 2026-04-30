"""Adapter registry for managing channel adapters."""
from shared.messaging.outbound.core.base_adapter import BaseChannelAdapter
from shared.messaging.outbound.core.enums import ChannelStatus


class AdapterRegistry:
    """Registry for channel adapters.

    Instance-based: each registry has its own adapter dict.
    For backward compatibility, class methods delegate to a default instance.
    """

    _default: "AdapterRegistry | None" = None

    def __init__(self) -> None:
        self._adapters: dict[str, BaseChannelAdapter] = {}

    def register(self, adapter: BaseChannelAdapter) -> None:
        """Register an adapter."""
        self._adapters[adapter.channel_id] = adapter

    def unregister(self, channel_id: str) -> None:
        """Unregister an adapter."""
        self._adapters.pop(channel_id, None)

    def get(self, channel_id: str) -> BaseChannelAdapter | None:
        """Get an adapter by channel ID."""
        return self._adapters.get(channel_id)

    def has(self, channel_id: str) -> bool:
        """Check if an adapter is registered."""
        return channel_id in self._adapters

    def list_all(self) -> list[BaseChannelAdapter]:
        """List all registered adapters."""
        return list(self._adapters.values())

    def list_by_status(self, status: ChannelStatus) -> list[BaseChannelAdapter]:
        """List adapters by status."""
        return [a for a in self._adapters.values() if a.status == status]

    def clear(self) -> None:
        """Clear all registered adapters."""
        self._adapters.clear()

    @classmethod
    def default(cls) -> "AdapterRegistry":
        """Get or create the default (global) registry instance."""
        if cls._default is None:
            cls._default = cls()
        return cls._default
