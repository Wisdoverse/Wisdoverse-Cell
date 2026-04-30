"""
A2A Agent Registry

Service discovery and agent registration for A2A protocol.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..client.client import A2AClient, A2AClientConfig, discover_agent
from ..models import AgentCard


class RegisteredAgent(BaseModel):
    """Registered agent information."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(..., description="Unique agent identifier")
    url: str = Field(..., description="Agent base URL")
    card: AgentCard = Field(..., description="Agent card")
    registered_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Registration timestamp",
    )
    last_health_check: datetime | None = Field(
        default=None, description="Last successful health check"
    )
    is_healthy: bool = Field(default=True, description="Current health status")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


class AgentRegistry:
    """
    Registry for discovering and managing A2A agents.

    Supports:
    - Registering agents by URL (auto-discovers agent card)
    - Registering agents with explicit card
    - Finding agents by skill, capability, or ID
    - Health checking registered agents
    - Redis-backed storage for distributed access
    """

    def __init__(self, redis_client=None, key_prefix: str = "a2a:registry"):
        """
        Initialize the registry.

        Args:
            redis_client: Optional Redis client for distributed storage.
            key_prefix: Key prefix for Redis storage.
        """
        self._redis = redis_client
        self._key_prefix = key_prefix
        self._local_agents: dict[str, RegisteredAgent] = {}
        self._lock = asyncio.Lock()

    async def _get_redis_key(self, agent_id: str) -> str:
        """Get Redis key for an agent."""
        return f"{self._key_prefix}:{agent_id}"

    async def _store_agent(self, agent: RegisteredAgent) -> None:
        """Store agent in backend."""
        if self._redis:
            key = await self._get_redis_key(agent.agent_id)
            await self._redis.set(
                key,
                agent.model_dump_json(),
                ex=3600,  # 1 hour TTL
            )
        else:
            self._local_agents[agent.agent_id] = agent

    async def _load_agent(self, agent_id: str) -> RegisteredAgent | None:
        """Load agent from backend."""
        if self._redis:
            key = await self._get_redis_key(agent_id)
            data = await self._redis.get(key)
            if data:
                return RegisteredAgent.model_validate_json(data)
            return None
        else:
            return self._local_agents.get(agent_id)

    async def _delete_agent(self, agent_id: str) -> bool:
        """Delete agent from backend."""
        if self._redis:
            key = await self._get_redis_key(agent_id)
            return await self._redis.delete(key) > 0
        else:
            if agent_id in self._local_agents:
                del self._local_agents[agent_id]
                return True
            return False

    async def _list_agents(self) -> list[RegisteredAgent]:
        """List all agents from backend."""
        if self._redis:
            pattern = f"{self._key_prefix}:*"
            agents = []
            async for key in self._redis.scan_iter(match=pattern, count=100):
                data = await self._redis.get(key)
                if data:
                    agents.append(RegisteredAgent.model_validate_json(data))
            return agents
        else:
            return list(self._local_agents.values())

    # ============ Registration ============

    async def register_by_url(
        self,
        url: str,
        agent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RegisteredAgent:
        """
        Register an agent by discovering its agent card.

        Args:
            url: Base URL of the agent.
            agent_id: Optional explicit agent ID (defaults to card name).
            metadata: Optional additional metadata.

        Returns:
            The registered agent.

        Raises:
            A2AError: If discovery fails.
        """
        card = await discover_agent(url)

        effective_id = agent_id or card.name.lower().replace(" ", "-")

        agent = RegisteredAgent(
            agent_id=effective_id,
            url=url,
            card=card,
            metadata=metadata or {},
        )

        async with self._lock:
            await self._store_agent(agent)

        return agent

    async def register(
        self,
        agent_id: str,
        url: str,
        card: AgentCard,
        metadata: dict[str, Any] | None = None,
    ) -> RegisteredAgent:
        """
        Register an agent with an explicit card.

        Args:
            agent_id: Unique agent identifier.
            url: Base URL of the agent.
            card: The agent's AgentCard.
            metadata: Optional additional metadata.

        Returns:
            The registered agent.
        """
        agent = RegisteredAgent(
            agent_id=agent_id,
            url=url,
            card=card,
            metadata=metadata or {},
        )

        async with self._lock:
            await self._store_agent(agent)

        return agent

    async def unregister(self, agent_id: str) -> bool:
        """
        Unregister an agent.

        Args:
            agent_id: The agent ID to unregister.

        Returns:
            True if agent was unregistered, False if not found.
        """
        async with self._lock:
            return await self._delete_agent(agent_id)

    # ============ Discovery ============

    async def get(self, agent_id: str) -> RegisteredAgent | None:
        """
        Get a registered agent by ID.

        Args:
            agent_id: The agent ID to retrieve.

        Returns:
            The registered agent or None if not found.
        """
        return await self._load_agent(agent_id)

    async def list_all(self) -> list[RegisteredAgent]:
        """
        List all registered agents.

        Returns:
            List of all registered agents.
        """
        return await self._list_agents()

    async def find_by_skill(self, skill_id: str) -> list[RegisteredAgent]:
        """
        Find agents that have a specific skill.

        Args:
            skill_id: The skill ID to search for.

        Returns:
            List of agents with the skill.
        """
        agents = await self._list_agents()
        return [
            agent
            for agent in agents
            if any(skill.id == skill_id for skill in agent.card.skills)
        ]

    async def find_by_capability(
        self,
        capability: str,
        value: bool = True,
    ) -> list[RegisteredAgent]:
        """
        Find agents with a specific capability.

        Args:
            capability: Capability name (e.g., "streaming", "push_notifications").
            value: Expected capability value.

        Returns:
            List of agents with the capability.
        """
        agents = await self._list_agents()
        result = []
        for agent in agents:
            cap_value = getattr(agent.card.capabilities, capability, None)
            if cap_value == value:
                result.append(agent)
        return result

    async def find_by_tag(self, tag: str) -> list[RegisteredAgent]:
        """
        Find agents with skills containing a specific tag.

        Args:
            tag: The tag to search for.

        Returns:
            List of agents with skills containing the tag.
        """
        agents = await self._list_agents()
        return [
            agent
            for agent in agents
            if any(tag in skill.tags for skill in agent.card.skills)
        ]

    async def find_healthy(self) -> list[RegisteredAgent]:
        """
        Find all healthy agents.

        Returns:
            List of healthy agents.
        """
        agents = await self._list_agents()
        return [agent for agent in agents if agent.is_healthy]

    # ============ Health Checking ============

    async def check_health(self, agent_id: str) -> bool:
        """
        Check health of a specific agent.

        Args:
            agent_id: The agent ID to check.

        Returns:
            True if agent is healthy.
        """
        agent = await self._load_agent(agent_id)
        if agent is None:
            return False

        try:
            config = A2AClientConfig(base_url=agent.url, timeout=5.0)
            async with A2AClient(config) as client:
                await client.discover()

            agent.is_healthy = True
            agent.last_health_check = datetime.now(UTC)
        except Exception:
            agent.is_healthy = False

        await self._store_agent(agent)
        return agent.is_healthy

    async def check_all_health(self) -> dict[str, bool]:
        """
        Check health of all registered agents.

        Returns:
            Dictionary mapping agent_id to health status.
        """
        agents = await self._list_agents()
        results = {}

        tasks = [self.check_health(agent.agent_id) for agent in agents]
        health_results = await asyncio.gather(*tasks, return_exceptions=True)

        for agent, result in zip(agents, health_results):
            if isinstance(result, BaseException):
                results[agent.agent_id] = False
            else:
                results[agent.agent_id] = bool(result)

        return results

    # ============ Client Factory ============

    async def get_client(
        self,
        agent_id: str,
        auth_token: str | None = None,
        api_key: str | None = None,
    ) -> A2AClient:
        """
        Get an A2A client for a registered agent.

        Args:
            agent_id: The agent ID.
            auth_token: Optional auth token.
            api_key: Optional API key.

        Returns:
            Configured A2AClient.

        Raises:
            ValueError: If agent not found.
        """
        agent = await self._load_agent(agent_id)
        if agent is None:
            raise ValueError(f"Agent not found: {agent_id}")

        config = A2AClientConfig(
            base_url=agent.url,
            auth_token=auth_token,
            api_key=api_key,
        )

        client = A2AClient(config)
        client._agent_card = agent.card
        await client.connect()

        return client


# Global registry instance
_registry: AgentRegistry | None = None


def get_registry(redis_client=None) -> AgentRegistry:
    """
    Get the global agent registry instance.

    Args:
        redis_client: Optional Redis client (used on first call).

    Returns:
        The global AgentRegistry instance.
    """
    global _registry
    if _registry is None:
        _registry = AgentRegistry(redis_client)
    return _registry
