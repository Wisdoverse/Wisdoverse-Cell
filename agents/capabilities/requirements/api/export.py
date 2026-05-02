"""
Export API - 导出接口

提供 PRD 文档和问题清单的导出功能。
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
    status: Optional[str] = Query(None, description="状态筛选: confirmed/pending/all"),
    format: str = Query("json", description="输出格式: json/markdown"),
    project_name: str = Query("Wisdoverse Cell", description="项目名称"),
    version: str = Query("1.0", description="文档版本"),
    session: AsyncSession = Depends(get_db)
):
    """
    导出 PRD 文档

    从已有需求生成产品需求文档。支持按状态筛选。
    """
    repo = RequirementRepository(session)

    # 获取需求
    if status and status != "all":
        requirements, _ = await repo.list_all(status=status, limit=500)
    else:
        requirements, _ = await repo.list_all(limit=500)

    # 转换为字典列表
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

    # 生成 PRD
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

    # 根据格式返回
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
    status: Optional[str] = Query(None, description="状态筛选"),
    project_name: str = Query("Wisdoverse Cell", description="项目名称"),
    version: str = Query("1.0", description="文档版本"),
    session: AsyncSession = Depends(get_db)
):
    """
    下载 PRD 文档 (Markdown 文件)
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
    status: Optional[str] = Query(None, description="状态筛选: open/answered/all"),
    format: str = Query("json", description="输出格式: json/markdown"),
    project_name: str = Query("Wisdoverse Cell", description="项目名称"),
    session: AsyncSession = Depends(get_db)
):
    """
    导出问题清单

    导出待确认问题，用于下次会议讨论。
    """
    question_repo = QuestionRepository(session)
    requirement_repo = RequirementRepository(session)

    # 获取问题
    if status == "open":
        questions = await question_repo.list_open(limit=200)
    elif status == "answered":
        # 需要实现 list_answered 方法，这里简化处理
        questions = []
    else:
        questions = await question_repo.list_open(limit=200)

    # 获取关联的需求标题
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
            "requirement_title": req.title if req else "未知需求",
        })

    # 生成导出
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
    status: Optional[str] = Query("open", description="状态筛选"),
    project_name: str = Query("Wisdoverse Cell", description="项目名称"),
    session: AsyncSession = Depends(get_db)
):
    """
    下载问题清单 (Markdown 文件)
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
            "requirement_title": req.title if req else "未知需求",
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
