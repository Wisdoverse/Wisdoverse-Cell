# Coordinator Agent Implementation Plan

> Language note: English is the primary documentation language. This legacy document may still contain Chinese implementation details; when editing it, put the English explanation first.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Coordinator Agent — Wisdoverse Cell's CEO-level orchestration engine that receives events from all agents, makes LLM-powered decisions, and dispatches work through existing event contracts.

**Architecture:** Event-driven `BaseAgent` running inside `AgentRuntime` via `create_agent_app()`. Receives `coordinator.command` (from chat_agent), `task.notification` (from workers), and `task.progress` (real-time). Uses LLM to synthesize context and make decisions. Dispatches through existing event types (`pm.tasks-ready-for-dev`, `qa.run-requested`, etc.) preserving payload contracts. Global Scratchpad (filesystem) with 3-layer compaction. All state persisted to PostgreSQL.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest + pytest-asyncio, Redis (EventBus), PostgreSQL (state), Claude API (via `shared/infra/llm_gateway`), filesystem (Scratchpad)

**Spec:** `docs/superpowers/specs/2026-03-31-coordinator-agent-design.md`

---

## Phase 1: Foundation Schemas

### Task 1: Add Coordinator EventTypes

**Files:**
- Modify: `shared/schemas/event.py:67-153` (EventTypes class)
- Test: `shared/schemas/tests/test_coordinator_events.py`

- [ ] **Step 1: Write the failing test**

```python
# shared/schemas/tests/test_coordinator_events.py
"""Tests for coordinator-related EventTypes constants."""
import pytest
from shared.schemas.event import EventTypes


def test_coordinator_command_event_type():
    assert EventTypes.COORDINATOR_COMMAND == "coordinator.command"


def test_coordinator_response_event_type():
    assert EventTypes.COORDINATOR_RESPONSE == "coordinator.response"


def test_coordinator_dispatch_event_type():
    assert EventTypes.COORDINATOR_DISPATCH == "coordinator.dispatch"


def test_task_notification_event_type():
    assert EventTypes.TASK_NOTIFICATION == "task.notification"


def test_task_progress_event_type():
    assert EventTypes.TASK_PROGRESS == "task.progress"


def test_pm_prd_ready_event_type():
    assert EventTypes.PM_PRD_READY == "pm.prd-ready"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest shared/schemas/tests/test_coordinator_events.py -v`
Expected: FAIL with `AttributeError: type object 'EventTypes' has no attribute 'COORDINATOR_COMMAND'`

- [ ] **Step 3: Write minimal implementation**

Add to `shared/schemas/event.py` inside the `EventTypes` class, after the existing `DEV_TASK_FAILED` line (line 152):

```python
    # Coordinator 编排相关
    COORDINATOR_COMMAND = "coordinator.command"
    COORDINATOR_RESPONSE = "coordinator.response"
    COORDINATOR_DISPATCH = "coordinator.dispatch"
    TASK_NOTIFICATION = "task.notification"
    TASK_PROGRESS = "task.progress"
    PM_PRD_READY = "pm.prd-ready"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest shared/schemas/tests/test_coordinator_events.py -v`
Expected: 6 passed

- [ ] **Step 5: Run full schema tests to verify no regressions**

Run: `python -m pytest shared/schemas/ -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add shared/schemas/event.py shared/schemas/tests/test_coordinator_events.py
git commit -m "feat(schemas): add coordinator event types"
```

---

### Task 2: Coordinator Payload Schemas

**Files:**
- Create: `shared/schemas/coordinator.py`
- Test: `shared/schemas/tests/test_coordinator_schemas.py`

- [ ] **Step 1: Write the failing test**

```python
# shared/schemas/tests/test_coordinator_schemas.py
"""Tests for coordinator payload models."""
import pytest
from pydantic import ValidationError


def test_task_usage_defaults():
    from shared.schemas.coordinator import TaskUsage
    usage = TaskUsage(duration_ms=1500)
    assert usage.duration_ms == 1500
    assert usage.llm_tokens == 0
    assert usage.tool_calls == 0


def test_task_notification_required_fields():
    from shared.schemas.coordinator import TaskNotification
    notif = TaskNotification(
        task_id="task_001",
        agent_id="dev-agent",
        status="completed",
        summary="Task finished successfully",
    )
    assert notif.task_id == "task_001"
    assert notif.result is None
    assert notif.usage is None
    assert notif.error is None


def test_task_notification_rejects_invalid_status():
    from shared.schemas.coordinator import TaskNotification
    with pytest.raises(ValidationError):
        TaskNotification(
            task_id="t1",
            agent_id="a1",
            status="running",  # not in Literal
            summary="bad",
        )


def test_coordinator_command_required_fields():
    from shared.schemas.coordinator import CoordinatorCommand
    cmd = CoordinatorCommand(
        command_id="cmd_001",
        intent="create new feature",
        original_message="我们需要新功能",
        user_id="user_123",
        user_name="Alice",
    )
    assert cmd.priority == "normal"
    assert cmd.context == {}


def test_coordinator_response_required_fields():
    from shared.schemas.coordinator import CoordinatorResponse
    resp = CoordinatorResponse(
        command_id="cmd_001",
        status="completed",
        summary="Feature created",
    )
    assert resp.details == {}
    assert resp.follow_up is None


def test_agent_progress_required_fields():
    from shared.schemas.coordinator import AgentProgress, ToolActivity
    activity = ToolActivity(tool_name="llm_call", description="Analyzing PRD")
    progress = AgentProgress(
        task_id="task_001",
        agent_id="dev-agent",
        tool_use_count=5,
        llm_token_count=1200,
        last_activity=activity,
    )
    assert progress.recent_activities == []
    assert activity.is_read is False
    assert activity.is_write is False


def test_dispatch_permissions_defaults():
    from shared.schemas.coordinator import DispatchPermissions
    perms = DispatchPermissions()
    assert perms.allowed_tools is None
    assert perms.denied_tools == []
    assert perms.human_approval_required is False
    assert perms.max_llm_tokens is None


def test_dispatch_permissions_with_restrictions():
    from shared.schemas.coordinator import DispatchPermissions
    perms = DispatchPermissions(
        allowed_tools=["git_commit", "file_read"],
        denied_tools=["file_delete"],
        max_llm_tokens=50000,
        human_approval_required=True,
    )
    assert len(perms.allowed_tools) == 2
    assert perms.max_llm_tokens == 50000


def test_tool_activity_model_dump():
    from shared.schemas.coordinator import ToolActivity
    activity = ToolActivity(
        tool_name="feishu_api",
        description="Sending message",
        is_write=True,
    )
    data = activity.model_dump()
    assert data["tool_name"] == "feishu_api"
    assert data["is_write"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest shared/schemas/tests/test_coordinator_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shared.schemas.coordinator'`

