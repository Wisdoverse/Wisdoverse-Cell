"""Observability — tracing, metrics, and logging helpers."""

from importlib import import_module

__all__ = [
    "init_tracing",
    "instrument_fastapi",
    "instrument_httpx",
    "shutdown_tracing",
]


def __getattr__(name: str):
    """Load tracing helpers lazily so logger privacy setup has no import cycle."""
    if name in __all__:
        tracing = import_module("shared.observability.tracing")
        return getattr(tracing, name)
    raise AttributeError(name)
