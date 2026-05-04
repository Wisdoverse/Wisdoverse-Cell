"""Tests that existing agents accept Coordinator events."""
# ---------------------------------------------------------------------------
# Module stubs — block heavy optional dependencies that are not installed
# in the unit-test environment (lark_oapi, aiofiles, etc.)
# ---------------------------------------------------------------------------
import importlib
import importlib.abc
import importlib.machinery
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.schemas.event import Event, EventTypes


class _AutoMockFinder(importlib.abc.MetaPathFinder):
    """Automatically mock any import whose top-level package is in _BLOCKED_TOPS."""

    _BLOCKED_TOPS = {"lark_oapi", "aiofiles"}

    def find_spec(self, fullname, path, target=None):
        top = fullname.split(".")[0]
        if top in self._BLOCKED_TOPS:
            # Return a ModuleSpec backed by our loader
            return importlib.machinery.ModuleSpec(fullname, _AutoMockLoader())
        return None


class _AutoMockLoader(importlib.abc.Loader):
    def create_module(self, spec):
        return None  # use default machinery

    def exec_module(self, module):
        # Make every attribute access on the module return a new MagicMock,
        # so `from lark_oapi.foo import Bar` always succeeds.
        module.__getattr__ = lambda name: MagicMock()


# Install the finder at the front so it fires before the real finders
sys.meta_path.insert(0, _AutoMockFinder())


# ---------------------------------------------------------------------------
# chat_agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_agent_subscribes_coordinator_response():
    from services.gateways.user_interaction.service.agent import ChatAgent

    agent = ChatAgent(db=MagicMock(), bus=AsyncMock())
    assert EventTypes.COORDINATOR_RESPONSE in agent.subscribed_events


@pytest.mark.asyncio
async def test_chat_agent_publishes_coordinator_command():
    from services.gateways.user_interaction.service.agent import ChatAgent

    agent = ChatAgent(db=MagicMock(), bus=AsyncMock())
    assert EventTypes.COORDINATOR_COMMAND in agent.published_events


# ---------------------------------------------------------------------------
# requirement_manager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_requirement_manager_subscribes_coordinator_dispatch():
    from agents.requirement_manager.service.agent import RequirementManagerAgent

    agent = RequirementManagerAgent()
    assert EventTypes.COORDINATOR_DISPATCH in agent.subscribed_events


@pytest.mark.asyncio
async def test_requirement_manager_handles_coordinator_dispatch():
    from agents.requirement_manager.service.agent import RequirementManagerAgent

    agent = RequirementManagerAgent()
    event = Event.create(
        event_type=EventTypes.COORDINATOR_DISPATCH,
        source_agent="coordinator",
        payload={
            "target_agent": "requirement-manager",
            "task_id": "task_001",
            "instruction": "Produce PRD for feature X",
            "workflow_id": "wf_001",
        },
    )
    result = await agent.handle_event(event)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# pjm_agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pjm_agent_subscribes_coordinator_dispatch():
    from agents.pjm_agent.service.agent import PMAgent

    agent = PMAgent()
    assert EventTypes.COORDINATOR_DISPATCH in agent.subscribed_events
