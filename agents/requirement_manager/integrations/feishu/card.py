"""
CardHandler - 处理卡片按钮回调

处理用户在消息卡片中的点击操作。
"""

from agents.requirement_manager.integrations.feishu.cards.requirement import (
    build_batch_result_card,
    build_requirement_confirmed_card,
    build_requirement_detail_card,
    build_requirement_list_card,
    build_requirement_rejected_card,
)
from shared.integrations.feishu.cards.decomposition import (
    build_decomposition_approved_card,
    build_decomposition_rejected_card,
)
from shared.utils.logger import get_logger

logger = get_logger("feishu.handlers.card")


class CardHandler:
    """
    卡片回调处理器

    action value 约定：
    - {"action": "confirm_requirement", "req_id": "xxx"}
    - {"action": "reject_requirement", "req_id": "xxx"}
    - {"action": "view_detail", "req_id": "xxx"}
    - {"action": "list_confirm_requirement", "req_id": "xxx", "page": 1, "chat_id": "xxx"}
    - {"action": "list_reject_requirement", "req_id": "xxx", "page": 1, "chat_id": "xxx"}
    - {"action": "list_prev_page", "page": 1, "chat_id": "xxx"}
    - {"action": "list_next_page", "page": 2, "chat_id": "xxx"}
    - {"action": "approve_decomposition", "wp_id": 123}
    - {"action": "reject_decomposition", "wp_id": 123}
    """

    def __init__(self, feishu_client, agent, pm_client=None):
        self.client = feishu_client
        self.agent = agent
        self.pm_client = pm_client
        self._user_cache: dict[str, str] = {}

    async def handle_action(self, data: dict) -> dict:
        """
        处理卡片动作

        Args:
            data: 飞书卡片回调数据

        Returns:
            响应数据（toast 和/或 card）
        """
        action = data.get("action", {})
        action_value = action.get("value", {})
        action_type = action_value.get("action", "")
        operator = data.get("operator", {})
        operator_id = operator.get("open_id", "")

        logger.info(
            "card_action_received",
            action=action_type,
            operator=operator_id
        )

        try:
            if action_type == "confirm_requirement":
                return await self._handle_confirm(action_value, operator_id)

            elif action_type == "reject_requirement":
                return await self._handle_reject(action_value, operator_id, data)

            elif action_type == "view_detail":
                return await self._handle_view_detail(action_value)

            # List card actions
            elif action_type == "list_confirm_requirement":
                return await self._handle_list_confirm(action_value, operator_id)

            elif action_type == "list_reject_requirement":
                return await self._handle_list_reject(action_value, operator_id, data)

            elif action_type in ("list_prev_page", "list_next_page"):
                return await self._handle_list_pagination(action_value)

            # Batch operations
            elif action_type == "batch_confirm_all":
                return await self._handle_batch_confirm(action_value, operator_id)

            elif action_type == "batch_reject_all":
                return await self._handle_batch_reject(action_value, operator_id)

            # Decomposition approval actions
            elif action_type == "approve_decomposition":
                return await self._handle_approve_decomposition(action_value, operator_id)

            elif action_type == "reject_decomposition":
                return await self._handle_reject_decomposition(action_value, operator_id, data)

            else:
                logger.warning("unknown_card_action", action=action_type)
                return {
                    "toast": {
                        "type": "info",
                        "content": "未知操作"
                    }
                }

        except Exception as e:
            logger.error("card_action_error", action=action_type, error=str(e))
            return {
                "toast": {
                    "type": "error",
                    "content": f"操作失败: {str(e)}"
                }
            }

    async def _get_user_name(self, open_id: str) -> str:
        """获取用户名（带缓存）"""
        if open_id in self._user_cache:
            return self._user_cache[open_id]

        try:
            user_info = await self.client.get_user_info(open_id)
            name = user_info.get("name", "Unknown")
            self._user_cache[open_id] = name
            return name
        except Exception:
            return "Unknown"

    async def _handle_confirm(self, action_value: dict, operator_id: str) -> dict:
        """处理确认需求"""
        req_id = action_value.get("req_id")
        if not req_id:
            return {"toast": {"type": "error", "content": "缺少需求 ID"}}

        user_name = await self._get_user_name(operator_id)

        # Call agent to confirm
        requirement = await self.agent.confirm_requirement(
            requirement_id=req_id,
            confirmed_by=user_name,
        )

        if not requirement:
            return {"toast": {"type": "error", "content": "需求不存在"}}

        # Build updated card
        card = build_requirement_confirmed_card(
            requirement={
                "id": requirement.id,
                "title": requirement.title,
                "description": requirement.description,
                "priority": requirement.priority,
            },
            confirmed_by=user_name
        )

        logger.info("requirement_confirmed_via_card", req_id=req_id, by=user_name)

        return {
            "toast": {
                "type": "success",
                "content": "需求已确认"
            },
            "card": card
        }

    async def _handle_reject(
        self,
        action_value: dict,
        operator_id: str,
        data: dict
    ) -> dict:
        """处理拒绝需求"""
        req_id = action_value.get("req_id")
        if not req_id:
            return {"toast": {"type": "error", "content": "缺少需求 ID"}}

        # Check if reason was provided (from form submission)
        form_value = data.get("action", {}).get("form_value", {})
        reason = form_value.get("reason") or action_value.get("reason", "未提供原因")

        user_name = await self._get_user_name(operator_id)

        # Call agent to reject
        requirement = await self.agent.reject_requirement(
            requirement_id=req_id,
            reason=reason,
            rejected_by=user_name,
        )

        if not requirement:
            return {"toast": {"type": "error", "content": "需求不存在"}}

        # Build updated card
        card = build_requirement_rejected_card(
            requirement={
                "id": requirement.id,
                "title": requirement.title,
                "description": getattr(requirement, "description", ""),
            },
            rejected_by=user_name,
            reason=reason
        )

        logger.info("requirement_rejected_via_card", req_id=req_id, by=user_name)

        return {
            "toast": {
                "type": "success",
                "content": "需求已拒绝"
            },
            "card": card
        }

    async def _handle_view_detail(self, action_value: dict) -> dict:
        """处理查看详情 - 弹出详情卡片"""
        req_id = action_value.get("req_id")
        if not req_id:
            return {"toast": {"type": "error", "content": "缺少需求 ID"}}

        requirement = await self.agent.get_requirement(req_id)
        if not requirement:
            return {"toast": {"type": "error", "content": "需求不存在"}}

        # Fetch associated meeting if available
        meeting = None
        if requirement.source_meeting_ids:
            meeting = await self.agent.get_meeting(requirement.source_meeting_ids[0])

        # Build detail card
        req_data = self._requirement_to_dict(requirement)
        meeting_data = self._meeting_to_dict(meeting) if meeting else None
        card = build_requirement_detail_card(req_data, meeting_data)

        return {
            "toast": {"type": "success", "content": "已加载详情"},
            "card": card
        }

    def _requirement_to_dict(self, requirement) -> dict:
        """Convert requirement model to dict for card rendering"""
        return {
            "id": requirement.id,
            "title": requirement.title,
            "description": requirement.description,
            "priority": requirement.priority,
            "category": requirement.category,
            "status": requirement.status,
            "source_quote": requirement.source_quote,
        }

    def _meeting_to_dict(self, meeting) -> dict:
        """Convert meeting model to dict for card rendering"""
        meeting_date = None
        if meeting.meeting_date:
            meeting_date = meeting.meeting_date.strftime("%Y-%m-%d %H:%M")

        return {
            "id": meeting.id,
            "title": meeting.title,
            "meeting_date": meeting_date,
            "participants": meeting.participants or [],
        }

    async def _handle_list_confirm(self, action_value: dict, operator_id: str) -> dict:
        """处理列表中的确认需求"""
        req_id = action_value.get("req_id")
        page = action_value.get("page", 1)
        chat_id = action_value.get("chat_id", "")

        if not req_id:
            return {"toast": {"type": "error", "content": "缺少需求 ID"}}

        user_name = await self._get_user_name(operator_id)

        # Confirm requirement
        requirement = await self.agent.confirm_requirement(
            requirement_id=req_id,
            confirmed_by=user_name,
        )

        if not requirement:
            return {"toast": {"type": "error", "content": "需求不存在"}}

        logger.info("requirement_confirmed_from_list", req_id=req_id, by=user_name)

        # Refresh list card
        requirements, total, total_pages = await self.agent.list_pending_requirements(
            page=page,
            page_size=5
        )

        card = build_requirement_list_card(
            requirements=requirements,
            page=page,
            total_pages=total_pages,
            total_count=total,
            chat_id=chat_id
        )

        return {
            "toast": {
                "type": "success",
                "content": f"已确认: {requirement.title}"
            },
            "card": card
        }

    async def _handle_list_reject(
        self,
        action_value: dict,
        operator_id: str,
        data: dict
    ) -> dict:
        """处理列表中的拒绝需求"""
        req_id = action_value.get("req_id")
        page = action_value.get("page", 1)
        chat_id = action_value.get("chat_id", "")

        if not req_id:
            return {"toast": {"type": "error", "content": "缺少需求 ID"}}

        # Check if reason was provided (from form submission)
        form_value = data.get("action", {}).get("form_value", {})
        reason = form_value.get("reason") or action_value.get("reason", "未提供原因")

        user_name = await self._get_user_name(operator_id)

        # Reject requirement
        requirement = await self.agent.reject_requirement(
            requirement_id=req_id,
            reason=reason,
            rejected_by=user_name,
        )

        if not requirement:
            return {"toast": {"type": "error", "content": "需求不存在"}}

        logger.info("requirement_rejected_from_list", req_id=req_id, by=user_name)

        # Refresh list card
        requirements, total, total_pages = await self.agent.list_pending_requirements(
            page=page,
            page_size=5
        )

        card = build_requirement_list_card(
            requirements=requirements,
            page=page,
            total_pages=total_pages,
            total_count=total,
            chat_id=chat_id
        )

        return {
            "toast": {
                "type": "success",
                "content": f"已拒绝: {requirement.title}"
            },
            "card": card
        }

    async def _handle_list_pagination(self, action_value: dict) -> dict:
        """处理列表翻页"""
        page = action_value.get("page", 1)
        chat_id = action_value.get("chat_id", "")

        # Get requirements for the page
        requirements, total, total_pages = await self.agent.list_pending_requirements(
            page=page,
            page_size=5
        )

        card = build_requirement_list_card(
            requirements=requirements,
            page=page,
            total_pages=total_pages,
            total_count=total,
            chat_id=chat_id
        )

        return {"card": card}

    async def _handle_batch_confirm(self, action_value: dict, operator_id: str) -> dict:
        """处理批量确认"""
        req_ids = action_value.get("req_ids", [])

        if not req_ids:
            return {"toast": {"type": "error", "content": "没有需要确认的需求"}}

        user_name = await self._get_user_name(operator_id)

        # Call agent to batch confirm
        success_count, failed_count = await self.agent.batch_confirm_requirements(
            requirement_ids=req_ids,
            confirmed_by=user_name,
        )

        logger.info(
            "batch_confirm_complete",
            success=success_count,
            failed=failed_count,
            by=user_name
        )

        # Build result card
        card = build_batch_result_card(
            action_type="confirm",
            success_count=success_count,
            failed_count=failed_count,
            operator_name=user_name
        )

        return {
            "toast": {
                "type": "success",
                "content": f"已确认 {success_count} 个需求"
            },
            "card": card
        }

    async def _handle_batch_reject(self, action_value: dict, operator_id: str) -> dict:
        """处理批量拒绝"""
        req_ids = action_value.get("req_ids", [])
        reason = action_value.get("reason", "批量拒绝")

        if not req_ids:
            return {"toast": {"type": "error", "content": "没有需要拒绝的需求"}}

        user_name = await self._get_user_name(operator_id)

        # Call agent to batch reject
        success_count, failed_count = await self.agent.batch_reject_requirements(
            requirement_ids=req_ids,
            reason=reason,
            rejected_by=user_name,
        )

        logger.info(
            "batch_reject_complete",
            success=success_count,
            failed=failed_count,
            by=user_name
        )

        # Build result card
        card = build_batch_result_card(
            action_type="reject",
            success_count=success_count,
            failed_count=failed_count,
            operator_name=user_name
        )

        return {
            "toast": {
                "type": "success",
                "content": f"已拒绝 {success_count} 个需求"
            },
            "card": card
        }

    async def _handle_approve_decomposition(self, action_value: dict, operator_id: str) -> dict:
        wp_id = action_value.get("wp_id")
        if not wp_id:
            return {"toast": {"type": "error", "content": "缺少工作包 ID"}}
        if not self.pm_client:
            return {"toast": {"type": "error", "content": "PJM Agent 未配置"}}

        user_name = await self._get_user_name(operator_id)
        try:
            result = await self.pm_client.approve_decomposition(wp_id=wp_id, operator=user_name)
        except Exception as e:
            logger.error("approve_decomposition_request_failed", wp_id=wp_id, error=str(e))
            return {"toast": {"type": "error", "content": f"审批请求失败: {e}"}}

        if not result:
            return {"toast": {"type": "error", "content": "审批失败：记录不存在"}}

        card = build_decomposition_approved_card(
            wp_id=wp_id,
            subject=result.get("subject", ""),
            approved_by=user_name,
            story_count=result.get("story_count", 0),
            task_count=result.get("task_count", 0),
        )
        logger.info("decomposition_approved_via_card", wp_id=wp_id, by=user_name)
        return {"toast": {"type": "success", "content": "拆解已批准，正在写入 OP"}, "card": card}

    async def _handle_reject_decomposition(self, action_value: dict, operator_id: str, data: dict) -> dict:
        wp_id = action_value.get("wp_id")
        if not wp_id:
            return {"toast": {"type": "error", "content": "缺少工作包 ID"}}
        if not self.pm_client:
            return {"toast": {"type": "error", "content": "PJM Agent 未配置"}}

        # Extract rejection reason from form input
        form_value = data.get("action", {}).get("form_value", {})
        reason = form_value.get("reject_reason") or action_value.get("reject_reason", "")

        user_name = await self._get_user_name(operator_id)
        try:
            result = await self.pm_client.reject_decomposition(wp_id=wp_id, operator=user_name, reason=reason)
        except Exception as e:
            logger.error("reject_decomposition_request_failed", wp_id=wp_id, error=str(e))
            return {"toast": {"type": "error", "content": f"拒绝请求失败: {e}"}}

        if not result:
            return {"toast": {"type": "error", "content": "操作失败：记录不存在"}}

        card = build_decomposition_rejected_card(
            wp_id=wp_id,
            subject=result.get("subject", ""),
            rejected_by=user_name,
            reason=reason,
        )
        logger.info("decomposition_rejected_via_card", wp_id=wp_id, by=user_name, reason=reason)
        return {"toast": {"type": "success", "content": "已拒绝拆解方案"}, "card": card}
