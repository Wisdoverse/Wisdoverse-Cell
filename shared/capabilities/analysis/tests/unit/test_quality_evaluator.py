"""Tests for deliverable quality evaluation."""
from unittest.mock import AsyncMock, patch

import pytest

from shared.capabilities.analysis.core.quality_evaluator import QualityEvaluator


@pytest.fixture
def bitable():
    service = AsyncMock()
    service.list_all_records = AsyncMock(return_value=[])
    service.update_record = AsyncMock()
    return service


@pytest.fixture
def llm():
    gateway = AsyncMock()
    gateway.complete = AsyncMock(
        return_value='{"quality":"合格","comment":"Metadata is sufficient.","confidence":0.7}'
    )
    return gateway


@pytest.mark.asyncio
async def test_fetch_tasks_with_deliverables_skips_scored_tasks(bitable):
    evaluator = QualityEvaluator(bitable)
    bitable.list_all_records.return_value = [
        {
            "record_id": "rec_1",
            "fields": {
                "任务(动宾短语)": "Prepare PRD",
                "交付物/产出链接": "https://example.feishu.cn/docx/abc?token=secret",
            },
        },
        {
            "record_id": "rec_2",
            "fields": {
                "任务(动宾短语)": "Reviewed",
                "交付物/产出链接": "https://example.feishu.cn/docx/def",
                "交付物质量": "合格",
            },
        },
    ]

    with patch("shared.capabilities.analysis.core.quality_evaluator.settings") as mock_settings:
        mock_settings.feishu_pm_app_token = "app"
        mock_settings.feishu_pm_task_table_id = "table"
        tasks = await evaluator._fetch_tasks_with_deliverables()

    assert [task["record_id"] for task in tasks] == ["rec_1"]
    assert tasks[0]["name"] == "Prepare PRD"


@pytest.mark.asyncio
async def test_evaluate_all_calls_llm_and_writes_back(bitable, llm):
    evaluator = QualityEvaluator(bitable, llm_gateway=llm)
    bitable.list_all_records.return_value = [
        {
            "record_id": "rec_1",
            "fields": {
                "任务(动宾短语)": "Prepare PRD",
                "状态": "进行中",
                "交付物/产出链接": "https://example.feishu.cn/docx/abc?token=secret",
                "验收标准": "Must include scope and risks.",
            },
        }
    ]

    with patch("shared.capabilities.analysis.core.quality_evaluator.settings") as mock_settings:
        mock_settings.feishu_pm_app_token = "app"
        mock_settings.feishu_pm_task_table_id = "table"
        result = await evaluator.evaluate_all()

    assert result == [
        {
            "record_id": "rec_1",
            "task": "Prepare PRD",
            "quality": "合格",
            "comment": "Metadata is sufficient.",
            "confidence": 0.7,
            "write_back": True,
        }
    ]
    prompt = llm.complete.await_args.kwargs["prompt"]
    assert "example.feishu.cn" in prompt
    assert "token=secret" not in prompt
    bitable.update_record.assert_awaited_once_with(
        record_id="rec_1",
        fields={"交付物质量": "合格", "质量评语": "Metadata is sufficient."},
        app_token="app",
        table_id="table",
    )


@pytest.mark.asyncio
async def test_evaluate_all_without_llm_degrades_visibly(bitable):
    evaluator = QualityEvaluator(bitable)
    bitable.list_all_records.return_value = [
        {
            "record_id": "rec_1",
            "fields": {
                "任务(动宾短语)": "Prepare PRD",
                "交付物/产出链接": "https://example.feishu.cn/docx/abc",
            },
        }
    ]

    with patch("shared.capabilities.analysis.core.quality_evaluator.settings") as mock_settings:
        mock_settings.feishu_pm_app_token = "app"
        mock_settings.feishu_pm_task_table_id = "table"
        result = await evaluator.evaluate_all()

    assert result == []
    bitable.update_record.assert_not_awaited()


def test_parse_evaluation_rejects_non_json(bitable, llm):
    evaluator = QualityEvaluator(bitable, llm_gateway=llm)

    with pytest.raises(ValueError, match="quality_evaluation_json_missing"):
        evaluator._parse_evaluation("not json")
