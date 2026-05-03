"""Adapter implementations for dev_agent external systems."""

from .agentforge_client import ForgeClient, ForgeClientError
from .gitlab_client import GitLabClient, GitLabClientError

__all__ = [
    "ForgeClient",
    "ForgeClientError",
    "GitLabClient",
    "GitLabClientError",
]