- [ ] **Step 3: Write minimal implementation**

```python
# shared/schemas/coordinator.py
"""Coordinator Agent payload schemas.

Models for communication between Coordinator and other agents:
- TaskNotification: Agent → Coordinator completion report
- CoordinatorCommand: chat_agent → Coordinator escalation
- CoordinatorResponse: Coordinator → chat_agent result
- AgentProgress: Agent → Coordinator real-time progress
- DispatchPermissions: Coordinator → Agent capability limits
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class TaskUsage(BaseModel):
    """Resource usage for a completed task."""
    model_config = ConfigDict(strict=True)

    duration_ms: int
    llm_tokens: int = 0
    tool_calls: int = 0


class TaskNotification(BaseModel):
    """Agent → Coordinator task completion notification."""
    model_config = ConfigDict(strict=True)

    task_id: str
    agent_id: str
    status: Literal["completed", "failed", "blocked"]
    summary: str
    result: dict[str, Any] | None = None
    usage: TaskUsage | None = None
    error: str | None = None


class CoordinatorCommand(BaseModel):
    """chat_agent → Coordinator escalation command."""
    command_id: str
    intent: str
    original_message: str
    user_id: str
    user_name: str
    context: dict[str, Any] = {}
    priority: Literal["normal", "high", "urgent"] = "normal"


class CoordinatorResponse(BaseModel):
    """Coordinator → chat_agent result."""
    command_id: str
    status: Literal["completed", "in_progress", "failed"]
    summary: str
    details: dict[str, Any] = {}
    follow_up: str | None = None


class ToolActivity(BaseModel):
    """Single tool invocation record for progress tracking."""
    tool_name: str
    description: str | None = None
    is_read: bool = False
    is_write: bool = False


class AgentProgress(BaseModel):
    """Agent → Coordinator real-time progress report."""
    task_id: str
    agent_id: str
    tool_use_count: int
    llm_token_count: int
    last_activity: ToolActivity | None = None
    recent_activities: list[ToolActivity] = []


class DispatchPermissions(BaseModel):
    """Coordinator → Agent capability limits per task dispatch."""
    allowed_tools: list[str] | None = None
    denied_tools: list[str] = []
    allowed_events: list[str] | None = None
    max_llm_tokens: int | None = None
    max_duration_ms: int | None = None
    human_approval_required: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest shared/schemas/tests/test_coordinator_schemas.py -v`
Expected: All 10 passed

- [ ] **Step 5: Commit**

```bash
git add shared/schemas/coordinator.py shared/schemas/tests/test_coordinator_schemas.py
git commit -m "feat(schemas): add coordinator payload models"
```

---

## Phase 2: Scratchpad Infrastructure

### Task 3: Scratchpad Read/Write

**Files:**
- Create: `shared/infra/scratchpad.py`
- Test: `shared/infra/tests/test_scratchpad.py`

- [ ] **Step 1: Write the failing test**

```python
# shared/infra/tests/test_scratchpad.py
"""Tests for Scratchpad file-based state management."""
import os
import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def scratchpad(tmp_path):
    from shared.infra.scratchpad import Scratchpad
    sp = Scratchpad(base_dir=str(tmp_path / "scratchpad"))
    await sp.initialize()
    return sp


@pytest.mark.asyncio
async def test_initialize_creates_directory_structure(scratchpad, tmp_path):
    base = tmp_path / "scratchpad"
    assert (base / "global_status.md").exists()
    assert (base / "workflows").is_dir()
    assert (base / "agents").is_dir()
    assert (base / "decisions").is_dir()
    assert (base / "decisions" / "pending.md").exists()
    assert (base / "decisions" / "log.md").exists()


@pytest.mark.asyncio
async def test_write_agent_output(scratchpad):
    await scratchpad.write_agent_output("dev-agent", "## Task Complete\nCommit abc123")
    content = await scratchpad.read_agent_output("dev-agent")
    assert "Commit abc123" in content


@pytest.mark.asyncio
async def test_read_nonexistent_agent_output_returns_empty(scratchpad):
    content = await scratchpad.read_agent_output("nonexistent-agent")
    assert content == ""


@pytest.mark.asyncio
async def test_write_workflow(scratchpad):
    await scratchpad.write_workflow("wf_001", "## PRD Phase\nIn progress")
    content = await scratchpad.read_workflow("wf_001")
    assert "PRD Phase" in content


@pytest.mark.asyncio
async def test_update_global_status(scratchpad):
    await scratchpad.update_global_status("All systems nominal")
    content = await scratchpad.read_global_status()
    assert "All systems nominal" in content


@pytest.mark.asyncio
async def test_read_incremental_returns_all_sections(scratchpad):
    await scratchpad.update_global_status("Status OK")
    await scratchpad.write_agent_output("dev-agent", "Dev done")
    await scratchpad.write_workflow("wf_001", "WF active")

    snapshot = await scratchpad.read_incremental()
    assert "Status OK" in snapshot
    assert "Dev done" in snapshot
    assert "WF active" in snapshot


@pytest.mark.asyncio
async def test_append_decision_log(scratchpad):
    await scratchpad.append_decision("Dispatched dev-agent for task_001")
    await scratchpad.append_decision("QA requested for task_001")
    content = await scratchpad.read_decision_log()
    assert "Dispatched dev-agent" in content
    assert "QA requested" in content


@pytest.mark.asyncio
async def test_token_estimate(scratchpad):
    await scratchpad.update_global_status("x" * 1000)
    estimate = await scratchpad.estimate_tokens()
    # ~250 tokens for 1000 chars (rough 4 bytes/token estimate)
    assert estimate > 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest shared/infra/tests/test_scratchpad.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shared.infra.scratchpad'`

- [ ] **Step 3: Write minimal implementation**

