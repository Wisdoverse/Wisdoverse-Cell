"""
CardHandler for Feishu card button callbacks.

Handles user actions submitted from interactive message cards.
"""

from shared.integrations.feishu.cards.decomposition import (
    build_decomposition_approved_card,
    build_decomposition_rejected_card,
)
from shared.observability.privacy import hash_identifier
from shared.utils.logger import get_logger

from .acl import FeishuCardAction, FeishuCardActionResponse
from .cards.requirement import (
    build_batch_result_card,
    build_requirement_confirmed_card,
    build_requirement_detail_card,
    build_requirement_list_card,
    build_requirement_rejected_card,
)

logger = get_logger("feishu.handlers.card")


class CardHandler:
    """
    Feishu card callback handler.

    Action value contract:
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
        Handle an interactive card action.

        Args:
            data: Feishu card callback data.

        Returns:
            Response payload with toast and/or card data.
        """
        action = FeishuCardAction.from_payload(data)

        logger.info(
            "card_action_received",
            action=action.action_type,
            operator_hash=hash_identifier(action.operator_id),
        )

        try:
            if action.action_type == "confirm_requirement":
                return await self._handle_confirm(action)

            elif action.action_type == "reject_requirement":
                return await self._handle_reject(action)

            elif action.action_type == "view_detail":
                return await self._handle_view_detail(action)

            # List card actions
            elif action.action_type == "list_confirm_requirement":
                return await self._handle_list_confirm(action)

            elif action.action_type == "list_reject_requirement":
                return await self._handle_list_reject(action)

            elif action.action_type in ("list_prev_page", "list_next_page"):
                return await self._handle_list_pagination(action)

            # Batch operations
            elif action.action_type == "batch_confirm_all":
                return await self._handle_batch_confirm(action)

            elif action.action_type == "batch_reject_all":
                return await self._handle_batch_reject(action)

            # Decomposition approval actions
            elif action.action_type == "approve_decomposition":
                return await self._handle_approve_decomposition(action)

            elif action.action_type == "reject_decomposition":
                return await self._handle_reject_decomposition(action)

            else:
                logger.warning("unknown_card_action", action=action.action_type)
                return FeishuCardActionResponse.info("未知操作").to_payload()

        except Exception as e:
            logger.error("card_action_error", action=action.action_type, error=str(e))
            return FeishuCardActionResponse.error("操作失败，请稍后重试").to_payload()

    async def _get_user_name(self, open_id: str) -> str:
        """Get user name with cache."""
        if open_id in self._user_cache:
            return self._user_cache[open_id]

        try:
            user_info = await self.client.get_user_info(open_id)
            name = user_info.get("name", "Unknown")
            self._user_cache[open_id] = name
            return name
        except Exception:
            return "Unknown"

    async def _handle_confirm(self, action: FeishuCardAction) -> dict:
        """Handle requirement confirmation."""
        if not action.has_requirement_id:
            return FeishuCardActionResponse.error("缺少需求 ID").to_payload()

        user_name = await self._get_user_name(action.operator_id)

        # Call agent to confirm
        requirement = await self.agent.confirm_requirement(
            requirement_id=action.requirement_id,
            confirmed_by=user_name,
        )

        if not requirement:
            return FeishuCardActionResponse.error("需求不存在").to_payload()

        # Build updated card
        card = build_requirement_confirmed_card(
            requirement={
                "id": requirement.id,
                "title": requirement.title,
                "description": requirement.description,
                "priority": requirement.priority,
            },
            confirmed_by=user_name,
        )

        logger.info(
            "requirement_confirmed_via_card",
            req_id=action.requirement_id,
            operator_hash=hash_identifier(action.operator_id),
        )

        return FeishuCardActionResponse.success("需求已确认", card=card).to_payload()

    async def _handle_reject(self, action: FeishuCardAction) -> dict:
        """Handle requirement rejection."""
        if not action.has_requirement_id:
            return FeishuCardActionResponse.error("缺少需求 ID").to_payload()

        reason = action.requirement_rejection_reason

        user_name = await self._get_user_name(action.operator_id)

        # Call agent to reject
        requirement = await self.agent.reject_requirement(
            requirement_id=action.requirement_id,
            reason=reason,
            rejected_by=user_name,
        )

        if not requirement:
            return FeishuCardActionResponse.error("需求不存在").to_payload()

        # Build updated card
        card = build_requirement_rejected_card(
            requirement={
                "id": requirement.id,
                "title": requirement.title,
                "description": getattr(requirement, "description", ""),
            },
            rejected_by=user_name,
            reason=reason,
        )

        logger.info(
            "requirement_rejected_via_card",
            req_id=action.requirement_id,
            operator_hash=hash_identifier(action.operator_id),
            reason_hash=hash_identifier(reason),
            reason_length=len(reason),
        )

        return FeishuCardActionResponse.success("需求已拒绝", card=card).to_payload()

    async def _handle_view_detail(self, action: FeishuCardAction) -> dict:
        """Handle detail view and return the detail card."""
        if not action.has_requirement_id:
            return FeishuCardActionResponse.error("缺少需求 ID").to_payload()

        requirement = await self.agent.get_requirement(action.requirement_id)
        if not requirement:
            return FeishuCardActionResponse.error("需求不存在").to_payload()

        # Fetch associated meeting if available
        meeting = None
        if requirement.source_meeting_ids:
            meeting = await self.agent.get_meeting(requirement.source_meeting_ids[0])

        # Build detail card
        req_data = self._requirement_to_dict(requirement)
        meeting_data = self._meeting_to_dict(meeting) if meeting else None
        card = build_requirement_detail_card(req_data, meeting_data)

        return FeishuCardActionResponse.success("已加载详情", card=card).to_payload()

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

    async def _handle_list_confirm(self, action: FeishuCardAction) -> dict:
        """Handle requirement confirmation from the list card."""
        if not action.has_requirement_id:
            return FeishuCardActionResponse.error("缺少需求 ID").to_payload()

        user_name = await self._get_user_name(action.operator_id)

        # Confirm requirement
        requirement = await self.agent.confirm_requirement(
            requirement_id=action.requirement_id,
            confirmed_by=user_name,
        )

        if not requirement:
            return FeishuCardActionResponse.error("需求不存在").to_payload()

        logger.info(
            "requirement_confirmed_from_list",
            req_id=action.requirement_id,
            operator_hash=hash_identifier(action.operator_id),
        )

        # Refresh list card
        requirements, total, total_pages = await self.agent.list_pending_requirements(
            page=action.page, page_size=5
        )

        card = build_requirement_list_card(
            requirements=requirements,
            page=action.page,
            total_pages=total_pages,
            total_count=total,
            chat_id=action.chat_id,
        )

        return FeishuCardActionResponse.success(
            f"已确认: {requirement.title}",
            card=card,
        ).to_payload()

    async def _handle_list_reject(self, action: FeishuCardAction) -> dict:
        """Handle requirement rejection from the list card."""
        if not action.has_requirement_id:
            return FeishuCardActionResponse.error("缺少需求 ID").to_payload()

        reason = action.requirement_rejection_reason

        user_name = await self._get_user_name(action.operator_id)

        # Reject requirement
        requirement = await self.agent.reject_requirement(
            requirement_id=action.requirement_id,
            reason=reason,
            rejected_by=user_name,
        )

        if not requirement:
            return FeishuCardActionResponse.error("需求不存在").to_payload()

        logger.info(
            "requirement_rejected_from_list",
            req_id=action.requirement_id,
            operator_hash=hash_identifier(action.operator_id),
            reason_hash=hash_identifier(reason),
            reason_length=len(reason),
        )

        # Refresh list card
        requirements, total, total_pages = await self.agent.list_pending_requirements(
            page=action.page, page_size=5
        )

        card = build_requirement_list_card(
            requirements=requirements,
            page=action.page,
            total_pages=total_pages,
            total_count=total,
            chat_id=action.chat_id,
        )

        return FeishuCardActionResponse.success(
            f"已拒绝: {requirement.title}",
            card=card,
        ).to_payload()

    async def _handle_list_pagination(self, action: FeishuCardAction) -> dict:
        """Handle list pagination."""
        # Get requirements for the page
        requirements, total, total_pages = await self.agent.list_pending_requirements(
            page=action.page, page_size=5
        )

        card = build_requirement_list_card(
            requirements=requirements,
            page=action.page,
            total_pages=total_pages,
            total_count=total,
            chat_id=action.chat_id,
        )

        return FeishuCardActionResponse.card_only(card).to_payload()

    async def _handle_batch_confirm(self, action: FeishuCardAction) -> dict:
        """Handle batch confirmation."""
        if not action.has_requirement_ids:
            return FeishuCardActionResponse.error("没有需要确认的需求").to_payload()

        user_name = await self._get_user_name(action.operator_id)

        # Call agent to batch confirm
        success_count, failed_count = await self.agent.batch_confirm_requirements(
            requirement_ids=action.requirement_ids_list(),
            confirmed_by=user_name,
        )

        logger.info(
            "batch_confirm_complete",
            success=success_count,
            failed=failed_count,
            operator_hash=hash_identifier(action.operator_id),
        )

        # Build result card
        card = build_batch_result_card(
            action_type="confirm",
            success_count=success_count,
            failed_count=failed_count,
            operator_name=user_name,
        )

        return FeishuCardActionResponse.success(
            f"已确认 {success_count} 个需求",
            card=card,
        ).to_payload()

    async def _handle_batch_reject(self, action: FeishuCardAction) -> dict:
        """Handle batch rejection."""
        reason = action.batch_rejection_reason

        if not action.has_requirement_ids:
            return FeishuCardActionResponse.error("没有需要拒绝的需求").to_payload()

        user_name = await self._get_user_name(action.operator_id)

        # Call agent to batch reject
        success_count, failed_count = await self.agent.batch_reject_requirements(
            requirement_ids=action.requirement_ids_list(),
            reason=reason,
            rejected_by=user_name,
        )

        logger.info(
            "batch_reject_complete",
            success=success_count,
            failed=failed_count,
            operator_hash=hash_identifier(action.operator_id),
            reason_hash=hash_identifier(reason),
            reason_length=len(reason),
        )

        # Build result card
        card = build_batch_result_card(
            action_type="reject",
            success_count=success_count,
            failed_count=failed_count,
            operator_name=user_name,
        )

        return FeishuCardActionResponse.success(
            f"已拒绝 {success_count} 个需求",
            card=card,
        ).to_payload()

    async def _handle_approve_decomposition(self, action: FeishuCardAction) -> dict:
        if not action.has_work_package_id:
            return FeishuCardActionResponse.error("缺少工作包 ID").to_payload()
        if not self.pm_client:
            return FeishuCardActionResponse.error("PJM Agent 未配置").to_payload()

        user_name = await self._get_user_name(action.operator_id)
        try:
            result = await self.pm_client.approve_decomposition(
                wp_id=action.work_package_id, operator=user_name
            )
        except Exception as e:
            logger.error(
                "approve_decomposition_request_failed",
                wp_id=action.work_package_id,
                error=str(e),
            )
            return FeishuCardActionResponse.error("审批请求失败，请稍后重试").to_payload()

        if not result:
            return FeishuCardActionResponse.error("审批失败：记录不存在").to_payload()

        card = build_decomposition_approved_card(
            wp_id=action.work_package_id,
            subject=result.get("subject", ""),
            approved_by=user_name,
            story_count=result.get("story_count", 0),
            task_count=result.get("task_count", 0),
        )
        logger.info(
            "decomposition_approved_via_card",
            wp_id=action.work_package_id,
            operator_hash=hash_identifier(action.operator_id),
        )
        return FeishuCardActionResponse.success(
            "拆解已批准，正在写入 OP",
            card=card,
        ).to_payload()

    async def _handle_reject_decomposition(self, action: FeishuCardAction) -> dict:
        if not action.has_work_package_id:
            return FeishuCardActionResponse.error("缺少工作包 ID").to_payload()
        if not self.pm_client:
            return FeishuCardActionResponse.error("PJM Agent 未配置").to_payload()

        reason = action.decomposition_rejection_reason

        user_name = await self._get_user_name(action.operator_id)
        try:
            result = await self.pm_client.reject_decomposition(
                wp_id=action.work_package_id, operator=user_name, reason=reason
            )
        except Exception as e:
            logger.error(
                "reject_decomposition_request_failed",
                wp_id=action.work_package_id,
                error=str(e),
            )
            return FeishuCardActionResponse.error("拒绝请求失败，请稍后重试").to_payload()

        if not result:
            return FeishuCardActionResponse.error("操作失败：记录不存在").to_payload()

        card = build_decomposition_rejected_card(
            wp_id=action.work_package_id,
            subject=result.get("subject", ""),
            rejected_by=user_name,
            reason=reason,
        )
        logger.info(
            "decomposition_rejected_via_card",
            wp_id=action.work_package_id,
            operator_hash=hash_identifier(action.operator_id),
            reason_hash=hash_identifier(reason),
            reason_length=len(reason),
        )
        return FeishuCardActionResponse.success("已拒绝拆解方案", card=card).to_payload()
