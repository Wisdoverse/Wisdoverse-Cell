"""
Skill Base Classes - Foundation for all skills in the system.

Defines SkillParameter for parameter specification and BaseSkill as the
abstract base class that all skills must inherit from.
"""
from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, Field

from shared.infra.skill.models import Permission, SkillContext, SkillResult


class SkillParameter(BaseModel):
    """Parameter definition for a skill.

    Used to declare what parameters a skill accepts, their types,
    and whether they are required.
    """

    name: str = Field(..., description="Parameter name")
    param_type: type = Field(..., description="Python type (str, int, etc.)")
    required: bool = Field(default=True, description="Whether the parameter is required")
    default: Any = Field(default=None, description="Default value if not provided")
    description: Optional[str] = Field(
        default=None, description="Human-readable description"
    )

    model_config = {"arbitrary_types_allowed": True}


class BaseSkill(ABC):
    """Abstract base class for all skills.

    Subclasses must define:
    - name: Unique skill identifier (e.g., "export_prd")
    - description: Human-readable description
    - execute(): The skill's main logic

    Optional overrides:
    - commands: Slash commands that trigger this skill (e.g., ["/export_prd", "/prd"])
    - patterns: Regex patterns for natural language matching
    - permissions: Required permissions for resource access
    - parameters: Parameter definitions
    """

    # Metadata - subclasses must override these
    name: str
    description: str

    # Trigger conditions - optional
    commands: list[str] = []
    patterns: list[str] = []

    # Permission declarations - default allows gateway reply only
    permissions: list[Permission] = [Permission.GATEWAY_REPLY]

    # Parameter definitions - optional
    parameters: list[SkillParameter] = []

    @abstractmethod
    async def execute(self, context: SkillContext) -> SkillResult:
        """Execute the skill logic.

        Args:
            context: Execution context with message, user, parameters,
                    and permission-injected resources (db, redis, etc.)

        Returns:
            SkillResult indicating success/failure and optional response.

        Raises:
            SkillError: For user-visible business errors.
        """
        ...
