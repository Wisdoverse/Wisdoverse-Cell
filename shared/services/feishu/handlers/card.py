"""Deprecated: use shared.integrations.feishu.handlers.card"""
import importlib
import sys

_real = importlib.import_module("shared.integrations.feishu.handlers.card")
sys.modules[__name__] = _real
sys.modules["shared.services.feishu.handlers.card"] = _real
