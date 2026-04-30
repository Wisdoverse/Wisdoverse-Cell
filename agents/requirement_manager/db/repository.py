"""
Repository - 数据访问层
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..models.feedback import FeedbackRecord

from sqlalchemy import Integer, and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from shared.utils.logger import get_logger

from ..models import LLMUsage, Meeting, OpenQuestion, Requirement, RequirementStatus
from ..models.chat_message import ChatMessage

logger = get_logger("repository")


class MeetingRepository:
    """会议记录数据访问"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, meeting: Meeting) -> Meeting:
        """创建会议记录"""
        self.session.add(meeting)
        await self.session.flush()
        return meeting

    async def get_by_id(self, meeting_id: str) -> Optional[Meeting]:
        """根据ID获取会议"""
        result = await self.session.execute(
            select(Meeting).where(Meeting.id == meeting_id)
        )
        return result.scalar_one_or_none()

    async def get_by_source_id(self, source: str, source_id: str) -> Optional[Meeting]:
        """根据来源ID获取会议（用于去重）"""
        result = await self.session.execute(
            select(Meeting).where(
                Meeting.source == source,
                Meeting.source_id == source_id
            )
        )
        return result.scalar_one_or_none()

    async def list_unprocessed(self, limit: int = 100) -> list[Meeting]:
        """获取未处理的会议"""
        result = await self.session.execute(
            select(Meeting)
            .where(Meeting.processed.is_(False))
            .order_by(Meeting.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_all(
        self,
        source: Optional[str] = None,
        skip: int = 0,
        limit: int = 20
    ) -> tuple[list[Meeting], int]:
        """获取会议列表"""
        query = select(Meeting)

        if source:
            query = query.where(Meeting.source == source)

        # 获取总数
        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.session.execute(count_query)).scalar()

        # 获取分页数据
        result = await self.session.execute(
            query.order_by(Meeting.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def mark_processed(self, meeting_id: str):
        """标记为已处理"""
        await self.session.execute(
            update(Meeting)
            .where(Meeting.id == meeting_id)
            .values(processed=True, processed_at=datetime.now(UTC))
        )


class RequirementRepository:
    """需求数据访问"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, requirement: Requirement) -> Requirement:
        """创建需求"""
        self.session.add(requirement)
        await self.session.flush()
        return requirement

    async def create_batch(self, requirements: list[Requirement]) -> list[Requirement]:
        """批量创建需求"""
        self.session.add_all(requirements)
        await self.session.flush()
        return requirements

    async def get_by_id(self, requirement_id: str) -> Optional[Requirement]:
        """根据ID获取需求（包含关联的问题）"""
        result = await self.session.execute(
            select(Requirement)
            .options(selectinload(Requirement.open_questions))
            .where(Requirement.id == requirement_id)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        skip: int = 0,
        limit: int = 20
    ) -> tuple[list[Requirement], int]:
        """获取需求列表"""
        query = select(Requirement).options(selectinload(Requirement.open_questions))

        if status:
            query = query.where(Requirement.status == status)
        if category:
            query = query.where(Requirement.category == category)
        if priority:
            query = query.where(Requirement.priority == priority)

        # 获取总数
        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.session.execute(count_query)).scalar()

        # 获取分页数据
        result = await self.session.execute(
            query.order_by(Requirement.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def update(
        self,
        requirement_id: str,
        **kwargs
    ) -> Optional[Requirement]:
        """更新需求"""
        await self.session.execute(
            update(Requirement)
            .where(Requirement.id == requirement_id)
            .values(**kwargs, updated_at=datetime.now(UTC))
        )
        return await self.get_by_id(requirement_id)

    async def confirm(
        self,
        requirement_id: str,
        confirmed_by: str
    ) -> Optional[Requirement]:
        """确认需求"""
        requirement = await self.get_by_id(requirement_id)
        if requirement:
            requirement.status = RequirementStatus.CONFIRMED.value
            requirement.confirmed_by = confirmed_by
            requirement.confirmed_at = datetime.now(UTC)
            requirement.add_history("confirmed", "需求已确认", confirmed_by)
            await self.session.flush()
        return requirement

    async def reject(
        self,
        requirement_id: str,
        reason: str,
        rejected_by: str
    ) -> Optional[Requirement]:
        """拒绝需求"""
        requirement = await self.get_by_id(requirement_id)
        if requirement:
            requirement.status = RequirementStatus.REJECTED.value
            requirement.rejection_reason = reason
            requirement.add_history("rejected", f"需求已拒绝: {reason}", rejected_by)
            await self.session.flush()
        return requirement

    async def get_by_meeting_id(self, meeting_id: str) -> list[Requirement]:
        """获取某个会议关联的需求"""
        result = await self.session.execute(
            select(Requirement)
            .where(Requirement.source_meeting_ids.contains([meeting_id]))
        )
        return list(result.scalars().all())

    async def count_by_status(self) -> dict[str, int]:
        """按状态统计需求数量"""
        result = await self.session.execute(
            select(Requirement.status, func.count())
            .group_by(Requirement.status)
        )
        return {status: count for status, count in result.all()}

    async def count_by_priority(self) -> dict[str, int]:
        """按优先级统计需求数量"""
        result = await self.session.execute(
            select(Requirement.priority, func.count())
            .group_by(Requirement.priority)
        )
        return {priority: count for priority, count in result.all()}

    async def count_by_category(self) -> dict[str, int]:
        """按分类统计需求数量"""
        result = await self.session.execute(
            select(Requirement.category, func.count())
            .group_by(Requirement.category)
        )
        return {category: count for category, count in result.all()}

    async def get_daily_counts(self, days: int = 7) -> list[dict]:
        """获取每日新增需求数量"""
        from datetime import timedelta

        end_date = datetime.now(UTC).date()
        start_date = end_date - timedelta(days=days - 1)

        result = await self.session.execute(
            select(
                func.date(Requirement.created_at).label('date'),
                func.count().label('count')
            )
            .where(func.date(Requirement.created_at) >= start_date)
            .group_by(func.date(Requirement.created_at))
            .order_by(func.date(Requirement.created_at))
        )

        # 创建日期到数量的映射
        counts_map = {str(row.date): row.count for row in result.all()}

        # 填充所有日期
        trend = []
        current = start_date
        while current <= end_date:
            trend.append({
                'date': current.strftime('%m/%d'),
                'count': counts_map.get(str(current), 0)
            })
            current += timedelta(days=1)

        return trend

    async def count_today(self) -> int:
        """获取今日新增需求数量"""
        today = datetime.now(UTC).date()
        result = await self.session.execute(
            select(func.count())
            .where(func.date(Requirement.created_at) == today)
        )
        return result.scalar() or 0

    async def delete(self, requirement_id: str) -> Optional[Requirement]:
        """
        删除需求（同步删除向量库记录）

        事务一致性策略:
        1. 先删除向量库记录（失败时记录警告，继续执行）
        2. 再删除数据库记录
        3. 向量库是辅助索引，数据库是主数据源

        如果向量库删除失败但数据库删除成功，会产生孤立的向量记录。
        这些孤立记录会在下次查询时被过滤（因为找不到对应的数据库记录）。

        Args:
            requirement_id: 需求ID

        Returns:
            被删除的需求对象，如果不存在返回 None
        """
        from ..db.vector_store import vector_store

        # 1. 获取需求（用于返回和记录）
        requirement = await self.get_by_id(requirement_id)
        if not requirement:
            return None

        # 2. 先删除向量库记录（在数据库事务提交之前）
        # 向量库删除失败不阻塞主流程，但需要记录日志以便后续清理
        try:
            await vector_store.delete_requirement(requirement_id)
            logger.info(
                "vector_store_record_deleted",
                requirement_id=requirement_id
            )
        except Exception as e:
            # 向量库删除失败，记录警告日志
            # 孤立的向量记录会在查询时被过滤
            logger.warning(
                "vector_store_delete_failed",
                requirement_id=requirement_id,
                error=str(e),
                note="Orphaned vector record may exist, will be filtered on query"
            )

        # 3. 删除关联的 OpenQuestion
        await self.session.execute(
            delete(OpenQuestion).where(OpenQuestion.requirement_id == requirement_id)
        )

        # 4. 删除 Requirement 记录
        await self.session.execute(
            delete(Requirement).where(Requirement.id == requirement_id)
        )

        logger.info(
            "requirement_deleted_from_db",
            requirement_id=requirement_id,
            title=requirement.title
        )

        return requirement


class QuestionRepository:
    """待确认问题数据访问"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, question: OpenQuestion) -> OpenQuestion:
        """创建问题"""
        self.session.add(question)
        await self.session.flush()
        return question

    async def create_batch(self, questions: list[OpenQuestion]) -> list[OpenQuestion]:
        """批量创建问题"""
        self.session.add_all(questions)
        await self.session.flush()
        return questions

    async def get_by_id(self, question_id: str) -> Optional[OpenQuestion]:
        """根据ID获取问题"""
        result = await self.session.execute(
            select(OpenQuestion).where(OpenQuestion.id == question_id)
        )
        return result.scalar_one_or_none()

    async def list_open(self, limit: int = 50) -> list[OpenQuestion]:
        """获取所有未回答的问题"""
        result = await self.session.execute(
            select(OpenQuestion)
            .where(OpenQuestion.status == "open")
            .order_by(OpenQuestion.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def answer(
        self,
        question_id: str,
        answer: str,
        answered_by: str
    ) -> Optional[OpenQuestion]:
        """回答问题"""
        question = await self.get_by_id(question_id)
        if question:
            question.status = "answered"
            question.answer = answer
            question.answered_by = answered_by
            question.answered_at = datetime.now(UTC)
            await self.session.flush()
        return question


class LLMUsageRepository:
    """
    LLM 使用记录数据访问

    提供 LLM 调用记录的 CRUD 操作和统计查询。
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, usage: LLMUsage) -> LLMUsage:
        """创建使用记录"""
        self.session.add(usage)
        await self.session.flush()
        return usage

    async def get_daily_summary(
        self,
        date: str,
        agent_id: Optional[str] = None
    ) -> dict:
        """
        获取某天的使用汇总

        Args:
            date: 日期字符串 (YYYY-MM-DD)
            agent_id: 可选的 Agent ID 过滤

        Returns:
            包含统计数据的字典
        """
        # 解析日期范围
        start_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
        end_date = start_date.replace(hour=23, minute=59, second=59)

        # 基础查询条件
        base_condition = [
            LLMUsage.created_at >= start_date,
            LLMUsage.created_at <= end_date
        ]

        if agent_id:
            base_condition.append(LLMUsage.agent_id == agent_id)

        # 总体统计
        total_query = select(
            func.count().label("total_calls"),
            func.sum(func.cast(LLMUsage.success, Integer)).label("success_calls"),
            func.sum(LLMUsage.input_tokens).label("total_input_tokens"),
            func.sum(LLMUsage.output_tokens).label("total_output_tokens"),
            func.sum(LLMUsage.cost_usd).label("total_cost_usd"),
            func.avg(LLMUsage.latency_ms).label("avg_latency_ms")
        ).where(*base_condition)

        result = await self.session.execute(total_query)
        row = result.one()

        total_calls = row.total_calls or 0
        success_calls = int(row.success_calls or 0)

        summary = {
            "date": date,
            "total_calls": total_calls,
            "success_calls": success_calls,
            "failed_calls": total_calls - success_calls,
            "total_input_tokens": int(row.total_input_tokens or 0),
            "total_output_tokens": int(row.total_output_tokens or 0),
            "total_cost_usd": round(float(row.total_cost_usd or 0), 6),
            "avg_latency_ms": int(row.avg_latency_ms or 0),
            "by_agent": {},
            "by_task_type": {}
        }

        # 按 Agent 分组统计
        agent_query = select(
            LLMUsage.agent_id,
            func.count().label("calls"),
            func.sum(LLMUsage.cost_usd).label("cost_usd"),
            func.sum(LLMUsage.input_tokens).label("input_tokens"),
            func.sum(LLMUsage.output_tokens).label("output_tokens")
        ).where(*base_condition).group_by(LLMUsage.agent_id)

        agent_result = await self.session.execute(agent_query)
        for row in agent_result.all():
            summary["by_agent"][row.agent_id] = {
                "calls": row.calls,
                "cost_usd": round(float(row.cost_usd or 0), 6),
                "input_tokens": int(row.input_tokens or 0),
                "output_tokens": int(row.output_tokens or 0)
            }

        # 按任务类型分组统计
        task_query = select(
            LLMUsage.task_type,
            func.count().label("calls"),
            func.sum(LLMUsage.cost_usd).label("cost_usd")
        ).where(*base_condition).group_by(LLMUsage.task_type)

        task_result = await self.session.execute(task_query)
        for row in task_result.all():
            summary["by_task_type"][row.task_type] = {
                "calls": row.calls,
                "cost_usd": round(float(row.cost_usd or 0), 6)
            }

        return summary

    async def get_usage_by_agent(
        self,
        agent_id: str,
        start_date: str,
        end_date: str
    ) -> list[LLMUsage]:
        """
        获取某个 Agent 在指定时间范围内的调用记录

        Args:
            agent_id: Agent ID
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            LLMUsage 记录列表
        """
        start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=UTC)
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=UTC
        )

        result = await self.session.execute(
            select(LLMUsage)
            .where(
                LLMUsage.agent_id == agent_id,
                LLMUsage.created_at >= start,
                LLMUsage.created_at <= end
            )
            .order_by(LLMUsage.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_recent_failures(self, limit: int = 20) -> list[LLMUsage]:
        """获取最近的失败记录"""
        result = await self.session.execute(
            select(LLMUsage)
            .where(LLMUsage.success.is_(False))
            .order_by(LLMUsage.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


class MessageRepository:
    """消息数据访问层"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, message: ChatMessage) -> ChatMessage:
        """Insert new message"""
        self.session.add(message)
        await self.session.flush()
        await self.session.refresh(message)
        return message

    async def get_by_id(self, message_id: str) -> Optional[ChatMessage]:
        """Get by internal ID"""
        result = await self.session.execute(
            select(ChatMessage).where(ChatMessage.id == message_id)
        )
        return result.scalar_one_or_none()

    async def get_by_feishu_message_id(self, feishu_message_id: str) -> Optional[ChatMessage]:
        """Get by Feishu message_id (for dedup check)"""
        result = await self.session.execute(
            select(ChatMessage).where(ChatMessage.message_id == feishu_message_id)
        )
        return result.scalar_one_or_none()

    async def search(
        self,
        keyword: Optional[str] = None,
        chat_id: Optional[str] = None,
        sender_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ChatMessage], int]:
        """Search messages with PostgreSQL full-text search"""
        query = select(ChatMessage)
        count_query = select(func.count()).select_from(ChatMessage)

        conditions = []

        if keyword:
            # PostgreSQL full-text search using 'simple' configuration for Chinese
            ts_query = func.plainto_tsquery('simple', keyword)
            ts_vector = func.to_tsvector('simple', ChatMessage.content)
            conditions.append(ts_vector.op('@@')(ts_query))

        if chat_id:
            conditions.append(ChatMessage.chat_id == chat_id)

        if sender_id:
            conditions.append(ChatMessage.sender_id == sender_id)

        if start_time:
            conditions.append(ChatMessage.sent_at >= start_time)

        if end_time:
            conditions.append(ChatMessage.sent_at <= end_time)

        if conditions:
            query = query.where(and_(*conditions))
            count_query = count_query.where(and_(*conditions))

        # Get total count
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination
        query = query.order_by(ChatMessage.sent_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def get_by_session(self, session_id: str) -> list[ChatMessage]:
        """Get all messages in a session, ordered by sent_at ASC"""
        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.sent_at.asc())
        )
        return list(result.scalars().all())

    async def count_by_session(self, session_id: str) -> int:
        """Count messages in a session"""
        result = await self.session.execute(
            select(func.count())
            .select_from(ChatMessage)
            .where(ChatMessage.session_id == session_id)
        )
        return result.scalar() or 0

    async def mark_extracted(self, session_id: str, requirement_ids: list[str]) -> int:
        """Mark session messages as extracted and link to requirements"""
        result = await self.session.execute(
            update(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .values(extracted=True, requirement_ids=requirement_ids)
        )
        return result.rowcount


class FeedbackRepository:
    """
    Feedback record data access layer.

    Manages user corrections/feedback for learning.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, feedback: "FeedbackRecord") -> "FeedbackRecord":
        """Create a feedback record."""
        self.session.add(feedback)
        await self.session.flush()
        return feedback

    async def get_by_id(self, feedback_id: str) -> Optional["FeedbackRecord"]:
        """Get feedback by ID."""
        from ..models import FeedbackRecord as FeedbackModel
        result = await self.session.execute(
            select(FeedbackModel).where(FeedbackModel.id == feedback_id)
        )
        return result.scalar_one_or_none()

    async def list_by_requirement(self, requirement_id: str) -> list["FeedbackRecord"]:
        """Get all feedback for a requirement."""
        from ..models import FeedbackRecord as FeedbackModel
        result = await self.session.execute(
            select(FeedbackModel)
            .where(FeedbackModel.requirement_id == requirement_id)
            .order_by(FeedbackModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_recent(
        self,
        limit: int = 20,
        feedback_type: Optional[str] = None,
        unused_only: bool = False,
    ) -> list["FeedbackRecord"]:
        """
        Get recent feedback records for prompt examples.

        Args:
            limit: Maximum number of records
            feedback_type: Filter by type (correction, rejection, merge)
            unused_only: Only get records not yet used in prompts

        Returns:
            List of FeedbackRecord
        """
        from ..models import FeedbackRecord as FeedbackModel
        query = select(FeedbackModel)

        if feedback_type:
            query = query.where(FeedbackModel.feedback_type == feedback_type)

        if unused_only:
            query = query.where(FeedbackModel.used_in_prompt.is_(False))

        query = query.order_by(FeedbackModel.created_at.desc()).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_examples_for_prompt(self, limit: int = 5) -> list[dict]:
        """
        Get feedback examples formatted for LLM prompt.

        Returns the most recent corrections as examples to include
        in the extraction prompt for few-shot learning.
        """
        records = await self.list_recent(limit=limit, feedback_type="correction")
        return [r.to_example() for r in records]

    async def mark_used(self, feedback_ids: list[str]) -> int:
        """Mark feedback records as used in prompt."""
        from ..models import FeedbackRecord as FeedbackModel
        result = await self.session.execute(
            update(FeedbackModel)
            .where(FeedbackModel.id.in_(feedback_ids))
            .values(used_in_prompt=True)
        )
        return result.rowcount

    async def count_by_type(self) -> dict[str, int]:
        """Count feedback records by type."""
        from ..models import FeedbackRecord as FeedbackModel
        result = await self.session.execute(
            select(FeedbackModel.feedback_type, func.count())
            .group_by(FeedbackModel.feedback_type)
        )
        return {ftype: count for ftype, count in result.all()}
