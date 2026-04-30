"""AnalysisAgent API Schemas"""
from datetime import UTC, datetime

from pydantic import BaseModel, Field


class DailyReportResponse(BaseModel):
    status: str = "ok"
    content: str = ""
    summary: str = ""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WeeklyReportResponse(BaseModel):
    status: str = "ok"
    content: str = ""
    summary: str = ""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RiskItem(BaseModel):
    feature: str = ""
    risk_level: str = ""
    days_remaining: int = 0
    progress: int = 0
    message: str = ""


class RiskCheckResponse(BaseModel):
    total: int = 0
    risks: list[RiskItem] = []


class HealthResponse(BaseModel):
    status: str
    agent: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, bool]
