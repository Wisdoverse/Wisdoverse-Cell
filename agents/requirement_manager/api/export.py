"""
Export API.

Exports PRD documents and question lists.
"""
from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse

from shared.utils.logger import get_logger

from ..core.export_use_cases import ExportUseCase
from .dependencies import get_export_use_case
from .schemas import PRDExportResponse, QuestionsExportResponse

router = APIRouter(prefix="/api/v1/export", tags=["export"])
logger = get_logger("api.export")


@router.get("/prd", response_model=PRDExportResponse)
async def export_prd(
    status: Optional[str] = Query(None, description="Status filter: confirmed/pending/all"),
    format: str = Query("json", description="Output format: json/markdown"),
    project_name: str = Query("Wisdoverse Cell", description="Project name"),
    version: str = Query("1.0", description="Document version"),
    exports: ExportUseCase = Depends(get_export_use_case),
):
    """
    Export a PRD document.

    Generates a product requirements document from existing requirements.
    Supports filtering by requirement status.
    """
    result = await exports.export_prd(
        status=status,
        project_name=project_name,
        version=version,
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
    exports: ExportUseCase = Depends(get_export_use_case),
):
    """
    Download a PRD document as a Markdown file.
    """
    result = await exports.export_prd(
        status=status,
        project_name=project_name,
        version=version,
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
    exports: ExportUseCase = Depends(get_export_use_case),
):
    """
    Export a question list.

    Exports open clarification questions for the next discussion.
    """
    result = await exports.export_questions(
        status=status,
        project_name=project_name,
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
    exports: ExportUseCase = Depends(get_export_use_case),
):
    """
    Download a question list as a Markdown file.
    """
    result = await exports.export_questions(
        status=status,
        project_name=project_name,
    )

    filename = f"Questions_{project_name.replace(' ', '_')}_{datetime.now(UTC).strftime('%Y%m%d')}.md"

    return PlainTextResponse(
        content=result.content,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\""
        }
    )
