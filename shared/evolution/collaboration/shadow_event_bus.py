"""ShadowEventBus — records publish() calls without producing real side effects.

Used by ShadowRunner to safely execute collaboration patterns during shadow
execution (parallel dry-runs alongside production traffic).
"""

from shared.schemas.event import Event


class ShadowEventBus:
    """Event bus that records publish() calls but never actually sends them.

    Used by ShadowRunner to safely execute collaboration patterns
    without producing real side effects.
    """

    def __init__(self) -> None:
        self.published_events: list[Event] = []

    async def publish(self, event: Event) -> None:
        self.published_events.append(event)

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    def reset(self) -> None:
        self.published_events.clear()
