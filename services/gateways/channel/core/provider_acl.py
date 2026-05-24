"""Provider ACL for Channel Gateway outbound delivery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from shared.messaging.outbound.models.messages import DeliveryResult, OutboundMessage


class ChannelProviderAdapterPort(Protocol):
    """External channel provider adapter operations used by the gateway."""

    async def send_message(self, message: OutboundMessage) -> DeliveryResult:
        """Send one outbound message to the provider."""


class ChannelProviderRegistryPort(Protocol):
    """Registry boundary for provider adapters."""

    def get(self, channel_id: str) -> ChannelProviderAdapterPort | None:
        """Return the adapter registered for a channel."""


@dataclass(frozen=True, slots=True)
class ChannelProviderDeliveryRequest:
    """Gateway-local request passed to outbound provider adapters."""

    message: OutboundMessage
    trace_id: str | None = None

    @property
    def channel_id(self) -> str:
        return self.message.channel_id

    @property
    def message_id(self) -> str:
        return self.message.message_id


@dataclass(frozen=True, slots=True)
class ChannelProviderDeliveryResponse:
    """Gateway-local response translated from outbound provider results."""

    request: ChannelProviderDeliveryRequest
    result: DeliveryResult


class ChannelProviderACL:
    """Translate gateway delivery attempts to provider adapter calls."""

    async def deliver(
        self,
        *,
        adapter: ChannelProviderAdapterPort,
        request: ChannelProviderDeliveryRequest,
    ) -> ChannelProviderDeliveryResponse:
        try:
            result = await adapter.send_message(request.message)
        except Exception as exc:
            result = DeliveryResult(
                success=False,
                error_code=exc.__class__.__name__,
                error_message=str(exc),
            )
        return ChannelProviderDeliveryResponse(request=request, result=result)

    def adapter_missing(
        self,
        request: ChannelProviderDeliveryRequest,
    ) -> ChannelProviderDeliveryResponse:
        return ChannelProviderDeliveryResponse(
            request=request,
            result=DeliveryResult(
                success=False,
                error_code="adapter_not_found",
                error_message=f"No adapter registered for channel '{request.channel_id}'",
            ),
        )


__all__ = [
    "ChannelProviderACL",
    "ChannelProviderAdapterPort",
    "ChannelProviderDeliveryRequest",
    "ChannelProviderDeliveryResponse",
    "ChannelProviderRegistryPort",
]
