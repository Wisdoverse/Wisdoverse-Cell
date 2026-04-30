"""Deprecated: use shared.integrations.feishu.platform_adapter"""
import importlib
import sys

_real = importlib.import_module("shared.integrations.feishu.platform_adapter")
sys.modules[__name__] = _real