```python
# shared/infra/scratchpad.py
"""Scratchpad — file-based global state for Coordinator Agent.

Directory structure:
    scratchpad/
      global_status.md          # Global project status summary
      workflows/{id}.md         # Per-workflow progress
      agents/{id}_output.md     # Per-agent latest output
      decisions/pending.md      # Pending decision queue
      decisions/log.md          # Decision history
"""
import os
from pathlib import Path

import aiofiles

from shared.utils.logger import get_logger

logger = get_logger("infra.scratchpad")

_TOKEN_ESTIMATE_BYTES_PER_TOKEN = 4


class Scratchpad:
    """File-based scratchpad for Coordinator global state."""

    def __init__(self, base_dir: str = "data/scratchpad"):
        self._base = Path(base_dir)

    async def initialize(self) -> None:
        """Create directory structure and seed files."""
        for subdir in ["workflows", "agents", "decisions"]:
            (self._base / subdir).mkdir(parents=True, exist_ok=True)
        for seed in [
            "global_status.md",
            "decisions/pending.md",
            "decisions/log.md",
        ]:
            path = self._base / seed
            if not path.exists():
                path.write_text("")

    # ── Writes ──────────────────────────────────────────────

    async def write_agent_output(self, agent_id: str, content: str) -> None:
        await self._write(f"agents/{agent_id}_output.md", content)

    async def write_workflow(self, workflow_id: str, content: str) -> None:
        await self._write(f"workflows/{workflow_id}.md", content)

    async def update_global_status(self, content: str) -> None:
        await self._write("global_status.md", content)

    async def append_decision(self, entry: str) -> None:
        path = self._base / "decisions" / "log.md"
        async with aiofiles.open(path, "a") as f:
            await f.write(f"\n{entry}")

    # ── Reads ───────────────────────────────────────────────

    async def read_agent_output(self, agent_id: str) -> str:
        return await self._read(f"agents/{agent_id}_output.md")

    async def read_workflow(self, workflow_id: str) -> str:
        return await self._read(f"workflows/{workflow_id}.md")

    async def read_global_status(self) -> str:
        return await self._read("global_status.md")

    async def read_decision_log(self) -> str:
        return await self._read("decisions/log.md")

    async def read_incremental(self) -> str:
        """Read all scratchpad sections as a combined snapshot."""
        parts: list[str] = []
        status = await self.read_global_status()
        if status.strip():
            parts.append(f"## Global Status\n{status}")

        agents_dir = self._base / "agents"
        if agents_dir.is_dir():
            for f in sorted(agents_dir.glob("*_output.md")):
                content = f.read_text()
                if content.strip():
                    agent_id = f.stem.replace("_output", "")
                    parts.append(f"## Agent: {agent_id}\n{content}")

        workflows_dir = self._base / "workflows"
        if workflows_dir.is_dir():
            for f in sorted(workflows_dir.glob("*.md")):
                content = f.read_text()
                if content.strip():
                    wf_id = f.stem
                    parts.append(f"## Workflow: {wf_id}\n{content}")

        return "\n\n---\n\n".join(parts)

    # ── Metrics ─────────────────────────────────────────────

    async def estimate_tokens(self) -> int:
        """Rough token estimate: total bytes / 4."""
        total_bytes = 0
        for root, _dirs, files in os.walk(self._base):
            for fname in files:
                total_bytes += os.path.getsize(os.path.join(root, fname))
        return total_bytes // _TOKEN_ESTIMATE_BYTES_PER_TOKEN

    def should_compact(self) -> bool:
        """Check if L3 Full compaction is needed. Placeholder for threshold logic."""
        return False

    async def compact(self) -> None:
        """L3 Full compaction. Placeholder — requires forked_agent (Task 7)."""
        pass

    # ── Internal ────────────────────────────────────────────

    async def _write(self, rel_path: str, content: str) -> None:
        path = self._base / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, "w") as f:
            await f.write(content)

    async def _read(self, rel_path: str) -> str:
        path = self._base / rel_path
        if not path.exists():
            return ""
        async with aiofiles.open(path, "r") as f:
            return await f.read()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest shared/infra/tests/test_scratchpad.py -v`
Expected: All 9 passed

- [ ] **Step 5: Commit**

```bash
git add shared/infra/scratchpad.py shared/infra/tests/test_scratchpad.py
git commit -m "feat(infra): add Scratchpad file-based state manager"
```

---

## Phase 3: Coordinator Agent Core

### Task 4: Coordinator State Store

**Files:**
- Create: `agents/coordinator/db/models.py`
- Create: `agents/coordinator/db/state_store.py`
- Test: `agents/coordinator/tests/unit/test_state_store.py`

- [ ] **Step 1: Write the failing test**

```python
# agents/coordinator/tests/__init__.py
# (empty)

# agents/coordinator/tests/unit/__init__.py
# (empty)

# agents/coordinator/tests/unit/test_state_store.py
"""Tests for CoordinatorStateStore in-memory operations."""
import pytest
from datetime import UTC, datetime


def test_workflow_state_creation():
    from agents.coordinator.db.models import WorkflowState
    wf = WorkflowState(
        workflow_id="wf_001",
        type="requirement_to_deploy",
        status="active",
        current_phase="development",
        agents_involved=["dev-agent", "qa-agent"],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        context={"prd_id": "prd_001"},
    )
    assert wf.workflow_id == "wf_001"
    assert wf.status == "active"


def test_agent_state_defaults():
    from agents.coordinator.db.models import AgentStateRecord
    state = AgentStateRecord(agent_id="dev-agent", status="idle")
    assert state.current_task is None
    assert state.last_output_at is None
    assert state.error is None


def test_decision_record_creation():
    from agents.coordinator.db.models import DecisionRecord
    rec = DecisionRecord(
        decision_id="dec_001",
        workflow_id="wf_001",
        reasoning="PRD ready, dispatch to dev",
        action="dispatch_task",
        target_agent="dev-agent",
        created_at=datetime.now(UTC),
    )
    assert rec.outcome is None


@pytest.mark.asyncio
async def test_state_store_get_agent_states_empty():
    from agents.coordinator.db.state_store import CoordinatorStateStore
    store = CoordinatorStateStore()
    states = await store.get_agent_states()
    assert states == {}


@pytest.mark.asyncio
async def test_state_store_update_and_get_agent_state():
    from agents.coordinator.db.state_store import CoordinatorStateStore
    from agents.coordinator.db.models import AgentStateRecord
    store = CoordinatorStateStore()
    await store.update_agent_state("dev-agent", status="working", current_task="task_001")
    states = await store.get_agent_states()
    assert "dev-agent" in states
    assert states["dev-agent"].status == "working"
    assert states["dev-agent"].current_task == "task_001"


@pytest.mark.asyncio
async def test_state_store_get_pending_decisions_empty():
    from agents.coordinator.db.state_store import CoordinatorStateStore
    store = CoordinatorStateStore()
    pending = await store.get_pending_decisions()
    assert pending == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest agents/coordinator/tests/unit/test_state_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agents.coordinator'`

