"""Ports and immutable replay decisions for an owning runtime's executor ledger."""

from dataclasses import dataclass
from typing import Protocol

from shared.protocols.executor import ExecutorRequest, ExecutorResponse


class NativeExecutorError(ValueError):
    def __init__(self, code: str, status_code: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class ExecutorClaim:
    acquired: bool
    state: str
    response: ExecutorResponse | None = None


class NativeExecutorLedger(Protocol):
    async def initialize(self) -> None: ...
    async def verify_schema(self) -> None: ...
    async def claim(self, request: ExecutorRequest, request_hash: str) -> ExecutorClaim: ...
    async def complete(
        self, run_id: str, request_hash: str, response: ExecutorResponse
    ) -> None: ...
    async def mark_uncertain(self, run_id: str, request_hash: str) -> None: ...
    async def lookup(self, company_id: str, run_id: str) -> ExecutorClaim | None: ...
