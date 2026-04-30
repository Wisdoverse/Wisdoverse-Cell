"""Deprecated: use shared.integrations.feishu.handlers.bot"""
import importlib
import sys

_real = importlib.import_module("shared.integrations.feishu.handlers.bot")
sys.modules[__name__] = _real
sys.modules["shared.services.feishu.handlers.bot"] = _real
