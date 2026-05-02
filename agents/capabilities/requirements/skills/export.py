"""
ExportSkill - Export requirements as PRD.

Generates a PRD document from confirmed requirements.
"""
from agents.capabilities.requirements.db.repository import RequirementRepository
from agents.capabilities.requirements.models import RequirementStatus
from shared.infra.skill import BaseSkill, Permission, SkillContext, SkillError, SkillResult
from shared.messaging.inbound import AgentResponse, CardAction, CardActionStyle, UnifiedCard


class ExportSkill(BaseSkill):
    """Export confirmed requirements as PRD."""

    name = "export"
    description = "导出需求文档"
    commands = ["/export", "/导出", "/prd"]
    patterns = [r"导出.*需求", r"生成.*PRD", r"需求文档"]
    permissions = [Permission.DB_READ, Permission.GATEWAY_REPLY]

    async def execute(self, context: SkillContext) -> SkillResult:
        """Execute export skill."""
        format_type = context.parameters.get("format", "summary")

        if context.db is None:
            raise SkillError("数据库不可用")

        repo = RequirementRepository(context.db)

        # Get confirmed requirements
        requirements, total = await repo.list_all(
            status=RequirementStatus.CONFIRMED.value,
            limit=100,
        )

        if not requirements:
            return SkillResult(
                success=True,
                response=AgentResponse(card=UnifiedCard(
                    title="📄 导出需求",
                    content="暂无已确认的需求可导出",
                )),
            )

        if format_type == "detail":
            card = self._build_detail_card(requirements, total)
        else:
            card = self._build_summary_card(requirements, total)

        return SkillResult(success=True, response=AgentResponse(card=card))

    def _build_summary_card(self, requirements: list, total: int) -> UnifiedCard:
        """Build summary export card."""
        # Group by category
        by_category = {}
        for req in requirements:
            cat = req.category or "其他"
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(req)

        lines = [
            f"已确认需求共 **{total}** 条",
            "",
        ]

        for category, reqs in sorted(by_category.items()):
            lines.append(f"### {category} ({len(reqs)})")
            for req in reqs[:5]:
                priority_emoji = self._priority_emoji(req.priority)
                lines.append(f"- {priority_emoji} **{req.title}**")
            if len(reqs) > 5:
                lines.append(f"- ...及其他 {len(reqs) - 5} 条")
            lines.append("")

        return UnifiedCard(
            title="📄 需求摘要",
            content="\n".join(lines),
            actions=[
                CardAction(
                    label="查看详情",
                    action_id="export_detail",
                    value={"action": "export", "format": "detail"},
                    style=CardActionStyle.PRIMARY,
                ),
            ],
        )

    def _build_detail_card(self, requirements: list, total: int) -> UnifiedCard:
        """Build detailed export card."""
        lines = [
            "# 产品需求文档 (PRD)",
            "",
            f"**需求总数**: {total}",
            "**生成时间**: 自动生成",
            "",
            "---",
            "",
        ]

        for i, req in enumerate(requirements[:10], 1):
            priority_emoji = self._priority_emoji(req.priority)
            lines.extend([
                f"## {i}. {req.title} {priority_emoji}",
                "",
                f"**ID**: `{req.id}`",
                f"**分类**: {req.category or '未分类'}",
                f"**优先级**: {req.priority or '未设置'}",
                "",
                "**描述**:",
                req.description or "无描述",
                "",
                "---",
                "",
            ])

        if total > 10:
            lines.append(f"*...共 {total} 条需求，仅显示前 10 条*")

        return UnifiedCard(
            title="📄 PRD 详情",
            content="\n".join(lines),
        )

    def _priority_emoji(self, priority: str) -> str:
        """Get emoji for priority level."""
        return {
            "high": "🔴",
            "medium": "🟡",
            "low": "🟢",
        }.get(priority or "", "⚪")
