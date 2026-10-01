"""Immutable reviewed mapping from a confirmed requirement to delivery context."""

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DeliveryHandoffCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"] = "1.0"
    company_id: str = Field(min_length=1, max_length=48)
    project_id: int = Field(gt=0)
    wp_id: int = Field(gt=0)
    goal_id: str = Field(min_length=1, max_length=48)
    work_item_id: str = Field(min_length=1, max_length=48)
    requirement_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(min_length=1, max_length=2000)
    project_name: str = Field(default="", max_length=256)


@dataclass(frozen=True)
class ConfirmedRequirementSnapshot:
    requirement_id: str
    title: str
    description: str
    status: str
    confirmed_by: str | None

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(
            json.dumps(
                {
                    "requirement_id": self.requirement_id,
                    "title": self.title,
                    "description": self.description,
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()

    def assert_reviewed(self, command: DeliveryHandoffCommand) -> None:
        if self.status != "confirmed" or not self.confirmed_by:
            raise ValueError("requirement_confirmation_required")
        if self.content_hash != command.requirement_hash:
            raise ValueError("requirement_review_snapshot_changed")
        if not command.reason.strip():
            raise ValueError("handoff_review_reason_required")


class DeliveryHandoffReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"] = "1.0"
    requirement_id: str
    company_id: str
    event_id: str
    command_hash: str
    requirement_hash: str
    project_id: int
    wp_id: int
    goal_id: str
    work_item_id: str
    reviewed_by: str
    review_reason: str
    status: Literal["queued_for_decomposition"] = "queued_for_decomposition"


class DeliveryReviewSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    requirement_id: str
    company_id: str
    title: str
    description: str
    status: str
    confirmed_by: str | None
    requirement_hash: str
