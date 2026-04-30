"""Deprecated: use shared.integrations.feishu.adapter"""
import importlib
import sys

_real = importlib.import_module("shared.integrations.feishu.adapter")
sys.modules[__name__] = _real
