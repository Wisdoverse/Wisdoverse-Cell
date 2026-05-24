"""Compatibility Bitable proxy routes for the chat-agent API."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..adapters.chat_agent_client import get_chat_agent_client

router = APIRouter(prefix="/api/bitable", tags=["bitable"])


class ConfirmRequest(BaseModel):
    record_id: str = ""
    fields: dict[str, Any] = Field(default_factory=dict)
    table_id: str = ""
    user_id: str = ""
    user_name: str = ""
    action_id: str = ""


class RejectRequest(BaseModel):
    action_type: str = ""
    user_id: str = ""
    user_name: str = ""
    fields: dict[str, Any] = Field(default_factory=dict)
    table_id: str = ""
    record_id: str = ""


class CreateRequest(BaseModel):
    fields: dict[str, Any] = Field(default_factory=dict)
    table_id: str = ""
    user_id: str = ""
    user_name: str = ""
    action_id: str = ""


@router.post("/confirm")
async def confirm_update(req: ConfirmRequest) -> dict[str, Any]:
    """Proxy confirmed Bitable updates to chat-agent."""
    return await get_chat_agent_client().confirm_bitable_update(req.model_dump())


@router.post("/reject")
async def reject_operation(req: RejectRequest) -> dict[str, Any]:
    """Proxy Bitable rejection tracking to chat-agent."""
    return await get_chat_agent_client().reject_bitable_operation(req.model_dump())


@router.post("/create")
async def create_record(req: CreateRequest) -> dict[str, Any]:
    """Proxy confirmed Bitable creates to chat-agent."""
    return await get_chat_agent_client().create_bitable_record(req.model_dump())
