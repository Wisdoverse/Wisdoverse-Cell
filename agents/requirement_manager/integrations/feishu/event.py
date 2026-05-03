"""
EventHandler - 处理飞书事件订阅

支持的事件：
- vc.meeting.meeting_ended_v1    会议结束
- calendar.calendar.event_changed_v4  日历变更
"""
import re
from datetime import datetime
from typing import Callable

from shared.integrations.feishu.cards.requirement import (
    build_calendar_reminder_card,
    build_requirement_extracted_card,
)
from shared.observability.privacy import hash_identifier
from shared.utils.logger import get_logger

logger = get_logger("feishu.handlers.event")

# 日历事件关键词过滤
CALENDAR_KEYWORDS = ["需求", "产品", "review", "PRD", "评审", "规划", "迭代"]


class EventHandler:
    """
    事件订阅处理器

    处理飞书主动推送的事件。
    """

    def __init__(self, feishu_client, agent):
        self.client = feishu_client
        self.agent = agent

        self._handlers: dict[str, Callable] = {
            "vc.meeting.meeting_ended_v1": self._handle_meeting_ended,
            "calendar.calendar.event_changed_v4": self._handle_calendar_changed,
        }

        # 编译关键词正则
        self._keyword_pattern = re.compile(
            "|".join(CALENDAR_KEYWORDS),
            re.IGNORECASE
        )

    async def dispatch(self, event_type: str, data: dict) -> dict:
        """
        分发事件到对应处理器

        Args:
            event_type: 事件类型
            data: 完整事件数据

        Returns:
            响应数据
        """
        handler = self._handlers.get(event_type)

        if not handler:
            logger.warning("unhandled_feishu_event", event_type=event_type)
            return {"code": 0}

        try:
            return await handler(data)
        except Exception as e:
            logger.error(
                "feishu_event_handler_error",
                event_type=event_type,
                error=str(e)
            )
            return {"code": 0}  # Return success to avoid retry

    async def _handle_meeting_ended(self, data: dict) -> dict:
        """
        处理会议结束事件

        流程：
        1. 提取会议信息
        2. 调用 Agent 提取需求
        3. 发送卡片通知到会议群
        """
        event = data.get("event", {})
        meeting = event.get("meeting", {})

        meeting_id = meeting.get("meeting_id", "")
        topic = meeting.get("topic", "")
        chat_id = meeting.get("chat_id", "")
        summary = meeting.get("summary", "")

        logger.info(
            "meeting_ended_event",
            meeting_id=meeting_id,
            topic=topic,
            has_summary=bool(summary)
        )

        # Skip if no summary
        if not summary:
            logger.info("meeting_no_summary", meeting_id=meeting_id)
            return {"code": 0}

        # Call agent to extract requirements
        result = await self.agent.ingest_meeting(
            content=summary,
            source="feishu_meeting",
            title=topic,
            source_id=meeting_id,
        )

        logger.info(
            "meeting_extraction_complete",
            meeting_id=meeting_id,
            requirements=result.requirements_extracted,
            questions=result.questions_generated
        )

        # Send notification card to meeting chat
        if result.requirements_extracted > 0 and chat_id:
            try:
                card = build_requirement_extracted_card(
                    requirements=result.requirements if hasattr(result, 'requirements') else [],
                    meeting_title=topic,
                    questions_count=result.questions_generated
                )
                await self.client.send_card(
                    receive_id=chat_id,
                    receive_id_type="chat_id",
                    card=card
                )
                logger.info("meeting_card_sent", chat_hash=hash_identifier(chat_id))
            except Exception as e:
                logger.error("meeting_card_send_error", error=str(e))

        return {"code": 0}

    async def _handle_calendar_changed(self, data: dict) -> dict:
        """
        处理日历变更事件

        流程：
        1. 过滤事件类型（只处理 create/update）
        2. 检查标题是否包含需求相关关键词
        3. 如果匹配，发送提醒卡片给组织者
        """
        event = data.get("event", {})
        calendar_event = event.get("event", {})

        event_id = calendar_event.get("event_id", "")
        summary = calendar_event.get("summary", "")  # 会议标题
        organizer = calendar_event.get("organizer", {})
        organizer_id = organizer.get("user_id", "")
        start_time = calendar_event.get("start_time", {})
        attendees = calendar_event.get("attendees", [])

        # 变更类型
        change_type = event.get("type", "")

        logger.info(
            "calendar_event_received",
            event_id=event_id,
            summary=summary,
            change_type=change_type,
            has_organizer=bool(organizer_id)
        )

        # 只处理创建和更新事件
        if change_type not in ("created", "updated"):
            logger.debug("calendar_event_skipped_type", change_type=change_type)
            return {"code": 0}

        # 检查标题是否包含关键词
        matched_keywords = self._keyword_pattern.findall(summary)
        if not matched_keywords:
            logger.debug(
                "calendar_event_no_keyword_match",
                event_id=event_id,
                summary=summary
            )
            return {"code": 0}

        logger.info(
            "calendar_event_keyword_matched",
            event_id=event_id,
            summary=summary,
            keywords=matched_keywords
        )

        # 解析开始时间
        start_timestamp = start_time.get("timestamp", "")
        if start_timestamp:
            try:
                dt = datetime.fromtimestamp(int(start_timestamp))
                start_time_str = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                start_time_str = "未知时间"
        else:
            start_time_str = start_time.get("date", "未知时间")

        # 获取参与者名称
        attendee_names = []
        for att in attendees[:10]:  # 最多取10人
            if att.get("display_name"):
                attendee_names.append(att["display_name"])

        # 发送提醒卡片给组织者
        if organizer_id:
            try:
                card = build_calendar_reminder_card(
                    event_title=summary,
                    start_time=start_time_str,
                    organizer=organizer.get("display_name", ""),
                    attendees=attendee_names,
                    keywords_found=list(set(matched_keywords))
                )
                await self.client.send_card(
                    receive_id=organizer_id,
                    receive_id_type="user_id",
                    card=card
                )
                logger.info(
                    "calendar_reminder_sent",
                    event_id=event_id,
                    organizer_id=organizer_id
                )
            except Exception as e:
                logger.error(
                    "calendar_reminder_send_error",
                    event_id=event_id,
                    error=str(e)
                )

        return {"code": 0}
