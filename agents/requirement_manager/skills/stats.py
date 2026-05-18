"""
StatsSkill - Show requirement statistics.

Displays a dashboard card with requirement statistics via chat.
"""
from agents.requirement_manager.db.skill_store import build_requirement_skill_store
from shared.infra.skill import BaseSkill, Permission, SkillContext, SkillError, SkillResult
from shared.messaging.inbound import AgentResponse, UnifiedCard


class StatsSkill(BaseSkill):
    """Show requirement statistics dashboard."""

    name = "stats"
    description = "查看需求统计数据"
    commands = ["/stats", "/统计", "/dashboard"]
    patterns = [r"统计", r"数据看板", r"需求状态"]
    permissions = [Permission.DB_READ, Permission.GATEWAY_REPLY]

    async def execute(self, context: SkillContext) -> SkillResult:
        """Execute stats skill."""
        if context.db is None:
            raise SkillError("数据库不可用")

        store = build_requirement_skill_store(context.db)

        # Gather statistics
        status_counts = await store.count_by_status()
        priority_counts = await store.count_by_priority()
        category_counts = await store.count_by_category()
        weekly_trend = await store.get_daily_counts(days=7)
        today_count = await store.count_today()

        # Meeting stats
        total_meetings, unprocessed_meetings = await store.meeting_counts()

        card = self._build_card(
            status_counts=status_counts,
            priority_counts=priority_counts,
            category_counts=category_counts,
            weekly_trend=weekly_trend,
            today_count=today_count,
            total_meetings=total_meetings,
            unprocessed_meetings=unprocessed_meetings,
        )

        return SkillResult(success=True, response=AgentResponse(card=card))

    def _build_card(
        self,
        status_counts: dict,
        priority_counts: dict,
        category_counts: dict,
        weekly_trend: list,
        today_count: int,
        total_meetings: int,
        unprocessed_meetings: int,
    ) -> UnifiedCard:
        """Build statistics card."""
        # Status section
        pending = status_counts.get("pending", 0)
        confirmed = status_counts.get("confirmed", 0)
        rejected = status_counts.get("rejected", 0)
        total_reqs = pending + confirmed + rejected

        lines = [
            "## 需求概览",
            "",
            "| 状态 | 数量 | 占比 |",
            "|------|------|------|",
            f"| 🟡 待确认 | {pending} | {self._pct(pending, total_reqs)} |",
            f"| ✅ 已确认 | {confirmed} | {self._pct(confirmed, total_reqs)} |",
            f"| ❌ 已拒绝 | {rejected} | {self._pct(rejected, total_reqs)} |",
            f"| **合计** | **{total_reqs}** | 100% |",
            "",
        ]

        # Priority section
        if priority_counts:
            high = priority_counts.get("high", 0)
            medium = priority_counts.get("medium", 0)
            low = priority_counts.get("low", 0)
            lines.extend([
                "## 优先级分布",
                "",
                f"🔴 高: {high}  |  🟡 中: {medium}  |  🟢 低: {low}",
                "",
            ])

        # Trend section
        if weekly_trend:
            trend_str = "  ".join([f"{t['date']}:{t['count']}" for t in weekly_trend[-5:]])
            lines.extend([
                "## 近期趋势",
                "",
                f"📈 今日新增: **{today_count}**",
                f"近5日: {trend_str}",
                "",
            ])

        # Meeting section
        lines.extend([
            "## 会议处理",
            "",
            f"📅 会议总数: {total_meetings}",
            f"⏳ 待处理: {unprocessed_meetings}",
        ])

        return UnifiedCard(
            title="📊 需求统计看板",
            content="\n".join(lines),
        )

    def _pct(self, part: int, total: int) -> str:
        """Calculate percentage string."""
        if total == 0:
            return "0%"
        return f"{round(part / total * 100)}%"
