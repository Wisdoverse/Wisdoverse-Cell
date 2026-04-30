"""ChatAgent API Schemas"""
from pydantic import BaseModel


class WebhookResponse(BaseModel):
    code: int = 0


class ChallengeResponse(BaseModel):
    challenge: str


class HealthResponse(BaseModel):
    status: str
    agent: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, bool]
