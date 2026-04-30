"""
Logger - 统一的日志配置

使用structlog实现结构化日志，便于后续分析。
"""
import logging
import sys
from typing import Optional

import structlog


def get_logger(name: Optional[str] = None) -> structlog.BoundLogger:
    """
    获取配置好的logger实例

    Args:
        name: logger名称，通常是模块名或Agent ID

    Returns:
        配置好的structlog logger
    """
    return structlog.get_logger(name)


def setup_logging(
    level: str = "INFO",
    json_format: bool = False,
    log_file: Optional[str] = None
):
    """
    设置全局日志配置

    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
        json_format: 是否使用JSON格式输出
        log_file: 日志文件路径（可选）
    """
    # 设置标准库日志级别
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )

    # 简化的处理器列表
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_format:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,  # type: ignore[arg-type]
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


# 默认配置
setup_logging()
