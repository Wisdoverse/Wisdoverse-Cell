"""Deprecated: use shared.integrations.feishu.client"""
import importlib
import sys

_real = importlib.import_module("shared.integrations.feishu.client")
sys.modules[__name__] = _real