- [ ] **Step 3: Write minimal implementation**

```python
# agents/coordinator/__init__.py
# (empty)

# agents/coordinator/db/__init__.py
# (empty)

# agents/coordinator/db/models.py
"""Coordinator persistent state models."""
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class WorkflowState(BaseModel):
    """Active workflow state."""
    workflow_id: str
    type: str
    status: Literal["active", "paused", "completed", "failed"]
    current_phase: str
    agents_involved: list[str]
    created_at: datetime
    updated_at: datetime
    context: dict[str, Any] = {}


class AgentStateRecord(BaseModel):
    """Agent runtime state as seen by Coordinator."""
    agent_id: str
    status: Literal["idle", "working", "blocked", "error"]
    current_task: str | None = None
    last_output_at: datetime | None = None
    error: str | None = None


class DecisionRecord(BaseModel):
    """Coordinator decision log entry."""
    decision_id: str
    workflow_id: str | None = None
    reasoning: str
    action: str
    target_agent: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    outcome: str | None = None
```

```python
# agents/coordinator/db/state_store.py
"""In-memory state store for Coordinator Agent.

First version uses in-memory dicts. PostgreSQL persistence
will be added in a later task.
"""
from datetime import UTC, datetime

from .models import AgentStateRecord, DecisionRecord, WorkflowState


class CoordinatorStateStore:
    """Manages Coordinator's runtime state."""

    def __init__(self):
        self._agent_states: dict[str, AgentStateRecord] = {}
        self._workflows: dict[str, WorkflowState] = {}
        self._pending_decisions: list[DecisionRecord] = []

    async def get_agent_states(self) -> dict[str, AgentStateRecord]:
        return dict(self._agent_states)

    async def update_agent_state(
        self,
        agent_id: str,
        *,
        status: str = "idle",
        current_task: str | None = None,
        error: str | None = None,
    ) -> None:
        self._agent_states[agent_id] = AgentStateRecord(
            agent_id=agent_id,
            status=status,
            current_task=current_task,
            last_output_at=datetime.now(UTC),
            error=error,
        )

    async def get_pending_decisions(self) -> list[DecisionRecord]:
        return list(self._pending_decisions)

    async def persist(self, decisions: list) -> None:
        """Persist decisions. In-memory for now."""
        pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest agents/coordinator/tests/unit/test_state_store.py -v`
Expected: All 7 passed

- [ ] **Step 5: Commit**

```bash
git add agents/coordinator/
git commit -m "feat(coordinator): add state store and models"
```

---

### Task 5: Event Classifier

**Files:**
- Create: `agents/coordinator/core/classifier.py`
- Test: `agents/coordinator/tests/unit/test_classifier.py`

- [ ] **Step 1: Write the failing test**

```python
# agents/coordinator/tests/unit/test_classifier.py
"""Tests for Coordinator event classifier."""
import pytest
from shared.schemas.event import Event, EventTypes


def test_classify_coordinator_command():
    from agents.coordinator.core.classifier import classify_event
    event = Event.create(
        event_type=EventTypes.COORDINATOR_COMMAND,
        source_agent="chat-agent",
        payload={
            "command_id": "cmd_001",
            "intent": "create feature",
            "original_message": "新功能",
            "user_id": "u1",
            "user_name": "Alice",
        },
    )
    result = classify_event(event)
    assert result.kind == "command"
    assert result.data.command_id == "cmd_001"


def test_classify_task_notification():
    from agents.coordinator.core.classifier import classify_event
    event = Event.create(
        event_type=EventTypes.TASK_NOTIFICATION,
        source_agent="dev-agent",
        payload={
            "task_id": "task_001",
            "agent_id": "dev-agent",
            "status": "completed",
            "summary": "Done",
        },
    )
    result = classify_event(event)
    assert result.kind == "notification"
    assert result.data.status == "completed"


def test_classify_task_progress():
    from agents.coordinator.core.classifier import classify_event
    event = Event.create(
        event_type=EventTypes.TASK_PROGRESS,
        source_agent="dev-agent",
        payload={
            "task_id": "task_001",
            "agent_id": "dev-agent",
            "tool_use_count": 5,
            "llm_token_count": 1200,
        },
    )
    result = classify_event(event)
    assert result.kind == "progress"
    assert result.data.tool_use_count == 5


def test_classify_generic_event():
    from agents.coordinator.core.classifier import classify_event
    event = Event.create(
        event_type=EventTypes.PM_DECOMPOSE_COMPLETED,
        source_agent="pjm-agent",
        payload={"wp_id": 100, "tasks": []},
    )
    result = classify_event(event)
    assert result.kind == "event"
    assert result.data.event_type == EventTypes.PM_DECOMPOSE_COMPLETED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest agents/coordinator/tests/unit/test_classifier.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agents.coordinator.core'`

- [ ] **Step 3: Write minimal implementation**

```python
# agents/coordinator/core/__init__.py
# (empty)

# agents/coordinator/core/classifier.py
"""Event classifier for Coordinator Agent.

Converts raw EventBus events into typed ClassifiedEvent objects.
"""
from dataclasses import dataclass
from typing import Union

from shared.schemas.coordinator import (
    AgentProgress,
    CoordinatorCommand,
    TaskNotification,
)
from shared.schemas.event import Event, EventTypes


@dataclass
class ClassifiedEvent:
    """Typed event for Coordinator processing."""
    kind: str  # "command" | "notification" | "progress" | "event"
    data: Union[CoordinatorCommand, TaskNotification, AgentProgress, Event]


def classify_event(event: Event) -> ClassifiedEvent:
    """Classify an EventBus event into a Coordinator-internal type."""
    if event.event_type == EventTypes.COORDINATOR_COMMAND:
        return ClassifiedEvent(
            kind="command",
            data=CoordinatorCommand(**event.payload),
        )
    if event.event_type == EventTypes.TASK_NOTIFICATION:
        return ClassifiedEvent(
            kind="notification",
            data=TaskNotification(**event.payload),
        )
    if event.event_type == EventTypes.TASK_PROGRESS:
        return ClassifiedEvent(
            kind="progress",
            data=AgentProgress(**event.payload),
        )
    return ClassifiedEvent(kind="event", data=event)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest agents/coordinator/tests/unit/test_classifier.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add agents/coordinator/core/
git commit -m "feat(coordinator): add event classifier"
```

