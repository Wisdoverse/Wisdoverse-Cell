"""Lazy compatibility aliases for moved agent packages."""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import sys

_ALIASES: dict[str, str] = {}
_FINDER_INSTALLED = False


class _AliasLoader(importlib.abc.Loader):
    def __init__(self, alias_name: str, target_name: str) -> None:
        self._alias_name = alias_name
        self._target_name = target_name

    def create_module(self, spec):
        module = importlib.import_module(self._target_name)
        sys.modules[self._alias_name] = module
        return module

    def exec_module(self, module) -> None:
        sys.modules[self._alias_name] = module


class _AliasFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path=None, target=None):
        for alias_name, target_name in _ALIASES.items():
            if fullname == alias_name:
                mapped_name = target_name
            elif fullname.startswith(f"{alias_name}."):
                mapped_name = f"{target_name}{fullname[len(alias_name):]}"
            else:
                continue

            mapped_spec = importlib.util.find_spec(mapped_name)
            if mapped_spec is None:
                return None
            is_package = mapped_spec.submodule_search_locations is not None
            spec = importlib.util.spec_from_loader(
                fullname,
                _AliasLoader(fullname, mapped_name),
                is_package=is_package,
            )
            if spec is not None and is_package:
                spec.submodule_search_locations = mapped_spec.submodule_search_locations
            return spec
        return None


def alias_package(alias_name: str, target_name: str) -> None:
    """Map a legacy package name and all its submodules to a new package."""
    global _FINDER_INSTALLED

    _ALIASES[alias_name] = target_name
    target_module = importlib.import_module(target_name)
    sys.modules[alias_name] = target_module

    if not _FINDER_INSTALLED:
        sys.meta_path.insert(0, _AliasFinder())
        _FINDER_INSTALLED = True

