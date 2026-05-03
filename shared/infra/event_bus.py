"""
Event Bus.

Redis Streams-based event bus with native consumer groups.

Each subscriber calls ``subscribe(..., group=agent_id)`` which creates
a Redis Streams consumer group.  When ``publish()`` is called, the event
is appended (XADD) to the stream for that event type.  Redis Streams
natively fan out to every consumer group, with built-in acknowledgment,
message persistence, replay, and dead-letter support via pending entries.

Agents communicate asynchronously through this bus.

Usage:
    bus = EventBus()

    # Publish an event.
    await bus.publish(event)

    # Subscribe to events, usually at agent startup.
    async for event in bus.subscribe(
        ["requirement.confirmed", "requirement.changed"],
        group="my-agent",
    ):
        await handle_event(event)
"""
import asyncio
import hashlib
import os
import socket
from typing import Any, AsyncGenerator, Optional, Protocol, runtime_checkable
from urllib.parse import urlparse, urlunparse

import redis.asyncio as redis
from pydantic import ValidationError

from ..config import settings
from ..schemas.event import Event, EventTypes
from ..utils.logger import get_logger

logger = get_logger("event_bus")


@runtime_checkable
class EventBusProtocol(Protocol):
    """Formal interface contract for all EventBus backends."""

    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def publish(self, event: Event) -> bool: ...
    def subscribe(
        self, event_types: list[str], timeout: int = 0, group: str | None = None
    ) -> AsyncGenerator[Event, None]: ...
    async def get_queue_length(self, event_type: str) -> int: ...
    async def get_all_queue_lengths(self) -> dict[str, int]: ...
    async def get_pending_count(self, event_type: str, group: str) -> int: ...
    async def get_dead_letter_count(self) -> int: ...
    async def list_dead_letters(self, limit: int = 50) -> list[Event]: ...

    @property
    def is_connected(self) -> bool: ...