---

### Task 6: Decision-to-Event Dispatcher

**Files:**
- Create: `agents/coordinator/core/dispatcher.py`
- Create: `agents/coordinator/core/models.py`
- Test: `agents/coordinator/tests/unit/test_dispatcher.py`

- [ ] **Step 1: Write the failing test**

```python
# agents/coordinator/tests/unit/test_dispatcher.py
"""Tests for Coordinator decision-to-event dispatcher."""
import pytest
from shared.schemas.event import EventTypes


def test_dispatch_to_requirement_manager():
    from agents.coordinator.core.dispatcher import decision_to_event
    from agents.coordinator.core.models import Decision
    decision = Decision(
        target_agent="requirement-manager",
        action="dispatch_task",
        task_id="task_001",
        instruction="Produce PRD for @mention feature",
        workflow_id="wf_001",
    )
    event = decision_to_event(decision)
    assert event.event_type == EventTypes.COORDINATOR_DISPATCH
    assert event.payload["target_agent"] == "requirement-manager"
    assert event.payload["instruction"] == "Produce PRD for @mention feature"
    assert event.source_agent == "coordinator"


def test_dispatch_to_dev_agent_preserves_contract():
    from agents.coordinator.core.dispatcher import decision_to_event
    from agents.coordinator.core.models import Decision
    decision = Decision(
        target_agent="dev-agent",
        action="dispatch_task",
        task_id="task_002",
        instruction="Implement @mention parsing",
        workflow_id="wf_001",
        context={"wp_id": 100, "tasks": [{"id": 1, "title": "Parse mentions"}]},
    )
    event = decision_to_event(decision)
    assert event.event_type == EventTypes.PM_TASKS_READY_FOR_DEV
    assert event.payload["wp_id"] == 100
    assert event.payload["tasks"][0]["title"] == "Parse mentions"
    assert event.payload["instruction"] == "Implement @mention parsing"


def test_dispatch_to_qa_agent_preserves_contract():
    from agents.coordinator.core.dispatcher import decision_to_event
    from agents.coordinator.core.models import Decision
    decision = Decision(
        target_agent="qa-agent",
        action="dispatch_task",
        task_id="task_003",
        instruction="Verify @mention feature",
        workflow_id="wf_001",
        context={
            "agent_name": "dev-agent",
            "commit_sha": "abc1234",
            "mr_iid": 42,
            "gitlab_project_id": 1,
            "files_changed": ["shared/integrations/feishu/mention.py"],
        },
    )
    event = decision_to_event(decision)
    assert event.event_type == EventTypes.QA_RUN_REQUESTED
    assert event.payload["agent_name"] == "dev-agent"
    assert event.payload["commit_sha"] == "abc1234"
    assert event.payload["requested_by"] == "coordinator"
    assert event.payload["instruction"] == "Verify @mention feature"


def test_dispatch_to_chat_agent_response():
    from agents.coordinator.core.dispatcher import decision_to_event
    from agents.coordinator.core.models import Decision
    decision = Decision(
        target_agent="chat-agent",
        action="respond",
        task_id="task_004",
        instruction="",
        command_id="cmd_001",
        status="completed",
        summary="Feature shipped",
    )
    event = decision_to_event(decision)
    assert event.event_type == EventTypes.COORDINATOR_RESPONSE
    assert event.payload["command_id"] == "cmd_001"
    assert event.payload["summary"] == "Feature shipped"


def test_dispatch_to_pjm_group():
    from agents.coordinator.core.dispatcher import decision_to_event
    from agents.coordinator.core.models import Decision
    decision = Decision(
        target_agent="pjm-agent",
        action="dispatch_task",
        task_id="task_005",
        instruction="Decompose PRD into tasks",
        workflow_id="wf_001",
        scratchpad_ref="scratchpad/workflows/wf_001.md",
    )
    event = decision_to_event(decision)
    assert event.event_type == EventTypes.COORDINATOR_DISPATCH
    assert event.payload["scratchpad_ref"] == "scratchpad/workflows/wf_001.md"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest agents/coordinator/tests/unit/test_dispatcher.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agents.coordinator.core.dispatcher'`

- [ ] **Step 3: Write minimal implementation**

```python
# agents/coordinator/core/models.py
"""Internal models for Coordinator decision-making."""
from typing import Any

from pydantic import BaseModel


class Decision(BaseModel):
    """A single decision from the Coordinator's _think() step."""
    target_agent: str
    action: str  # dispatch_task, continue_task, respond, escalate, wait
    task_id: str
    instruction: str
    workflow_id: str | None = None
    priority: str = "normal"
    reasoning: str = ""
    context: dict[str, Any] = {}
    # For chat_agent responses
    command_id: str | None = None
    status: str | None = None
    summary: str | None = None
    # For PJM group
    scratchpad_ref: str | None = None
    # Permissions
    permissions: Any | None = None
```

```python
# agents/coordinator/core/dispatcher.py
"""Convert Coordinator decisions into EventBus events.

Key principle: use existing event types and payload contracts.
Coordinator-specific fields (instruction, workflow_id) are optional extensions.
"""
from shared.schemas.coordinator import CoordinatorResponse
from shared.schemas.event import Event, EventTypes

from .models import Decision


def decision_to_event(decision: Decision) -> Event:
    """Convert a Decision into an Event the target Agent understands."""
    target = decision.target_agent

    if target == "dev-agent":
        return Event.create(
            event_type=EventTypes.PM_TASKS_READY_FOR_DEV,
            source_agent="coordinator",
            payload={
                "wp_id": decision.context.get("wp_id"),
                "tasks": decision.context.get("tasks", []),
                "instruction": decision.instruction,
                "workflow_id": decision.workflow_id,
            },
        )

    if target == "qa-agent":
        return Event.create(
            event_type=EventTypes.QA_RUN_REQUESTED,
            source_agent="coordinator",
            payload={
                "agent_name": decision.context.get("agent_name"),
                "commit_sha": decision.context.get("commit_sha"),
                "mr_iid": decision.context.get("mr_iid"),
                "gitlab_project_id": decision.context.get("gitlab_project_id"),
                "files_changed": decision.context.get("files_changed", []),
                "requested_by": "coordinator",
                "instruction": decision.instruction,
                "workflow_id": decision.workflow_id,
            },
        )

    if target == "chat-agent":
        return Event.create(
            event_type=EventTypes.COORDINATOR_RESPONSE,
            source_agent="coordinator",
            payload=CoordinatorResponse(
                command_id=decision.command_id or "",
                status=decision.status or "completed",
                summary=decision.summary or "",
            ).model_dump(),
        )

    # Default: coordinator.dispatch (for RM, PJM group, others)
    return Event.create(
        event_type=EventTypes.COORDINATOR_DISPATCH,
        source_agent="coordinator",
        payload={
            "target_agent": target,
            "task_id": decision.task_id,
            "instruction": decision.instruction,
            "workflow_id": decision.workflow_id,
            "scratchpad_ref": decision.scratchpad_ref,
        },
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest agents/coordinator/tests/unit/test_dispatcher.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add agents/coordinator/core/models.py agents/coordinator/core/dispatcher.py agents/coordinator/tests/unit/test_dispatcher.py
git commit -m "feat(coordinator): add decision-to-event dispatcher"
```

