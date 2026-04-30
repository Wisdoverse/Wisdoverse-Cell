# shared/messaging/inbound/tests/test_user_service.py
"""
Tests for UserService - 用户身份服务测试
"""
from datetime import UTC, datetime
from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest

from shared.messaging.inbound import Platform
from shared.messaging.inbound.user_service import UserService


class MockAdapter:
    """Mock adapter for testing"""

    def __init__(self, email: Optional[str] = "test@example.com", name: str = "Test User"):
        self._email = email
        self._name = name

    async def get_user_email(self, platform_user_id: str) -> Optional[str]:
        return self._email

    async def get_user_name(self, platform_user_id: str) -> Optional[str]:
        return self._name


class MockUser:
    """Mock User model for testing"""

    def __init__(
        self,
        id: str = "user_123",
        email: Optional[str] = None,
        name: str = "Test User",
    ):
        self.id = id
        self.email = email
        self.phone = None
        self.name = name
        self.avatar_url = None
        self.feishu_open_id = None
        self.feishu_user_id = None
        self.wecom_user_id = None
        self.web_user_id = None
        self.created_at = datetime.now(UTC)
        self.last_active_at = datetime.now(UTC)
        self.last_active_platform = None


class MockRepository:
    """Mock UserRepository for testing"""

    def __init__(self):
        self.users: dict[str, MockUser] = {}
        self.users_by_email: dict[str, MockUser] = {}
        self.users_by_platform: dict[tuple[Platform, str], MockUser] = {}

    async def get_by_id(self, user_id: str) -> Optional[MockUser]:
        return self.users.get(user_id)

    async def get_by_email(self, email: str) -> Optional[MockUser]:
        return self.users_by_email.get(email)

    async def get_by_platform_id(
        self, platform: Platform, platform_user_id: str
    ) -> Optional[MockUser]:
        return self.users_by_platform.get((platform, platform_user_id))

    async def create(self, user: MockUser) -> MockUser:
        self.users[user.id] = user
        if user.email:
            self.users_by_email[user.email] = user
        return user

    async def update(self, user: MockUser) -> MockUser:
        return user


class MockSession:
    """Mock database session"""

    def __init__(self, repo: MockRepository):
        self._repo = repo

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass


class MockDb:
    """Mock DatabaseManager"""

    def __init__(self, repo: MockRepository):
        self._repo = repo

    def session(self):
        return MockSessionContext(self._repo)


class MockSessionContext:
    """Context manager for mock session"""

    def __init__(self, repo: MockRepository):
        self._repo = repo
        self._session = MockSession(repo)

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        pass


class TestUserServiceInit:
    """Test UserService initialization"""

    def test_init_minimal(self):
        """Can initialize with minimal params"""
        repo = MockRepository()
        db = MockDb(repo)
        service = UserService(db=db)

        assert service.db == db
        assert service.redis is None
        assert service.adapters == {}

    def test_init_with_adapters(self):
        """Can initialize with adapters"""
        repo = MockRepository()
        db = MockDb(repo)
        adapters = {Platform.FEISHU: MockAdapter()}
        service = UserService(db=db, adapters=adapters)

        assert Platform.FEISHU in service.adapters

    def test_set_adapters(self):
        """Can set adapters after init"""
        repo = MockRepository()
        db = MockDb(repo)
        service = UserService(db=db)

        adapters = {Platform.WECOM: MockAdapter()}
        service.set_adapters(adapters)

        assert Platform.WECOM in service.adapters


