from __future__ import annotations

from shared.core.identifiers import UserId
from shared.core.identity_domain import PlatformUserRef
from shared.core.identity_resolution import IdentityResolutionUseCase
from shared.messaging.inbound import Platform
from shared.models.user import User


class FakeAdapter:
    def __init__(
        self,
        *,
        email: str | None = "test@example.com",
        name: str | None = "Test User",
    ) -> None:
        self.email = email
        self.name = name

    async def get_user_email(self, platform_user_id: str) -> str | None:
        return self.email

    async def get_user_name(self, platform_user_id: str) -> str | None:
        return self.name


class FakeUserStore:
    def __init__(self) -> None:
        self.users_by_email: dict[str, User] = {}
        self.users_by_platform: dict[tuple[Platform, str], User] = {}
        self.created: list[User] = []
        self.updated: list[User] = []

    async def create(self, user: User) -> User:
        self.created.append(user)
        if user.email:
            self.users_by_email[user.email] = user
        if user.feishu_open_id:
            self.users_by_platform[(Platform.FEISHU, user.feishu_open_id)] = user
        if user.wecom_user_id:
            self.users_by_platform[(Platform.WECOM, user.wecom_user_id)] = user
        if user.web_user_id:
            self.users_by_platform[(Platform.WEB, user.web_user_id)] = user
        return user

    async def get_by_id(self, user_id: str) -> User | None:
        for user in self.users_by_email.values():
            if user.id == user_id:
                return user
        return None

    async def get_by_email(self, email: str) -> User | None:
        return self.users_by_email.get(email)

    async def get_by_platform_id(
        self,
        platform: Platform,
        platform_user_id: str,
    ) -> User | None:
        return self.users_by_platform.get((platform, platform_user_id))

    async def update(self, user: User) -> User:
        self.updated.append(user)
        return user


def _use_case(
    adapters=None,
    invalid_email_calls: list[PlatformUserRef] | None = None,
) -> IdentityResolutionUseCase:
    return IdentityResolutionUseCase(
        adapters=adapters or {},
        user_id_factory=lambda: UserId("usr_identity_resolution"),
        invalid_email_handler=(
            invalid_email_calls.append if invalid_email_calls is not None else None
        ),
    )


async def test_resolve_creates_and_activates_user_from_platform_directory() -> None:
    store = FakeUserStore()
    use_case = _use_case(
        adapters={
            Platform.FEISHU: FakeAdapter(
                email="New@Example.COM",
                name="New User",
            )
        }
    )

    result = await use_case.resolve(
        store=store,
        platform_ref=PlatformUserRef(Platform.FEISHU, "ou_new"),
    )

    assert result.user.id == "usr_identity_resolution"
    assert result.user.email == "new@example.com"
    assert result.user.name == "New User"
    assert result.user.feishu_open_id == "ou_new"
    assert result.user.last_active_platform == "feishu"
    assert [event.event_name for event in result.domain_events] == [
        "UserCreated",
        "PlatformLinked",
        "UserActivated",
    ]
    assert store.created == [result.user]
    assert store.updated == [result.user]


async def test_resolve_links_existing_user_by_normalized_email() -> None:
    existing_user = User.create_identity(
        user_id=UserId("usr_existing_identity"),
        name="Existing User",
        email="shared@example.com",
        platform_ref=PlatformUserRef(Platform.FEISHU, "ou_existing"),
    )
    existing_user.pull_domain_events()
    store = FakeUserStore()
    store.users_by_email["shared@example.com"] = existing_user
    use_case = _use_case(
        adapters={Platform.WECOM: FakeAdapter(email="Shared@Example.com")}
    )

    result = await use_case.resolve(
        store=store,
        platform_ref=PlatformUserRef(Platform.WECOM, "ww_user"),
    )

    assert result.user is existing_user
    assert result.user.wecom_user_id == "ww_user"
    assert result.user.last_active_platform == "wecom"
    assert [event.event_name for event in result.domain_events] == [
        "PlatformLinked",
        "UserActivated",
    ]
    assert store.created == []
    assert store.updated == [existing_user]


async def test_resolve_ignores_invalid_optional_adapter_email() -> None:
    invalid_email_calls: list[PlatformUserRef] = []
    store = FakeUserStore()
    use_case = _use_case(
        adapters={Platform.FEISHU: FakeAdapter(email="not-an-email")},
        invalid_email_calls=invalid_email_calls,
    )

    result = await use_case.resolve(
        store=store,
        platform_ref=PlatformUserRef(Platform.FEISHU, "ou_invalid"),
    )

    assert result.user.email is None
    assert result.user.feishu_open_id == "ou_invalid"
    assert len(invalid_email_calls) == 1
    assert invalid_email_calls[0].platform_user_id == "ou_invalid"
