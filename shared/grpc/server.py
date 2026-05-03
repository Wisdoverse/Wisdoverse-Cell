"""Deprecated shared gRPC server entry point.

The requirements gRPC runtime is owned by
``agents.requirement_manager.grpc.server``. Shared gRPC code should hold
protocol artifacts only, not capability runtime implementations.
"""


def main() -> None:
    raise SystemExit(
        "shared.grpc.server is deprecated; use "
        "python -m agents.requirement_manager.grpc.server"
    )


if __name__ == "__main__":
    main()
