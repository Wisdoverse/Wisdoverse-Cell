"""
Requirements API.
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
    status: Optional[str] = Query(None, description="Status filter: pending/confirmed/changed/rejected"),
    category: Optional[str] = Query(None, description="Category filter"),
    priority: Optional[str] = Query(None, description="Priority filter: high/medium/low"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    session: AsyncSession = Depends(get_db)
):
    """List requirements."""
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
    """Get requirement details."""
    repo = RequirementRepository(session)

    requirement = await repo.get_by_id(requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="Requirement not found")

    return RequirementOut.model_validate(requirement)


@router.put("/requirements/{requirement_id}", response_model=RequirementOut)
async def update_requirement(
    requirement_id: str,
    request: RequirementUpdateRequest,
    session: AsyncSession = Depends(get_db)
):
    """Update requirement information."""
    from ..service.feedback_learning import FeedbackLearningService

    repo = RequirementRepository(session)

    # Check that the requirement exists.
    requirement = await repo.get_by_id(requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="Requirement not found")

    # Build update fields.
    update_data = request.model_dump(exclude_unset=True, exclude_none=True)
    if "comment" in update_data:
        del update_data["comment"]  # comment is history metadata, not a field update

    if update_data:
        # Capture original values for feedback learning.
        original_values = {
            "title": requirement.title,
            "description": requirement.description,
            "priority": requirement.priority,
            "category": requirement.category,
        }

        # Record change history.
        requirement.add_history(
            action="updated",
            detail=f"Updated fields: {list(update_data.keys())}",
            by=request.comment or "system"
        )

        # Update fields.
        requirement = await repo.update(requirement_id, **update_data)

        # Record feedback for learning when key fields changed.
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
                pass  # feedback recording must not block the main flow

    return RequirementOut.model_validate(requirement)


@router.delete("/requirements/{requirement_id}", response_model=DeleteRequirementResponse)
async def delete_requirement(
    requirement_id: str,
    request: DeleteRequirementRequest,
    session: AsyncSession = Depends(get_db)
):
    """
    Delete a requirement.

    Deletes related questions and vector-store records as well. Emits a
    requirement.deleted event after deletion.
    """
    repo = RequirementRepository(session)

    # Delete the requirement, including vector-store synchronization.
    requirement = await repo.delete(requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="Requirement not found")

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
    q: str = Query(..., min_length=1, description="Search keyword"),
    category: Optional[str] = Query(None, description="Category filter"),
    limit: int = Query(20, ge=1, le=100, description="Result limit"),
    min_similarity: float = Query(0.5, ge=0, le=1, description="Minimum similarity threshold"),
):
    """
    Semantically search requirements.

    Uses the vector database for semantic matching and returns the most
    relevant requirements for the query.
    """
    # Search the vector store.
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
    limit: int = Query(5, ge=1, le=20, description="Result limit"),
    min_similarity: float = Query(0.7, ge=0, le=1, description="Minimum similarity"),
    session: AsyncSession = Depends(get_db)
):
    """
    Find similar requirements.

    Finds other semantically similar requirements for the selected requirement.
    Useful for duplicate or related requirement discovery.
    """
    repo = RequirementRepository(session)

    # Verify that the requirement exists.
    requirement = await repo.get_by_id(requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="Requirement not found")

    # Find similar requirements.
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
    Check requirement conflicts.

    Checks whether a new or updated requirement conflicts with, duplicates, or
    updates existing requirements. Returns the relation and suggested action.
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
    source: Optional[str] = Query(None, description="Source filter"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db)
):
    """List meetings."""
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
    """Get statistics."""
    req_repo = RequirementRepository(session)
    meeting_repo = MeetingRepository(session)

    # Count requirements by status.
    status_counts = await req_repo.count_by_status()

    # Meeting statistics.
    meetings, total_meetings = await meeting_repo.list_all(limit=1)
    unprocessed = await meeting_repo.list_unprocessed(limit=1000)

    # Vector-store statistics.
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
    """Get enhanced statistics with trends."""
    req_repo = RequirementRepository(session)
    meeting_repo = MeetingRepository(session)

    # Multi-dimensional statistics.
    status_counts = await req_repo.count_by_status()
    priority_counts = await req_repo.count_by_priority()
    category_counts = await req_repo.count_by_category()

    # Meeting statistics.
    meetings, total_meetings = await meeting_repo.list_all(limit=1)
    unprocessed = await meeting_repo.list_unprocessed(limit=1000)

    # Vector-store statistics.
    vector_stats = await vector_store.get_stats()

    # Trend data.
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
    use_llm: bool = Query(False, description="Use LLM for deeper analysis"),
    session: AsyncSession = Depends(get_db)
):
    """
    Analyze a requirement and provide intelligent suggestions.

    Returns:
    - Category suggestion.
    - Priority suggestion.
    - Complexity estimate.
    - Dependency analysis.
    - Risk assessment.
    """
    repo = RequirementRepository(session)

    requirement = await repo.get_by_id(requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="Requirement not found")

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
    title: str = Query(..., description="Requirement title"),
    description: str = Query("", description="Requirement description"),
    use_llm: bool = Query(False, description="Use LLM for deeper analysis")
):
    """
    Analyze text and provide intelligent suggestions without creating a requirement.
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
    Get requirement change history.

    Returns all change records for the requirement, including:
    - Creation.
    - Confirmation or rejection.
    - Updates.
    - Status changes.
    """
    repo = RequirementRepository(session)

    requirement = await repo.get_by_id(requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="Requirement not found")

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
    from_index: int = Query(0, description="Start change index"),
    to_index: int = Query(-1, description="End change index (-1 means latest)"),
    session: AsyncSession = Depends(get_db)
):
    """
    Get a requirement change diff.

    Compares requirement state changes across two points in its history.
    """
    repo = RequirementRepository(session)

    requirement = await repo.get_by_id(requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="Requirement not found")

    history = requirement.history or []

    if not history:
        return {
            "requirement_id": requirement_id,
            "message": "No change history",
            "diff": []
        }

    # Normalize indexes.
    if to_index == -1 or to_index >= len(history):
        to_index = len(history) - 1

    if from_index >= len(history):
        from_index = 0

    # Fetch changes in range.
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
