"""
Service Layer - 服务层

包含 Agent 核心逻辑和事件处理器。
"""
from .agent import RequirementManagerAgent, agent, get_agent

__all__ = ["RequirementManagerAgent", "agent", "get_agent"]
