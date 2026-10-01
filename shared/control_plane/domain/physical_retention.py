"""Bounded, explicit retention commands and compact replay evidence."""

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RetentionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    company_id: str = Field(min_length=1, max_length=48)
    batch_size: int = Field(default=100, ge=1, le=1000)
    dry_run: bool = True

    @property
    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True).encode()).hexdigest()


class RetentionReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"] = "1.0"
    company_id: str
    dry_run: bool
    audit_cutoff: datetime
    eligible_audit_events: int
    purged_audit_events: int
    purged_published_outbox_events: int
    expired_knowledge: int
    purged_knowledge: int
    minimal_replay_receipts_retained: Literal[True] = True


def idempotency_digest(company_id: str, key: str) -> str:
    return hashlib.sha256(json.dumps([company_id, key], separators=(",", ":")).encode()).hexdigest()
