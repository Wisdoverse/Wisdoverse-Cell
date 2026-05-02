"""
API schemas - Pydantic models for API requests and responses.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# ============ Import Models ============

class UploadRequest(BaseModel):
    """Manual upload request."""
    source: str = Field(default="upload", description="Source: upload/wechat")
    content: str = Field(..., min_length=10, description="Meeting content")
    title: Optional[str] = Field(None, description="Title")
    meeting_date: Optional[str] = Field(None, description="Meeting date in ISO format")
    participants: Optional[list[str]] = Field(None, description="Participant list")
    context: Optional[str] = Field(None, description="Context notes")


class FeishuWebhookRequest(BaseModel):
    """Feishu webhook callback request."""
    event_type: str
    meeting_id: Optional[str] = None
    topic: Optional[str] = None
    summary: str
    participants: Optional[list[str]] = None
    meeting_time: Optional[str] = None


class IngestResponse(BaseModel):
    """Ingest response."""
    status: str = "ok"
    meeting_id: str
    requirements_extracted: int
    questions_generated: int


# ============ Requirement Models ============

class OpenQuestionOut(BaseModel):
    """Open clarification question output."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    question: str
    context: Optional[str]
    status: str
    answer: Optional[str]
    answered_by: Optional[str]
    created_at: datetime


class HistoryEntry(BaseModel):
    """Change history entry."""
    action: str
    detail: str
    by: Optional[str] = None
    at: datetime


class RequirementOut(BaseModel):
    """Requirement output."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: str
    source_quote: Optional[str]
    status: str
    priority: str
    category: str
    source_meeting_ids: list[str]
    confirmed_by: Optional[str]
    confirmed_at: Optional[datetime]
    open_questions: list[OpenQuestionOut] = []
    history: list[HistoryEntry] = []
    created_at: datetime
    updated_at: datetime


class RequirementListResponse(BaseModel):
    """Requirement list response."""
    total: int
    page: int
    page_size: int
    items: list[RequirementOut]


class RequirementUpdateRequest(BaseModel):
    """Requirement update request."""
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    comment: Optional[str] = None


class DeleteRequirementRequest(BaseModel):
    """Delete requirement request."""
    deleted_by: str = Field(..., min_length=1, description="Deletion actor")


class DeleteRequirementResponse(BaseModel):
    """Delete requirement response."""
    message: str = "Requirement deleted"
    requirement_id: str
    title: str


# ============ Feedback Models ============

class ConfirmRequest(BaseModel):
    """Confirm requirement request."""
    confirmed_by: str = Field(..., min_length=1)


class RejectRequest(BaseModel):
    """Reject requirement request."""
    reason: str = Field(..., min_length=1)
    rejected_by: str = Field(default="system")


class AnswerQuestionRequest(BaseModel):
    """Answer open question request."""
    answer: str = Field(..., min_length=1)
    answered_by: str = Field(default="system")


class BatchConfirmRequest(BaseModel):
    """Batch requirement confirmation request."""
    requirement_ids: list[str] = Field(..., min_length=1, description="Requirement ID list")
    confirmed_by: str = Field(..., min_length=1, description="Confirmation actor")


class BatchRejectRequest(BaseModel):
    """Batch requirement rejection request."""
    requirement_ids: list[str] = Field(..., min_length=1, description="Requirement ID list")
    reason: str = Field(..., min_length=1, description="Rejection reason")
    rejected_by: str = Field(default="system", description="Rejection actor")


class BatchOperationResult(BaseModel):
    """Single result in a batch operation."""
    requirement_id: str
    success: bool
    error: Optional[str] = None


class BatchOperationResponse(BaseModel):
    """Batch operation response."""
    total: int = Field(..., description="Number of requirements processed")
    succeeded: int = Field(..., description="Success count")
    failed: int = Field(..., description="Failure count")
    results: list[BatchOperationResult]


# ============ Meeting Models ============

class MeetingOut(BaseModel):
    """Meeting output."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    title: Optional[str]
    meeting_date: Optional[datetime]
    participants: list[str]
    processed: bool
    created_at: datetime


class MeetingListResponse(BaseModel):
    """Meeting list response."""
    total: int
    page: int
    page_size: int
    items: list[MeetingOut]


# ============ Search Models ============

class SearchResultItem(BaseModel):
    """Search result item."""
    id: str
    title: str
    category: str
    similarity: float = Field(..., ge=0, le=1, description="Similarity score (0-1)")


class SemanticSearchResponse(BaseModel):
    """Semantic search response."""
    query: str
    total: int
    items: list[SearchResultItem]


class SimilarRequirementItem(BaseModel):
    """Similar requirement item."""
    id: str
    title: str
    category: str
    similarity: float


class SimilarRequirementsResponse(BaseModel):
    """Similar requirements response."""
    requirement_id: str
    similar: list[SimilarRequirementItem]


# ============ Conflict Detection Models ============

class ConflictCheckRequest(BaseModel):
    """Conflict check request."""
    title: str = Field(..., min_length=1, description="Requirement title")
    description: str = Field(..., min_length=1, description="Requirement description")
    category: Optional[str] = Field(None, description="Requirement category")
    exclude_ids: Optional[list[str]] = Field(None, description="Requirement IDs to exclude")


class ConflictCheckResponse(BaseModel):
    """Conflict check response."""
    relation: str = Field(..., description="Relation type: new/duplicate/update/conflict")
    confidence: float = Field(..., ge=0, le=1, description="Decision confidence")
    explanation: str
    suggested_action: str
    related_requirement_id: Optional[str] = None
    merge_suggestion: Optional[str] = None


# ============ Statistics Models ============

class DailyTrendItem(BaseModel):
    """Daily trend item."""
    date: str
    count: int


class StatsResponse(BaseModel):
    """Statistics response."""
    requirements_by_status: dict[str, int]
    total_meetings: int
    unprocessed_meetings: int
    vector_store_count: Optional[int] = None


class EnhancedStatsResponse(BaseModel):
    """Enhanced statistics response with trends."""
    requirements_by_status: dict[str, int]
    requirements_by_priority: dict[str, int]
    requirements_by_category: dict[str, int]
    total_meetings: int
    unprocessed_meetings: int
    vector_store_count: Optional[int] = None
    weekly_trend: list[DailyTrendItem] = []
    today_count: int = 0


# ============ Export Models ============

class PRDExportResponse(BaseModel):
    """PRD export response."""
    content: str = Field(..., description="PRD document content (Markdown)")
    format: str = "markdown"
    generated_at: datetime
    requirements_count: int
    version: str


class QuestionsExportResponse(BaseModel):
    """Question list export response."""
    content: str = Field(..., description="Question list content (Markdown)")
    format: str = "markdown"
    generated_at: datetime
    questions_count: int
