"""
Feedback API.

Handles requirement confirmation, rejection, and question answers by
delegating business logic to the agent.
"""
from fastapi import APIRouter, Depends

from shared.api import raise_question_not_found, raise_requirement_not_found
from shared.observability.privacy import hash_identifier
from shared.utils.logger import get_logger

from ..core.feedback_use_cases import RequirementFeedbackUseCase
from .dependencies import get_requirement_feedback_use_case
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
    feedback: RequirementFeedbackUseCase = Depends(get_requirement_feedback_use_case),
):
    """Confirm a requirement."""
    requirement = await feedback.confirm_requirement(
        requirement_id=requirement_id,
        confirmed_by=request.confirmed_by,
    )

    if not requirement:
        raise_requirement_not_found()

    return RequirementOut.model_validate(requirement)


@router.put("/requirements/{requirement_id}/reject", response_model=RequirementOut)
async def reject_requirement(
    requirement_id: str,
    request: RejectRequest,
    feedback: RequirementFeedbackUseCase = Depends(get_requirement_feedback_use_case),
):
    """Reject a requirement."""
    requirement = await feedback.reject_requirement(
        requirement_id=requirement_id,
        reason=request.reason,
        rejected_by=request.rejected_by,
    )

    if not requirement:
        raise_requirement_not_found()

    return RequirementOut.model_validate(requirement)


@router.post("/questions/{question_id}/answer", response_model=OpenQuestionOut)
async def answer_question(
    question_id: str,
    request: AnswerQuestionRequest,
    feedback: RequirementFeedbackUseCase = Depends(get_requirement_feedback_use_case),
):
    """Answer an open clarification question."""
    question = await feedback.answer_question(
        question_id,
        answer=request.answer,
        answered_by=request.answered_by,
    )
    if not question:
        raise_question_not_found()

    return OpenQuestionOut.model_validate(question)


@router.get("/questions/open", response_model=list[OpenQuestionOut])
async def list_open_questions(
    feedback: RequirementFeedbackUseCase = Depends(get_requirement_feedback_use_case),
):
    """List all unanswered questions."""
    questions = await feedback.list_open_questions()
    return [OpenQuestionOut.model_validate(q) for q in questions]


@router.post("/requirements/batch/confirm", response_model=BatchOperationResponse)
async def batch_confirm_requirements(
    request: BatchConfirmRequest,
    feedback: RequirementFeedbackUseCase = Depends(get_requirement_feedback_use_case),
):
    """
    Batch-confirm requirements.

    Confirms multiple requirements in one request for batch workflows.
    """
    result = await feedback.batch_confirm_requirements(
        requirement_ids=request.requirement_ids,
        confirmed_by=request.confirmed_by
    )

    logger.info(
        "batch_confirm_completed",
        total=len(request.requirement_ids),
        succeeded=result.succeeded,
        failed=result.failed,
        confirmed_by=request.confirmed_by
    )

    return BatchOperationResponse(
        total=result.total,
        succeeded=result.succeeded,
        failed=result.failed,
        results=[BatchOperationResult(**item) for item in result.results]
    )


@router.post("/requirements/batch/reject", response_model=BatchOperationResponse)
async def batch_reject_requirements(
    request: BatchRejectRequest,
    feedback: RequirementFeedbackUseCase = Depends(get_requirement_feedback_use_case),
):
    """
    Batch-reject requirements.

    Rejects multiple requirements with the same rejection reason.
    """
    result = await feedback.batch_reject_requirements(
        requirement_ids=request.requirement_ids,
        reason=request.reason,
        rejected_by=request.rejected_by
    )

    logger.info(
        "batch_reject_completed",
        total=len(request.requirement_ids),
        succeeded=result.succeeded,
        failed=result.failed,
        reason_length=len(request.reason or ""),
        rejected_by_hash=hash_identifier(request.rejected_by),
    )

    return BatchOperationResponse(
        total=result.total,
        succeeded=result.succeeded,
        failed=result.failed,
        results=[BatchOperationResult(**item) for item in result.results]
    )
