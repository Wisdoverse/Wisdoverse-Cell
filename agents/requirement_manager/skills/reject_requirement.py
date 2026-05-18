"""
RejectSkill - Reject a pending requirement.

Triggered by /reject command or card button callback.
"""
from datetime import UTC, datetime

from agents.requirement_manager.db.skill_store import build_requirement_skill_store
from agents.requirement_manager.models import RequirementStatus
from shared.infra.skill import BaseSkill, Permission, SkillContext, SkillError, SkillResult
from shared.messaging.inbound import AgentResponse, UnifiedCard


class RejectSkill(BaseSkill):
    """Reject a pending requirement."""

    name = "reject"
    description = "拒绝需求"
    commands = ["/reject"]
    patterns = [r"拒绝\s*(req_\w+|REQ\w+)"]
    permissions = [Permission.DB_WRITE, Permission.GATEWAY_REPLY]

    async def execute(self, context: SkillContext) -> SkillResult:
        """Execute reject skill."""
        requirement_id = context.parameters.get("requirement_id")
        reason = context.parameters.get("reason", "")

        if not requirement_id:
            raise SkillError("请提供需求ID，例如: /reject req_xxx 原因")

        if context.db is None:
            raise SkillError("数据库不可用")

        store = build_requirement_skill_store(context.db)

        requirement = await store.get_by_id(requirement_id)
        if not requirement:
            raise SkillError(f"找不到需求 {requirement_id}")

        if requirement.status != RequirementStatus.PENDING.value:
            raise SkillError(f"该需求已被处理（当前状态: {requirement.status}）")

        await store.reject(requirement_id, reason, context.user.id)
        await store.commit()

        content = f"**{requirement.title}**\n\n"
        if reason:
            content += f"拒绝原因: {reason}\n"
        content += (
            f"操作人: {context.user.name}\n"
            f"时间: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')}"
        )

        card = UnifiedCard(
            title="❌ 需求已拒绝",
            content=content,
            status="rejected",
            status_color="red",
        )

        return SkillResult(
            success=True,
            response=AgentResponse(card=card),
        )
