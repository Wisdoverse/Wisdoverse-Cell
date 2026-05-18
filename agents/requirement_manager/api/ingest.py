"""
Ingest API.

Handles meeting content ingestion by delegating processing to the agent.
"""

from fastapi import APIRouter, Depends

from shared.utils.logger import get_logger

from ..core.ingest_use_cases import IngestUseCase
from .dependencies import get_ingest_use_case
from .schemas import (
    FeishuWebhookRequest,
    IngestResponse,
    UploadRequest,
)

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])
logger = get_logger("api.ingest")


@router.post("/upload", response_model=IngestResponse)
async def upload_content(
    request: UploadRequest,
    ingest: IngestUseCase = Depends(get_ingest_use_case),
):
    """
    Manually upload meeting content.

    Supports WeChat chat logs, manually curated meeting notes, and similar
    source material.
    """
    result = await ingest.upload_content(
        content=request.content,
        source=request.source,
        title=request.title,
        meeting_date=request.meeting_date,
        participants=request.participants,
        context=request.context,
    )

    logger.info(
        "meeting_uploaded",
        meeting_id=result.meeting_id,
        source=request.source,
        requirements_count=result.requirements_extracted
    )

    return IngestResponse(
        meeting_id=result.meeting_id,
        requirements_extracted=result.requirements_extracted,
        questions_generated=result.questions_generated
    )


@router.post("/feishu", response_model=IngestResponse)
async def feishu_webhook(
    request: FeishuWebhookRequest,
    ingest: IngestUseCase = Depends(get_ingest_use_case),
):
    """
    Feishu webhook callback.

    Receives Feishu meeting summary webhook events.
    """
    result = await ingest.ingest_feishu(
        summary=request.summary,
        meeting_id=request.meeting_id,
        topic=request.topic,
        participants=request.participants,
        meeting_time=request.meeting_time,
    )

    if result.deduplicated:
        logger.info("meeting_already_exists", meeting_id=request.meeting_id)
        return IngestResponse(
            meeting_id=result.meeting_id,
            requirements_extracted=result.requirements_extracted,
            questions_generated=result.questions_generated,
        )

    logger.info(
        "feishu_meeting_received",
        meeting_id=result.meeting_id,
        feishu_meeting_id=request.meeting_id,
        requirements_count=result.requirements_extracted
    )

    return IngestResponse(
        meeting_id=result.meeting_id,
        requirements_extracted=result.requirements_extracted,
        questions_generated=result.questions_generated
    )
