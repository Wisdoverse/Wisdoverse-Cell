"""Architecture checks for external integration ports."""

from pathlib import Path

import pytest

from agents.dev_agent.adapters.gitlab_client import GitLabClient as DevGitLabClient
from shared.core import (
    BitableTablePort,
    FeishuContactLookupPort,
    FeishuMessengerPort,
    FeishuWebhookPort,
    GitLabMergeRequestNotePort,
    GitLabMergeRequestPort,
    OpenProjectWorkPackagePort,
)
from shared.integrations.feishu.bitable import BitableService
from shared.integrations.feishu.client import FeishuClient
from shared.integrations.feishu.webhook import FeishuWebhookClient
from shared.integrations.gitlab import GitLabClient
from shared.integrations.openproject.client import OpenProjectClient


def test_openproject_client_satisfies_work_package_port() -> None:
    client = OpenProjectClient(base_url="https://openproject.example", api_key="test")
    assert isinstance(client, OpenProjectWorkPackagePort)


def test_bitable_service_satisfies_table_port() -> None:
    service = BitableService()
    assert isinstance(service, BitableTablePort)


def test_feishu_client_satisfies_gateway_ports() -> None:
    client = FeishuClient(app_id="cli_test", app_secret="secret")
    assert isinstance(client, FeishuMessengerPort)
    assert isinstance(client, FeishuContactLookupPort)


def test_feishu_webhook_client_satisfies_webhook_port() -> None:
    assert isinstance(FeishuWebhookClient(), FeishuWebhookPort)


def test_gitlab_client_satisfies_mr_note_port() -> None:
    assert isinstance(GitLabClient(), GitLabMergeRequestNotePort)


def test_dev_gitlab_client_satisfies_merge_request_port() -> None:
    client = DevGitLabClient(
        base_url="https://gitlab.example",
        token="test-token",
        project_id=1,
    )
    assert isinstance(client, GitLabMergeRequestPort)


def test_dev_agent_core_does_not_own_http_adapters() -> None:
    for path in Path("agents/dev_agent/core").glob("*.py"):
        source = path.read_text()
        assert "import httpx" not in source
        assert "httpx." not in source


@pytest.mark.parametrize(
    "path",
    [
        "agents/pjm_agent/core/alert_service.py",
        "agents/pjm_agent/core/config_service.py",
        "agents/pjm_agent/core/decomposition_orchestrator.py",
        "agents/dev_agent/core/notifier.py",
        "agents/pjm_agent/core/op_writer.py",
        "agents/pjm_agent/core/push_service.py",
        "agents/pjm_agent/core/report_service.py",
        "agents/dev_agent/core/result_collector.py",
        "agents/qa_agent/core/notifier.py",
        "services/gateways/user_interaction/core/daily_tasks.py",
        "services/gateways/user_interaction/core/tools.py",
        "shared/capabilities/analysis/core/daily_report.py",
        "shared/capabilities/analysis/core/milestone_checker.py",
        "shared/capabilities/analysis/core/quality_evaluator.py",
        "shared/capabilities/analysis/core/weekly_report.py",
        "shared/capabilities/sync/core/engine.py",
    ],
)
def test_core_services_depend_on_ports_not_concrete_external_clients(path: str) -> None:
    source = Path(path).read_text()
    assert "shared.integrations.openproject" not in source
    assert "shared.integrations.feishu.bitable" not in source
    assert "shared.integrations.feishu.client" not in source
