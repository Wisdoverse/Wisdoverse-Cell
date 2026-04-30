"""Deprecated: use shared.integrations.feishu.router"""
import importlib
import sys

# Re-export everything from the new location
from shared.integrations.feishu.router import *  # noqa: F401,F403

# Ensure sys.modules points to the actual module so that
# patch.object(sys.modules["shared.services.feishu.router"], "settings")
# patches the real module's settings attribute.
_real = importlib.import_module("shared.integrations.feishu.router")
sys.modules[__name__] = _real
