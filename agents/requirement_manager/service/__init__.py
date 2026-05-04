"""
Requirement Manager service layer.

Contains agent application logic and event handlers.
"""
from .agent import RequirementManagerAgent, agent, get_agent

__all__ = ["RequirementManagerAgent", "agent", "get_agent"]
