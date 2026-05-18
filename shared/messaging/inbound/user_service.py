# shared/services/gateway/user_service.py
"""
UserService - user identity management service.

Handles cross-platform user identity mapping and links platform accounts by
email.
"""
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional

from shared.core.identity_ports import UserIdentityStore
from shared.core.ids import IDPrefix, generate_id
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
    ):
        """
        Args:
            db: DatabaseManager instance.
            redis: Redis client used for caching.
            adapters: Platform adapter dictionary.
            user_store_factory: Optional session-scoped user identity store factory.
        """
        self.db = db
        self.redis = redis
        self.adapters = adapters or {}
        self._user_store_factory = user_store_factory

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
        # 1. Check cache.
        cache_key = self._cache_key(platform, platform_user_id)
        if self.redis:
            cached = await self.redis.get(cache_key)
            if cached:
                logger.debug(
                    "user_cache_hit",
                    platform=platform.value,
                    user_hash=hash_identifier(platform_user_id),
                )
                return self._deserialize_user(cached)

        # 2. Query database.
        async with self.db.session() as session:
            store = self._new_user_store(session)

            user = await store.get_by_platform_id(platform, platform_user_id)

            if not user:
                # 3. Create or link user.
                user = await self._create_or_link_user(
                    store, platform, platform_user_id
                )

            # Update active timestamp.
            user.last_active_at = datetime.now(UTC)
            user.last_active_platform = platform.value
            await store.update(user)
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

    async def _create_or_link_user(
        self,
        store: UserIdentityStore,
        platform: Platform,
        platform_user_id: str,
    ) -> User:
        """
        Create a new user or link to an existing user.

        Uses email to find and link an existing user; otherwise creates a new
        user.
        """
        adapter = self.adapters.get(platform)
        if not adapter:
            logger.warning("adapter_not_found", platform=platform.value)
            return await self._create_new_user(store, platform, platform_user_id, None, "Unknown")

        # Fetch user info.
        email = await adapter.get_user_email(platform_user_id)
        name = await adapter.get_user_name(platform_user_id) or "Unknown"

        if email:
            # Try to find an existing user by email.
            existing_user = await store.get_by_email(email)
            if existing_user:
                # Link the platform account.
                self._set_platform_id(existing_user, platform, platform_user_id)
                logger.info(
                    "user_linked",
                    user_hash=hash_identifier(existing_user.id),
                    platform=platform.value,
                    platform_user_hash=hash_identifier(platform_user_id),
                )
                return existing_user

        # Create a new user.
        return await self._create_new_user(store, platform, platform_user_id, email, name)

    async def _create_new_user(
        self,
        store: UserIdentityStore,
        platform: Platform,
        platform_user_id: str,
        email: Optional[str],
        name: str,
    ) -> User:
        """Create a new user."""
        user = User(
            id=generate_id(IDPrefix.USER),
            email=email,
            name=name,
        )
        self._set_platform_id(user, platform, platform_user_id)

        user = await store.create(user)

        logger.info(
            "user_created",
            user_hash=hash_identifier(user.id),
            platform=platform.value,
            platform_user_hash=hash_identifier(platform_user_id),
            email_hash=hash_identifier(email),
        )

        return user

    def _new_user_store(self, session) -> UserIdentityStore:
        """Create a session-scoped identity store."""
        factory = self._user_store_factory or SqlAlchemyUserIdentityStore
        return factory(session)

    def _set_platform_id(
        self,
        user: User,
        platform: Platform,
        platform_user_id: str,
    ) -> None:
        """Set the user's platform ID."""
        if platform == Platform.FEISHU:
            user.feishu_open_id = platform_user_id
        elif platform == Platform.WECOM:
            user.wecom_user_id = platform_user_id
        elif platform == Platform.WEB:
            user.web_user_id = platform_user_id

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
