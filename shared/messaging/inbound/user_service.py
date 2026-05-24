# shared/services/gateway/user_service.py
"""
UserService - user identity management service.

Handles cross-platform user identity mapping and links platform accounts by
email.
"""
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from shared.core.identifiers import UserId
from shared.core.identity_domain import IdentityDomainEvent, PlatformUserRef
from shared.core.identity_event_outbox import identity_event_from_domain_event
from shared.core.identity_ports import IdentityEventOutboxStore, UserIdentityStore
from shared.core.identity_resolution import (
    IdentityResolutionResult,
    IdentityResolutionUseCase,
)
from shared.core.ids import IDPrefix, generate_id
from shared.db.identity_event_outbox_store import SqlAlchemyIdentityEventOutboxStore
from shared.db.user_store import SqlAlchemyUserIdentityStore
from shared.models.user import User
from shared.observability.privacy import hash_identifier
from shared.utils.logger import get_logger

from .models import Platform

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from .adapter import BasePlatformAdapter

logger = get_logger("gateway.user_service")


class UserService:
    """
    User identity management service.

    Responsibilities:
    1. Map platform user IDs to unified users.
    2. Create or link users automatically.
    3. Cache user information.
    """

    CACHE_TTL = 3600  # One-hour cache.
    CACHE_PREFIX = "user"

    def __init__(
        self,
        db,
        redis: Optional["Redis"] = None,
        adapters: Optional[dict[Platform, "BasePlatformAdapter"]] = None,
        user_store_factory=None,
        identity_outbox_factory=None,
    ):
        """
        Args:
            db: DatabaseManager instance.
            redis: Redis client used for caching.
            adapters: Platform adapter dictionary.
            user_store_factory: Optional session-scoped user identity store factory.
            identity_outbox_factory: Optional session-scoped identity event outbox factory.
        """
        self.db = db
        self.redis = redis
        self.adapters = adapters or {}
        self._user_store_factory = user_store_factory
        self._identity_outbox_factory = identity_outbox_factory

    def set_adapters(self, adapters: dict[Platform, "BasePlatformAdapter"]) -> None:
        """Set platform adapters and avoid circular imports."""
        self.adapters = adapters

    async def resolve_user(
        self,
        platform: Platform,
        platform_user_id: str,
    ) -> User:
        """
        Resolve a platform user to a unified user.

        Flow:
        1. Check cache.
        2. Query the database by platform ID.
        3. If missing, call the platform API for email, then find or create the user.

        Args:
            platform: Platform type.
            platform_user_id: Platform user ID.

        Returns:
            Unified user object.
        """
        platform_ref = PlatformUserRef(platform, platform_user_id)

        # 1. Check cache.
        cache_key = self._cache_key(platform_ref.platform, platform_ref.platform_user_id)
        if self.redis:
            cached = await self.redis.get(cache_key)
            if cached:
                logger.debug(
                    "user_cache_hit",
                    platform=platform_ref.platform.value,
                    user_hash=hash_identifier(platform_ref.platform_user_id),
                )
                return self._deserialize_user(cached)

        # 2. Query database.
        async with self.db.session() as session:
            store = self._new_user_store(session)

            result = await self._identity_resolution_use_case().resolve(
                store=store,
                platform_ref=platform_ref,
            )
            user = result.user
            await self._stage_identity_events(session, user, result)
            self._log_identity_events(user, result)
            await session.commit()

            # Refresh to load the full model.
            await session.refresh(user)

        # Write cache.
        if self.redis:
            await self.redis.setex(
                cache_key,
                self.CACHE_TTL,
                self._serialize_user(user),
            )

        return user

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get a user by unified user ID."""
        async with self.db.session() as session:
            store = self._new_user_store(session)
            return await store.get_by_id(user_id)

    async def invalidate_cache(
        self,
        platform: Platform,
        platform_user_id: str,
    ) -> None:
        """Invalidate a cached user mapping."""
        if self.redis:
            cache_key = self._cache_key(platform, platform_user_id)
            await self.redis.delete(cache_key)

    # === Private Methods ===

    def _new_user_store(self, session) -> UserIdentityStore:
        """Create a session-scoped identity store."""
        factory = self._user_store_factory or SqlAlchemyUserIdentityStore
        return factory(session)

    def _new_identity_outbox(self, session) -> IdentityEventOutboxStore:
        """Create a session-scoped identity event outbox."""
        factory = self._identity_outbox_factory or SqlAlchemyIdentityEventOutboxStore
        return factory(session)

    def _identity_resolution_use_case(self) -> IdentityResolutionUseCase:
        """Create the session-independent identity resolution use case."""
        return IdentityResolutionUseCase(
            adapters=self.adapters,
            user_id_factory=self._new_user_id,
            invalid_email_handler=self._log_invalid_identity_email,
        )

    def _new_user_id(self) -> UserId:
        """Create a stable unified-user identity."""
        return UserId(generate_id(IDPrefix.USER))

    async def _stage_identity_events(
        self,
        session,
        user: User,
        result: IdentityResolutionResult,
    ) -> None:
        """Stage aggregate-raised identity events in the durable outbox."""
        outbox = self._new_identity_outbox(session)
        for event in result.domain_events:
            if not isinstance(event, IdentityDomainEvent):
                logger.debug(
                    "identity_domain_event_not_stageable",
                    domain_event=getattr(event, "event_name", type(event).__name__),
                    user_hash=hash_identifier(user.id),
                )
                continue
            await outbox.add(identity_event_from_domain_event(event))

    def _log_identity_events(
        self,
        user: User,
        result: IdentityResolutionResult,
    ) -> None:
        """Log aggregate-raised events with PII-safe identifiers."""
        for event in result.domain_events:
            logger.debug(
                "identity_domain_event_raised",
                domain_event=event.event_name,
                user_hash=hash_identifier(user.id),
            )

    def _log_invalid_identity_email(
        self,
        platform_ref: PlatformUserRef,
    ) -> None:
        """Log invalid optional adapter emails without blocking resolution."""
        logger.warning(
            "invalid_identity_email_ignored",
            platform=platform_ref.platform.value,
            platform_user_hash=hash_identifier(platform_ref.platform_user_id),
        )

    def _cache_key(self, platform: Platform, platform_user_id: str) -> str:
        """Generate a cache key."""
        return f"{self.CACHE_PREFIX}:{platform.value}:{platform_user_id}"

    def _serialize_user(self, user: User) -> str:
        """Serialize a user object for cache storage."""
        import json
        return json.dumps({
            "id": user.id,
            "email": user.email,
            "phone": user.phone,
            "name": user.name,
            "avatar_url": user.avatar_url,
            "feishu_open_id": user.feishu_open_id,
            "feishu_user_id": user.feishu_user_id,
            "wecom_user_id": user.wecom_user_id,
            "web_user_id": user.web_user_id,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_active_at": user.last_active_at.isoformat() if user.last_active_at else None,
            "last_active_platform": user.last_active_platform,
        })

    def _deserialize_user(self, data: str | bytes) -> User:
        """Deserialize a user object from cache."""
        import json
        if isinstance(data, bytes):
            data = data.decode("utf-8")

        obj = json.loads(data)

        user = User(
            id=obj["id"],
            email=obj.get("email"),
            phone=obj.get("phone"),
            name=obj["name"],
            avatar_url=obj.get("avatar_url"),
            feishu_open_id=obj.get("feishu_open_id"),
            feishu_user_id=obj.get("feishu_user_id"),
            wecom_user_id=obj.get("wecom_user_id"),
            web_user_id=obj.get("web_user_id"),
            last_active_platform=obj.get("last_active_platform"),
        )

        # Parse timestamps.
        if obj.get("created_at"):
            user.created_at = datetime.fromisoformat(obj["created_at"])
        if obj.get("last_active_at"):
            user.last_active_at = datetime.fromisoformat(obj["last_active_at"])

        return user
