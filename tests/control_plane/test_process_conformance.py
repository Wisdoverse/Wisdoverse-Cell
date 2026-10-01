"""Fault and isolation checks for the bounded local process executor."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from shared.control_plane.agent_runner import AgentWakeupError, ControlPlaneAgentRunner
from shared.control_plane.domain.agent_wakeup_adapter import AgentWakeupAdapterConfig
from shared.control_plane.execution_ports import ExecutionTicket


def _process_config(*, source: str, timeout: int = 10) -> AgentWakeupAdapterConfig:
    return AgentWakeupAdapterConfig(
        agent_id="process-conformance",
        adapter_type="process",
        config={
            "command": [sys.executable, "-c", source],
            "timeout_sec": timeout,
        },
    )


def _pid_is_running(pid: int) -> bool:
    """Treat exited zombies as stopped; Linux exposes their state in /proc."""
    stat = Path(f"/proc/{pid}/stat")
    try:
        fields = stat.read_text(encoding="utf-8").split()
    except (FileNotFoundError, PermissionError):
        return False
    return len(fields) > 2 and fields[2] != "Z"


@pytest.mark.asyncio
async def test_process_executor_does_not_inherit_parent_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_name = "WISDOVERSE_PROCESS_TEST_SECRET"
    monkeypatch.setenv(secret_name, "parent-only-secret-value")
    runner = ControlPlaneAgentRunner(repo=object())
    result = await runner._execute_process(
        _process_config(source=f"import os; print(os.getenv({secret_name!r}, 'missing'))"),
        {"run_id": "run-secret-isolation"},
    )

    assert result["status"] == "ok"
    assert result["stdout"].strip() == "missing"
    assert "parent-only-secret-value" not in str(result)


@pytest.mark.asyncio
async def test_process_timeout_kills_the_entire_process_group_and_child(
    tmp_path: Path,
) -> None:
    child_pid_path = tmp_path / "child.pid"
    child_effect_path = tmp_path / "child-survived"
    child_source = (
        "import pathlib,time; time.sleep(1.4); "
        f"pathlib.Path({str(child_effect_path)!r}).write_text('survived')"
    )
    parent_source = (
        "import pathlib,subprocess,sys,time; "
        f"child=subprocess.Popen([sys.executable, '-c', {child_source!r}]); "
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid)); "
        "time.sleep(20)"
    )
    runner = ControlPlaneAgentRunner(repo=object())

    with pytest.raises(AgentWakeupError, match="local_adapter_timeout") as failure:
        await runner._execute_process(
            _process_config(source=parent_source, timeout=1),
            {"run_id": "run-process-timeout"},
        )

    assert failure.value.error_category == "timeout"
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    await asyncio.sleep(0.6)
    assert not child_effect_path.exists()
    if Path("/proc").exists():
        assert not _pid_is_running(child_pid)


@pytest.mark.asyncio
async def test_process_pause_then_resume_holds_child_until_resumed(
    tmp_path: Path,
) -> None:
    done_path = tmp_path / "process-completed"
    source = (
        "import pathlib,time; time.sleep(0.35); "
        f"pathlib.Path({str(done_path)!r}).write_text('done'); print('complete')"
    )

    class PauseThenResume:
        calls = 0
        saw_done_while_paused: list[bool] = []

        async def control_action(self, _ticket: ExecutionTicket) -> str:
            self.calls += 1
            if self.calls <= 2:
                self.saw_done_while_paused.append(done_path.exists())
                return "pause"
            return "resume"

    runner = ControlPlaneAgentRunner(repo=object())
    governance = PauseThenResume()
    runner._ticket = ExecutionTicket(
        execution_id="execution-process-pause",
        run_id="run-process-pause",
        owner_id="process-owner",
        ceiling_usd=0,
    )
    runner._governance = governance
    result = await runner._execute_process(
        _process_config(source=source), {"run_id": "run-process-pause"}
    )

    assert result["status"] == "ok"
    assert result["stdout"].strip() == "complete"
    assert governance.calls >= 3
    assert governance.saw_done_while_paused == [False, False]
    assert done_path.read_text(encoding="utf-8") == "done"


@pytest.mark.asyncio
async def test_process_terminate_kills_child_and_reports_cancelled(
    tmp_path: Path,
) -> None:
    child_effect_path = tmp_path / "terminated-child-effect"
    child_source = (
        "import pathlib,time; time.sleep(1.0); "
        f"pathlib.Path({str(child_effect_path)!r}).write_text('survived')"
    )
    parent_source = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable, '-c', {child_source!r}]); "
        "time.sleep(20)"
    )

    class TerminateAfterStart:
        calls = 0

        async def control_action(self, _ticket: ExecutionTicket) -> str:
            self.calls += 1
            return "resume" if self.calls == 1 else "terminate"

    runner = ControlPlaneAgentRunner(repo=object())
    governance = TerminateAfterStart()
    runner._ticket = ExecutionTicket(
        execution_id="execution-process-terminate",
        run_id="run-process-terminate",
        owner_id="process-owner",
        ceiling_usd=0,
    )
    runner._governance = governance

    with pytest.raises(AgentWakeupError, match="execution_terminated") as failure:
        await runner._execute_process(
            _process_config(source=parent_source), {"run_id": "run-process-terminate"}
        )

    assert failure.value.error_category == "cancelled"
    assert governance.calls >= 2
    await asyncio.sleep(1.1)
    assert not child_effect_path.exists()
