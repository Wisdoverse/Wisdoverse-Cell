"""
ListSkill - List pending requirements.

Displays pending requirements in a paginated card with confirm/reject buttons.
"""
from agents.capabilities.requirements.db.repository import RequirementRepository
from agents.capabilities.requirements.models import RequirementStatus
from shared.infra.skill import BaseSkill, Permission, SkillContext, SkillError, SkillResult
from shared.messaging.inbound import AgentResponse, CardAction, CardActionStyle, UnifiedCard


class ListSkill(BaseSkill):
    """List pending requirements with pagination."""

    name = "list"
    description = "查看待确认需求列表"
    commands = ["/list", "/需求"]
    patterns = [r"查看.*需求", r"待确认", r"需求列表"]
    permissions = [Permission.DB_READ, Permission.GATEWAY_REPLY]

    PAGE_SIZE = 5

    async def execute(self, context: SkillContext) -> SkillResult:
        """Execute list skill to show pending requirements."""
        page = int(context.parameters.get("page", 1))

        if context.db is None:
            raise SkillError("数据库不可用")

        repo = RequirementRepository(context.db)
        skip = (page - 1) * self.PAGE_SIZE

        requirements, total = await repo.list_all(
            status=RequirementStatus.PENDING.value,
            skip=skip,
            limit=self.PAGE_SIZE,
        )

        total_pages = (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE if total > 0 else 1

        card = self._build_card(requirements, page, total_pages, total)

        return SkillResult(
            success=True,
            response=AgentResponse(card=card),
        )

    def _build_card(
        self,
        requirements: list,
        page: int,
        total_pages: int,
        total: int,
    ) -> UnifiedCard:
        """Build requirement list card."""
        if not requirements:
            return UnifiedCard(
                title="📋 待确认需求",
                content="暂无待确认的需求",
            )

        lines = []
        for i, req in enumerate(requirements, start=1):
            priority_emoji = self._priority_emoji(req.priority)
            lines.append(f"**{i}. {req.title}** {priority_emoji}")
            lines.append(f"   分类: {req.category} | ID: `{req.id}`")
            if req.description:
                desc = (
                    req.description[:50] + "..."
                    if len(req.description) > 50
                    else req.description
                )
                lines.append(f"   {desc}")
            lines.append("")

        content = "\n".join(lines)
        content += f"\n---\n第 {page}/{total_pages} 页 | 共 {total} 条"

        actions = []

        if page > 1:
            actions.append(CardAction(
                label="上一页",
                action_id="list_page",
                value={"action": "list_page", "page": page - 1},
                style=CardActionStyle.DEFAULT,
            ))

        if page < total_pages:
            actions.append(CardAction(
                label="下一页",
                action_id="list_page",
                value={"action": "list_page", "page": page + 1},
                style=CardActionStyle.DEFAULT,
            ))

        return UnifiedCard(
            title=f"📋 待确认需求 ({total})",
            content=content,
            actions=actions,
        )

    def _priority_emoji(self, priority: str) -> str:
        """Get emoji for priority level."""
        return {
            "high": "🔴",
            "medium": "🟡",
            "low": "🟢",
        }.get(priority, "⚪")
