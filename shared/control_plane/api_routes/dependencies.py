"""Shared dependency type aliases for Control Plane route modules."""

from collections.abc import AsyncGenerator, Callable
from typing import Any

from ..store_factory import ControlPlaneStores
from ..unit_of_work import ControlPlaneUnitOfWork

StoresDependency = Callable[[], AsyncGenerator[ControlPlaneStores, None]]
UnitOfWorkDependency = Callable[[], AsyncGenerator[ControlPlaneUnitOfWork, None]]
CompanyResolver = Callable[[str | None], str]


def clean_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError("must be a list")
    return [str(item).strip() for item in value if str(item).strip()]
