"""Deprecated compatibility shim for requirement Feishu card templates."""

from shared.integrations.feishu.cards.requirement import (
    FeishuRequirementCardRenderer,
    build_batch_confirmation_card,
    build_batch_result_card,
    build_bot_help_card,
    build_calendar_reminder_card,
    build_prd_preview_card,
    build_requirement_confirmed_card,
    build_requirement_detail_card,
    build_requirement_extracted_card,
    build_requirement_list_card,
    build_requirement_rejected_card,
)

__all__ = [
    "FeishuRequirementCardRenderer",
    "build_batch_confirmation_card",
    "build_batch_result_card",
    "build_bot_help_card",
    "build_calendar_reminder_card",
    "build_prd_preview_card",
    "build_requirement_confirmed_card",
    "build_requirement_detail_card",
    "build_requirement_extracted_card",
    "build_requirement_list_card",
    "build_requirement_rejected_card",
]
