# shared/services/skill/tests/test_matcher.py
"""
Tests for SkillMatcher - command, pattern, and LLM matching.
"""
from unittest.mock import MagicMock

import pytest

from shared.infra.skill.base import BaseSkill, SkillParameter
from shared.infra.skill.matcher import SkillMatcher
from shared.infra.skill.models import SkillContext, SkillResult
from shared.infra.skill.registry import SkillRegistry


class HelpSkill(BaseSkill):
    """Help skill for testing."""

    name = "help"
    description = "Show available skills"
    commands = ["/help", "/h"]
    patterns = [r"有什么技能", r"what can you do", r"帮助"]

    async def execute(self, context: SkillContext) -> SkillResult:
        return SkillResult(success=True)


class ExportPrdSkill(BaseSkill):
    """PRD export skill for testing."""

    name = "export_prd"
    description = "Export PRD document"
    commands = ["/prd", "/export_prd"]
    patterns = [r"导出.*PRD", r"生成.*文档"]
    parameters = [
        SkillParameter(name="req_id", param_type=str, required=True),
        SkillParameter(name="format", param_type=str, required=False, default="md"),
    ]

    async def execute(self, context: SkillContext) -> SkillResult:
        return SkillResult(success=True)


class PatternWithGroupsSkill(BaseSkill):
    """Skill with named groups in patterns for testing."""

    name = "pattern_groups"
    description = "Skill with named capture groups"
    commands = []
    patterns = [r"查询需求\s+(?P<req_id>REQ\d+)"]

    async def execute(self, context: SkillContext) -> SkillResult:
        return SkillResult(success=True)


@pytest.fixture
def registry() -> SkillRegistry:
    """Create a registry with test skills."""
    registry = SkillRegistry()
    registry.register(HelpSkill())
    registry.register(ExportPrdSkill())
    registry.register(PatternWithGroupsSkill())
    return registry


@pytest.fixture
def matcher(registry: SkillRegistry) -> SkillMatcher:
    """Create a matcher with the test registry."""
    return SkillMatcher(registry=registry)


class TestCommandMatching:
    """Test command matching functionality."""

    @pytest.mark.asyncio
    async def test_command_match_help(self, matcher: SkillMatcher):
        """/help matches HelpSkill."""
        match = await matcher.match("/help")

        assert match is not None
        assert match.skill.name == "help"
        assert match.confidence == 1.0
        assert match.match_type == "command"

    @pytest.mark.asyncio
    async def test_command_match_alias(self, matcher: SkillMatcher):
        """Command aliases work (/h for help)."""
        match = await matcher.match("/h")

        assert match is not None
        assert match.skill.name == "help"

    @pytest.mark.asyncio
    async def test_command_with_args(self, matcher: SkillMatcher):
        """/prd REQ123 extracts parameters."""
        match = await matcher.match("/prd REQ123")

        assert match is not None
        assert match.skill.name == "export_prd"
        assert match.parameters["req_id"] == "REQ123"
        assert match.match_type == "command"

    @pytest.mark.asyncio
    async def test_command_with_multiple_args(self, matcher: SkillMatcher):
        """Command with multiple args extracts all parameters."""
        match = await matcher.match("/prd REQ456 pdf")

        assert match is not None
        assert match.parameters["req_id"] == "REQ456"
        assert match.parameters["format"] == "pdf"

    @pytest.mark.asyncio
    async def test_command_with_default_param(self, matcher: SkillMatcher):
        """Missing optional param uses default."""
        match = await matcher.match("/prd REQ789")

        assert match is not None
        assert match.parameters["req_id"] == "REQ789"
        # format uses default "md"
        assert match.parameters.get("format") == "md"

    @pytest.mark.asyncio
    async def test_command_case_insensitive(self, matcher: SkillMatcher):
        """Commands are case-insensitive."""
        match = await matcher.match("/HELP")

        assert match is not None
        assert match.skill.name == "help"

    @pytest.mark.asyncio
    async def test_command_unknown(self, matcher: SkillMatcher):
        """Unknown command returns None."""
        match = await matcher.match("/unknown")

        assert match is None

    @pytest.mark.asyncio
    async def test_command_no_args_when_required(self, matcher: SkillMatcher):
        """Command without required args still matches (params empty)."""
        match = await matcher.match("/prd")

        assert match is not None
        assert match.parameters == {}


