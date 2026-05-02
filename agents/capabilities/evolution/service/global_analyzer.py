"""
GlobalAnalyzer — Cross-agent trace analysis for architecture-level suggestions.

Analyzes all agents' recent execution traces and uses LLM to propose
architecture-level optimizations (suggestion mode only, Phase 2).
"""

import json

from shared.utils.logger import get_logger

logger = get_logger("evolution_agent.global_analyzer")

# Operation whitelist (from design spec Section 5.2)
ALLOWED_OPERATIONS = [
    "add_skill",
    "adjust_skill_ordering",
    "modify_event_subscription",
    "adjust_sampling_parameters",
    "add_loop_logic",
]

# Known agent IDs in the system
_KNOWN_AGENT_IDS = [
    "pjm-agent",
    "analysis-agent",
    "chat-agent",
    "sync-agent",
    "requirement-manager",
    "qa-agent",
]


class GlobalAnalyzer:
    """Cross-agent trace analysis for architecture-level suggestions."""

    def __init__(self, llm_gateway):
        self._llm = llm_gateway

    async def analyze(self, db_manager, days: int = 7) -> list[dict]:
        """Analyze all agents' recent traces and return proposals.

        Each proposal is a dict with:
        - operation: str (from ALLOWED_OPERATIONS)
        - target_agent: str
        - target_skill: str (optional)
        - description: str
        - rationale: str
        - confidence: float (0-1)
        """
        if db_manager is None:
            logger.warning("global_analysis_skipped", reason="db_manager is None")
            return []

        if self._llm is None:
            logger.warning("global_analysis_skipped", reason="llm_gateway is None")
            return []

        try:
            async with db_manager.session() as session:
                from shared.evolution.db.repository import EvolutionRepository

                repo = EvolutionRepository(session)

                # Gather data from all agents
                summaries = []
                for agent_id in _KNOWN_AGENT_IDS:
                    traces = await repo.get_recent_traces(agent_id, limit=100)
                    if traces:
                        success = sum(1 for t in traces if t.success)
                        total = len(traces)
                        summaries.append(
                            f"- {agent_id}: {success}/{total} success ({success / total:.0%})"
                        )

            if not summaries:
                return []

            prompt = f"""You are the architecture evolution engine for Wisdoverse Cell.

Analyze the following agent performance data from the last {days} days:

{chr(10).join(summaries)}

Propose 0-3 improvements. Each must be one of: {ALLOWED_OPERATIONS}

Return a JSON array of proposals:
[{{"operation": "...", "target_agent": "...", "target_skill": "...",
"description": "...", "rationale": "...", "confidence": 0.8}}]

Rules:
- Only propose if confidence > 0.6
- You CANNOT: delete agents, modify EventBus, change DB schema, modify security code
- Return [] if no improvements needed"""

            response = await self._llm.complete(
                prompt=prompt,
                agent_id="evolution-agent",
                task_type="global_analysis",
                max_tokens=2048,
                temperature=0.2,
            )

            proposals = json.loads(response)
            # Filter to whitelist
            return [p for p in proposals if p.get("operation") in ALLOWED_OPERATIONS]
        except Exception as e:
            logger.error("global_analysis_failed", error=str(e))
            return []
