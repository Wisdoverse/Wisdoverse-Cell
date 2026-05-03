"""
RequirementManagerAgent - 需求管理 Agent 核心

继承 BaseAgent，实现标准 Agent 接口。
所有业务逻辑通过此类协调，FastAPI 只是 HTTP 适配器。
"""
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import settings as app_settings
from shared.infra.event_bus import EventBus, event_bus
from shared.infra.notification import NotificationChannel, notification_service
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..core.extractor import extractor
from ..db.database import DatabaseManager, db_manager
from ..db.repository import (
    MeetingRepository,
    MessageRepository,
    QuestionRepository,
    RequirementRepository,
)
from ..db.vector_store import VectorStore, vector_store
from ..models import Meeting, OpenQuestion, Requirement

logger = get_logger("requirement-manager.agent")


@dataclass
class IngestResult:
    """导入会议的结果"""
    meeting_id: str
    requirements_extracted: int
    questions_generated: int
    requirement_ids: list[str]


class RequirementManagerAgent(BaseAgent):
    """
    需求管理 Agent

    职责：
    - 从会议记录中提取需求
    - 管理需求的生命周期（待确认 -> 已确认/已拒绝）
    - 发布需求相关事件供其他 Agent 消费
    """

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        bus: Optional[EventBus] = None,
        vectors: Optional[VectorStore] = None,
    ):
        # 导入订阅事件列表
        from .event_handlers import SUBSCRIBED_EVENTS

        super().__init__(
            agent_id="requirement-manager",
            agent_name="Requirement Manager",
            subscribed_events=SUBSCRIBED_EVENTS,
            published_events=[
                EventTypes.REQUIREMENT_EXTRACTED,
                EventTypes.REQUIREMENT_CONFIRMED,
                EventTypes.REQUIREMENT_REJECTED,
                EventTypes.REQUIREMENT_DELETED,
            ]
        )
        # 依赖注入，支持测试时替换
        self._db_manager = db or db_manager
        self._event_bus = bus or event_bus
        self._vector_store = vectors or vector_store

    # ========== 生命周期 ==========

    async def startup(self):
        """Agent 启动时初始化资源"""
        logger.info("agent_starting", agent_id=self.agent_id)

        # 初始化数据库表 (production uses Alembic)
        if app_settings.app_env == "development":
            await self._db_manager.create_tables()
            logger.info("database_initialized")
        else:
            logger.info("schema_managed_by_alembic")

        # 连接事件总线
        await self._event_bus.connect()
        logger.info("event_bus_connected")

        # Vector store lifecycle is now managed by VectorStorePlugin.
        # The plugin starts during runtime.startup() and the facade is
        # bound via the on_startup callback in main.py.

        # Event loop is managed by AgentRuntime.start_event_loop()

        logger.info("agent_started", agent_id=self.agent_id)

    async def shutdown(self):
        """Agent 关闭时清理资源"""
        logger.info("agent_stopping", agent_id=self.agent_id)

        await self._event_bus.disconnect()

        # Vector store lifecycle is now managed by VectorStorePlugin.
        # Shutdown is handled via the on_shutdown callback in main.py.

        # 关闭数据库连接
        await self._db_manager.close()

        logger.info("agent_stopped", agent_id=self.agent_id)

    # ========== 事件处理 ==========

    async def handle_event(self, event: Event) -> list[Event]:
        """
        处理接收到的事件

        委托给 event_handlers 模块处理。
        """
        from .event_handlers import dispatch_event
        return await dispatch_event(self, event)

    async def handle_request(self, request: dict) -> dict:
        """
        处理 API 请求

        此方法供未来扩展使用，当前通过 FastAPI 路由直接调用业务方法。
        """
        standard_response = await self.handle_standard_request(request)
        if standard_response is not None:
            return standard_response

        action = request.get("action")
        if action == "ingest":
            content = request.get("content")
            if not isinstance(content, str) or not content.strip():
                return {"status": "error", "error": "content_required"}

            try:
                meeting_date = self._parse_meeting_date(request.get("meeting_date"))
            except ValueError as exc:
                return {"status": "error", "error": str(exc)}

            async with self._db_manager.session() as session:
                result = await self.ingest_meeting(
                    content=content,
                    source=str(request.get("source") or "agent_request"),
                    session=session,
                    title=self._optional_str(request.get("title")),
                    meeting_date=meeting_date,
                    participants=self._string_list(request.get("participants")),
                    context=self._optional_str(request.get("context")),
                    source_id=self._optional_str(request.get("source_id")),
                )

            return {
                "status": "ok",
                "meeting_id": result.meeting_id,
                "requirements_extracted": result.requirements_extracted,
                "questions_generated": result.questions_generated,
                "requirement_ids": result.requirement_ids,
            }
        return {"status": "ok"}

    def _parse_meeting_date(self, value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str):
            raise ValueError("meeting_date_must_be_iso_datetime")
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError("meeting_date_must_be_iso_datetime") from exc
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed

    def _optional_str(self, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    def _string_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        return [str(value)]

    # ========== 业务方法 ==========

    async def ingest_meeting(
        self,
        content: str,
        source: str,
        session: AsyncSession,
        title: Optional[str] = None,
        meeting_date: Optional[datetime] = None,
        participants: Optional[list[str]] = None,
        context: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> IngestResult:
        """
        导入会议内容，提取需求

        Args:
            content: 会议原始内容
            source: 来源（upload/feishu/wechat）
            session: 数据库会话
            title: 会议标题
            meeting_date: 会议日期
            participants: 参与者列表
            context: 额外上下文
            source_id: 来源系统的ID（用于去重）

        Returns:
            IngestResult 包含提取的需求和问题数量
        """
        meeting_repo = MeetingRepository(session)
        requirement_repo = RequirementRepository(session)
        question_repo = QuestionRepository(session)

        # 创建会议记录
        meeting = Meeting(
            source=source,
            source_id=source_id,
            title=title,
            raw_content=content,
            meeting_date=meeting_date,
            participants=participants or [],
            context=context
        )
        await meeting_repo.create(meeting)

        logger.info(
            "meeting_created",
            meeting_id=meeting.id,
            source=source,
            content_length=len(content)
        )

        # 提取需求
        result = await extractor.extract(
            content=content,
            source=source,
            meeting_date=meeting_date.isoformat() if meeting_date else None,
            participants=participants,
            context=context
        )

        # 保存需求
        requirements: list[Requirement] = []
        for req in result.requirements:
            requirement = Requirement(
                title=req.title,
                description=req.description,
                category=req.category,
                priority=req.priority,
                source_quote=req.source_quote,
                source_meeting_ids=[meeting.id]
            )
            requirements.append(requirement)

        if requirements:
            await requirement_repo.create_batch(requirements)

            # 同步添加到向量库（非关键路径，失败不阻塞主流程）
            try:
                vector_docs = [
                    {
                        "id": req.id,
                        "title": req.title,
                        "description": req.description,
                        "category": req.category,
                        "metadata": {"meeting_id": meeting.id, "priority": req.priority}
                    }
                    for req in requirements
                ]
                await self._vector_store.add_requirements_batch(vector_docs)
            except Exception as e:
                logger.warning(
                    "vector_store_batch_add_failed",
                    meeting_id=meeting.id,
                    count=len(requirements),
                    error=str(e),
                )

        # 保存问题
        questions: list[OpenQuestion] = []
        for q in result.open_questions:
            req_id = requirements[0].id if requirements else None
            if req_id:
                question = OpenQuestion(
                    requirement_id=req_id,
                    question=q.question,
                    context=q.context
                )
                questions.append(question)

        if questions:
            await question_repo.create_batch(questions)

        # 标记会议为已处理
        await meeting_repo.mark_processed(meeting.id)

        # 发布事件
        await self._publish_requirements_extracted(
            requirements=requirements,
            meeting_id=meeting.id
        )

        # 发送通知（非关键路径，失败不阻塞主流程）
        if requirements:
            try:
                await notification_service.send(
                    channel=NotificationChannel.FEISHU,
                    title="新需求待确认",
                    content=(
                        f"从会议中提取了 {len(requirements)} 个新需求，"
                        f"{len(questions)} 个待确认问题。"
                    )
                )
            except Exception as e:
                logger.warning(
                    "notification_send_failed",
                    meeting_id=meeting.id,
                    error=str(e),
                )

        return IngestResult(
            meeting_id=meeting.id,
            requirements_extracted=len(requirements),
            questions_generated=len(questions),
            requirement_ids=[r.id for r in requirements]
        )

    async def confirm_requirement(
        self,
        requirement_id: str,
        confirmed_by: str,
        session: AsyncSession,
    ) -> Optional[Requirement]:
        """
        确认需求

        Args:
            requirement_id: 需求ID
            confirmed_by: 确认人
            session: 数据库会话

        Returns:
            确认后的需求，如果不存在返回 None
        """
        repo = RequirementRepository(session)
        requirement = await repo.confirm(requirement_id, confirmed_by)

        if not requirement:
            return None

        logger.info(
            "requirement_confirmed",
            requirement_id=requirement_id,
            confirmed_by=confirmed_by
        )

        # 发布事件
        await self._publish_requirement_confirmed(requirement, confirmed_by)

        return requirement

    async def reject_requirement(
        self,
        requirement_id: str,
        reason: str,
        rejected_by: str,
        session: AsyncSession,
    ) -> Optional[Requirement]:
        """
        拒绝需求

        Args:
            requirement_id: 需求ID
            reason: 拒绝原因
            rejected_by: 拒绝人
            session: 数据库会话

        Returns:
            拒绝后的需求，如果不存在返回 None
        """
        from .feedback_learning import FeedbackLearningService

        repo = RequirementRepository(session)

        # 获取原始需求用于反馈学习
        original_req = await repo.get_by_id(requirement_id)
        if not original_req:
            return None

        original_values = {
            "title": original_req.title,
            "description": original_req.description,
            "priority": original_req.priority,
            "category": original_req.category,
        }

        requirement = await repo.reject(requirement_id, reason=reason, rejected_by=rejected_by)

        if not requirement:
            return None

        logger.info(
            "requirement_rejected",
            requirement_id=requirement_id,
            reason=reason,
            rejected_by=rejected_by
        )

        # 记录拒绝反馈用于学习（不阻塞主流程）
        try:
            feedback_service = FeedbackLearningService(session)
            await feedback_service.record_rejection(
                requirement_id=requirement_id,
                original=original_values,
                rejected_by=rejected_by,
                reason=reason,
            )
        except Exception as e:
            logger.warning(
                "feedback_recording_failed",
                requirement_id=requirement_id,
                error=str(e),
            )

        # 发布事件
        await self._publish_requirement_rejected(requirement, reason)

        return requirement

    async def delete_requirement(
        self,
        requirement_id: str,
        deleted_by: str,
        session: AsyncSession,
    ) -> Optional[Requirement]:
        """
        删除需求

        同时删除向量库记录并发布事件。

        Args:
            requirement_id: 需求ID
            deleted_by: 删除人
            session: 数据库会话

        Returns:
            被删除的需求，如果不存在返回 None
        """
        repo = RequirementRepository(session)
        requirement = await repo.delete(requirement_id)

        if not requirement:
            return None

        logger.info(
            "requirement_deleted",
            requirement_id=requirement_id,
            title=requirement.title,
            deleted_by=deleted_by
        )

        # 发布事件
        await self._publish_requirement_deleted(requirement, deleted_by)

        return requirement

    # ========== 无 Session 的便捷方法（供 Feishu Handler 使用）==========

    async def list_pending_requirements(
        self,
        page: int = 1,
        page_size: int = 5,
    ) -> tuple[list[dict], int, int]:
        """
        列出待确认需求（自动创建 session）

        供 Feishu Bot Handler 使用，无需外部传入 session。

        Args:
            page: 页码（从 1 开始）
            page_size: 每页数量

        Returns:
            (requirements_list, total_count, total_pages)
        """
        async with self._db_manager.session() as session:
            repo = RequirementRepository(session)
            skip = (page - 1) * page_size
            requirements, total = await repo.list_all(
                status="PENDING",
                skip=skip,
                limit=page_size
            )

            total_pages = (total + page_size - 1) // page_size if total > 0 else 1

            # Convert to dict for Feishu card
            req_list = [
                {
                    "id": r.id,
                    "title": r.title,
                    "description": r.description,
                    "priority": r.priority,
                    "category": r.category,
                }
                for r in requirements
            ]

            return req_list, total, total_pages

    async def get_confirmed_requirements(self) -> list[dict]:
        """
        获取所有已确认需求（供 PRD 导出使用）

        Returns:
            已确认需求列表
        """
        async with self._db_manager.session() as session:
            repo = RequirementRepository(session)
            requirements, _ = await repo.list_all(status="CONFIRMED", limit=1000)

            return [
                {
                    "id": r.id,
                    "title": r.title,
                    "description": r.description,
                    "priority": r.priority,
                    "category": r.category,
                    "source_quote": r.source_quote,
                    "status": r.status,
                }
                for r in requirements
            ]

    async def batch_confirm_requirements(
        self,
        requirement_ids: list[str],
        confirmed_by: str,
    ) -> list[dict]:
        """
        批量确认需求

        Args:
            requirement_ids: 需求ID列表
            confirmed_by: 确认人

        Returns:
            操作结果列表，每个元素包含 requirement_id, success, error
        """
        results = []
        async with self._db_manager.session() as session:
            repo = RequirementRepository(session)

            for req_id in requirement_ids:
                try:
                    requirement = await repo.confirm(req_id, confirmed_by)
                    if requirement:
                        # 发布事件
                        await self._publish_requirement_confirmed(requirement, confirmed_by)
                        results.append({
                            "requirement_id": req_id,
                            "success": True,
                            "error": None
                        })
                        logger.info(
                            "batch_requirement_confirmed",
                            requirement_id=req_id,
                            confirmed_by=confirmed_by
                        )
                    else:
                        results.append({
                            "requirement_id": req_id,
                            "success": False,
                            "error": "需求不存在或已处理"
                        })
                except Exception as e:
                    results.append({
                        "requirement_id": req_id,
                        "success": False,
                        "error": str(e)
                    })
                    logger.error(
                        "batch_confirm_error",
                        requirement_id=req_id,
                        error=str(e)
                    )

        return results

    async def batch_reject_requirements(
        self,
        requirement_ids: list[str],
        reason: str,
        rejected_by: str,
    ) -> list[dict]:
        """
        批量拒绝需求

        Args:
            requirement_ids: 需求ID列表
            reason: 拒绝原因（共享）
            rejected_by: 拒绝人

        Returns:
            操作结果列表，每个元素包含 requirement_id, success, error
        """
        results = []
        async with self._db_manager.session() as session:
            repo = RequirementRepository(session)

            for req_id in requirement_ids:
                try:
                    requirement = await repo.reject(req_id, reason=reason, rejected_by=rejected_by)
                    if requirement:
                        # 发布事件
                        await self._publish_requirement_rejected(requirement, reason)
                        results.append({
                            "requirement_id": req_id,
                            "success": True,
                            "error": None
                        })
                        logger.info(
                            "batch_requirement_rejected",
                            requirement_id=req_id,
                            reason=reason,
                            rejected_by=rejected_by
                        )
                    else:
                        results.append({
                            "requirement_id": req_id,
                            "success": False,
                            "error": "需求不存在或已处理"
                        })
                except Exception as e:
                    results.append({
                        "requirement_id": req_id,
                        "success": False,
                        "error": str(e)
                    })
                    logger.error(
                        "batch_reject_error",
                        requirement_id=req_id,
                        error=str(e)
                    )

        return results

    async def get_requirement(self, requirement_id: str) -> Optional[Requirement]:
        """
        获取单个需求详情（自动管理 session）

        Args:
            requirement_id: 需求 ID

        Returns:
            需求对象，不存在则返回 None
        """
        async with self._db_manager.session() as session:
            repo = RequirementRepository(session)
            return await repo.get_by_id(requirement_id)

    async def get_meeting(self, meeting_id: str) -> Optional[Meeting]:
        """
        获取单个会议详情（自动管理 session）

        Args:
            meeting_id: 会议 ID

        Returns:
            会议对象，不存在则返回 None
        """
        async with self._db_manager.session() as session:
            repo = MeetingRepository(session)
            return await repo.get_by_id(meeting_id)

    # ========== 会话提取方法（供 SessionManager 使用）==========

    async def extract_from_session(self, session_id: str) -> Optional[IngestResult]:
        """
        Extract requirements from a chat session's messages.

        Called by SessionManager when session times out.

        Args:
            session_id: The session ID to extract from

        Returns:
            IngestResult if extraction succeeded, None if no messages or error
        """
        async with self._db_manager.session() as db_session:
            msg_repo = MessageRepository(db_session)
            req_repo = RequirementRepository(db_session)

            # Get all messages in session
            messages = await msg_repo.get_by_session(session_id)
            if not messages:
                logger.warning("extract_from_session_no_messages", session_id=session_id)
                return None

            # Get chat_id from first message (for notifications)
            chat_id = messages[0].chat_id

            # Format messages for LLM extraction
            content = self._format_messages_for_extraction(messages)

            logger.info(
                "extract_from_session_starting",
                session_id=session_id,
                message_count=len(messages),
                content_length=len(content),
            )

            # Call existing extraction logic via ingest_meeting
            result = await self.ingest_meeting(
                content=content,
                source="feishu_session",
                session=db_session,
                context=f"Session {session_id} from chat {chat_id} with {len(messages)} messages",
            )

            if result and result.requirements_extracted > 0:
                # Mark messages as extracted and link to requirements
                await msg_repo.mark_extracted(session_id, result.requirement_ids)

                # Get message IDs for context linking
                message_ids = [m.id for m in messages]

                # Update requirements with context_message_ids
                for req_id in result.requirement_ids:
                    req = await req_repo.get_by_id(req_id)
                    if req and hasattr(req, 'context_message_ids'):
                        req.context_message_ids = message_ids

                await db_session.commit()

                # Send notification card to chat
                await self._send_session_extraction_card(chat_id, result, session_id)

                logger.info(
                    "extract_from_session_complete",
                    session_id=session_id,
                    requirements_extracted=result.requirements_extracted,
                )

            return result

    def _format_messages_for_extraction(self, messages: list) -> str:
        """
        Format messages as conversation text for LLM extraction.

        Args:
            messages: List of ChatMessage objects ordered by sent_at

        Returns:
            Formatted conversation text
        """
        lines = []

        for msg in messages:
            sender = msg.sender_name or "Unknown"
            time_str = msg.sent_at.strftime("%H:%M") if msg.sent_at else "??:??"
            content = msg.content or ""

            # Skip empty content
            if not content.strip():
                continue

            lines.append(f"[{time_str}] {sender}: {content}")

        return "\n".join(lines)

    async def _send_session_extraction_card(
        self,
        chat_id: str,
        result: IngestResult,
        session_id: str,
    ):
        """
        Send extraction result card to the chat.

        Similar to existing notification but includes session context.
        """
        try:
            from agents.requirement_manager.integrations.feishu.cards.requirement import (
                build_requirement_extracted_card,
            )
            from shared.integrations.feishu import feishu_client

            client = feishu_client()

            # Build card with requirements
            card = build_requirement_extracted_card(
                requirements=result.requirements if hasattr(result, 'requirements') else [],
                meeting_title=f"群聊会话 {session_id[:8]}...",
                questions_count=(
                    result.questions_generated
                    if hasattr(result, "questions_generated")
                    else 0
                ),
            )

            await client.send_card(
                receive_id=chat_id,
                receive_id_type="chat_id",
                card=card,
            )

            logger.info(
                "session_extraction_card_sent",
                chat_id=chat_id,
                session_id=session_id,
            )

        except Exception as e:
            logger.error(
                "session_extraction_card_failed",
                chat_id=chat_id,
                session_id=session_id,
                error=str(e),
            )

    # ========== 事件发布（内部方法）==========

    async def _publish_requirements_extracted(
        self,
        requirements: list[Requirement],
        meeting_id: str
    ):
        """发布需求提取事件"""
        if not requirements:
            return

        # 发布聚合事件（一次会议提取的所有需求）
        event = self.create_event(
            event_type=EventTypes.REQUIREMENT_EXTRACTED,
            payload={
                "meeting_id": meeting_id,
                "requirement_ids": [r.id for r in requirements],
                "count": len(requirements),
                "requirements": [
                    {
                        "id": r.id,
                        "title": r.title,
                        "priority": r.priority,
                        "category": r.category,
                    }
                    for r in requirements
                ]
            }
        )

        try:
            await self._event_bus.publish(event)
            logger.info(
                "event_published",
                event_id=event.event_id,
                event_type=event.event_type,
                requirement_count=len(requirements)
            )
        except Exception as e:
            # 事件发布失败不阻塞主流程
            logger.error(
                "event_publish_failed",
                event_type=EventTypes.REQUIREMENT_EXTRACTED,
                error=str(e)
            )

    async def _publish_requirement_confirmed(
        self,
        requirement: Requirement,
        confirmed_by: str
    ):
        """发布需求确认事件"""
        event = self.create_event(
            event_type=EventTypes.REQUIREMENT_CONFIRMED,
            payload={
                "requirement_id": requirement.id,
                "title": requirement.title,
                "priority": requirement.priority,
                "category": requirement.category,
                "confirmed_by": confirmed_by,
                "confirmed_at": datetime.now(UTC).isoformat()
            }
        )

        try:
            await self._event_bus.publish(event)
            logger.info(
                "event_published",
                event_id=event.event_id,
                event_type=event.event_type,
                requirement_id=requirement.id
            )
        except Exception as e:
            logger.error(
                "event_publish_failed",
                event_type=EventTypes.REQUIREMENT_CONFIRMED,
                error=str(e)
            )

    async def _publish_requirement_rejected(
        self,
        requirement: Requirement,
        reason: str
    ):
        """发布需求拒绝事件"""
        event = self.create_event(
            event_type=EventTypes.REQUIREMENT_REJECTED,
            payload={
                "requirement_id": requirement.id,
                "title": requirement.title,
                "reason": reason,
                "rejected_at": datetime.now(UTC).isoformat()
            }
        )

        try:
            await self._event_bus.publish(event)
            logger.info(
                "event_published",
                event_id=event.event_id,
                event_type=event.event_type,
                requirement_id=requirement.id
            )
        except Exception as e:
            logger.error(
                "event_publish_failed",
                event_type=EventTypes.REQUIREMENT_REJECTED,
                error=str(e)
            )

    async def _publish_requirement_deleted(
        self,
        requirement: Requirement,
        deleted_by: str
    ):
        """发布需求删除事件"""
        event = self.create_event(
            event_type=EventTypes.REQUIREMENT_DELETED,
            payload={
                "requirement_id": requirement.id,
                "title": requirement.title,
                "deleted_by": deleted_by,
                "deleted_at": datetime.now(UTC).isoformat()
            }
        )

        try:
            await self._event_bus.publish(event)
            logger.info(
                "event_published",
                event_id=event.event_id,
                event_type=event.event_type,
                requirement_id=requirement.id
            )
        except Exception as e:
            logger.error(
                "event_publish_failed",
                event_type=EventTypes.REQUIREMENT_DELETED,
                error=str(e)
            )


# 全局 Agent 实例（单例）
agent = RequirementManagerAgent()


def get_agent() -> RequirementManagerAgent:
    """获取当前 Agent 实例（支持测试时替换）"""
    return agent
