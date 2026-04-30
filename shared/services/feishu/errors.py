"""Deprecated: use shared.integrations.feishu.errors"""
import importlib
import sys

_real = importlib.import_module("shared.integrations.feishu.errors")
sys.modules[__name__] = _real
