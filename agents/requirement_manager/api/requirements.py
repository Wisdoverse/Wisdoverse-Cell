"""
Requirements API.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from shared.api import raise_requirement_not_found

from ..core.conflict_check import RequirementConflictCheckUseCase
from ..core.requirement_analysis import RequirementAnalysisUseCase
from ..core.requirement_context_queries import RequirementContextQueryService
from ..core.requirement_mutations import RequirementMutationUseCase
from ..core.requirement_queries import RequirementQueryService
from .dependencies import (
    get_requirement_analysis_use_case,
    get_requirement_conflict_check_use_case,
    get_requirement_context_query_service,
    get_requirement_mutation_use_case,
    get_requirement_query_service,
)
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


@router.get("/requirements", response_model=RequirementListResponse)
async def list_requirements(
    status: Optional[str] = Query(None, description="Status filter: pending/confirmed/changed/rejected"),
    category: Optional[str] = Query(None, description="Category filter"),
    priority: Optional[str] = Query(None, description="Priority filter: high/medium/low"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    queries: RequirementQueryService = Depends(get_requirement_query_service),
):
    """List requirements."""
    result = await queries.list_requirements(
        status=status,
        category=category,
        priority=priority,
        page=page,
        page_size=page_size,
    )

    return RequirementListResponse(
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        items=[RequirementOut.model_validate(requirement) for requirement in result.items],
    )


@router.get("/requirements/search", response_model=SemanticSearchResponse)
async def search_requirements(
    q: str = Query(..., min_length=1, description="Search keyword"),
    category: Optional[str] = Query(None, description="Category filter"),
    limit: int = Query(20, ge=1, le=100, description="Result limit"),
    min_similarity: float = Query(0.5, ge=0, le=1, description="Minimum similarity threshold"),
    queries: RequirementQueryService = Depends(get_requirement_query_service),
):
    """
    Semantically search requirements.

    Uses the vector database for semantic matching and returns the most
    relevant requirements for the query.
    """
    result = await queries.search_requirements(
        query=q,
        category=category,
        limit=limit,
        min_similarity=min_similarity,
    )

    items = [
        SearchResultItem(
            id=item.id,
            title=item.title,
            category=item.category,
            similarity=item.similarity,
        )
        for item in result.items
    ]

    return SemanticSearchResponse(
        query=result.query,
        total=len(items),
        items=items
    )


@router.get("/requirements/{requirement_id}", response_model=RequirementOut)
async def get_requirement(
    requirement_id: str,
    queries: RequirementQueryService = Depends(get_requirement_query_service),
):
    """Get requirement details."""
    requirement = await queries.get_requirement(requirement_id)
    if not requirement:
        raise_requirement_not_found()

    return RequirementOut.model_validate(requirement)


@router.put("/requirements/{requirement_id}", response_model=RequirementOut)
async def update_requirement(
    requirement_id: str,
    request: RequirementUpdateRequest,
    mutations: RequirementMutationUseCase = Depends(get_requirement_mutation_use_case),
):
    """Update requirement information."""
    requirement = await mutations.update_requirement(
        requirement_id=requirement_id,
        changes=request.model_dump(exclude_unset=True, exclude_none=True),
    )
    if not requirement:
        raise_requirement_not_found()

    return RequirementOut.model_validate(requirement)


@router.delete("/requirements/{requirement_id}", response_model=DeleteRequirementResponse)
async def delete_requirement(
    requirement_id: str,
    request: DeleteRequirementRequest,
    mutations: RequirementMutationUseCase = Depends(get_requirement_mutation_use_case),
):
    """
    Delete a requirement.

    Deletes related questions and vector-store records as well. Emits a
    requirement.deleted event after deletion.
    """
    requirement = await mutations.delete_requirement(
        requirement_id=requirement_id,
        deleted_by=request.deleted_by,
    )
    if not requirement:
        raise_requirement_not_found()

    return DeleteRequirementResponse(
        requirement_id=requirement_id,
        title=requirement.title
    )


@router.get("/requirements/{requirement_id}/similar", response_model=SimilarRequirementsResponse)
async def find_similar_requirements(
    requirement_id: str,
    limit: int = Query(5, ge=1, le=20, description="Result limit"),
    min_similarity: float = Query(0.7, ge=0, le=1, description="Minimum similarity"),
    queries: RequirementQueryService = Depends(get_requirement_query_service),
):
    """
    Find similar requirements.

    Finds other semantically similar requirements for the selected requirement.
    Useful for duplicate or related requirement discovery.
    """
    result = await queries.find_similar_requirements(
        requirement_id,
        limit=limit,
        min_similarity=min_similarity,
    )
    if result is None:
        raise_requirement_not_found()

    similar = [
        SimilarRequirementItem(
            id=item.id,
            title=item.title,
            category=item.category,
            similarity=item.similarity,
        )
        for item in result.similar
    ]

    return SimilarRequirementsResponse(
        requirement_id=result.requirement_id,
        similar=similar,
    )


@router.post("/requirements/check-conflict", response_model=ConflictCheckResponse)
async def check_conflict(
    request: ConflictCheckRequest,
    conflict_checks: RequirementConflictCheckUseCase = Depends(
        get_requirement_conflict_check_use_case
    ),
):
    """
    Check requirement conflicts.

    Checks whether a new or updated requirement conflicts with, duplicates, or
    updates existing requirements. Returns the relation and suggested action.
    """
    result = await conflict_checks.check_conflict(
        title=request.title,
        description=request.description,
        category=request.category,
        exclude_ids=request.exclude_ids,
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
    queries: RequirementQueryService = Depends(get_requirement_query_service),
):
    """List meetings."""
    result = await queries.list_meetings(
        source=source,
        page=page,
        page_size=page_size,
    )

    return MeetingListResponse(
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        items=[MeetingOut.model_validate(meeting) for meeting in result.items],
    )


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    queries: RequirementQueryService = Depends(get_requirement_query_service),
):
    """Get statistics."""
    result = await queries.get_stats()
    return StatsResponse(
        requirements_by_status=result.requirements_by_status,
        total_meetings=result.total_meetings,
        unprocessed_meetings=result.unprocessed_meetings,
        vector_store_count=result.vector_store_count,
    )


@router.get("/stats/enhanced", response_model=EnhancedStatsResponse)
async def get_enhanced_stats(
    queries: RequirementQueryService = Depends(get_requirement_query_service),
):
    """Get enhanced statistics with trends."""
    result = await queries.get_enhanced_stats()
    return EnhancedStatsResponse(
        requirements_by_status=result.requirements_by_status,
        requirements_by_priority=result.requirements_by_priority,
        requirements_by_category=result.requirements_by_category,
        total_meetings=result.total_meetings,
        unprocessed_meetings=result.unprocessed_meetings,
        vector_store_count=result.vector_store_count,
        weekly_trend=[DailyTrendItem(**item) for item in result.weekly_trend],
        today_count=result.today_count,
    )


@router.post("/requirements/{requirement_id}/analyze")
async def analyze_requirement(
    requirement_id: str,
    use_llm: bool = Query(False, description="Use LLM for deeper analysis"),
    analysis: RequirementAnalysisUseCase = Depends(get_requirement_analysis_use_case),
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
    result = await analysis.analyze_requirement(requirement_id, use_llm=use_llm)
    if result is None:
        raise_requirement_not_found()

    return {
        "requirement_id": requirement_id,
        "analysis": result.model_dump(),
    }


@router.post("/requirements/analyze-text")
async def analyze_text(
    title: str = Query(..., description="Requirement title"),
    description: str = Query("", description="Requirement description"),
    use_llm: bool = Query(False, description="Use LLM for deeper analysis"),
    analysis: RequirementAnalysisUseCase = Depends(get_requirement_analysis_use_case),
):
    """
    Analyze text and provide intelligent suggestions without creating a requirement.
    """
    result = await analysis.analyze_text(
        title=title,
        description=description,
        use_llm=use_llm,
    )

    return {
        "title": title,
        "analysis": result.model_dump(),
    }


@router.get("/requirements/{requirement_id}/history")
async def get_requirement_history(
    requirement_id: str,
    queries: RequirementQueryService = Depends(get_requirement_query_service),
):
    """
    Get requirement change history.

    Returns all change records for the requirement, including:
    - Creation.
    - Confirmation or rejection.
    - Updates.
    - Status changes.
    """
    result = await queries.get_requirement_history(requirement_id)
    if result is None:
        raise_requirement_not_found()

    return {
        "requirement_id": result.requirement_id,
        "title": result.title,
        "current_status": result.current_status,
        "history": result.history,
        "total_changes": result.total_changes,
    }


@router.get("/requirements/{requirement_id}/diff")
async def get_requirement_diff(
    requirement_id: str,
    from_index: int = Query(0, description="Start change index"),
    to_index: int = Query(-1, description="End change index (-1 means latest)"),
    queries: RequirementQueryService = Depends(get_requirement_query_service),
):
    """
    Get a requirement change diff.

    Compares requirement state changes across two points in its history.
    """
    result = await queries.get_requirement_diff(
        requirement_id,
        from_index=from_index,
        to_index=to_index,
    )
    if result is None:
        raise_requirement_not_found()

    if result.message is not None:
        return {
            "requirement_id": result.requirement_id,
            "message": result.message,
            "diff": result.diff,
        }

    return {
        "requirement_id": result.requirement_id,
        "from_index": result.from_index,
        "to_index": result.to_index,
        "changes": result.changes,
        "total_in_range": result.total_in_range,
    }


@router.get("/requirements/{requirement_id}/context")
async def get_requirement_context(
    requirement_id: str,
    queries: RequirementContextQueryService = Depends(
        get_requirement_context_query_service
    ),
):
    """
    Get the context messages that led to this requirement.

    Returns the requirement along with its source messages and session info.
    """
    result = await queries.get_context(requirement_id)
    if result is None:
        raise_requirement_not_found()

    return {
        "requirement": _requirement_to_dict(result.requirement),
        "context_messages": [
            _message_to_dict(message) for message in result.context_messages
        ],
        "session": _session_to_dict(result.session) if result.session else None,
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


def _session_to_dict(session) -> dict:
    """Convert context session metadata to dict."""
    return {
        "session_id": session.session_id,
        "total_messages": session.total_messages,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
    }
