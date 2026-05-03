"""
Agent Base Class - common base for all agents.

Defines the standard agent interface. Every agent should inherit this base
class. Optional A2A and MCP protocol extensions are supported.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from .event import Event, validate_agent_id

if TYPE_CHECKING:
    from shared.protocols.a2a.models import AgentCard, Message


class BaseAgent(ABC):
    """
    Base class for repository agents.

    Every agent must implement:
    1. handle_event: process received events.
    2. handle_request: process API requests.

    Attributes:
    - agent_id: unique identifier, for example "requirement-manager".
    - agent_name: display name, for example "Requirement Manager".
    - subscribed_events: event types consumed by the agent.
    - published_events: event types emitted by the agent.
    - a2a_enabled: whether A2A protocol support is enabled.
    - mcp_enabled: whether MCP protocol support is enabled.
    """

    def __init__(
        self,
        agent_id: str,
        agent_name: str,
        subscribed_events: list[str] | None = None,
        published_events: list[str] | None = None,
        *,
        a2a_enabled: bool = False,
        mcp_enabled: bool = False,
    ):
        self.agent_id = validate_agent_id(agent_id)
        self.agent_name = agent_name
        self.subscribed_events = subscribed_events or []
        self.published_events = published_events or []
        self._a2a_enabled = a2a_enabled
        self._mcp_enabled = mcp_enabled

    @property
    def a2a_enabled(self) -> bool:
        """Whether A2A protocol support is enabled."""
        return self._a2a_enabled

    @property
    def mcp_enabled(self) -> bool:
        """Whether MCP protocol support is enabled."""
        return self._mcp_enabled

    @abstractmethod
    async def handle_event(self, event: Event) -> list[Event]:
        """
        Process a received event.

        Args:
            event: Received event.

        Returns:
            New events produced while handling the input event.
        """
        pass

    @abstractmethod
    async def handle_request(self, request: dict) -> dict:
        """
        Process an API request.

        Args:
            request: Request payload.

        Returns:
            Response payload.
        """
        pass

    async def startup(self) -> None:
        """Run agent initialization logic at startup."""
        pass

    async def shutdown(self) -> None:
        """Run agent cleanup logic at shutdown."""
        pass

    async def health_check(self) -> dict[str, bool]:
        """Return this agent's health check results."""
        return {}

    def create_event(
        self, event_type: str, payload: dict, trace_id: str | None = None
    ) -> Event:
        """Create an event emitted by this agent."""
        return Event.create(
            event_type=event_type,
            source_agent=self.agent_id,
            payload=payload,
            trace_id=trace_id,
        )

    def _create_task_notification(
        self,
        task_id: str,
        status: str,
        summary: str,
        *,
        result: dict | None = None,
        error: str | None = None,
        usage: dict | None = None,
    ) -> Event:
        """Create a task.notification Event for Coordinator consumption.

        Convenience method — subclasses call this when completing a task
        dispatched by the Coordinator.
        """
        from .event import EventTypes
        payload: dict = {
            "task_id": task_id,
            "agent_id": self.agent_id,
            "status": status,
            "summary": summary,
        }
        if result is not None:
            payload["result"] = result
        if error is not None:
            payload["error"] = error
        if usage is not None:
            payload["usage"] = usage
        return self.create_event(EventTypes.TASK_NOTIFICATION, payload)

    def _create_progress_event(
        self,
        task_id: str,
        tool_use_count: int,
        llm_token_count: int,
        *,
        last_activity: dict | None = None,
        recent_activities: list[dict] | None = None,
    ) -> Event:
        """Create a task.progress Event for Coordinator real-time tracking.

        Convenience method — subclasses call this periodically during long tasks.
        """
        from .event import EventTypes
        payload: dict = {
            "task_id": task_id,
            "agent_id": self.agent_id,
            "tool_use_count": tool_use_count,
            "llm_token_count": llm_token_count,
        }
        if last_activity is not None:
            payload["last_activity"] = last_activity
        if recent_activities is not None:
            payload["recent_activities"] = recent_activities
        return self.create_event(EventTypes.TASK_PROGRESS, payload)

    async def describe(self) -> dict[str, Any]:
        """Return a compact agent description for APIs and tools."""
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "subscribed_events": self.subscribed_events,
            "published_events": self.published_events,
            "protocols": {
                "a2a_enabled": self.a2a_enabled,
                "mcp_enabled": self.mcp_enabled,
            },
        }

    async def audit(self) -> dict[str, Any]:
        """
        Return a lightweight audit result aligned with repository rules.

        The structure follows the `Analysis / Risk / Fixes` convention while
        staying JSON-friendly for direct API and tooling consumption.
        """
        health_checks = await self.health_check()
        failed_checks = [name for name, ok in health_checks.items() if not ok]

        fixes = (
            [f"Restore health check: {name}" for name in failed_checks]
            if failed_checks
            else ["No immediate fixes required."]
        )

        return {
            "analysis": {
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "event_contract": {
                    "subscribed_events": self.subscribed_events,
                    "published_events": self.published_events,
                },
                "health_checks": health_checks,
                "compliance": {
                    "inherits_base_agent": True,
                    "agent_id_kebab_case": "_" not in self.agent_id,
                    "async_lifecycle_supported": True,
                },
            },
            "risk": "medium" if failed_checks else "low",
            "fixes": fixes,
        }

    async def handle_standard_request(
        self, request: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Handle governance requests shared by all agents."""
        action = request.get("action")
        if action == "describe":
            return await self.describe()
        if action == "health":
            return {
                "agent_id": self.agent_id,
                "checks": await self.health_check(),
            }
        if action == "audit":
            return await self.audit()
        return None

    # ============ A2A Protocol Methods ============

    def get_agent_card(self) -> "AgentCard":
        """
        Get the A2A Agent Card for this agent.

        Override this method to customize the agent card.
        Only available when a2a_enabled=True.

        Returns:
            AgentCard describing this agent's capabilities.

        Raises:
            NotImplementedError: If A2A is not enabled or not implemented.
        """
        if not self._a2a_enabled:
            raise NotImplementedError(
                f"A2A protocol not enabled for agent {self.agent_id}"
            )
        # Default implementation - subclasses should override
        from shared.protocols.a2a.models import AgentCapabilities, AgentCard, AgentSkill

        return AgentCard(
            name=self.agent_name,
            description=f"Agent: {self.agent_name}",
            url=f"http://localhost:8000/a2a/{self.agent_id}",
            capabilities=AgentCapabilities(streaming=False, push_notifications=False),  # type: ignore[call-arg]
            skills=[
                AgentSkill(**s) if isinstance(s, dict) else s
                for s in self.get_a2a_skills()
            ],
        )

    def get_a2a_skills(self) -> list[dict[str, Any]]:
        """
        Get list of A2A skills this agent provides.

        Override this method to define agent skills.

        Returns:
            List of skill definitions.
        """
        return []

    async def handle_a2a_task(
        self, task_id: str, message: "Message"
    ) -> dict[str, Any]:
        """
        Handle an incoming A2A task message.

        Override this method to implement A2A task handling.

        Args:
            task_id: The A2A task identifier.
            message: The incoming message.

        Returns:
            Response dictionary with task result.

        Raises:
            NotImplementedError: If not implemented.
        """
        raise NotImplementedError(
            f"A2A task handling not implemented for agent {self.agent_id}"
        )

    # ============ MCP Protocol Methods ============

    def get_mcp_router(self) -> Any:
        """
        Get the MCP router for this agent.

        Override this method to provide MCP tools/resources.
        Only available when mcp_enabled=True.

        Returns:
            MCPRouter instance with registered tools/resources.

        Raises:
            NotImplementedError: If MCP is not enabled or not implemented.
        """
        if not self._mcp_enabled:
            raise NotImplementedError(
                f"MCP protocol not enabled for agent {self.agent_id}"
            )
        raise NotImplementedError(
            f"MCP router not implemented for agent {self.agent_id}"
        )

    def get_mcp_tools(self) -> list[dict[str, Any]]:
        """
        Get list of MCP tools this agent provides.

        Returns:
            List of tool definitions in MCP format.
        """
        return []

    def __repr__(self) -> str:
        protocols = []
        if self._a2a_enabled:
            protocols.append("A2A")
        if self._mcp_enabled:
            protocols.append("MCP")
        proto_str = f" protocols=[{', '.join(protocols)}]" if protocols else ""
        return f"<{self.__class__.__name__} id={self.agent_id} name={self.agent_name}{proto_str}>"
