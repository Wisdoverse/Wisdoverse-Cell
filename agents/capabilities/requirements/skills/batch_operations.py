"""
BatchSkill - Batch confirm/reject requirements.

Allows users to confirm or reject multiple requirements at once.
"""
from agents.capabilities.requirements.db.repository import RequirementRepository
from agents.capabilities.requirements.models import RequirementStatus
from shared.infra.skill import BaseSkill, Permission, SkillContext, SkillError, SkillResult
from shared.messaging.inbound import AgentResponse, UnifiedCard


class BatchConfirmSkill(BaseSkill):
    """Batch confirm multiple requirements."""

    name = "batch_confirm"
    description = "批量确认需求"
    commands = ["/batch-confirm", "/批量确认"]
    patterns = [r"批量确认\s+(.+)"]
    permissions = [Permission.DB_WRITE, Permission.GATEWAY_REPLY]

    async def execute(self, context: SkillContext) -> SkillResult:
        """Execute batch confirm."""
        ids_str = context.parameters.get("requirement_ids", "")
        if not ids_str:
            raise SkillError("请提供需求ID列表，例如: /batch-confirm req_001,req_002")

        requirement_ids = [id.strip() for id in ids_str.split(",") if id.strip()]
        if not requirement_ids:
            raise SkillError("请提供有效的需求ID列表")

        if context.db is None:
            raise SkillError("数据库不可用")

        repo = RequirementRepository(context.db)
        results = []

        for req_id in requirement_ids:
            try:
                req = await repo.get_by_id(req_id)
                if not req:
                    results.append({"id": req_id, "success": False, "error": "不存在"})
                    continue

                if req.status != RequirementStatus.PENDING.value:
                    results.append({
                        "id": req_id,
                        "success": False,
                        "error": f"状态为 {req.status}",
                    })
                    continue

                await repo.confirm(req_id, context.user.id)
                results.append({"id": req_id, "success": True, "title": req.title})
            except Exception as e:
                results.append({"id": req_id, "success": False, "error": str(e)})

        await context.db.commit()

        succeeded = [r for r in results if r["success"]]
        failed = [r for r in results if not r["success"]]

        card = self._build_result_card(succeeded, failed, "确认")
        return SkillResult(success=True, response=AgentResponse(card=card))

    def _build_result_card(self, succeeded: list, failed: list, action: str) -> UnifiedCard:
        """Build result card."""
        lines = []

        if succeeded:
            lines.append(f"**✅ 成功{action} ({len(succeeded)})**")
            for r in succeeded[:5]:
                lines.append(f"- `{r['id']}` {r.get('title', '')[:20]}")
            if len(succeeded) > 5:
                lines.append(f"- ...及其他 {len(succeeded) - 5} 条")
            lines.append("")

        if failed:
            lines.append(f"**❌ 失败 ({len(failed)})**")
            for r in failed[:5]:
                lines.append(f"- `{r['id']}`: {r['error']}")
            if len(failed) > 5:
                lines.append(f"- ...及其他 {len(failed) - 5} 条")

        return UnifiedCard(
            title=f"批量{action}结果",
            content="\n".join(lines),
            status="completed" if not failed else "partial",
            status_color="green" if not failed else "orange",
        )


class BatchRejectSkill(BaseSkill):
    """Batch reject multiple requirements."""

    name = "batch_reject"
    description = "批量拒绝需求"
    commands = ["/batch-reject", "/批量拒绝"]
    patterns = [r"批量拒绝\s+(.+)"]
    permissions = [Permission.DB_WRITE, Permission.GATEWAY_REPLY]

    async def execute(self, context: SkillContext) -> SkillResult:
        """Execute batch reject."""
        ids_str = context.parameters.get("requirement_ids", "")
        reason = context.parameters.get("reason", "批量拒绝")

        if not ids_str:
            raise SkillError("请提供需求ID列表，例如: /batch-reject req_001,req_002 原因")

        requirement_ids = [id.strip() for id in ids_str.split(",") if id.strip()]
        if not requirement_ids:
            raise SkillError("请提供有效的需求ID列表")

        if context.db is None:
            raise SkillError("数据库不可用")

        repo = RequirementRepository(context.db)
        results = []

        for req_id in requirement_ids:
            try:
                req = await repo.get_by_id(req_id)
                if not req:
                    results.append({"id": req_id, "success": False, "error": "不存在"})
                    continue

                if req.status != RequirementStatus.PENDING.value:
                    results.append({
                        "id": req_id,
                        "success": False,
                        "error": f"状态为 {req.status}",
                    })
                    continue

                await repo.reject(req_id, reason, context.user.id)
                results.append({"id": req_id, "success": True, "title": req.title})
            except Exception as e:
                results.append({"id": req_id, "success": False, "error": str(e)})

        await context.db.commit()

        succeeded = [r for r in results if r["success"]]
        failed = [r for r in results if not r["success"]]

        card = self._build_result_card(succeeded, failed, "拒绝", reason)
        return SkillResult(success=True, response=AgentResponse(card=card))

    def _build_result_card(
        self, succeeded: list, failed: list,
        action: str, reason: str,
    ) -> UnifiedCard:
        """Build result card."""
        lines = []

        if succeeded:
            lines.append(f"**✅ 成功{action} ({len(succeeded)})**")
            for r in succeeded[:5]:
                lines.append(f"- `{r['id']}` {r.get('title', '')[:20]}")
            if len(succeeded) > 5:
                lines.append(f"- ...及其他 {len(succeeded) - 5} 条")
            lines.append(f"\n原因: {reason}")
            lines.append("")

        if failed:
            lines.append(f"**❌ 失败 ({len(failed)})**")
            for r in failed[:5]:
                lines.append(f"- `{r['id']}`: {r['error']}")
            if len(failed) > 5:
                lines.append(f"- ...及其他 {len(failed) - 5} 条")

        return UnifiedCard(
            title=f"批量{action}结果",
            content="\n".join(lines),
            status="completed" if not failed else "partial",
            status_color="red" if not failed else "orange",
        )
