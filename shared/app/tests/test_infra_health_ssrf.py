from unittest.mock import MagicMock

import pytest

from shared.app.plugins.infra_health import InfraHealthPlugin


class TestValidateMilvusUrl:
    def test_valid_http(self):
        url = InfraHealthPlugin._validate_milvus_url("http://milvus.svc:19530")
        assert url == "http://milvus.svc:9091"

    def test_valid_https(self):
        url = InfraHealthPlugin._validate_milvus_url("https://milvus.prod:19530")
        assert url == "https://milvus.prod:9091"

    def test_invalid_scheme_raises(self):
        with pytest.raises(ValueError, match="scheme"):
            InfraHealthPlugin._validate_milvus_url("ftp://milvus:19530")

    def test_link_local_blocked(self):
        with pytest.raises(ValueError, match="link-local"):
            InfraHealthPlugin._validate_milvus_url("http://169.254.169.254:19530")

    def test_private_ip_blocked(self):
        with pytest.raises(ValueError, match="private"):
            InfraHealthPlugin._validate_milvus_url("http://10.0.0.1:19530")

    def test_loopback_allowed_on_milvus_port(self):
        url = InfraHealthPlugin._validate_milvus_url("http://127.0.0.1:19530")
        assert url == "http://127.0.0.1:9091"

    def test_loopback_blocked_on_non_milvus_port(self):
        with pytest.raises(ValueError, match="private"):
            InfraHealthPlugin._validate_milvus_url("http://127.0.0.1:80")

    def test_hostname_passthrough(self):
        url = InfraHealthPlugin._validate_milvus_url("http://my-milvus.cluster.local:19530")
        assert url == "http://my-milvus.cluster.local:9091"

    def test_ipv6_link_local_blocked(self):
        with pytest.raises(ValueError, match="link-local"):
            InfraHealthPlugin._validate_milvus_url("http://[fe80::1]:19530")


class TestInfraHealthPlugin:
    @pytest.mark.asyncio
    async def test_startup_fails_without_db_manager(self):
        plugin = InfraHealthPlugin(check_postgres=True, check_redis=False)
        mock_runtime = MagicMock()
        mock_runtime.agent = MagicMock(spec=[])
        with pytest.raises(RuntimeError, match="db_manager is None"):
            await plugin.startup(mock_runtime)

    @pytest.mark.asyncio
    async def test_health_check_skips_unconfigured(self):
        plugin = InfraHealthPlugin(check_postgres=False, check_redis=False)
        mock_runtime = MagicMock()
        mock_runtime.agent = MagicMock()
        await plugin.startup(mock_runtime)
        result = await plugin.health_check()
        assert "postgres" not in result
        assert "redis" not in result
