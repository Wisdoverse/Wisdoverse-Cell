# shared/services/gateway/user_service.py
"""
UserService - 用户身份管理服务

负责跨平台用户身份映射，通过邮箱关联不同平台账号。
"""
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional

from shared.db.repository import UserRepository
from shared.models.user import User
from shared.utils.id_generator import IDPrefix, generate_id
from shared.utils.logger import get_logger

from .models import Platform

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from .adapter import BasePlatformAdapter

logger = get_logger("gateway.user_service")


class UserService:
    """
    用户身份管理服务

    职责：
    1. 平台用户 ID → 统一用户映射
    2. 自动创建/关联用户
    3. 缓存用户信息
    """

    CACHE_TTL = 3600  # 1 小时缓存
    CACHE_PREFIX = "user"

    def __init__(
        self,
        db,
        redis: Optional["Redis"] = None,
        adapters: Optional[dict[Platform, "BasePlatformAdapter"]] = None,
    ):
        """
        Args:
            db: DatabaseManager 实例
            redis: Redis 客户端（用于缓存）
            adapters: 平台适配器字典
        """
        self.db = db
        self.redis = redis
        self.adapters = adapters or {}

    def set_adapters(self, adapters: dict[Platform, "BasePlatformAdapter"]) -> None:
        """设置平台适配器（避免循环依赖）"""
        self.adapters = adapters

    async def resolve_user(
        self,
        platform: Platform,
        platform_user_id: str,
    ) -> User:
        """
        解析平台用户 → 统一用户

        流程：
        1. 查缓存
        2. 查数据库（按平台 ID）
        3. 无记录 → 调 API 获取邮箱 → 查/建用户

        Args:
            platform: 平台类型
            platform_user_id: 平台用户 ID

        Returns:
            统一用户对象
        """
        # 1. 查缓存
        cache_key = self._cache_key(platform, platform_user_id)
        if self.redis:
            cached = await self.redis.get(cache_key)
            if cached:
                logger.debug("user_cache_hit", platform=platform.value, user_id=platform_user_id)
                return self._deserialize_user(cached)

        # 2. 查数据库
        async with self.db.session() as session:
            repo = UserRepository(session)

            user = await repo.get_by_platform_id(platform, platform_user_id)

            if not user:
                # 3. 创建或关联用户
                user = await self._create_or_link_user(
                    repo, platform, platform_user_id
                )

            # 更新活跃时间
            user.last_active_at = datetime.now(UTC)
            user.last_active_platform = platform.value
            await repo.update(user)
            await session.commit()

            # 刷新以获取完整数据
            await session.refresh(user)

        # 写缓存
        if self.redis:
            await self.redis.setex(
                cache_key,
                self.CACHE_TTL,
                self._serialize_user(user),
            )

        return user

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """通过统一用户 ID 获取用户"""
        async with self.db.session() as session:
            repo = UserRepository(session)
            return await repo.get_by_id(user_id)

    async def invalidate_cache(
        self,
        platform: Platform,
        platform_user_id: str,
    ) -> None:
        """使缓存失效"""
        if self.redis:
            cache_key = self._cache_key(platform, platform_user_id)
            await self.redis.delete(cache_key)

    # === Private Methods ===

    async def _create_or_link_user(
        self,
        repo: UserRepository,
        platform: Platform,
        platform_user_id: str,
    ) -> User:
        """
        创建新用户或关联到已有用户

        通过邮箱查找已有用户进行关联，否则创建新用户。
        """
        adapter = self.adapters.get(platform)
        if not adapter:
            logger.warning("adapter_not_found", platform=platform.value)
            return await self._create_new_user(repo, platform, platform_user_id, None, "Unknown")

        # 获取用户信息
        email = await adapter.get_user_email(platform_user_id)
        name = await adapter.get_user_name(platform_user_id) or "Unknown"

        if email:
            # 尝试通过邮箱找已有用户
            existing_user = await repo.get_by_email(email)
            if existing_user:
                # 关联平台账号
                self._set_platform_id(existing_user, platform, platform_user_id)
                logger.info(
                    "user_linked",
                    user_id=existing_user.id,
                    platform=platform.value,
                    platform_user_id=platform_user_id,
                )
                return existing_user

        # 创建新用户
        return await self._create_new_user(repo, platform, platform_user_id, email, name)

    async def _create_new_user(
        self,
        repo: UserRepository,
        platform: Platform,
        platform_user_id: str,
        email: Optional[str],
        name: str,
    ) -> User:
        """创建新用户"""
        user = User(
            id=generate_id(IDPrefix.USER),
            email=email,
            name=name,
        )
        self._set_platform_id(user, platform, platform_user_id)

        user = await repo.create(user)

        logger.info(
            "user_created",
            user_id=user.id,
            platform=platform.value,
            platform_user_id=platform_user_id,
            email=email,
        )

        return user

    def _set_platform_id(
        self,
        user: User,
        platform: Platform,
        platform_user_id: str,
    ) -> None:
        """设置用户的平台 ID"""
        if platform == Platform.FEISHU:
            user.feishu_open_id = platform_user_id
        elif platform == Platform.WECOM:
            user.wecom_user_id = platform_user_id
        elif platform == Platform.WEB:
            user.web_user_id = platform_user_id

    def _cache_key(self, platform: Platform, platform_user_id: str) -> str:
        """生成缓存 key"""
        return f"{self.CACHE_PREFIX}:{platform.value}:{platform_user_id}"

    def _serialize_user(self, user: User) -> str:
        """序列化用户对象用于缓存"""
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
        """从缓存反序列化用户对象"""
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

        # 解析时间
        if obj.get("created_at"):
            user.created_at = datetime.fromisoformat(obj["created_at"])
        if obj.get("last_active_at"):
            user.last_active_at = datetime.fromisoformat(obj["last_active_at"])

        return user
