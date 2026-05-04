"""
ConfirmSkill - Confirm a pending requirement.

Triggered by /confirm command or card button callback.
"""
from datetime import UTC, datetime

from agents.requirement_manager.db.repository import RequirementRepository
from agents.requirement_manager.models import RequirementStatus
from shared.infra.skill import BaseSkill, Permission, SkillContext, SkillError, SkillResult
from shared.messaging.inbound import AgentResponse, UnifiedCard


class ConfirmSkill(BaseSkill):
    """Confirm a pending requirement."""

    name = "confirm"
    description = "确认需求"
    commands = ["/confirm"]
    patterns = [r"确认\s*(req_\w+|REQ\w+)"]
    permissions = [Permission.DB_WRITE, Permission.GATEWAY_REPLY]

    async def execute(self, context: SkillContext) -> SkillResult:
        """Execute confirm skill."""
        requirement_id = context.parameters.get("requirement_id")

        if not requirement_id:
            raise SkillError("请提供需求ID，例如: /confirm req_xxx")

        if context.db is None:
            raise SkillError("数据库不可用")

        repo = RequirementRepository(context.db)

        requirement = await repo.get_by_id(requirement_id)
        if not requirement:
            raise SkillError(f"找不到需求 {requirement_id}")

        if requirement.status != RequirementStatus.PENDING.value:
            raise SkillError(f"该需求已被处理（当前状态: {requirement.status}）")

        await repo.confirm(requirement_id, context.user.id)
        await context.db.commit()

        card = UnifiedCard(
            title="✅ 需求已确认",
            content=(
                f"**{requirement.title}**\n\n"
                f"确认人: {context.user.name}\n"
                f"时间: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')}"
            ),
            status="confirmed",
            status_color="green",
        )

        return SkillResult(
            success=True,
            response=AgentResponse(card=card),
        )
