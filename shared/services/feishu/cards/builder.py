"""Deprecated: use shared.integrations.feishu.cards.builder"""
import importlib
import sys

_real = importlib.import_module("shared.integrations.feishu.cards.builder")
sys.modules[__name__] = _real
sys.modules["shared.services.feishu.cards.builder"] = _real
