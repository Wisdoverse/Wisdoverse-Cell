"""
LLM Usage Model & Repository Tests
"""
import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中
_project_root = Path(__file__).parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from datetime import UTC, datetime

import pytest

from agents.capabilities.requirements.db.repository import LLMUsageRepository
from agents.capabilities.requirements.models.llm_usage import LLMUsage
from shared.utils.id_generator import generate_ulid


class TestLLMUsageModel:
    """LLMUsage 模型测试"""

    def test_create_usage_record(self):
        """测试创建使用记录"""
        usage = LLMUsage(
            id=generate_ulid(),
            agent_id="requirement-manager",
            task_type="extraction",
            model="claude-sonnet-4-20250514",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.0105,
            latency_ms=1200,
            success=True
        )

        assert usage.agent_id == "requirement-manager"
        assert usage.task_type == "extraction"
        assert usage.input_tokens == 1000
        assert usage.output_tokens == 500
        assert usage.success is True

    def test_create_failed_record(self):
        """测试创建失败记录"""
        usage = LLMUsage(
            id=generate_ulid(),
            agent_id="requirement-manager",
            task_type="generation",
            model="claude-sonnet-4-20250514",
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            latency_ms=5000,
            success=False,
            error_message="Rate limit exceeded"
        )

        assert usage.success is False
        assert usage.error_message == "Rate limit exceeded"

    def test_repr(self):
        """测试字符串表示"""
        usage = LLMUsage(
            id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            agent_id="test-agent",
            task_type="test",
            model="test-model",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
            latency_ms=100,
            success=True
        )

        repr_str = repr(usage)
        assert "LLMUsage" in repr_str
        assert "test-agent" in repr_str


@pytest.mark.asyncio
class TestLLMUsageRepository:
    """LLMUsageRepository 测试"""

    async def test_create_usage(self, db_session):
        """测试创建使用记录"""
        repo = LLMUsageRepository(db_session)

        usage = LLMUsage(
            id=generate_ulid(),
            agent_id="requirement-manager",
            task_type="extraction",
            model="claude-sonnet-4-20250514",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.0105,
            latency_ms=1200,
            success=True
        )

        created = await repo.create(usage)
        assert created.id == usage.id

    async def test_get_daily_summary_empty(self, db_session):
        """测试获取空的每日汇总"""
        repo = LLMUsageRepository(db_session)

        summary = await repo.get_daily_summary("2026-01-01")

        assert summary["date"] == "2026-01-01"
        assert summary["total_calls"] == 0
        assert summary["total_cost_usd"] == 0.0

    async def test_get_daily_summary_with_data(self, db_session):
        """测试获取有数据的每日汇总"""
        repo = LLMUsageRepository(db_session)
        today = datetime.now(UTC).strftime("%Y-%m-%d")

        # 创建测试数据
        for i in range(3):
            usage = LLMUsage(
                id=generate_ulid(),
                agent_id="requirement-manager",
                task_type="extraction" if i < 2 else "generation",
                model="claude-sonnet-4-20250514",
                input_tokens=1000,
                output_tokens=500,
                cost_usd=0.01,
                latency_ms=1000 + i * 100,
                success=True
            )
            await repo.create(usage)

        # 添加一条失败记录
        failed_usage = LLMUsage(
            id=generate_ulid(),
            agent_id="requirement-manager",
            task_type="extraction",
            model="claude-sonnet-4-20250514",
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            latency_ms=5000,
            success=False,
            error_message="API Error"
        )
        await repo.create(failed_usage)

        # 获取汇总
        summary = await repo.get_daily_summary(today)

        assert summary["total_calls"] == 4
        assert summary["success_calls"] == 3
        assert summary["failed_calls"] == 1
        assert summary["total_input_tokens"] == 3000
        assert summary["total_output_tokens"] == 1500
        assert summary["total_cost_usd"] == 0.03
        assert "requirement-manager" in summary["by_agent"]
        assert "extraction" in summary["by_task_type"]
        assert "generation" in summary["by_task_type"]

    async def test_get_daily_summary_filtered_by_agent(self, db_session):
        """测试按 Agent 过滤的每日汇总"""
        repo = LLMUsageRepository(db_session)
        today = datetime.now(UTC).strftime("%Y-%m-%d")

        # 创建不同 Agent 的数据
        for agent in ["agent-a", "agent-b"]:
            usage = LLMUsage(
                id=generate_ulid(),
                agent_id=agent,
                task_type="test",
                model="claude-sonnet-4-20250514",
                input_tokens=1000,
                output_tokens=500,
                cost_usd=0.01,
                latency_ms=1000,
                success=True
            )
            await repo.create(usage)

        # 按 Agent 过滤
        summary = await repo.get_daily_summary(today, agent_id="agent-a")

        assert summary["total_calls"] == 1
        assert "agent-a" in summary["by_agent"]
        assert "agent-b" not in summary["by_agent"]

    async def test_get_usage_by_agent(self, db_session):
        """测试获取某个 Agent 的使用记录"""
        repo = LLMUsageRepository(db_session)
        today = datetime.now(UTC).strftime("%Y-%m-%d")

        # 创建测试数据
        for i in range(5):
            usage = LLMUsage(
                id=generate_ulid(),
                agent_id="target-agent",
                task_type="test",
                model="claude-sonnet-4-20250514",
                input_tokens=100 * (i + 1),
                output_tokens=50,
                cost_usd=0.001,
                latency_ms=100,
                success=True
            )
            await repo.create(usage)

        # 创建其他 Agent 的数据
        other_usage = LLMUsage(
            id=generate_ulid(),
            agent_id="other-agent",
            task_type="test",
            model="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
            latency_ms=100,
            success=True
        )
        await repo.create(other_usage)

        # 查询
        records = await repo.get_usage_by_agent("target-agent", today, today)

        assert len(records) == 5
        assert all(r.agent_id == "target-agent" for r in records)

    async def test_get_recent_failures(self, db_session):
        """测试获取最近的失败记录"""
        repo = LLMUsageRepository(db_session)

        # 创建成功记录
        success_usage = LLMUsage(
            id=generate_ulid(),
            agent_id="test-agent",
            task_type="test",
            model="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
            latency_ms=100,
            success=True
        )
        await repo.create(success_usage)

        # 创建失败记录
        for i in range(3):
            failed_usage = LLMUsage(
                id=generate_ulid(),
                agent_id="test-agent",
                task_type="test",
                model="claude-sonnet-4-20250514",
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                latency_ms=5000,
                success=False,
                error_message=f"Error {i}"
            )
            await repo.create(failed_usage)

        # 查询失败记录
        failures = await repo.get_recent_failures(limit=10)

        assert len(failures) == 3
        assert all(not f.success for f in failures)
