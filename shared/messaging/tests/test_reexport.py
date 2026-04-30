"""Verify shared.messaging re-export layer matches shared.services.gateway exports."""
import shared.messaging as new
import shared.services.gateway as old


def test_all_gateway_exports_available():
    for name in old.__all__:
        assert hasattr(new, name), f"Missing re-export in shared.messaging: {name}"

def test_same_objects():
    assert new.UnifiedGateway is old.UnifiedGateway
    assert new.UnifiedMessage is old.UnifiedMessage
    assert new.BasePlatformAdapter is old.BasePlatformAdapter
    assert new.UserService is old.UserService