---

### Task 7: Coordinator Agent (handle_event skeleton)

**Files:**
- Create: `agents/coordinator/service/__init__.py`
- Create: `agents/coordinator/service/agent.py`
- Create: `agents/coordinator/app/__init__.py`
- Create: `agents/coordinator/app/main.py`
- Test: `agents/coordinator/tests/unit/test_agent.py`

- [ ] **Step 1: Write the failing test**

```python
# agents/coordinator/tests/unit/test_agent.py
"""Tests for CoordinatorAgent event handling."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from shared.schemas.event import Event, EventTypes


@pytest.mark.asyncio
async def test_coordinator_agent_init():
    from agents.coordinator.service.agent import CoordinatorAgent
    agent = CoordinatorAgent()
    assert agent.agent_id == "coordinator"
    assert EventTypes.COORDINATOR_COMMAND in agent.subscribed_events
    assert EventTypes.TASK_NOTIFICATION in agent.subscribed_events
    assert EventTypes.TASK_PROGRESS in agent.subscribed_events


@pytest.mark.asyncio
async def test_handle_event_with_command_returns_events():
    from agents.coordinator.service.agent import CoordinatorAgent
    from agents.coordinator.core.models import Decision
    agent = CoordinatorAgent()

    # Mock _think to return a known decision
    mock_decision = Decision(
        target_agent="requirement-manager",
        action="dispatch_task",
        task_id="task_001",
        instruction="Produce PRD",
        workflow_id="wf_001",
    )
    agent._think = AsyncMock(return_value=[mock_decision])
    agent._scratchpad = MagicMock()
    agent._scratchpad.read_incremental = AsyncMock(return_value="")
    agent._scratchpad.update = AsyncMock()
    agent._scratchpad.should_compact = MagicMock(return_value=False)
    agent._state_store = MagicMock()
    agent._state_store.get_agent_states = AsyncMock(return_value={})
    agent._state_store.get_pending_decisions = AsyncMock(return_value=[])
    agent._state_store.persist = AsyncMock()

    event = Event.create(
        event_type=EventTypes.COORDINATOR_COMMAND,
        source_agent="chat-agent",
        payload={
            "command_id": "cmd_001",
            "intent": "new feature",
            "original_message": "新功能",
            "user_id": "u1",
            "user_name": "Alice",
        },
    )
    result_events = await agent.handle_event(event)
    assert len(result_events) == 1
    assert result_events[0].event_type == EventTypes.COORDINATOR_DISPATCH
    assert result_events[0].payload["target_agent"] == "requirement-manager"


@pytest.mark.asyncio
async def test_handle_event_with_progress_updates_state():
    from agents.coordinator.service.agent import CoordinatorAgent
    agent = CoordinatorAgent()

    agent._think = AsyncMock(return_value=[])
    agent._scratchpad = MagicMock()
    agent._scratchpad.read_incremental = AsyncMock(return_value="")
    agent._scratchpad.update = AsyncMock()
    agent._scratchpad.should_compact = MagicMock(return_value=False)
    agent._state_store = MagicMock()
    agent._state_store.get_agent_states = AsyncMock(return_value={})
    agent._state_store.get_pending_decisions = AsyncMock(return_value=[])
    agent._state_store.persist = AsyncMock()
    agent._state_store.update_agent_state = AsyncMock()

    event = Event.create(
        event_type=EventTypes.TASK_PROGRESS,
        source_agent="dev-agent",
        payload={
            "task_id": "task_001",
            "agent_id": "dev-agent",
            "tool_use_count": 3,
            "llm_token_count": 500,
        },
    )
    result_events = await agent.handle_event(event)
    assert result_events == []
    agent._state_store.update_agent_state.assert_awaited_once_with(
        "dev-agent", status="working", current_task="task_001"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest agents/coordinator/tests/unit/test_agent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agents.coordinator.service'`

- [ ] **Step 3: Write minimal implementation**

```python
# agents/coordinator/service/__init__.py
# (empty)

# agents/coordinator/service/agent.py
"""CoordinatorAgent — CEO-level orchestration engine.

Event-driven BaseAgent running inside AgentRuntime.
Receives events, calls LLM for synthesis, dispatches decisions.
"""
import asyncio
from typing import Any

from shared.infra.scratchpad import Scratchpad
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..core.classifier import ClassifiedEvent, classify_event
from ..core.dispatcher import decision_to_event
from ..core.models import Decision
from ..db.state_store import CoordinatorStateStore

logger = get_logger("coordinator.agent")


class CoordinatorAgent(BaseAgent):
    """Global orchestration engine."""

    def __init__(self):
        super().__init__(
            agent_id="coordinator",
            agent_name="Coordinator",
            subscribed_events=[
                EventTypes.COORDINATOR_COMMAND,
                EventTypes.TASK_NOTIFICATION,
                EventTypes.TASK_PROGRESS,
                EventTypes.PM_PRD_READY,
                EventTypes.PM_DECOMPOSE_COMPLETED,
                EventTypes.PM_DECOMPOSITION_FAILED,
                EventTypes.ANALYSIS_RISK_DETECTED,
            ],
            published_events=[
                EventTypes.COORDINATOR_RESPONSE,
                EventTypes.COORDINATOR_DISPATCH,
            ],
        )
        self._scratchpad = Scratchpad()
        self._state_store = CoordinatorStateStore()

    async def startup(self) -> None:
        await self._scratchpad.initialize()
        logger.info("coordinator_started")

    async def shutdown(self) -> None:
        logger.info("coordinator_stopped")

    async def handle_event(self, event: Event) -> list[Event]:
        """Single entry point for all events."""
        classified = classify_event(event)

        # Progress events update state directly, no LLM call
        if classified.kind == "progress":
            progress = classified.data
            await self._state_store.update_agent_state(
                progress.agent_id,
                status="working",
                current_task=progress.task_id,
            )
            return []

        # All other events go through synthesis
        scratchpad = await self._scratchpad.read_incremental()
        agent_states = await self._state_store.get_agent_states()
        pending = await self._state_store.get_pending_decisions()

        context = self._build_context(
            scratchpad=scratchpad,
            agent_states=agent_states,
            incoming=classified,
            pending_decisions=pending,
        )
        decisions = await self._think(context)

        outgoing = [decision_to_event(d) for d in decisions]

        await self._scratchpad.update(decisions)
        await self._state_store.persist(decisions)

        if self._scratchpad.should_compact():
            asyncio.create_task(self._scratchpad.compact())

        return outgoing

    def _build_context(
        self,
        *,
        scratchpad: str,
        agent_states: dict,
        incoming: ClassifiedEvent,
        pending_decisions: list,
    ) -> dict[str, Any]:
        """Build context dict for LLM synthesis."""
        return {
            "scratchpad": scratchpad,
            "agent_states": {
                k: v.model_dump() for k, v in agent_states.items()
            },
            "incoming_event": {
                "kind": incoming.kind,
                "data": (
                    incoming.data.model_dump()
                    if hasattr(incoming.data, "model_dump")
                    else incoming.data.payload
                ),
            },
            "pending_decisions": [d.model_dump() for d in pending_decisions],
        }

    async def _think(self, context: dict[str, Any]) -> list[Decision]:
        """LLM synthesis. Placeholder — will call llm_gateway in next task."""
        return []
```

