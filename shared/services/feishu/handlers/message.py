"""Deprecated: use shared.integrations.feishu.handlers.message"""
import importlib
import sys

_real = importlib.import_module("shared.integrations.feishu.handlers.message")
sys.modules[__name__] = _real
# Also register under the old path so patches target the same object
sys.modules["shared.services.feishu.handlers.message"] = _real
