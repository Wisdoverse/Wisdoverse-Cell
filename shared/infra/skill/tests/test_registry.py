# shared/services/skill/tests/test_registry.py
"""
Tests for SkillRegistry - registration, lookup, and discovery.
"""
import sys
import types
from unittest.mock import patch

from shared.infra.skill.base import BaseSkill
from shared.infra.skill.models import Permission, SkillContext, SkillResult
from shared.infra.skill.registry import SkillRegistry


class MockSkill(BaseSkill):
    """Mock skill for testing."""

    name = "mock_skill"
    description = "A mock skill for testing"
    commands = ["/mock", "/m"]
    patterns = [r"mock me"]
    permissions = [Permission.GATEWAY_REPLY]

    async def execute(self, context: SkillContext) -> SkillResult:
        return SkillResult(success=True)


class AnotherMockSkill(BaseSkill):
    """Another mock skill for testing."""

    name = "another_skill"
    description = "Another mock skill"
    commands = ["/another"]
    patterns = []

    async def execute(self, context: SkillContext) -> SkillResult:
        return SkillResult(success=True)


class TestSkillRegistryRegistration:
    """Test skill registration functionality."""

    def test_register_adds_skill(self):
        """register() adds skill to registry."""
        registry = SkillRegistry()
        skill = MockSkill()

        registry.register(skill)

        assert registry.get("mock_skill") == skill

    def test_register_multiple_skills(self):
        """Can register multiple skills."""
        registry = SkillRegistry()
        skill1 = MockSkill()
        skill2 = AnotherMockSkill()

        registry.register(skill1)
        registry.register(skill2)

        assert registry.get("mock_skill") == skill1
        assert registry.get("another_skill") == skill2

    def test_register_overwrites_same_name(self):
        """Registering skill with same name overwrites previous."""
        registry = SkillRegistry()
        skill1 = MockSkill()

        class MockSkillV2(BaseSkill):
            name = "mock_skill"  # Same name
            description = "Version 2"

            async def execute(self, context: SkillContext) -> SkillResult:
                return SkillResult(success=True)

        skill2 = MockSkillV2()

        registry.register(skill1)
        registry.register(skill2)

        assert registry.get("mock_skill") == skill2


class TestSkillRegistryLookup:
    """Test skill lookup functionality."""

    def test_get_returns_skill_by_name(self):
        """get() returns skill by name."""
        registry = SkillRegistry()
        skill = MockSkill()
        registry.register(skill)

        result = registry.get("mock_skill")

        assert result == skill

    def test_get_returns_none_for_unknown(self):
        """get() returns None for unknown skill name."""
        registry = SkillRegistry()

        result = registry.get("nonexistent_skill")

        assert result is None

    def test_all_returns_all_skills(self):
        """all() returns list of all registered skills."""
        registry = SkillRegistry()
        skill1 = MockSkill()
        skill2 = AnotherMockSkill()
        registry.register(skill1)
        registry.register(skill2)

        result = registry.all()

        assert len(result) == 2
        assert skill1 in result
        assert skill2 in result

    def test_all_returns_empty_list_when_empty(self):
        """all() returns empty list when no skills registered."""
        registry = SkillRegistry()

        result = registry.all()

        assert result == []


class TestSkillRegistryCommandsMap:
    """Test commands_map() functionality."""

    def test_commands_map_builds_correct_mapping(self):
        """commands_map() maps commands to skills."""
        registry = SkillRegistry()
        skill = MockSkill()
        registry.register(skill)

        cmd_map = registry.commands_map()

        assert cmd_map["/mock"] == skill
        assert cmd_map["/m"] == skill

    def test_commands_map_multiple_skills(self):
        """commands_map() handles multiple skills."""
        registry = SkillRegistry()
        skill1 = MockSkill()
        skill2 = AnotherMockSkill()
        registry.register(skill1)
        registry.register(skill2)

        cmd_map = registry.commands_map()

        assert cmd_map["/mock"] == skill1
        assert cmd_map["/m"] == skill1
        assert cmd_map["/another"] == skill2

    def test_commands_map_empty_when_no_skills(self):
        """commands_map() returns empty dict when no skills."""
        registry = SkillRegistry()

        cmd_map = registry.commands_map()

        assert cmd_map == {}

    def test_commands_map_skill_without_commands(self):
        """commands_map() handles skills without commands."""

        class NoCommandSkill(BaseSkill):
            name = "no_command"
            description = "No commands"
            commands = []

            async def execute(self, context: SkillContext) -> SkillResult:
                return SkillResult(success=True)

        registry = SkillRegistry()
        registry.register(NoCommandSkill())

        cmd_map = registry.commands_map()

        assert cmd_map == {}

    def test_commands_map_warns_on_duplicate_command(self):
        """commands_map() logs warning on duplicate commands."""

        class DuplicateCommandSkill(BaseSkill):
            name = "duplicate"
            description = "Has duplicate command"
            commands = ["/mock"]  # Same as MockSkill

            async def execute(self, context: SkillContext) -> SkillResult:
                return SkillResult(success=True)

        registry = SkillRegistry()
        registry.register(MockSkill())
        registry.register(DuplicateCommandSkill())

        # Should complete without error, later registration wins
        cmd_map = registry.commands_map()

        # The duplicate command should map to the later-registered skill
        assert cmd_map["/mock"].name == "duplicate"


