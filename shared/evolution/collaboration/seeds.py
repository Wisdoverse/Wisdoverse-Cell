"""
Seed collaboration patterns — pre-defined patterns shipped with the system.

These patterns are loaded on first boot and start in PROPOSED status,
requiring shadow validation and human approval before going active.
"""

from .models import CollaborationPattern, CollaborationStep, PatternStatus

RISK_REVIEW_V2 = CollaborationPattern(
    pattern_id="risk-review-v2",
    name="Risk Double Review",
    status=PatternStatus.PROPOSED,
    trigger_event="sync.completed",
    trigger_condition="payload.task_count > 0",
    steps=[
        CollaborationStep(
            step_id="analyze",
            agent_id="analysis-module",
            action="analyze",
            skill_id="analysis.risk-scan",
            output_to="review",
        ),
        CollaborationStep(
            step_id="review",
            agent_id="pjm-agent",
            action="review",
            skill_id="pm.risk-assess",
            input_from="analyze",
            output_to="decide",
        ),
        CollaborationStep(
            step_id="decide",
            agent_id="evolution-module",
            action="decide",
            skill_id="evolution.consensus-check",
            input_from="review",
            on_failure="fallback_to:escalate",
        ),
        CollaborationStep(
            step_id="escalate",
            agent_id="chat-agent",
            action="notify",
            skill_id="chat.human-escalation",
            input_from="review",
        ),
    ],
)

COLLABORATION_SEEDS = [RISK_REVIEW_V2]
