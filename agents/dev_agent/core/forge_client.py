"""Deprecated compatibility import for dev_agent AgentForge adapter."""

from ..adapters.agentforge_client import ForgeClient, ForgeClientError

__all__ = ["ForgeClient", "ForgeClientError"]
