"""
Platform - 支持的平台枚举

跨模块共享的领域枚举，定义系统支持的消息平台类型。
"""
from enum import Enum


class Platform(str, Enum):
    """支持的平台"""

    FEISHU = "feishu"
    WECOM = "wecom"
    WEB = "web"
    OPENCLAW = "openclaw"
