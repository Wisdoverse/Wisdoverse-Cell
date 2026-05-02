"""
Ingest API - 导入接口

处理会议内容的导入，委托给 Agent 处理。
"""
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from shared.utils.logger import get_logger

from ..db.database import get_db
from ..db.repository import MeetingRepository
from ..service import get_agent
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
    session: AsyncSession = Depends(get_db)
):
    """
    手动上传会议内容

    用于上传微信聊天记录、手工整理的会议纪要等。
    """
    # 解析会议日期
    meeting_date = None
    if request.meeting_date:
        try:
            meeting_date = datetime.fromisoformat(request.meeting_date.replace("Z", "+00:00"))
        except ValueError:
            pass

    # 委托给 Agent 处理
    result = await get_agent().ingest_meeting(
        content=request.content,
        source=request.source,
        session=session,
        title=request.title,
        meeting_date=meeting_date,
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
    session: AsyncSession = Depends(get_db)
):
    """
    飞书Webhook回调

    接收飞书会议纪要的Webhook推送。
    """
    meeting_repo = MeetingRepository(session)

    # 检查是否已处理过（去重）
    if request.meeting_id:
        existing = await meeting_repo.get_by_source_id("feishu", request.meeting_id)
        if existing:
            logger.info("meeting_already_exists", meeting_id=request.meeting_id)
            return IngestResponse(
                meeting_id=existing.id,
                requirements_extracted=0,
                questions_generated=0
            )

    # 解析会议时间
    meeting_date = None
    if request.meeting_time:
        try:
            meeting_date = datetime.fromisoformat(request.meeting_time.replace("Z", "+00:00"))
        except ValueError:
            pass

    # 委托给 Agent 处理
    result = await get_agent().ingest_meeting(
        content=request.summary,
        source="feishu",
        session=session,
        title=request.topic,
        meeting_date=meeting_date,
        participants=request.participants,
        source_id=request.meeting_id,
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
