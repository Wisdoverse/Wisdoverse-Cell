"""
API Schemas - Pydantic模型用于API请求/响应
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# ============ 导入相关 ============

class UploadRequest(BaseModel):
    """手动上传请求"""
    source: str = Field(default="upload", description="来源: upload/wechat")
    content: str = Field(..., min_length=10, description="会议内容")
    title: Optional[str] = Field(None, description="标题")
    meeting_date: Optional[str] = Field(None, description="会议日期 (ISO格式)")
    participants: Optional[list[str]] = Field(None, description="参与者列表")
    context: Optional[str] = Field(None, description="上下文说明")


class FeishuWebhookRequest(BaseModel):
    """飞书Webhook回调请求"""
    event_type: str
    meeting_id: Optional[str] = None
    topic: Optional[str] = None
    summary: str
    participants: Optional[list[str]] = None
    meeting_time: Optional[str] = None


class IngestResponse(BaseModel):
    """导入响应"""
    status: str = "ok"
    meeting_id: str
    requirements_extracted: int
    questions_generated: int


# ============ 需求相关 ============

class OpenQuestionOut(BaseModel):
    """待确认问题输出"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    question: str
    context: Optional[str]
    status: str
    answer: Optional[str]
    answered_by: Optional[str]
    created_at: datetime


class HistoryEntry(BaseModel):
    """变更历史条目"""
    action: str
    detail: str
    by: Optional[str] = None
    at: datetime


class RequirementOut(BaseModel):
    """需求输出"""
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
    """需求列表响应"""
    total: int
    page: int
    page_size: int
    items: list[RequirementOut]


class RequirementUpdateRequest(BaseModel):
    """需求更新请求"""
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    comment: Optional[str] = None


class DeleteRequirementRequest(BaseModel):
    """删除需求请求"""
    deleted_by: str = Field(..., min_length=1, description="删除操作人")


class DeleteRequirementResponse(BaseModel):
    """删除需求响应"""
    message: str = "Requirement deleted"
    requirement_id: str
    title: str


# ============ 反馈相关 ============

class ConfirmRequest(BaseModel):
    """确认需求请求"""
    confirmed_by: str = Field(..., min_length=1)


class RejectRequest(BaseModel):
    """拒绝需求请求"""
    reason: str = Field(..., min_length=1)
    rejected_by: str = Field(default="system")


class AnswerQuestionRequest(BaseModel):
    """回答问题请求"""
    answer: str = Field(..., min_length=1)
    answered_by: str = Field(default="system")


class BatchConfirmRequest(BaseModel):
    """批量确认需求请求"""
    requirement_ids: list[str] = Field(..., min_length=1, description="需求ID列表")
    confirmed_by: str = Field(..., min_length=1, description="确认人")


class BatchRejectRequest(BaseModel):
    """批量拒绝需求请求"""
    requirement_ids: list[str] = Field(..., min_length=1, description="需求ID列表")
    reason: str = Field(..., min_length=1, description="拒绝原因")
    rejected_by: str = Field(default="system", description="拒绝人")


class BatchOperationResult(BaseModel):
    """批量操作单个结果"""
    requirement_id: str
    success: bool
    error: Optional[str] = None


class BatchOperationResponse(BaseModel):
    """批量操作响应"""
    total: int = Field(..., description="请求处理的需求数")
    succeeded: int = Field(..., description="成功数")
    failed: int = Field(..., description="失败数")
    results: list[BatchOperationResult]


# ============ 会议相关 ============

class MeetingOut(BaseModel):
    """会议输出"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    title: Optional[str]
    meeting_date: Optional[datetime]
    participants: list[str]
    processed: bool
    created_at: datetime


class MeetingListResponse(BaseModel):
    """会议列表响应"""
    total: int
    page: int
    page_size: int
    items: list[MeetingOut]


# ============ 搜索相关 ============

class SearchResultItem(BaseModel):
    """搜索结果项"""
    id: str
    title: str
    category: str
    similarity: float = Field(..., ge=0, le=1, description="相似度分数 (0-1)")


class SemanticSearchResponse(BaseModel):
    """语义搜索响应"""
    query: str
    total: int
    items: list[SearchResultItem]


class SimilarRequirementItem(BaseModel):
    """相似需求项"""
    id: str
    title: str
    category: str
    similarity: float


class SimilarRequirementsResponse(BaseModel):
    """相似需求响应"""
    requirement_id: str
    similar: list[SimilarRequirementItem]


# ============ 冲突检测相关 ============

class ConflictCheckRequest(BaseModel):
    """冲突检测请求"""
    title: str = Field(..., min_length=1, description="需求标题")
    description: str = Field(..., min_length=1, description="需求描述")
    category: Optional[str] = Field(None, description="需求分类")
    exclude_ids: Optional[list[str]] = Field(None, description="排除的需求ID列表")


class ConflictCheckResponse(BaseModel):
    """冲突检测响应"""
    relation: str = Field(..., description="关系类型: new/duplicate/update/conflict")
    confidence: float = Field(..., ge=0, le=1, description="判断确信度")
    explanation: str
    suggested_action: str
    related_requirement_id: Optional[str] = None
    merge_suggestion: Optional[str] = None


# ============ 统计相关 ============

class DailyTrendItem(BaseModel):
    """每日趋势项"""
    date: str
    count: int


class StatsResponse(BaseModel):
    """统计响应"""
    requirements_by_status: dict[str, int]
    total_meetings: int
    unprocessed_meetings: int
    vector_store_count: Optional[int] = None


class EnhancedStatsResponse(BaseModel):
    """增强统计响应 (含趋势)"""
    requirements_by_status: dict[str, int]
    requirements_by_priority: dict[str, int]
    requirements_by_category: dict[str, int]
    total_meetings: int
    unprocessed_meetings: int
    vector_store_count: Optional[int] = None
    weekly_trend: list[DailyTrendItem] = []
    today_count: int = 0


# ============ 导出相关 ============

class PRDExportResponse(BaseModel):
    """PRD 导出响应"""
    content: str = Field(..., description="PRD 文档内容 (Markdown)")
    format: str = "markdown"
    generated_at: datetime
    requirements_count: int
    version: str


class QuestionsExportResponse(BaseModel):
    """问题清单导出响应"""
    content: str = Field(..., description="问题清单内容 (Markdown)")
    format: str = "markdown"
    generated_at: datetime
    questions_count: int