class TestUserServiceResolve:
    """Test user resolution"""

    @pytest.mark.asyncio
    async def test_resolve_existing_user_by_platform_id(self):
        """Resolves existing user by platform ID"""
        repo = MockRepository()
        existing_user = MockUser(id="user_existing", email="test@example.com")
        existing_user.feishu_open_id = "ou_123"
        repo.users_by_platform[(Platform.FEISHU, "ou_123")] = existing_user
        repo.users[existing_user.id] = existing_user

        db = MockDb(repo)
        service = UserService(db=db)

        # Patch UserRepository
        with patch(
            "shared.messaging.inbound.user_service.UserRepository",
            return_value=repo,
        ):
            user = await service.resolve_user(Platform.FEISHU, "ou_123")

        assert user.id == "user_existing"
        assert user.last_active_platform == Platform.FEISHU.value

    @pytest.mark.asyncio
    async def test_resolve_creates_new_user_when_not_found(self):
        """Creates new user when not found"""
        repo = MockRepository()
        db = MockDb(repo)
        adapters = {Platform.FEISHU: MockAdapter(email="new@example.com", name="New User")}
        service = UserService(db=db, adapters=adapters)

        with patch(
            "shared.messaging.inbound.user_service.UserRepository",
            return_value=repo,
        ):
            with patch(
                "shared.messaging.inbound.user_service.generate_id",
                return_value="user_new_123",
            ):
                user = await service.resolve_user(Platform.FEISHU, "ou_new")

        assert user.id == "user_new_123"
        assert user.email == "new@example.com"
        assert user.name == "New User"
        assert user.feishu_open_id == "ou_new"

    @pytest.mark.asyncio
    async def test_resolve_links_existing_user_by_email(self):
        """Links to existing user when email matches"""
        repo = MockRepository()
        existing_user = MockUser(id="user_existing", email="shared@example.com")
        repo.users_by_email["shared@example.com"] = existing_user

        db = MockDb(repo)
        adapters = {Platform.WECOM: MockAdapter(email="shared@example.com")}
        service = UserService(db=db, adapters=adapters)

        with patch(
            "shared.messaging.inbound.user_service.UserRepository",
            return_value=repo,
        ):
            user = await service.resolve_user(Platform.WECOM, "wecom_user_1")

        assert user.id == "user_existing"
        assert user.wecom_user_id == "wecom_user_1"

    @pytest.mark.asyncio
    async def test_resolve_creates_user_without_email(self):
        """Creates user even without email"""
        repo = MockRepository()
        db = MockDb(repo)
        adapters = {Platform.FEISHU: MockAdapter(email=None, name="No Email User")}
        service = UserService(db=db, adapters=adapters)

        with patch(
            "shared.messaging.inbound.user_service.UserRepository",
            return_value=repo,
        ):
            with patch(
                "shared.messaging.inbound.user_service.generate_id",
                return_value="user_no_email",
            ):
                user = await service.resolve_user(Platform.FEISHU, "ou_no_email")

        assert user.id == "user_no_email"
        assert user.email is None
        assert user.name == "No Email User"


class TestUserServiceCache:
    """Test caching behavior"""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_user(self):
        """Returns cached user on cache hit"""
        repo = MockRepository()
        db = MockDb(repo)

        # Mock Redis
        mock_redis = AsyncMock()
        cached_data = (
            '{"id": "user_cached", "email": "cached@example.com", "name": "Cached User", '
            '"phone": null, "avatar_url": null, "feishu_open_id": "ou_cached", '
            '"feishu_user_id": null, "wecom_user_id": null, "web_user_id": null, '
            '"created_at": "2026-01-27T10:00:00+00:00", '
            '"last_active_at": "2026-01-27T10:00:00+00:00", '
            '"last_active_platform": "feishu"}'
        )
        mock_redis.get.return_value = cached_data

        service = UserService(db=db, redis=mock_redis)

        user = await service.resolve_user(Platform.FEISHU, "ou_cached")

        assert user.id == "user_cached"
        assert user.email == "cached@example.com"
        mock_redis.get.assert_called_once_with("user:feishu:ou_cached")

    @pytest.mark.asyncio
    async def test_cache_miss_queries_db_and_caches(self):
        """Queries DB on cache miss and caches result"""
        repo = MockRepository()
        existing_user = MockUser(id="user_db", email="db@example.com")
        existing_user.feishu_open_id = "ou_db"
        repo.users_by_platform[(Platform.FEISHU, "ou_db")] = existing_user

        db = MockDb(repo)

        # Mock Redis
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # Cache miss

        service = UserService(db=db, redis=mock_redis)

        with patch(
            "shared.messaging.inbound.user_service.UserRepository",
            return_value=repo,
        ):
            user = await service.resolve_user(Platform.FEISHU, "ou_db")

        assert user.id == "user_db"
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == "user:feishu:ou_db"
        assert call_args[0][1] == 3600  # TTL

    @pytest.mark.asyncio
    async def test_invalidate_cache(self):
        """invalidate_cache removes cached user"""
        repo = MockRepository()
        db = MockDb(repo)

        mock_redis = AsyncMock()
        service = UserService(db=db, redis=mock_redis)

        await service.invalidate_cache(Platform.FEISHU, "ou_123")

        mock_redis.delete.assert_called_once_with("user:feishu:ou_123")


