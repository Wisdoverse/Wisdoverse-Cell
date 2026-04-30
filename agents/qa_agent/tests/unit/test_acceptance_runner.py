"""Unit tests for AcceptanceRunnerService."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.qa_agent.core.acceptance_runner import AcceptanceRunnerService


@pytest.fixture
def runner():
    return AcceptanceRunnerService(timeout=10)


class TestRunJson:
    @pytest.mark.asyncio
    async def test_successful_run_returns_parsed_report(self, runner):
        report = {"summary": {"l0_gate": "PASS"}, "results": [], "duration_seconds": 1.5}
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(json.dumps(report).encode(), b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await runner.run_json("pjm_agent", level="l0")

        assert result["summary"]["l0_gate"] == "PASS"
        assert result["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_l0_fail_returns_exit_code_1(self, runner):
        report = {
            "summary": {"l0_gate": "FAIL", "l0_failures": 2},
            "results": [{"level": "L0", "status": "FAIL", "check": "secrets"}],
            "duration_seconds": 3.0,
        }
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(json.dumps(report).encode(), b""))
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await runner.run_json("pjm_agent")

        assert result["summary"]["l0_gate"] == "FAIL"
        assert result["exit_code"] == 1

    @pytest.mark.asyncio
    async def test_invalid_json_returns_error(self, runner):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"not json", b"some error"))
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await runner.run_json("pjm_agent")

        assert result["summary"]["l0_gate"] == "ERROR"
        assert "error" in result
        assert "JSON parse failed" in result["error"]

    @pytest.mark.asyncio
    async def test_timeout_returns_error(self, runner):
        async def slow_communicate():
            await asyncio.sleep(100)
            return (b"", b"")

        mock_proc = AsyncMock()
        mock_proc.communicate = slow_communicate
        mock_proc.kill = MagicMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await runner.run_json("pjm_agent")

        assert result["summary"]["l0_gate"] == "ERROR"
        assert "timed out" in result["error"]

    @pytest.mark.asyncio
    async def test_diff_ref_passed_to_command(self, runner):
        report = {"summary": {"l0_gate": "PASS"}, "results": [], "duration_seconds": 0}
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(json.dumps(report).encode(), b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            await runner.run_json("pjm_agent", diff_ref="origin/main")

        call_args = mock_exec.call_args[0]
        assert "--diff" in call_args
        assert "origin/main" in call_args


class TestRunMarkdown:
    @pytest.mark.asyncio
    async def test_returns_markdown_output(self, runner):
        md = "## Acceptance Report\n\nAll checks passed."
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(md.encode(), b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await runner.run_markdown("pjm_agent")

        assert "Acceptance Report" in result

    @pytest.mark.asyncio
    async def test_timeout_returns_error_string(self, runner):
        async def slow():
            await asyncio.sleep(100)
            return (b"", b"")

        mock_proc = AsyncMock()
        mock_proc.communicate = slow
        mock_proc.kill = MagicMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await runner.run_markdown("pjm_agent")

        assert "timed out" in result
