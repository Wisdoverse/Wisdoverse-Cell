"""Deprecated: use shared.integrations.feishu.handlers.event"""
import importlib
import sys

_real = importlib.import_module("shared.integrations.feishu.handlers.event")
sys.modules[__name__] = _real
sys.modules["shared.services.feishu.handlers.event"] = _real
