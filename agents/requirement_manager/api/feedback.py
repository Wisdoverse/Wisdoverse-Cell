"""
Feedback API - 反馈接口

处理需求确认、拒绝、问题回答等操作，委托给 Agent 处理。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from shared.utils.logger import get_logger

from ..db.database import get_db
from ..db.repository import QuestionRepository
from ..service import get_agent
from .schemas import (
    AnswerQuestionRequest,
    BatchConfirmRequest,
    BatchOperationResponse,
    BatchOperationResult,
    BatchRejectRequest,
    ConfirmRequest,
    OpenQuestionOut,
    RejectRequest,
    RequirementOut,
)

router = APIRouter(prefix="/api/v1", tags=["feedback"])
logger = get_logger("api.feedback")


@router.put("/requirements/{requirement_id}/confirm", response_model=RequirementOut)
async def confirm_requirement(
    requirement_id: str,
    request: ConfirmRequest,
    session: AsyncSession = Depends(get_db)
):
    """确认需求"""
    requirement = await get_agent().confirm_requirement(
        requirement_id=requirement_id,
        confirmed_by=request.confirmed_by,
        session=session
    )

    if not requirement:
        raise HTTPException(status_code=404, detail="需求不存在")

    return RequirementOut.model_validate(requirement)


@router.put("/requirements/{requirement_id}/reject", response_model=RequirementOut)
async def reject_requirement(
    requirement_id: str,
    request: RejectRequest,
    session: AsyncSession = Depends(get_db)
):
    """拒绝需求"""
    requirement = await get_agent().reject_requirement(
        requirement_id=requirement_id,
        reason=request.reason,
        rejected_by=request.rejected_by,
        session=session
    )

    if not requirement:
        raise HTTPException(status_code=404, detail="需求不存在")

    return RequirementOut.model_validate(requirement)


@router.post("/questions/{question_id}/answer", response_model=OpenQuestionOut)
async def answer_question(
    question_id: str,
    request: AnswerQuestionRequest,
    session: AsyncSession = Depends(get_db)
):
    """回答待确认问题"""
    repo = QuestionRepository(session)

    question = await repo.answer(
        question_id,
        answer=request.answer,
        answered_by=request.answered_by
    )
    if not question:
        raise HTTPException(status_code=404, detail="问题不存在")

    logger.info(
        "question_answered",
        question_id=question_id,
        answered_by=request.answered_by
    )

    return OpenQuestionOut.model_validate(question)


@router.get("/questions/open", response_model=list[OpenQuestionOut])
async def list_open_questions(
    session: AsyncSession = Depends(get_db)
):
    """获取所有未回答的问题"""
    repo = QuestionRepository(session)

    questions = await repo.list_open()
    return [OpenQuestionOut.model_validate(q) for q in questions]


@router.post("/requirements/batch/confirm", response_model=BatchOperationResponse)
async def batch_confirm_requirements(
    request: BatchConfirmRequest,
):
    """
    批量确认需求

    一次确认多个需求，适用于批量处理场景。
    """
    results = await get_agent().batch_confirm_requirements(
        requirement_ids=request.requirement_ids,
        confirmed_by=request.confirmed_by
    )

    succeeded = sum(1 for r in results if r["success"])
    failed = len(results) - succeeded

    logger.info(
        "batch_confirm_completed",
        total=len(request.requirement_ids),
        succeeded=succeeded,
        failed=failed,
        confirmed_by=request.confirmed_by
    )

    return BatchOperationResponse(
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        results=[BatchOperationResult(**r) for r in results]
    )


@router.post("/requirements/batch/reject", response_model=BatchOperationResponse)
async def batch_reject_requirements(
    request: BatchRejectRequest,
):
    """
    批量拒绝需求

    一次拒绝多个需求，使用相同的拒绝原因。
    """
    results = await get_agent().batch_reject_requirements(
        requirement_ids=request.requirement_ids,
        reason=request.reason,
        rejected_by=request.rejected_by
    )

    succeeded = sum(1 for r in results if r["success"])
    failed = len(results) - succeeded

    logger.info(
        "batch_reject_completed",
        total=len(request.requirement_ids),
        succeeded=succeeded,
        failed=failed,
        reason=request.reason,
        rejected_by=request.rejected_by
    )

    return BatchOperationResponse(
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        results=[BatchOperationResult(**r) for r in results]
    )
