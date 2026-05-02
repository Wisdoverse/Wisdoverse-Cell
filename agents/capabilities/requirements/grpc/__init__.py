"""
gRPC Server Package

Provides gRPC interface for Go Gateway to communicate with AI Core.
"""
from .servicer import RequirementServicer

__all__ = [
    "RequirementServicer",
    "serve",
    "create_server",
]


def __getattr__(name: str):
    """Lazily import server helpers so protobuf imports do not shadow grpcio."""
    if name in {"create_server", "serve"}:
        from .server import create_server, serve

        return {"create_server": create_server, "serve": serve}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
