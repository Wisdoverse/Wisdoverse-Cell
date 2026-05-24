"""Value objects for PJM decomposition workflows."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DecompositionRejectionReason:
    """Operator rejection reason kept as an immutable domain value object."""

    text: str = ""

    @classmethod
    def from_text(cls, text: str | None) -> "DecompositionRejectionReason":
        return cls(text=(text or "").strip())

    @property
    def length(self) -> int:
        return len(self.text)

    def to_event_payload(self) -> str:
        return self.text


__all__ = ["DecompositionRejectionReason"]
