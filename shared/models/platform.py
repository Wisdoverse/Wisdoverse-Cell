"""
Platform - supported platform enum.

Shared domain enum for message platform types supported by the system.
"""
from enum import Enum


class Platform(str, Enum):
    """Supported platforms."""

    FEISHU = "feishu"
    WECOM = "wecom"
    WEB = "web"
    OPENCLAW = "openclaw"