```python
# agents/coordinator/app/__init__.py
# (empty)

# agents/coordinator/app/main.py
"""FastAPI entry point for Coordinator Agent."""
from shared.app import create_agent_app

from ..service.agent import CoordinatorAgent

agent = CoordinatorAgent()
app = create_agent_app(agent, title="Coordinator Agent")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest agents/coordinator/tests/unit/test_agent.py -v`
Expected: 3 passed

- [ ] **Step 5: Run all coordinator tests**

Run: `python -m pytest agents/coordinator/tests/ -v`
Expected: All passed (classifier + dispatcher + state_store + agent)

- [ ] **Step 6: Commit**

```bash
git add agents/coordinator/
git commit -m "feat(coordinator): add CoordinatorAgent with handle_event skeleton"
```

---

## Phase 4: LLM Think Engine (Deferred)

### Task 8: _think() LLM Integration

> **Note:** This task connects `_think()` to `llm_gateway.complete()` with a structured system prompt.
> It requires iterating on the prompt design with real LLM calls. Deferred to a separate
> focused session after the skeleton is tested end-to-end.

**Files:**
- Create: `agents/coordinator/core/think.py`
- Create: `agents/coordinator/core/prompts.py`
- Test: `agents/coordinator/tests/unit/test_think.py`

- [ ] **Step 1: Write the failing test**

```python
# agents/coordinator/tests/unit/test_think.py
"""Tests for Coordinator think engine."""
import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_think_returns_decision_list():
    from agents.coordinator.core.think import think
    from agents.coordinator.core.models import Decision

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value="""{
        "decisions": [
            {
                "target_agent": "requirement-manager",
                "action": "dispatch_task",
                "task_id": "task_001",
                "instruction": "Produce PRD for @mention feature",
                "workflow_id": "wf_001",
                "reasoning": "New feature request, needs PRD first"
            }
        ]
    }""")

    context = {
        "scratchpad": "",
        "agent_states": {},
        "incoming_event": {
            "kind": "command",
            "data": {
                "command_id": "cmd_001",
                "intent": "new feature",
                "original_message": "新功能",
                "user_id": "u1",
                "user_name": "Alice",
            },
        },
        "pending_decisions": [],
    }

    decisions = await think(context, llm=mock_llm)
    assert len(decisions) == 1
    assert isinstance(decisions[0], Decision)
    assert decisions[0].target_agent == "requirement-manager"
    mock_llm.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_think_handles_empty_response():
    from agents.coordinator.core.think import think

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value='{"decisions": []}')

    decisions = await think({"scratchpad": "", "agent_states": {}, "incoming_event": {"kind": "event", "data": {}}, "pending_decisions": []}, llm=mock_llm)
    assert decisions == []


@pytest.mark.asyncio
async def test_think_handles_malformed_json():
    from agents.coordinator.core.think import think

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value="not json at all")

    decisions = await think({"scratchpad": "", "agent_states": {}, "incoming_event": {"kind": "event", "data": {}}, "pending_decisions": []}, llm=mock_llm)
    assert decisions == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest agents/coordinator/tests/unit/test_think.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agents.coordinator.core.think'`

- [ ] **Step 3: Write minimal implementation**

```python
# agents/coordinator/core/think.py
"""LLM-powered decision engine for Coordinator.

Calls Claude with structured context, parses JSON response into Decision list.
"""
import json

from shared.utils.logger import get_logger

from .models import Decision
from .prompts import build_system_prompt

logger = get_logger("coordinator.think")


async def think(context: dict, *, llm) -> list[Decision]:
    """Call LLM with context, return list of Decisions."""
    system_prompt = build_system_prompt()
    user_prompt = json.dumps(context, ensure_ascii=False, default=str)

    try:
        raw = await llm.complete(
            prompt=user_prompt,
            agent_id="coordinator",
            task_type="coordinator_synthesis",
            system_prompt=system_prompt,
            max_tokens=4096,
        )
    except Exception:
        logger.exception("coordinator_think_llm_error")
        return []

    try:
        parsed = json.loads(raw)
        decisions_data = parsed.get("decisions", [])
        return [Decision(**d) for d in decisions_data]
    except (json.JSONDecodeError, Exception):
        logger.warning("coordinator_think_parse_error", raw_response=raw[:200])
        return []
```