class TestSkillRegistryDiscover:
    """Test skill discovery functionality."""

    def test_discover_returns_count(self):
        """discover() returns number of discovered skills."""
        registry = SkillRegistry()

        # Create a mock package with skills
        mock_module = types.ModuleType("mock_skills")
        mock_module.MockSkill = MockSkill
        mock_module.AnotherMockSkill = AnotherMockSkill
        mock_module.__path__ = None  # Treat as module, not package

        with patch.dict(sys.modules, {"mock_skills": mock_module}):
            count = registry.discover("mock_skills")

        assert count == 2

    def test_discover_registers_found_skills(self):
        """discover() registers skills it finds."""
        registry = SkillRegistry()

        mock_module = types.ModuleType("test_skills")
        mock_module.MockSkill = MockSkill
        mock_module.__path__ = None

        with patch.dict(sys.modules, {"test_skills": mock_module}):
            registry.discover("test_skills")

        assert registry.get("mock_skill") is not None

    def test_discover_skips_base_skill(self):
        """discover() skips BaseSkill itself."""
        registry = SkillRegistry()

        mock_module = types.ModuleType("skills_with_base")
        mock_module.BaseSkill = BaseSkill
        mock_module.MockSkill = MockSkill
        mock_module.__path__ = None

        with patch.dict(sys.modules, {"skills_with_base": mock_module}):
            count = registry.discover("skills_with_base")

        # Should only count MockSkill, not BaseSkill
        assert count == 1

    def test_discover_handles_import_error(self):
        """discover() handles ImportError gracefully."""
        registry = SkillRegistry()

        count = registry.discover("nonexistent.package")

        assert count == 0

    def test_discover_skips_abstract_classes(self):
        """discover() skips abstract skill classes."""
        from abc import abstractmethod

        class AbstractSkill(BaseSkill):
            name = "abstract"
            description = "Abstract skill"

            @abstractmethod
            async def execute(self, context: SkillContext) -> SkillResult:
                ...

        registry = SkillRegistry()

        mock_module = types.ModuleType("abstract_skills")
        mock_module.AbstractSkill = AbstractSkill
        mock_module.MockSkill = MockSkill
        mock_module.__path__ = None

        with patch.dict(sys.modules, {"abstract_skills": mock_module}):
            count = registry.discover("abstract_skills")

        # Should only count MockSkill, not AbstractSkill
        assert count == 1
        assert registry.get("abstract") is None
        assert registry.get("mock_skill") is not None

    def test_discover_handles_instantiation_error(self):
        """discover() handles skill instantiation errors."""

        class BrokenSkill(BaseSkill):
            name = "broken"
            description = "Broken skill"

            def __init__(self):
                raise RuntimeError("Cannot instantiate")

            async def execute(self, context: SkillContext) -> SkillResult:
                return SkillResult(success=True)

        registry = SkillRegistry()

        mock_module = types.ModuleType("broken_skills")
        mock_module.BrokenSkill = BrokenSkill
        mock_module.MockSkill = MockSkill
        mock_module.__path__ = None

        with patch.dict(sys.modules, {"broken_skills": mock_module}):
            count = registry.discover("broken_skills")

        # Should only count MockSkill, BrokenSkill failed to instantiate
        assert count == 1
        assert registry.get("broken") is None