class TestPatternMatching:
    """Test regex pattern matching functionality."""

    @pytest.mark.asyncio
    async def test_pattern_match_chinese(self, matcher: SkillMatcher):
        """Chinese pattern matches."""
        match = await matcher.match("有什么技能")

        assert match is not None
        assert match.skill.name == "help"
        assert match.confidence == 0.8
        assert match.match_type == "pattern"

    @pytest.mark.asyncio
    async def test_pattern_match_english(self, matcher: SkillMatcher):
        """English pattern matches."""
        match = await matcher.match("what can you do")

        assert match is not None
        assert match.skill.name == "help"

    @pytest.mark.asyncio
    async def test_pattern_match_partial(self, matcher: SkillMatcher):
        """Pattern can match part of message."""
        match = await matcher.match("请问有什么技能可以用？")

        assert match is not None
        assert match.skill.name == "help"

    @pytest.mark.asyncio
    async def test_pattern_match_prd_export(self, matcher: SkillMatcher):
        """PRD export pattern matches."""
        match = await matcher.match("帮我导出这个PRD")

        assert match is not None
        assert match.skill.name == "export_prd"

    @pytest.mark.asyncio
    async def test_pattern_extracts_named_groups(self, matcher: SkillMatcher):
        """Pattern with named groups extracts parameters."""
        match = await matcher.match("查询需求 REQ123")

        assert match is not None
        assert match.skill.name == "pattern_groups"
        assert match.parameters["req_id"] == "REQ123"

    @pytest.mark.asyncio
    async def test_pattern_case_insensitive(self, matcher: SkillMatcher):
        """Pattern matching is case-insensitive."""
        match = await matcher.match("What Can You Do")

        assert match is not None
        assert match.skill.name == "help"

    @pytest.mark.asyncio
    async def test_no_pattern_match(self, matcher: SkillMatcher):
        """No matching pattern returns None."""
        match = await matcher.match("random message without any match")

        assert match is None


class TestMatchPriority:
    """Test that command matching has priority over pattern matching."""

    @pytest.mark.asyncio
    async def test_command_priority_over_pattern(self, registry: SkillRegistry):
        """Command matching takes priority over pattern matching."""

        class DualTriggerSkill(BaseSkill):
            name = "dual_trigger"
            description = "Can be triggered by command or pattern"
            commands = ["/dual"]
            patterns = [r"/dual"]  # Pattern that matches the command

            async def execute(self, context: SkillContext) -> SkillResult:
                return SkillResult(success=True)

        registry.register(DualTriggerSkill())
        matcher = SkillMatcher(registry=registry)

        match = await matcher.match("/dual")

        assert match is not None
        assert match.match_type == "command"  # Command takes priority
        assert match.confidence == 1.0

    @pytest.mark.asyncio
    async def test_pattern_used_when_command_not_found(self, matcher: SkillMatcher):
        """Pattern matching is used when no command matches."""
        # A message that starts with / but is not a registered command
        # should fall through to pattern matching
        match = await matcher.match("有什么技能")

        assert match is not None
        assert match.match_type == "pattern"


class TestNoMatch:
    """Test cases where no skill matches."""

    @pytest.mark.asyncio
    async def test_empty_message(self, matcher: SkillMatcher):
        """Empty message returns None."""
        match = await matcher.match("")

        assert match is None

    @pytest.mark.asyncio
    async def test_whitespace_message(self, matcher: SkillMatcher):
        """Whitespace-only message returns None."""
        match = await matcher.match("   ")

        assert match is None

    @pytest.mark.asyncio
    async def test_no_match_returns_none(self, matcher: SkillMatcher):
        """Unrelated message returns None."""
        match = await matcher.match("今天天气怎么样")

        assert match is None


class TestLLMMatching:
    """Test LLM-based matching (Phase 2 placeholder)."""

    @pytest.mark.asyncio
    async def test_llm_matching_without_client(self, registry: SkillRegistry):
        """Without LLM client, returns None for unmatched messages."""
        matcher = SkillMatcher(registry=registry, llm_client=None)

        match = await matcher.match("complex intent that needs LLM")

        assert match is None

    @pytest.mark.asyncio
    async def test_llm_matching_with_client_placeholder(self, registry: SkillRegistry):
        """With LLM client, currently returns None (Phase 2)."""
        mock_llm = MagicMock()
        matcher = SkillMatcher(registry=registry, llm_client=mock_llm)

        # Currently _match_with_llm returns None as placeholder
        match = await matcher.match("complex intent that needs LLM")

        # In Phase 2, this would return a SkillMatch with match_type="llm"
        assert match is None
