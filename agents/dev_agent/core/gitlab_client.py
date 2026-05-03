"""Deprecated compatibility import for dev_agent GitLab adapter."""

from ..adapters.gitlab_client import GitLabClient, GitLabClientError

__all__ = ["GitLabClient", "GitLabClientError"]
