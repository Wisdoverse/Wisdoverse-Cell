"""Deprecated: use shared.integrations.feishu.cards.decomposition"""
import importlib
import sys

_real = importlib.import_module("shared.integrations.feishu.cards.decomposition")
sys.modules[__name__] = _real
sys.modules["shared.services.feishu.cards.decomposition"] = _real