```python
# agents/coordinator/core/prompts.py
"""System prompts for Coordinator Agent."""


def build_system_prompt() -> str:
    return """You are the Coordinator Agent (CEO) of Wisdoverse Cell, an AI-native company.

You receive events from other agents and make orchestration decisions.

## Your Role
- Synthesize information from agent outputs and events
- Make decisions about what to do next
- Generate complete, self-contained instructions for worker agents
- Never guess or fabricate agent results — only decide based on what you receive

## Response Format
Return a JSON object with a "decisions" array. Each decision has:
- target_agent: agent ID to dispatch to (e.g., "requirement-manager", "dev-agent", "qa-agent", "chat-agent")
- action: "dispatch_task" | "continue_task" | "respond" | "wait"
- task_id: unique task identifier
- instruction: complete instruction for the target agent
- workflow_id: workflow this belongs to (optional)
- reasoning: why you made this decision
- context: additional data needed by the target (e.g., wp_id, tasks[], agent_name, commit_sha)
- command_id: (for chat-agent responses) original command ID
- status: (for chat-agent responses) "completed" | "in_progress" | "failed"
- summary: (for chat-agent responses) human-readable summary

## Key Rules
- For dev-agent: context MUST include wp_id and tasks[] (existing contract)
- For qa-agent: context MUST include agent_name, commit_sha, mr_iid, gitlab_project_id, files_changed
- Wait for pm.decompose-completed before sending work to dev-agent
- After PRD is ready, emit pm.prd_ready first, wait for decomposition
- If you cannot decide, return {"decisions": []} to wait for more information
"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest agents/coordinator/tests/unit/test_think.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add agents/coordinator/core/think.py agents/coordinator/core/prompts.py agents/coordinator/tests/unit/test_think.py
git commit -m "feat(coordinator): add LLM think engine with prompt"
```

---

## Phase 5: Wire _think() into Agent

### Task 9: Connect CoordinatorAgent to think engine

**Files:**
- Modify: `agents/coordinator/service/agent.py`
- Test: `agents/coordinator/tests/unit/test_agent_think.py`

- [ ] **Step 1: Write the failing test**

```python
# agents/coordinator/tests/unit/test_agent_think.py
"""Tests for CoordinatorAgent with real think engine wired in."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from shared.schemas.event import Event, EventTypes


@pytest.mark.asyncio
async def test_coordinator_calls_llm_on_command():
    from agents.coordinator.service.agent import CoordinatorAgent

    agent = CoordinatorAgent()
    agent._scratchpad = MagicMock()
    agent._scratchpad.read_incremental = AsyncMock(return_value="Status OK")
    agent._scratchpad.update = AsyncMock()
    agent._scratchpad.should_compact = MagicMock(return_value=False)
    agent._scratchpad.initialize = AsyncMock()
    agent._state_store = MagicMock()
    agent._state_store.get_agent_states = AsyncMock(return_value={})
    agent._state_store.get_pending_decisions = AsyncMock(return_value=[])
    agent._state_store.persist = AsyncMock()

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value='{"decisions": [{"target_agent": "requirement-manager", "action": "dispatch_task", "task_id": "t1", "instruction": "Make PRD"}]}')
    agent._llm = mock_llm

    event = Event.create(
        event_type=EventTypes.COORDINATOR_COMMAND,
        source_agent="chat-agent",
        payload={
            "command_id": "cmd_001",
            "intent": "new feature",
            "original_message": "Build it",
            "user_id": "u1",
            "user_name": "Alice",
        },
    )
    results = await agent.handle_event(event)
    assert len(results) == 1
    assert results[0].event_type == EventTypes.COORDINATOR_DISPATCH
    mock_llm.complete.assert_awaited_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest agents/coordinator/tests/unit/test_agent_think.py -v`
Expected: FAIL — `_think()` returns `[]` because `_llm` is not wired

- [ ] **Step 3: Update CoordinatorAgent to use think engine**

In `agents/coordinator/service/agent.py`, add import and modify `__init__` and `_think`:

```python
# Add at top of file:
from shared.infra.llm_gateway import llm_gateway
from ..core.think import think as think_fn

# In __init__, add:
        self._llm = llm_gateway

# Replace _think method:
    async def _think(self, context: dict[str, Any]) -> list[Decision]:
        """LLM synthesis — calls think engine with current LLM gateway."""
        return await think_fn(context, llm=self._llm)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest agents/coordinator/tests/unit/test_agent_think.py -v`
Expected: 1 passed

- [ ] **Step 5: Run all coordinator tests**

Run: `python -m pytest agents/coordinator/tests/ -v`
Expected: All passed

- [ ] **Step 6: Commit**

```bash
git add agents/coordinator/service/agent.py agents/coordinator/tests/unit/test_agent_think.py
git commit -m "feat(coordinator): wire think engine into CoordinatorAgent"
```

---

## Phase 6-8: Deferred Tasks

> The following tasks are deferred to keep the first PR focused and reviewable.
> Each will be its own PR after Phase 5 is merged and tested.

### Task 10 (Deferred): Agent Memory — `shared/infra/agent_memory.py`
- Three-scope memory system (global/agent/workflow)
- Permission-isolated save with workflow_id parameter
- Integration into BaseAgent

### Task 11 (Deferred): Tool Registry — `shared/infra/tool_registry.py`
- `Tool` ABC, `ToolMeta`, `build_tool()` factory
- `ToolRegistry` with permission-filtered `list_for_agent()`
- First tool migrations

### Task 12 (Deferred): Forked Agent — `shared/infra/forked_agent.py`
- Isolated LLM execution with write permission whitelist
- Scratchpad L3 compaction integration
- `should_compact()` threshold logic

### Task 13 (Deferred): BaseAgent Extensions
- `_report_progress()` with ProgressTracker
- `TaskNotification` auto-emit on task completion
- Scratchpad output write hooks

### Task 14 (Deferred): Existing Agent Modifications
- chat_agent: escalation judgment + `coordinator.command` publishing
- requirement_manager: subscribe `coordinator.dispatch`
- dev_agent / qa_agent: payload compatibility for `instruction` field
- pjm_agent / sync_agent / analysis_agent: subscribe `coordinator.dispatch`

---

## File Map Summary

| File | Action | Task |
|------|--------|------|
| `shared/schemas/event.py` | Modify | 1 |
| `shared/schemas/coordinator.py` | Create | 2 |
| `shared/infra/scratchpad.py` | Create | 3 |
| `agents/coordinator/db/models.py` | Create | 4 |
| `agents/coordinator/db/state_store.py` | Create | 4 |
| `agents/coordinator/core/classifier.py` | Create | 5 |
| `agents/coordinator/core/models.py` | Create | 6 |
| `agents/coordinator/core/dispatcher.py` | Create | 6 |
| `agents/coordinator/service/agent.py` | Create | 7, 9 |
| `agents/coordinator/app/main.py` | Create | 7 |
| `agents/coordinator/core/think.py` | Create | 8 |
| `agents/coordinator/core/prompts.py` | Create | 8 |
