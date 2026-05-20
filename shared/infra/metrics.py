"""Compatibility exports for shared cross-cutting metrics.

The canonical metrics boundary is ``shared.observability.metrics``. This
module remains temporarily so older imports keep using the same collector
objects while callers migrate.
"""

from shared.observability import metrics as _metrics
from shared.observability.metrics import *  # noqa: F403

__all__ = _metrics.__all__
