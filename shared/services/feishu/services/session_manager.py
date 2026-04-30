"""Deprecated: use shared.integrations.feishu.services.session_manager"""
import importlib
import sys

_real = importlib.import_module("shared.integrations.feishu.services.session_manager")
sys.modules[__name__] = _real
sys.modules["shared.services.feishu.services.session_manager"] = _real
