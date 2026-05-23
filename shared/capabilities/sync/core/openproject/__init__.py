"""OpenProject sub-runtime (DDD-014 Stage 4 Step 1).

Internal sub-package for the OpenProject side of the sync runtime
per ADR-0009. Code that needs the OpenProject sync engine should
import from this package; legacy `shared.capabilities.sync.core`
imports remain as compatibility re-exports during the cutover
window.
"""
from .engine import OpenProjectSyncEngine

__all__ = ["OpenProjectSyncEngine"]
