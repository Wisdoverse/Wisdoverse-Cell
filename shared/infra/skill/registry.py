"""
Skill Registry - Auto-discovery and registration of skills.

Provides automatic scanning of packages to find and register BaseSkill subclasses.
"""
from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from typing import Optional

from shared.infra.skill.base import BaseSkill

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Skill registry with automatic discovery and registration.

    Manages a collection of skills, supporting both manual registration
    and automatic discovery from packages.
    """

    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        """Manually register a skill.

        Args:
            skill: The skill instance to register.
        """
        self._skills[skill.name] = skill
        logger.debug("Registered skill: %s", skill.name)

    def discover(self, package: str) -> int:
        """Scan package for BaseSkill subclasses and register them.

        Recursively scans the given package and all subpackages for classes
        that inherit from BaseSkill, instantiates them, and registers them.

        Args:
            package: The package name to scan (e.g., "skills").

        Returns:
            Number of skills discovered and registered.
        """
        discovered_count = 0

        try:
            pkg = importlib.import_module(package)
        except ImportError:
            logger.warning("Failed to import package: %s", package)
            return 0

        # Get the package path for scanning submodules
        pkg_path = getattr(pkg, "__path__", None)
        if pkg_path is None:
            # It's a module, not a package - scan just this module
            discovered_count += self._scan_module(pkg)
            return discovered_count

        # Recursively scan all modules in the package
        for _importer, modname, _ispkg in pkgutil.walk_packages(
            pkg_path, prefix=f"{package}."
        ):
            try:
                module = importlib.import_module(modname)
                discovered_count += self._scan_module(module)
            except ImportError as e:
                logger.warning("Failed to import module %s: %s", modname, e)
                continue

        logger.info(
            "Discovered %d skills from package: %s", discovered_count, package
        )
        return discovered_count

    def _scan_module(self, module: object) -> int:
        """Scan a module for BaseSkill subclasses.

        Args:
            module: The module object to scan.

        Returns:
            Number of skills found and registered.
        """
        count = 0

        for _name, obj in inspect.getmembers(module, inspect.isclass):
            # Check if it's a subclass of BaseSkill (but not BaseSkill itself)
            if not issubclass(obj, BaseSkill) or obj is BaseSkill:
                continue

            # Skip abstract classes
            if inspect.isabstract(obj):
                logger.debug("Skipping abstract class: %s", obj.__name__)
                continue

            # Instantiate and register
            try:
                skill_instance = obj()
                self.register(skill_instance)
                count += 1
            except Exception as e:
                logger.warning(
                    "Failed to instantiate skill %s: %s", obj.__name__, e
                )
                continue

        return count

    def get(self, name: str) -> Optional[BaseSkill]:
        """Get a skill by name.

        Args:
            name: The skill's unique name identifier.

        Returns:
            The skill instance, or None if not found.
        """
        return self._skills.get(name)

    def all(self) -> list[BaseSkill]:
        """Get all registered skills.

        Returns:
            List of all registered skill instances.
        """
        return list(self._skills.values())

    def commands_map(self) -> dict[str, BaseSkill]:
        """Build a map from commands to skills.

        Creates a dictionary mapping each command (e.g., "/prd") to its
        corresponding skill. Useful for fast command-based lookups.

        Returns:
            Dictionary mapping command strings to skill instances.
            Example: {"/prd": export_prd_skill, "/export_prd": export_prd_skill}
        """
        cmd_map: dict[str, BaseSkill] = {}

        for skill in self._skills.values():
            for command in skill.commands:
                if command in cmd_map:
                    logger.warning(
                        "Command %s already registered by %s, overwriting with %s",
                        command,
                        cmd_map[command].name,
                        skill.name,
                    )
                cmd_map[command] = skill

        return cmd_map
