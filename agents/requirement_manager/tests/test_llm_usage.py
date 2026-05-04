"""
LLM Usage Model & Repository Tests
"""
import sys
from pathlib import Path

# Ensure the project root is on the Python path.
_project_root = Path(__file__).parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from datetime import UTC, datetime

import pytest

from agents.requirement_manager.db.repository import LLMUsageRepository
from agents.requirement_manager.models.llm_usage import LLMUsage
from shared.core.ids import generate_ulid


class TestLLMUsageModel:
    """LLMUsage model tests."""

    def test_create_usage_record(self):
        """Create a usage record."""
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
        """Create a failed usage record."""
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
        """Render the string representation."""
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
    """LLMUsageRepository tests."""

    async def test_create_usage(self, db_session):
        """Create a usage record."""
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
        """Get an empty daily summary."""
        repo = LLMUsageRepository(db_session)

        summary = await repo.get_daily_summary("2026-01-01")

        assert summary["date"] == "2026-01-01"
        assert summary["total_calls"] == 0
        assert summary["total_cost_usd"] == 0.0

    async def test_get_daily_summary_with_data(self, db_session):
        """Get a daily summary with data."""
        repo = LLMUsageRepository(db_session)
        today = datetime.now(UTC).strftime("%Y-%m-%d")

        # Create test data.
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

        # Add one failed record.
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

        # Get summary.
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
        """Get a daily summary filtered by Agent."""
        repo = LLMUsageRepository(db_session)
        today = datetime.now(UTC).strftime("%Y-%m-%d")

        # Create data for different Agents.
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

        # Filter by Agent.
        summary = await repo.get_daily_summary(today, agent_id="agent-a")

        assert summary["total_calls"] == 1
        assert "agent-a" in summary["by_agent"]
        assert "agent-b" not in summary["by_agent"]

    async def test_get_usage_by_agent(self, db_session):
        """Get usage records for one Agent."""
        repo = LLMUsageRepository(db_session)
        today = datetime.now(UTC).strftime("%Y-%m-%d")

        # Create test data.
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

        # Create data for another Agent.
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

        # Query records.
        records = await repo.get_usage_by_agent("target-agent", today, today)

        assert len(records) == 5
        assert all(r.agent_id == "target-agent" for r in records)

    async def test_get_recent_failures(self, db_session):
        """Get recent failed usage records."""
        repo = LLMUsageRepository(db_session)

        # Create a successful record.
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

        # Create failed records.
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

        # Query failed records.
        failures = await repo.get_recent_failures(limit=10)

        assert len(failures) == 3
        assert all(not f.success for f in failures)
