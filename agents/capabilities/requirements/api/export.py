"""
Export API.

Exports PRD documents and question lists.
"""
from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from shared.utils.logger import get_logger

from ..core.generator import generator
from ..db.database import get_db
from ..db.repository import QuestionRepository, RequirementRepository
from .schemas import PRDExportResponse, QuestionsExportResponse

router = APIRouter(prefix="/api/v1/export", tags=["export"])
logger = get_logger("api.export")


@router.get("/prd", response_model=PRDExportResponse)
async def export_prd(
    status: Optional[str] = Query(None, description="Status filter: confirmed/pending/all"),
    format: str = Query("json", description="Output format: json/markdown"),
    project_name: str = Query("Wisdoverse Cell", description="Project name"),
    version: str = Query("1.0", description="Document version"),
    session: AsyncSession = Depends(get_db)
):
    """
    Export a PRD document.

    Generates a product requirements document from existing requirements.
    Supports filtering by requirement status.
    """
    repo = RequirementRepository(session)

    # Fetch requirements.
    if status and status != "all":
        requirements, _ = await repo.list_all(status=status, limit=500)
    else:
        requirements, _ = await repo.list_all(limit=500)

    # Convert to dictionaries.
    req_dicts = [
        {
            "id": r.id,
            "title": r.title,
            "description": r.description,
            "category": r.category,
            "priority": r.priority,
            "status": r.status,
            "source_quote": r.source_quote,
            "confirmed_by": r.confirmed_by,
            "confirmed_at": r.confirmed_at.isoformat() if r.confirmed_at else None,
        }
        for r in requirements
    ]

    # Generate the PRD.
    result = await generator.generate_prd(
        requirements=req_dicts,
        project_name=project_name,
        version=version
    )

    logger.info(
        "prd_exported",
        requirements_count=result.requirements_count,
        format=format
    )

    # Return according to requested format.
    if format == "markdown":
        return PlainTextResponse(
            content=result.content,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f"attachment; filename=PRD_{version}_{datetime.now(UTC).strftime('%Y%m%d')}.md"
            }
        )

    return PRDExportResponse(
        content=result.content,
        format=result.format,
        generated_at=result.generated_at,
        requirements_count=result.requirements_count,
        version=result.version
    )


@router.get("/prd/download")
async def download_prd(
    status: Optional[str] = Query(None, description="Status filter"),
    project_name: str = Query("Wisdoverse Cell", description="Project name"),
    version: str = Query("1.0", description="Document version"),
    session: AsyncSession = Depends(get_db)
):
    """
    Download a PRD document as a Markdown file.
    """
    repo = RequirementRepository(session)

    if status and status != "all":
        requirements, _ = await repo.list_all(status=status, limit=500)
    else:
        requirements, _ = await repo.list_all(limit=500)

    req_dicts = [
        {
            "id": r.id,
            "title": r.title,
            "description": r.description,
            "category": r.category,
            "priority": r.priority,
            "status": r.status,
            "source_quote": r.source_quote,
        }
        for r in requirements
    ]

    result = await generator.generate_prd(
        requirements=req_dicts,
        project_name=project_name,
        version=version
    )

    filename = f"PRD_{project_name.replace(' ', '_')}_{version}_{datetime.now(UTC).strftime('%Y%m%d')}.md"

    return PlainTextResponse(
        content=result.content,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\""
        }
    )


@router.get("/questions", response_model=QuestionsExportResponse)
async def export_questions(
    status: Optional[str] = Query(None, description="Status filter: open/answered/all"),
    format: str = Query("json", description="Output format: json/markdown"),
    project_name: str = Query("Wisdoverse Cell", description="Project name"),
    session: AsyncSession = Depends(get_db)
):
    """
    Export a question list.

    Exports open clarification questions for the next discussion.
    """
    question_repo = QuestionRepository(session)
    requirement_repo = RequirementRepository(session)

    # Fetch questions.
    if status == "open":
        questions = await question_repo.list_open(limit=200)
    elif status == "answered":
        # list_answered is not implemented yet, so keep the current behavior.
        questions = []
    else:
        questions = await question_repo.list_open(limit=200)

    # Fetch related requirement titles.
    question_dicts = []
    for q in questions:
        req = await requirement_repo.get_by_id(q.requirement_id)
        question_dicts.append({
            "id": q.id,
            "question": q.question,
            "context": q.context,
            "status": q.status,
            "answer": q.answer,
            "answered_by": q.answered_by,
            "requirement_title": req.title if req else "Unknown requirement",
        })

    # Generate export content.
    result = generator.generate_questions_export(
        questions=question_dicts,
        project_name=project_name
    )

    logger.info(
        "questions_exported",
        questions_count=result.questions_count,
        format=format
    )

    if format == "markdown":
        return PlainTextResponse(
            content=result.content,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f"attachment; filename=Questions_{datetime.now(UTC).strftime('%Y%m%d')}.md"
            }
        )

    return QuestionsExportResponse(
        content=result.content,
        format=result.format,
        generated_at=result.generated_at,
        questions_count=result.questions_count
    )


@router.get("/questions/download")
async def download_questions(
    status: Optional[str] = Query("open", description="Status filter"),
    project_name: str = Query("Wisdoverse Cell", description="Project name"),
    session: AsyncSession = Depends(get_db)
):
    """
    Download a question list as a Markdown file.
    """
    question_repo = QuestionRepository(session)
    requirement_repo = RequirementRepository(session)

    if status == "open":
        questions = await question_repo.list_open(limit=200)
    else:
        questions = await question_repo.list_open(limit=200)

    question_dicts = []
    for q in questions:
        req = await requirement_repo.get_by_id(q.requirement_id)
        question_dicts.append({
            "id": q.id,
            "question": q.question,
            "context": q.context,
            "status": q.status,
            "answer": q.answer,
            "answered_by": q.answered_by,
            "requirement_title": req.title if req else "Unknown requirement",
        })

    result = generator.generate_questions_export(
        questions=question_dicts,
        project_name=project_name
    )

    filename = f"Questions_{project_name.replace(' ', '_')}_{datetime.now(UTC).strftime('%Y%m%d')}.md"

    return PlainTextResponse(
        content=result.content,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\""
        }
    )
