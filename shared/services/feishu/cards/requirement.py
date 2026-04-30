"""Deprecated: use shared.integrations.feishu.cards.requirement"""
import importlib
import sys

_real = importlib.import_module("shared.integrations.feishu.cards.requirement")
sys.modules[__name__] = _real
sys.modules["shared.services.feishu.cards.requirement"] = _real
