"""
Requirements API - 需求查询接口
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from shared.utils.logger import get_logger

from ..core.analyzer import analyzer
from ..core.comparator import comparator
from ..db.database import get_db
from ..db.repository import MeetingRepository, MessageRepository, RequirementRepository
from ..db.vector_store import vector_store
from .schemas import (
    ConflictCheckRequest,
    ConflictCheckResponse,
    DailyTrendItem,
    DeleteRequirementRequest,
    DeleteRequirementResponse,
    EnhancedStatsResponse,
    MeetingListResponse,
    MeetingOut,
    RequirementListResponse,
    RequirementOut,
    RequirementUpdateRequest,
    SearchResultItem,
    SemanticSearchResponse,
    SimilarRequirementItem,
    SimilarRequirementsResponse,
    StatsResponse,
)

router = APIRouter(prefix="/api/v1", tags=["requirements"])
logger = get_logger("api.requirements")


@router.get("/requirements", response_model=RequirementListResponse)
async def list_requirements(
    status: Optional[str] = Query(None, description="状态筛选: pending/confirmed/changed/rejected"),
    category: Optional[str] = Query(None, description="分类筛选"),
    priority: Optional[str] = Query(None, description="优先级筛选: high/medium/low"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    session: AsyncSession = Depends(get_db)
):
    """获取需求列表"""
    repo = RequirementRepository(session)

    skip = (page - 1) * page_size
    requirements, total = await repo.list_all(
        status=status,
        category=category,
        priority=priority,
        skip=skip,
        limit=page_size
    )

    return RequirementListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[RequirementOut.model_validate(r) for r in requirements]
    )


@router.get("/requirements/{requirement_id}", response_model=RequirementOut)
async def get_requirement(
    requirement_id: str,
    session: AsyncSession = Depends(get_db)
):
    """获取需求详情"""
    repo = RequirementRepository(session)

    requirement = await repo.get_by_id(requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="需求不存在")

    return RequirementOut.model_validate(requirement)


@router.put("/requirements/{requirement_id}", response_model=RequirementOut)
async def update_requirement(
    requirement_id: str,
    request: RequirementUpdateRequest,
    session: AsyncSession = Depends(get_db)
):
    """更新需求信息"""
    from ..service.feedback_learning import FeedbackLearningService

    repo = RequirementRepository(session)

    # 检查需求是否存在
    requirement = await repo.get_by_id(requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="需求不存在")

    # 构建更新字段
    update_data = request.model_dump(exclude_unset=True, exclude_none=True)
    if "comment" in update_data:
        del update_data["comment"]  # comment用于记录历史，不直接更新

    if update_data:
        # 捕获原始值用于反馈学习
        original_values = {
            "title": requirement.title,
            "description": requirement.description,
            "priority": requirement.priority,
            "category": requirement.category,
        }

        # 记录变更历史
        requirement.add_history(
            action="updated",
            detail=f"字段更新: {list(update_data.keys())}",
            by=request.comment or "system"
        )

        # 更新字段
        requirement = await repo.update(requirement_id, **update_data)

        # 记录反馈用于学习（如果关键字段被修改，不阻塞主流程）
        feedback_fields = {"title", "description", "priority", "category"}
        if update_data.keys() & feedback_fields:
            try:
                corrected_values = {
                    "title": requirement.title,
                    "description": requirement.description,
                    "priority": requirement.priority,
                    "category": requirement.category,
                }
                feedback_service = FeedbackLearningService(session)
                await feedback_service.record_correction(
                    requirement_id=requirement_id,
                    original=original_values,
                    corrected=corrected_values,
                    corrected_by=request.comment or "user",
                    note=f"Updated fields: {list(update_data.keys())}",
                )
            except Exception:
                pass  # 反馈记录失败不影响主流程

    return RequirementOut.model_validate(requirement)


@router.delete("/requirements/{requirement_id}", response_model=DeleteRequirementResponse)
async def delete_requirement(
    requirement_id: str,
    request: DeleteRequirementRequest,
    session: AsyncSession = Depends(get_db)
):
    """
    删除需求

    同时删除关联的问题和向量库记录。
    删除后会发布 requirement.deleted 事件。
    """
    repo = RequirementRepository(session)

    # 删除需求（包括向量库同步删除）
    requirement = await repo.delete(requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="需求不存在")

    await session.commit()

    logger.info(
        "requirement_deleted",
        requirement_id=requirement_id,
        title=requirement.title,
        deleted_by=request.deleted_by
    )

    return DeleteRequirementResponse(
        requirement_id=requirement_id,
        title=requirement.title
    )


@router.get("/requirements/search", response_model=SemanticSearchResponse)
async def search_requirements(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    category: Optional[str] = Query(None, description="分类过滤"),
    limit: int = Query(20, ge=1, le=100, description="返回数量"),
    min_similarity: float = Query(0.5, ge=0, le=1, description="最小相似度阈值"),
):
    """
    语义搜索需求

    使用向量数据库进行语义匹配，返回与查询最相关的需求。
    支持自然语言查询，如"离线功能"、"用户登录相关"等。
    """
    # 使用向量库搜索
    results = await vector_store.search(
        query=q,
        n_results=limit,
        category_filter=category,
        min_similarity=min_similarity
    )

    items = [
        SearchResultItem(
            id=r["id"],
            title=r["title"],
            category=r["category"],
            similarity=r["similarity"]
        )
        for r in results
    ]

    logger.info(
        "semantic_search",
        query=q,
        results_count=len(items)
    )

    return SemanticSearchResponse(
        query=q,
        total=len(items),
        items=items
    )


@router.get("/requirements/{requirement_id}/similar", response_model=SimilarRequirementsResponse)
async def find_similar_requirements(
    requirement_id: str,
    limit: int = Query(5, ge=1, le=20, description="返回数量"),
    min_similarity: float = Query(0.7, ge=0, le=1, description="最小相似度"),
    session: AsyncSession = Depends(get_db)
):
    """
    查找相似需求

    根据指定需求，找出语义上相似的其他需求。
    用于发现重复需求或相关需求。
    """
    repo = RequirementRepository(session)

    # 验证需求存在
    requirement = await repo.get_by_id(requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="需求不存在")

    # 查找相似需求
    similar = await vector_store.find_similar(
        requirement_id=requirement_id,
        n_results=limit,
        min_similarity=min_similarity
    )

    items = [
        SimilarRequirementItem(
            id=s["id"],
            title=s["title"],
            category=s["category"],
            similarity=s["similarity"]
        )
        for s in similar
    ]

    return SimilarRequirementsResponse(
        requirement_id=requirement_id,
        similar=items
    )


@router.post("/requirements/check-conflict", response_model=ConflictCheckResponse)
async def check_conflict(
    request: ConflictCheckRequest,
):
    """
    检查需求冲突

    在创建或更新需求前，检查是否与已有需求冲突或重复。
    返回关系类型和建议操作。
    """
    result = await comparator.compare(
        new_title=request.title,
        new_description=request.description,
        new_category=request.category,
        exclude_ids=request.exclude_ids
    )

    logger.info(
        "conflict_check",
        title=request.title,
        relation=result.relation.value,
        confidence=result.confidence
    )

    return ConflictCheckResponse(
        relation=result.relation.value,
        confidence=result.confidence,
        explanation=result.explanation,
        suggested_action=result.suggested_action,
        related_requirement_id=result.related_requirement_id,
        merge_suggestion=result.merge_suggestion
    )


@router.get("/meetings", response_model=MeetingListResponse)
async def list_meetings(
    source: Optional[str] = Query(None, description="来源筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db)
):
    """获取会议列表"""
    repo = MeetingRepository(session)

    skip = (page - 1) * page_size
    meetings, total = await repo.list_all(
        source=source,
        skip=skip,
        limit=page_size
    )

    return MeetingListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[MeetingOut.model_validate(m) for m in meetings]
    )


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    session: AsyncSession = Depends(get_db)
):
    """获取统计信息"""
    req_repo = RequirementRepository(session)
    meeting_repo = MeetingRepository(session)

    # 按状态统计需求
    status_counts = await req_repo.count_by_status()

    # 会议统计
    meetings, total_meetings = await meeting_repo.list_all(limit=1)
    unprocessed = await meeting_repo.list_unprocessed(limit=1000)

    # 向量库统计
    vector_stats = await vector_store.get_stats()

    return StatsResponse(
        requirements_by_status=status_counts,
        total_meetings=total_meetings,
        unprocessed_meetings=len(unprocessed),
        vector_store_count=vector_stats["total_documents"]
    )


@router.get("/stats/enhanced", response_model=EnhancedStatsResponse)
async def get_enhanced_stats(
    session: AsyncSession = Depends(get_db)
):
    """获取增强统计信息（含趋势）"""
    req_repo = RequirementRepository(session)
    meeting_repo = MeetingRepository(session)

    # 多维度统计
    status_counts = await req_repo.count_by_status()
    priority_counts = await req_repo.count_by_priority()
    category_counts = await req_repo.count_by_category()

    # 会议统计
    meetings, total_meetings = await meeting_repo.list_all(limit=1)
    unprocessed = await meeting_repo.list_unprocessed(limit=1000)

    # 向量库统计
    vector_stats = await vector_store.get_stats()

    # 趋势数据
    weekly_trend = await req_repo.get_daily_counts(days=7)
    today_count = await req_repo.count_today()

    return EnhancedStatsResponse(
        requirements_by_status=status_counts,
        requirements_by_priority=priority_counts,
        requirements_by_category=category_counts,
        total_meetings=total_meetings,
        unprocessed_meetings=len(unprocessed),
        vector_store_count=vector_stats["total_documents"],
        weekly_trend=[DailyTrendItem(**t) for t in weekly_trend],
        today_count=today_count
    )


@router.post("/requirements/{requirement_id}/analyze")
async def analyze_requirement(
    requirement_id: str,
    use_llm: bool = Query(False, description="使用LLM深度分析"),
    session: AsyncSession = Depends(get_db)
):
    """
    分析需求，提供智能建议

    返回:
    - 分类建议
    - 优先级建议
    - 复杂度估算
    - 依赖分析
    - 风险评估
    """
    repo = RequirementRepository(session)

    requirement = await repo.get_by_id(requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="需求不存在")

    if use_llm:
        result = await analyzer.analyze_with_llm(
            title=requirement.title,
            description=requirement.description or "",
            source_quote=requirement.source_quote
        )
    else:
        result = await analyzer.analyze(
            title=requirement.title,
            description=requirement.description or "",
            source_quote=requirement.source_quote
        )

    return {
        "requirement_id": requirement_id,
        "analysis": result.model_dump()
    }


@router.post("/requirements/analyze-text")
async def analyze_text(
    title: str = Query(..., description="需求标题"),
    description: str = Query("", description="需求描述"),
    use_llm: bool = Query(False, description="使用LLM深度分析")
):
    """
    分析文本，提供智能建议（无需先创建需求）
    """
    if use_llm:
        result = await analyzer.analyze_with_llm(
            title=title,
            description=description
        )
    else:
        result = await analyzer.analyze(
            title=title,
            description=description
        )

    return {
        "title": title,
        "analysis": result.model_dump()
    }


@router.get("/requirements/{requirement_id}/history")
async def get_requirement_history(
    requirement_id: str,
    session: AsyncSession = Depends(get_db)
):
    """
    获取需求变更历史

    返回需求的所有变更记录，包括:
    - 创建
    - 确认/拒绝
    - 更新
    - 状态变更
    """
    repo = RequirementRepository(session)

    requirement = await repo.get_by_id(requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="需求不存在")

    history = requirement.history or []

    return {
        "requirement_id": requirement_id,
        "title": requirement.title,
        "current_status": requirement.status,
        "history": history,
        "total_changes": len(history)
    }


@router.get("/requirements/{requirement_id}/diff")
async def get_requirement_diff(
    requirement_id: str,
    from_index: int = Query(0, description="起始变更索引"),
    to_index: int = Query(-1, description="结束变更索引 (-1 表示最新)"),
    session: AsyncSession = Depends(get_db)
):
    """
    获取需求变更 diff

    比较两个时间点的需求状态差异。
    """
    repo = RequirementRepository(session)

    requirement = await repo.get_by_id(requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="需求不存在")

    history = requirement.history or []

    if not history:
        return {
            "requirement_id": requirement_id,
            "message": "无变更历史",
            "diff": []
        }

    # 调整索引
    if to_index == -1 or to_index >= len(history):
        to_index = len(history) - 1

    if from_index >= len(history):
        from_index = 0

    # 获取范围内的变更
    changes = history[from_index:to_index + 1]

    return {
        "requirement_id": requirement_id,
        "from_index": from_index,
        "to_index": to_index,
        "changes": changes,
        "total_in_range": len(changes)
    }


@router.get("/requirements/{requirement_id}/context")
async def get_requirement_context(
    requirement_id: str,
    session: AsyncSession = Depends(get_db),
):
    """
    Get the context messages that led to this requirement.

    Returns the requirement along with its source messages and session info.
    """
    req_repo = RequirementRepository(session)
    msg_repo = MessageRepository(session)

    # Get requirement
    requirement = await req_repo.get_by_id(requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="Requirement not found")

    # Get context messages
    context_messages = []
    if requirement.context_message_ids:
        for msg_id in requirement.context_message_ids:
            msg = await msg_repo.get_by_id(msg_id)
            if msg:
                context_messages.append(_message_to_dict(msg))

    # Get session info if available
    session_info = None
    if context_messages:
        session_id = context_messages[0].get("session_id")
        if session_id:
            all_session_msgs = await msg_repo.get_by_session(session_id)
            session_info = {
                "session_id": session_id,
                "total_messages": len(all_session_msgs),
                "started_at": all_session_msgs[0].sent_at.isoformat() if all_session_msgs else None,
                "ended_at": all_session_msgs[-1].sent_at.isoformat() if all_session_msgs else None,
            }

    return {
        "requirement": _requirement_to_dict(requirement),
        "context_messages": context_messages,
        "session": session_info,
    }


def _message_to_dict(message) -> dict:
    """Convert ChatMessage to dict"""
    return {
        "id": message.id,
        "sender_name": message.sender_name,
        "content": message.content,
        "message_type": message.message_type,
        "sent_at": message.sent_at.isoformat() if message.sent_at else None,
        "session_id": message.session_id,
    }


def _requirement_to_dict(requirement) -> dict:
    """Convert Requirement to dict"""
    return {
        "id": requirement.id,
        "title": requirement.title,
        "description": requirement.description,
        "status": requirement.status,
        "priority": requirement.priority,
        "category": requirement.category,
        "source_quote": requirement.source_quote,
        "confirmed_by": requirement.confirmed_by,
        "confirmed_at": requirement.confirmed_at.isoformat() if requirement.confirmed_at else None,
        "created_at": requirement.created_at.isoformat() if requirement.created_at else None,
    }