class TestUserServicePlatformMapping:
    """Test platform ID mapping"""

    @pytest.mark.asyncio
    async def test_feishu_user_mapping(self):
        """Maps Feishu open_id correctly"""
        repo = MockRepository()
        db = MockDb(repo)
        adapters = {Platform.FEISHU: MockAdapter()}
        service = UserService(db=db, adapters=adapters)

        with patch(
            "shared.messaging.inbound.user_service.UserRepository",
            return_value=repo,
        ):
            with patch(
                "shared.messaging.inbound.user_service.generate_id",
                return_value="user_feishu",
            ):
                user = await service.resolve_user(Platform.FEISHU, "ou_feishu_123")

        assert user.feishu_open_id == "ou_feishu_123"
        assert user.wecom_user_id is None
        assert user.web_user_id is None

    @pytest.mark.asyncio
    async def test_wecom_user_mapping(self):
        """Maps Wecom user_id correctly"""
        repo = MockRepository()
        db = MockDb(repo)
        adapters = {Platform.WECOM: MockAdapter()}
        service = UserService(db=db, adapters=adapters)

        with patch(
            "shared.messaging.inbound.user_service.UserRepository",
            return_value=repo,
        ):
            with patch(
                "shared.messaging.inbound.user_service.generate_id",
                return_value="user_wecom",
            ):
                user = await service.resolve_user(Platform.WECOM, "wecom_user_456")

        assert user.wecom_user_id == "wecom_user_456"
        assert user.feishu_open_id is None

    @pytest.mark.asyncio
    async def test_web_user_mapping(self):
        """Maps Web user_id correctly"""
        repo = MockRepository()
        db = MockDb(repo)
        adapters = {Platform.WEB: MockAdapter()}
        service = UserService(db=db, adapters=adapters)

        with patch(
            "shared.messaging.inbound.user_service.UserRepository",
            return_value=repo,
        ):
            with patch(
                "shared.messaging.inbound.user_service.generate_id",
                return_value="user_web",
            ):
                user = await service.resolve_user(Platform.WEB, "web_user_789")

        assert user.web_user_id == "web_user_789"
        assert user.feishu_open_id is None
        assert user.wecom_user_id is None


class TestUserServiceSerialization:
    """Test user serialization/deserialization"""

    def test_serialize_user(self):
        """Serializes user to JSON"""
        repo = MockRepository()
        db = MockDb(repo)
        service = UserService(db=db)

        user = MockUser(id="user_ser", email="ser@example.com", name="Ser User")
        user.feishu_open_id = "ou_ser"

        json_str = service._serialize_user(user)

        assert '"id": "user_ser"' in json_str
        assert '"email": "ser@example.com"' in json_str
        assert '"feishu_open_id": "ou_ser"' in json_str

    def test_deserialize_user(self):
        """Deserializes user from JSON"""
        repo = MockRepository()
        db = MockDb(repo)
        service = UserService(db=db)

        json_str = (
            '{"id": "user_de", "email": "de@example.com", "name": "De User", '
            '"phone": null, "avatar_url": null, "feishu_open_id": "ou_de", '
            '"feishu_user_id": null, "wecom_user_id": null, "web_user_id": null, '
            '"created_at": "2026-01-27T10:00:00+00:00", '
            '"last_active_at": "2026-01-27T10:00:00+00:00", '
            '"last_active_platform": "feishu"}'
        )

        user = service._deserialize_user(json_str)

        assert user.id == "user_de"
        assert user.email == "de@example.com"
        assert user.feishu_open_id == "ou_de"
        assert user.last_active_platform == "feishu"

    def test_deserialize_user_from_bytes(self):
        """Deserializes user from bytes (Redis returns bytes)"""
        repo = MockRepository()
        db = MockDb(repo)
        service = UserService(db=db)

        json_bytes = (
            b'{"id": "user_bytes", "email": "bytes@example.com", "name": "Bytes User", '
            b'"phone": null, "avatar_url": null, "feishu_open_id": null, '
            b'"feishu_user_id": null, "wecom_user_id": null, "web_user_id": null, '
            b'"created_at": null, "last_active_at": null, "last_active_platform": null}'
        )

        user = service._deserialize_user(json_bytes)

        assert user.id == "user_bytes"
        assert user.email == "bytes@example.com"
