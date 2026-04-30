"""GrpcPlugin — starts/stops a gRPC server alongside FastAPI."""

import asyncio

from shared.app.runtime import HealthCheckResult, RuntimePlugin


class GrpcPlugin(RuntimePlugin):
    name = "grpc"

    def __init__(self, *, server_factory=None, port: int | None = None):
        self._server_factory = server_factory
        self._port = port
        self._server = None

    async def startup(self, runtime) -> None:
        factory = self._server_factory
        if factory is None:
            from agents.requirement_manager.grpc.server import run_with_fastapi

            factory = run_with_fastapi
        self._server = await factory(agent=runtime.agent, grpc_port=self._port)

    async def shutdown(self, runtime) -> None:
        if self._server:
            await asyncio.wait_for(self._server.stop(grace=5), timeout=8)

    async def health_check(self) -> dict[str, HealthCheckResult]:
        return {
            "server": HealthCheckResult("ok")
            if self._server
            else HealthCheckResult("down", "not started")
        }
