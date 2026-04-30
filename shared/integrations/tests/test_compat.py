"""Verify old and new import paths resolve to same objects."""


def test_feishu_client_same():
    from shared.integrations.feishu import FeishuClient as New
    from shared.services.feishu import FeishuClient as Old
    assert New is Old


def test_wecom_client_same():
    from shared.integrations.wecom import WecomClient as New
    from shared.services.wecom import WecomClient as Old
    assert New is Old


def test_openclaw_adapter_same():
    from shared.integrations.openclaw import OpenClawChannelAdapter as New
    from shared.services.openclaw import OpenClawChannelAdapter as Old
    assert New is Old


def test_openproject_client_same():
    from shared.integrations.openproject import OpenProjectClient as New
    from shared.services.openproject import OpenProjectClient as Old
    assert New is Old
