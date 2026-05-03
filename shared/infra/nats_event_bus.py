"""
NATS JetStream EventBus — durable, consumer-grouped event bus.

Drop-in replacement for the Redis EventBus implementing EventBusProtocol
(connect, disconnect, publish, subscribe async generator).
"""
import asyncio
import hashlib
from typing import AsyncGenerator

import nats
from nats.js.api import (
    AckPolicy,
    ConsumerConfig,
    DeliverPolicy,
    StreamConfig,
)
from nats.js.errors import NotFoundError

from shared.schemas.event import Event
from shared.utils.logger import get_logger

logger = get_logger(__name__)

STREAM_NAME = "PROJECT_EVENTS"
SUBJECT_PREFIX = "events"


class NATSEventBus:
    """NATS JetStream EventBus implementation."""

    def __init__(self, nats_url: str, consumer_name: str = "projectcell"):
        self._nats_url = nats_url
        self._consumer_name = consumer_name
        self._nc: nats.NATS | None = None
        self._js = None

    @property
    def is_connected(self) -> bool:
        return self._nc is not None and self._nc.is_connected

    def _ensure_connected(self) -> None:
        """Raise if connect() has not been called."""
        if self._js is None:
            raise RuntimeError(
                "NATSEventBus.connect() must be called before use"
            )

    # -- lifecycle callbacks ---------------------------------------------------

    async def _on_error(self, e: Exception) -> None:
        logger.error("nats_connection_error", error=str(e))

    async def _on_disconnected(self) -> None:
        logger.warning("nats_disconnected")

    async def _on_reconnected(self) -> None:
        logger.info("nats_reconnected")

    async def _on_closed(self) -> None:
        logger.warning("nats_connection_closed")

    # -- public interface ------------------------------------------------------


    async def connect(self) -> None:
        """Connect to NATS cluster and ensure stream exists."""
        servers = [s.strip() for s in self._nats_url.split(",")]
        self._nc = await nats.connect(
            servers=servers,
            max_reconnect_attempts=60,
            reconnect_time_wait=2,
            error_cb=self._on_error,
            disconnected_cb=self._on_disconnected,
            reconnected_cb=self._on_reconnected,
            closed_cb=self._on_closed,
        )
        self._js = self._nc.jetstream()

        # Ensure the PROJECT_EVENTS stream exists
        try:
            await self._js.find_stream_info_by_subject(f"{SUBJECT_PREFIX}.>")
            logger.info("nats_stream_found", stream=STREAM_NAME)
        except NotFoundError:
            await self._js.add_stream(
                StreamConfig(
                    name=STREAM_NAME,
                    subjects=[f"{SUBJECT_PREFIX}.>"],
                    retention="limits",
                    max_age=7 * 24 * 3600 * 1_000_000_000,  # 7 days in nanoseconds
                    storage="file",
                    num_replicas=3,
                    discard="old",
                )
            )
            logger.info("nats_stream_created", stream=STREAM_NAME)

        logger.info("nats_event_bus_connected", servers=servers)

    async def disconnect(self) -> None:
        """Close NATS connection."""
        if self._nc and not self._nc.is_closed:
            await self._nc.close()
        logger.info("nats_event_bus_disconnected")

    async def publish(self, event: Event) -> bool:
        """Publish event to JetStream. Returns True on success, False on failure."""
        self._ensure_connected()
        subject = f"{SUBJECT_PREFIX}.{event.event_type}"
        data = event.model_dump_json().encode()
        headers = {}
        headers["Nats-Msg-Id"] = event.event_id
        if event.metadata and event.metadata.trace_id:
            headers["trace-id"] = event.metadata.trace_id

        try:
            ack = await self._js.publish(subject, data, headers=headers or None)
            logger.debug(
                "nats_event_published",
                event_id=event.event_id,
                subject=subject,
                seq=ack.seq,
            )
            return ack.seq > 0
        except Exception as e:
            logger.error(
                "nats_event_publish_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                error=str(e),
            )
            return False

    async def subscribe(
        self, event_types: list[str], timeout: int = 0, group: str | None = None,
    ) -> AsyncGenerator[Event, None]:
        """Async generator yielding Events from JetStream pull consumer.

        *group* is accepted for EventBusProtocol compatibility but is not
        used here — NATS JetStream already uses the *consumer_name* passed
        at construction time for consumer-group semantics.
        """
        self._ensure_connected()
        filter_subjects = [f"{SUBJECT_PREFIX}.{et}" for et in event_types]

        config = ConsumerConfig(
            durable_name=self._consumer_name,
            ack_policy=AckPolicy.EXPLICIT,
            deliver_policy=DeliverPolicy.ALL,
            max_deliver=3,
            ack_wait=30,
        )
        if len(filter_subjects) > 1:
            config.filter_subjects = filter_subjects

        sub = await self._js.pull_subscribe(
            subject=filter_subjects[0] if len(filter_subjects) == 1 else f"{SUBJECT_PREFIX}.>",
            durable=self._consumer_name,
            config=config,
        )

        while True:
            try:
                msgs = await sub.fetch(batch=10, timeout=5)
                for msg in msgs:
                    # Parse separately from yield+ack so handler errors
                    # don't get confused with deserialization errors.
                    try:
                        event = Event.model_validate_json(msg.data)
                    except Exception as e:
                        logger.error(
                            "nats_event_parse_error",
                            error=str(e),
                            subject=msg.subject,
                            payload_bytes=len(msg.data) if msg.data else 0,
                            payload_sha256=(
                                hashlib.sha256(msg.data).hexdigest() if msg.data else None
                            ),
                        )
                        await msg.nak()
                        continue

                    yield event

                    try:
                        await msg.ack()
                    except Exception as e:
                        logger.error(
                            "nats_event_ack_failed",
                            event_id=event.event_id,
                            subject=msg.subject,
                            error=str(e),
                        )
            except asyncio.CancelledError:
                raise
            except nats.errors.TimeoutError:
                # No messages available — keep polling
                continue
            except Exception as e:
                logger.error("nats_subscribe_error", error=str(e))
                await asyncio.sleep(1)

    async def get_queue_length(self, event_type: str) -> int:
        """Return pending message count for the consumer. Returns -1 on error."""
        try:
            self._ensure_connected()
            info = await self._js.consumer_info(STREAM_NAME, self._consumer_name)
            return info.num_pending
        except Exception as e:
            logger.warning(
                "nats_get_queue_length_failed",
                event_type=event_type,
                error=str(e),
            )
            return -1

    async def get_all_queue_lengths(self) -> dict[str, int]:
        """Return consumer stats. Returns empty dict on error."""
        try:
            self._ensure_connected()
            info = await self._js.consumer_info(STREAM_NAME, self._consumer_name)
            return {"pending": info.num_pending, "redelivered": info.num_redelivered}
        except Exception as e:
            logger.warning(
                "nats_get_all_queue_lengths_failed",
                error=str(e),
            )
            return {}

    async def get_pending_count(self, event_type: str, group: str) -> int:
        """Return count of unacknowledged messages for the consumer. Returns -1 on error."""
        try:
            self._ensure_connected()
            info = await self._js.consumer_info(STREAM_NAME, self._consumer_name)
            return info.num_pending
        except Exception as e:
            logger.warning(
                "nats_get_pending_count_failed",
                event_type=event_type,
                error=str(e),
            )
            return -1

    async def get_dead_letter_count(self) -> int:
        """NATS uses native redelivery; no Redis-style DLQ stream is exposed."""
        return 0

    async def list_dead_letters(self, limit: int = 50) -> list[Event]:
        """NATS uses native redelivery; no Redis-style DLQ stream is exposed."""
        return []