class EventBus:
    """
    Redis Streams-based event bus with native consumer groups.

    Implemented with Redis Streams:
    - XADD: publish appends to the stream for the event type
    - XREADGROUP: subscribe reads via consumer group with acknowledgment

    Consumer groups are created per ``subscribe(..., group=agent_id)``.
    Redis Streams natively fan out to all consumer groups, with built-in
    acknowledgment (XACK), message persistence, and dead-letter support.
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        queue_prefix: str = "projectcell:events"
    ):
        self.redis_url = redis_url or settings.redis_event_bus_url  # Always db 0
        self.queue_prefix = queue_prefix
        self._redis: Optional[redis.Redis] = None

    @staticmethod
    def _safe_url(url: str) -> str:
        """Return *url* with the password portion replaced by ``***``."""
        parsed = urlparse(url)
        if parsed.password:
            masked_netloc = parsed.netloc.replace(
                f":{parsed.password}@", ":***@", 1
            )
            return urlunparse(parsed._replace(netloc=masked_netloc))
        return url

    @property
    def is_connected(self) -> bool:
        return self._redis is not None

    async def connect(self):
        """Connect to Redis."""
        if self._redis is None:
            self._redis = redis.from_url(self.redis_url, decode_responses=True)
            logger.info("event_bus_connected", redis_url=self._safe_url(self.redis_url))

    async def disconnect(self):
        """Disconnect from Redis."""
        if self._redis:
            await self._redis.close()
            self._redis = None
            logger.info("event_bus_disconnected")

    def _get_stream_key(self, event_type: str) -> str:
        """Return the stream key for an event type.

        Returns ``{prefix}:{event_type}``.  All consumer groups share the
        same stream — Redis Streams handles fan-out natively.
        """
        return f"{self.queue_prefix}:{event_type}"

    def _processed_event_key(self, group: str, event_id: str) -> str:
        return f"{self.queue_prefix}:processed:{group}:{event_id}"

    def _processing_event_key(self, group: str, event_id: str) -> str:
        return f"{self.queue_prefix}:processing:{group}:{event_id}"

    @staticmethod
    def _consumer_name() -> str:
        """Generate a unique consumer name within a group (hostname-pid)."""
        return f"{socket.gethostname()}-{os.getpid()}"

    async def _ensure_consumer_group(self, stream_key: str, group: str) -> None:
        """Create a consumer group on the stream, ignoring if it already exists."""
        try:
            await self._redis.xgroup_create(
                stream_key, group, id="0", mkstream=True,
            )
        except Exception as exc:
            # BUSYGROUP = group already exists — safe to ignore
            if "BUSYGROUP" in str(exc):
                pass
            else:
                raise

    def _decode_xautoclaim_response(self, response: Any) -> list[tuple[str, list]]:
        """Normalize redis-py XAUTOCLAIM responses to stream result tuples."""
        if not response:
            return []

        messages: list = []
        if isinstance(response, (list, tuple)):
            # redis-py returns (next_start_id, [(message_id, fields), ...], deleted_ids).
            if len(response) >= 2 and isinstance(response[1], list):
                messages = response[1]
            # Some clients return [(message_id, fields), ...] directly.
            elif response and all(isinstance(item, (list, tuple)) for item in response):
                messages = list(response)

        return messages

    def _pending_claim_idle_ms(self) -> int:
        """Return a safe pending-claim threshold for the shared runtime."""
        configured_ms = max(1, settings.event_bus_pending_claim_idle_ms)
        handler_timeout_ms = max(1, settings.event_handler_timeout_seconds) * 1000
        return max(configured_ms, handler_timeout_ms + 1000)

    def _processing_lock_ttl_seconds(self) -> int:
        """Return a lock TTL long enough for one runtime handler attempt."""
        configured_seconds = max(1, settings.event_bus_processing_lock_ttl_seconds)
        handler_timeout_seconds = max(1, settings.event_handler_timeout_seconds)
        return max(configured_seconds, handler_timeout_seconds + 60)

    async def _is_processed(self, *, group: str, event_id: str) -> bool:
        key = self._processed_event_key(group, event_id)
        try:
            return bool(await self._redis.get(key))
        except Exception as exc:
            logger.warning(
                "event_idempotency_lookup_failed",
                group=group,
                event_id=event_id,
                error=str(exc),
            )
            return False

    async def _claim_processing(self, *, group: str, consumer: str, event_id: str) -> bool:
        key = self._processing_event_key(group, event_id)
        try:
            return bool(
                await self._redis.set(
                    key,
                    consumer,
                    nx=True,
                    ex=self._processing_lock_ttl_seconds(),
                )
            )
        except Exception as exc:
            logger.warning(
                "event_idempotency_claim_failed",
                group=group,
                event_id=event_id,
                error=str(exc),
            )
            return True

    async def _mark_processed(self, *, group: str, event_id: str) -> None:
        key = self._processed_event_key(group, event_id)
        lock_key = self._processing_event_key(group, event_id)
        try:
            await self._redis.set(
                key,
                "1",
                ex=max(1, settings.event_bus_processed_event_ttl_seconds),
            )
            await self._redis.delete(lock_key)
        except Exception as exc:
            logger.warning(
                "event_idempotency_mark_failed",
                group=group,
                event_id=event_id,
                error=str(exc),
            )

    async def _claim_pending(
        self,
        *,
        stream_keys: list[str],
        group: str,
        consumer: str,
    ) -> list[tuple[str, list]]:
        """Claim idle pending entries so consumer restarts preserve at-least-once delivery."""
        claimed: list[tuple[str, list]] = []
        idle_ms = self._pending_claim_idle_ms()
        count = max(1, settings.event_bus_pending_claim_count)

        for stream_key in stream_keys:
            try:
                response = await self._redis.xautoclaim(
                    stream_key,
                    group,
                    consumer,
                    min_idle_time=idle_ms,
                    start_id="0-0",
                    count=count,
                )
            except AttributeError:
                logger.warning("event_pending_claim_unavailable")
                return []
            except Exception as exc:
                logger.warning(
                    "event_pending_claim_failed",
                    stream=stream_key,
                    group=group,
                    error=str(exc),
                )
                continue

            messages = self._decode_xautoclaim_response(response)
            if messages:
                claimed.append((stream_key, messages))

        return claimed

    async def _yield_stream_results(
        self,
        results: list[tuple[str, list]],
        *,
        group: str,
        consumer: str,
    ) -> AsyncGenerator[Event, None]:
        """Validate, yield, and acknowledge Redis Stream messages."""
        for stream_key, messages in results:
            for message_id, fields in messages:
                event_data = fields.get("data", "")
                try:
                    event = Event.model_validate_json(event_data)
                except ValidationError as ve:
                    logger.error(
                        "event_validation_failed",
                        error=str(ve),
                        raw_event_data_length=len(event_data),
                    )
                    await self.publish_raw_dlq(
                        raw_event_data=event_data,
                        error=str(ve),
                        agent_id=group,
                    )
                    # ACK invalid messages to prevent infinite redelivery.
                    await self._redis.xack(stream_key, group, message_id)
                    continue

                if await self._is_processed(group=group, event_id=event.event_id):
                    logger.info(
                        "event_duplicate_skipped",
                        event_id=event.event_id,
                        event_type=event.event_type,
                        group=group,
                    )
                    await self._redis.xack(stream_key, group, message_id)
                    continue

                if not await self._claim_processing(
                    group=group,
                    consumer=consumer,
                    event_id=event.event_id,
                ):
                    logger.info(
                        "event_duplicate_in_progress",
                        event_id=event.event_id,
                        event_type=event.event_type,
                        group=group,
                    )
                    continue

                logger.debug(
                    "event_received",
                    event_id=event.event_id,
                    event_type=event.event_type,
                    stream_message_id=message_id,
                )

                yield event

                # ACK after successful processing by the async-for consumer.
                await self._mark_processed(group=group, event_id=event.event_id)
                await self._redis.xack(stream_key, group, message_id)

    async def publish(self, event: Event) -> bool:
        """
        Publish an event to a Redis Stream.

        The event is appended (XADD) to the stream for the event type.
        Redis Streams natively fan out to all consumer groups.

        Args:
            event: Event to publish.

        Returns:
            Whether publishing succeeded.
        """
        await self.connect()

        event_data = event.model_dump_json()
        stream_key = self._get_stream_key(event.event_type)

        try:
            await self._redis.xadd(
                stream_key,
                {"data": event_data},
                maxlen=settings.event_bus_queue_max_length,
                approximate=True,
            )

            logger.info(
                "event_published",
                event_id=event.event_id,
                event_type=event.event_type,
                source_agent=event.source_agent,
                stream=stream_key,
            )
            return True
        except Exception as e:
            logger.error(
                "event_publish_failed",
                event_id=event.event_id,
                error=str(e)
            )
            return False

    async def subscribe(
        self,
        event_types: list[str],
        timeout: int = 0,
        group: str | None = None,
    ) -> AsyncGenerator[Event, None]:
        """
        Subscribe to events via Redis Streams consumer groups.

        Args:
            event_types: Event types to subscribe to.
            timeout: Wait timeout in seconds. Zero means wait indefinitely.
            group: Consumer group identifier. Each group independently consumes the stream.
                   A consumer group is created on the stream if it doesn't exist.

        Yields:
            Received events.
        """
        await self.connect()

        consumer = self._consumer_name()
        group_name = group or "default"
        # Build stream keys and ensure consumer groups exist
        streams: dict[str, str] = {}
        for et in event_types:
            stream_key = self._get_stream_key(et)
            await self._ensure_consumer_group(stream_key, group_name)
            streams[stream_key] = ">"  # read only new messages

        logger.info(
            "event_subscribed",
            event_types=event_types,
            group=group_name,
            consumer=consumer,
        )

        # Convert timeout from seconds to milliseconds for XREADGROUP block param
        block_ms = timeout * 1000 if timeout > 0 else 0

        while True:
            try:
                claimed = await self._claim_pending(
                    stream_keys=list(streams.keys()),
                    group=group_name,
                    consumer=consumer,
                )
                if claimed:
                    async for event in self._yield_stream_results(
                        claimed,
                        group=group_name,
                        consumer=consumer,
                    ):
                        yield event
                    continue

                results = await self._redis.xreadgroup(
                    groupname=group_name,
                    consumername=consumer,
                    streams=streams,
                    count=1,
                    block=block_ms,
                )

                if not results:
                    continue

                async for event in self._yield_stream_results(
                    results,
                    group=group_name,
                    consumer=consumer,
                ):
                    yield event

            except asyncio.CancelledError:
                # Don't ACK — message will be re-delivered to another consumer
                logger.info("event_subscription_cancelled")
                break
            except Exception as e:
                logger.error("event_receive_failed", error=str(e))
                await asyncio.sleep(1)  # retry after an error

    async def get_queue_length(self, event_type: str) -> int:
        """Return stream length for an event type."""
        await self.connect()
        stream_key = self._get_stream_key(event_type)
        try:
            return await self._redis.xlen(stream_key)
        except Exception:
            return 0

    async def get_all_queue_lengths(self) -> dict[str, int]:
        """Return stream lengths for all event types."""
        await self.connect()

        # Use scan_iter (not KEYS) to avoid blocking Redis on large keyspaces
        pattern = f"{self.queue_prefix}:*"
        keys = []
        async for key in self._redis.scan_iter(match=pattern, count=100):
            keys.append(key)

        result = {}
        for key in keys:
            event_type = key.replace(f"{self.queue_prefix}:", "")
            if event_type.startswith(("processed:", "processing:")):
                continue
            try:
                length = await self._redis.xlen(key)
            except Exception:
                length = 0
            result[event_type] = length

        return result

    async def publish_dlq(self, event: Event, error: str, agent_id: str) -> None:
        """Publish a failed event to the dead letter queue stream."""
        await self.connect()
        dlq_event = Event.create(
            event_type=EventTypes.DLQ_FAILED,
            source_agent=agent_id,
            payload={
                "original_event_id": event.event_id,
                "original_event_type": event.event_type,
                "original_source": event.source_agent,
                "original_payload": event.payload,
                "failed_by_agent": agent_id,
                "failure_stage": "handler",
                "error": error[:2000],
            },
            trace_id=event.metadata.trace_id,
        )
        try:
            key = self._get_stream_key(EventTypes.DLQ_FAILED)
            await self._redis.xadd(
                key, {"data": dlq_event.model_dump_json()}, maxlen=10_000,
            )
            logger.info(
                "dlq_event_published",
                event_id=event.event_id,
                event_type=event.event_type,
            )
        except Exception as exc:
            logger.error(
                "dlq_publish_failed",
                event_id=event.event_id,
                error=str(exc),
            )

    async def publish_raw_dlq(
        self,
        *,
        raw_event_data: str,
        error: str,
        agent_id: str,
    ) -> None:
        """Publish an invalid/raw event payload to DLQ before acknowledging it."""
        await self.connect()
        raw_event_bytes = raw_event_data.encode("utf-8")
        dlq_event = Event.create(
            event_type=EventTypes.DLQ_FAILED,
            source_agent=agent_id,
            payload={
                "original_event_id": None,
                "original_event_type": None,
                "original_source": None,
                "original_payload": {
                    "raw_event_data_bytes": len(raw_event_bytes),
                    "raw_event_data_sha256": hashlib.sha256(raw_event_bytes).hexdigest(),
                },
                "failed_by_agent": agent_id,
                "failure_stage": "validation",
                "error": error[:2000],
            },
        )
        try:
            key = self._get_stream_key(EventTypes.DLQ_FAILED)
            await self._redis.xadd(
                key, {"data": dlq_event.model_dump_json()}, maxlen=10_000,
            )
            logger.info(
                "dlq_raw_event_published",
                failure_stage="validation",
                agent_id=agent_id,
            )
        except Exception as exc:
            logger.error(
                "dlq_raw_publish_failed",
                agent_id=agent_id,
                error=str(exc),
            )

    async def get_dead_letter_count(self) -> int:
        """Return count of events in the dead letter queue stream."""
        await self.connect()
        try:
            return await self._redis.xlen(self._get_stream_key(EventTypes.DLQ_FAILED))
        except Exception:
            return 0

    async def list_dead_letters(self, limit: int = 50) -> list[Event]:
        """Return recent dead letter events, newest first."""
        await self.connect()
        bounded_limit = max(1, min(limit, 500))
        try:
            rows = await self._redis.xrevrange(
                self._get_stream_key(EventTypes.DLQ_FAILED),
                count=bounded_limit,
            )
        except Exception:
            return []

        events: list[Event] = []
        for _, fields in rows:
            event_data = fields.get("data", "")
            try:
                events.append(Event.model_validate_json(event_data))
            except ValidationError as exc:
                logger.error(
                    "dlq_event_validation_failed",
                    error=str(exc),
                    raw_event_data_length=len(event_data),
                )
        return events

    async def get_pending_count(self, event_type: str, group: str) -> int:
        """Get count of unacknowledged messages for a consumer group."""
        await self.connect()
        stream_key = self._get_stream_key(event_type)
        try:
            info = await self._redis.xpending(stream_key, group)
            return info["pending"] if info else 0
        except Exception:
            return 0


def create_event_bus(backend: str | None = None) -> EventBusProtocol:
    """Create EventBus based on config. Returns Redis or NATS backend."""
    from ..config import settings

    chosen = (backend or settings.event_bus_backend).strip().lower()

    if chosen == "nats":
        try:
            from .nats_event_bus import NATSEventBus
        except ImportError:
            raise ImportError(
                "nats-py package required for NATS event bus backend. "
                "Install with: pip install nats-py"
            )
        consumer_name = (
            settings.event_bus_consumer_name.strip()
            or settings.otel_service_name.strip()
            or "projectcell"
        )
        logger.info(
            "event_bus_backend_selected",
            backend="nats",
            consumer_name=consumer_name,
            stream_replicas=settings.nats_stream_replicas,
        )
        return NATSEventBus(
            nats_url=settings.nats_url,
            consumer_name=consumer_name,
            stream_replicas=settings.nats_stream_replicas,
        )
    elif chosen == "redis":
        logger.info("event_bus_backend_selected", backend="redis")
        return EventBus(redis_url=settings.redis_event_bus_url)
    else:
        raise ValueError(
            f"Unknown EVENT_BUS_BACKEND: '{chosen}'. Must be 'redis' or 'nats'."
        )


# Global event bus instance (config-driven: redis or nats)
event_bus = create_event_bus()
