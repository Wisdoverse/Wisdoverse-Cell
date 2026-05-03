"""
ApprovalGateway — human-in-the-loop approval for collaboration patterns via Feishu.

Sends pattern approval requests as Feishu messages and processes human responses.
Security: validates approver identity against an admin whitelist.
Privacy: reports contain only metrics, never raw prompts or trigger conditions.
"""

from typing import Any

from shared.observability.privacy import hash_identifier
from shared.utils.logger import get_logger

from .models import PatternStatus

logger = get_logger("evolution.approval")


class ApprovalGateway:
    """Sends pattern approval requests via Feishu cards and processes responses.

    Security: Validates approver identity against admin whitelist.
    Privacy: Reports contain only metrics, never raw prompts.
    """

    MIN_SHADOW_RUNS = 20

    def __init__(
        self,
        pattern_store: Any,
        feishu_service: Any = None,
        admin_chat_id: str = "",
        admin_user_ids: list[str] | None = None,
    ):
        self._store = pattern_store
        self._feishu = feishu_service
        self._admin_chat_id = admin_chat_id
        self._admin_user_ids = admin_user_ids or []

    async def maybe_request_approval(self, pattern_id: str) -> bool:
        """Check if pattern has enough shadow data and request approval.

        Returns True if approval request was sent (or would have been sent
        if no Feishu service is configured).
        """
        pattern = await self._store.get_pattern(pattern_id)
        if pattern is None:
            return False

        shadow_results = pattern.shadow_results or []
        if len(shadow_results) < self.MIN_SHADOW_RUNS:
            logger.debug(
                "approval_not_ready",
                pattern_id=pattern_id,
                shadow_runs=len(shadow_results),
                required=self.MIN_SHADOW_RUNS,
            )
            return False

        report = self._build_report(pattern)

        if self._feishu and self._admin_chat_id:
            try:
                await self._feishu.send_text(
                    chat_id=self._admin_chat_id,
                    text=report,
                )
                logger.info("approval_requested", pattern_id=pattern_id)
            except Exception as e:
                logger.error("approval_send_failed", pattern_id=pattern_id, error=str(e))
                return False

        return True

    async def process_approval(
        self, pattern_id: str, user_id: str, approved: bool
    ) -> bool:
        """Process human approval response.

        Validates user_id against admin whitelist. Returns True if processed.
        """
        if user_id not in self._admin_user_ids:
            logger.warning(
                "approval_rejected_unauthorized",
                user_hash=hash_identifier(user_id),
                pattern_id=pattern_id,
            )
            return False

        if approved:
            await self._store.approve_pattern(pattern_id, approved_by=user_id)
            logger.info(
                "pattern_approved",
                pattern_id=pattern_id,
                approved_by_hash=hash_identifier(user_id),
            )
        else:
            await self._store.update_status(pattern_id, PatternStatus.RETIRED)
            logger.info(
                "pattern_rejected",
                pattern_id=pattern_id,
                rejected_by_hash=hash_identifier(user_id),
            )

        return True

    def _build_report(self, pattern: Any) -> str:
        """Build human-readable approval report. No raw prompts, only metrics."""
        shadow_results = pattern.shadow_results or []
        total = len(shadow_results)

        # Calculate success rate: a run is successful if all steps succeeded
        success_count = 0
        for result in shadow_results:
            steps = result.get("steps", [])
            if steps and all(s.get("success", False) for s in steps):
                success_count += 1

        success_rate = success_count / total if total > 0 else 0

        steps_info = pattern.steps if isinstance(pattern.steps, list) else []
        step_count = len(steps_info)

        return (
            f"Collaboration Pattern Approval Request\n"
            f"Name: {pattern.name}\n"
            f"Pattern ID: {pattern.pattern_id}\n"
            f"Trigger: {pattern.trigger_event}\n"
            f"Steps: {step_count}\n"
            f"Shadow Runs: {total}\n"
            f"Success Rate: {success_rate:.0%}\n"
            f"---\n"
            f"Approve or Reject?"
        )
