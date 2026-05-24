"""Channel Gateway provider ACL tests."""

import pytest

from services.gateways.channel.core.provider_acl import (
    ChannelProviderACL,
    ChannelProviderDeliveryRequest,
)
from shared.messaging.outbound.models.messages import DeliveryResult, OutboundMessage


class _Adapter:
    def __init__(
        self,
        *,
        result: DeliveryResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result or DeliveryResult(
            success=True,
            platform_message_id="platform_msg_1",
        )
        self.error = error
        self.sent: list[OutboundMessage] = []

    async def send_message(self, message: OutboundMessage) -> DeliveryResult:
        self.sent.append(message)
        if self.error is not None:
            raise self.error
        return self.result


def _request() -> ChannelProviderDeliveryRequest:
    return ChannelProviderDeliveryRequest(
        message=OutboundMessage(
            channel_id="fake",
            target_chat_id="chat_1",
            content="hello",
            trace_id="trace_1",
        ),
        trace_id="trace_1",
    )


@pytest.mark.asyncio
async def test_provider_acl_translates_successful_adapter_result() -> None:
    adapter = _Adapter()
    request = _request()

    response = await ChannelProviderACL().deliver(
        adapter=adapter,
        request=request,
    )

    assert adapter.sent == [request.message]
    assert response.request is request
    assert response.result.success is True
    assert response.result.platform_message_id == "platform_msg_1"


@pytest.mark.asyncio
async def test_provider_acl_translates_adapter_exception_to_delivery_result() -> None:
    request = _request()

    response = await ChannelProviderACL().deliver(
        adapter=_Adapter(error=RuntimeError("provider down")),
        request=request,
    )

    assert response.request is request
    assert response.result.success is False
    assert response.result.error_code == "RuntimeError"
    assert response.result.error_message == "provider down"


def test_provider_acl_translates_missing_adapter() -> None:
    request = _request()

    response = ChannelProviderACL().adapter_missing(request)

    assert response.request is request
    assert response.result.success is False
    assert response.result.error_code == "adapter_not_found"
    assert "fake" in (response.result.error_message or "")
