"""Deprecated: use shared.integrations.feishu.bitable"""
import importlib
import sys

_real = importlib.import_module("shared.integrations.feishu.bitable")
sys.modules[__name__] = _real
