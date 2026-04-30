"""Channel gateway exceptions."""


class ChannelGatewayError(Exception):
    """Base exception for channel gateway."""

    pass


class NotSupportedError(ChannelGatewayError):
    """Raised when an operation is not supported by the adapter."""

    def __init__(self, channel_id: str, operation: str):
        self.channel_id = channel_id
        self.operation = operation
        super().__init__(f"{channel_id} does not support {operation}")


class ConnectionError(ChannelGatewayError):
    """Raised when connection to platform fails."""

    pass


class DeliveryError(ChannelGatewayError):
    """Raised when message delivery fails."""

    pass


class RateLimitError(ChannelGatewayError):
    """Raised when rate limit is exceeded."""

    def __init__(self, channel_id: str, retry_after: int | None = None):
        self.channel_id = channel_id
        self.retry_after = retry_after
        msg = f"{channel_id} rate limited"
        if retry_after:
            msg += f", retry after {retry_after}s"
        super().__init__(msg)
