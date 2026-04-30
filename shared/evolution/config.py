"""
Evolution Config — settings for the self-evolution system.

All values can be overridden via environment variables with the ``EVOLUTION_`` prefix,
e.g. ``EVOLUTION_ENABLED=false`` or ``EVOLUTION_TRACE_SAMPLING_RATE=0.5``.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EvolutionSettings(BaseSettings):
    """Configuration for the evolution subsystem."""

    model_config = SettingsConfigDict(env_prefix="EVOLUTION_")

    enabled: bool = True
    trace_sampling_rate: float = 1.0  # 0.0 to 1.0
    self_reflect_interval: int = 50  # Every N executions
    rollback_threshold: float = 0.10
    min_samples: int = 10
    max_rollbacks_per_day: int = 3
    max_prompt_length: int = 50_000

    # Phase 2: auto-optimization, canary routing, semantic evaluation
    auto_optimize: bool = False
    canary_enabled: bool = False
    evaluator_semantic_enabled: bool = False

    # Phase 3: collaboration patterns
    collaboration_enabled: bool = False
    shadow_max_concurrent: int = 3
    shadow_min_runs_for_approval: int = 20
    admin_chat_id: str = ""
    admin_user_ids: list[str] = Field(default_factory=list)


evolution_settings = EvolutionSettings()
