"""Portable, side-effect-free company template DTOs and serialization."""

from __future__ import annotations

import ipaddress
import math
import re
from collections.abc import Iterable, Mapping
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class CompanyTemplateError(ValueError):
    """Raised when a company template is unsafe or internally inconsistent."""


class _TemplateModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _portable_text(value: str) -> str:
    text = value.strip()
    if _SECRET_ASSIGNMENT.search(text) or _looks_like_private_url(text):
        raise ValueError("portable_field_contains_sensitive_value")
    return text


_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_ -]?key|access[_ -]?token|refresh[_ -]?token|secret|password|credential)\b\s*[:=]"
    r"|\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"
    r"|\b(?:sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16})\b"
)
_URL = re.compile(r"(?i)\b(?:https?|ftp)://[^\s\]\[()<>\"']+")


def _looks_like_private_url(value: str) -> bool:
    for match in _URL.finditer(value):
        parsed = urlsplit(match.group(0).rstrip(".,;"))
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.username or parsed.password:
            return True
        if host in {"localhost", "localhost.localdomain"} or host.endswith(
            (".local", ".internal", ".private")
        ):
            return True
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            continue
        if not address.is_global:
            return True
    return False


class CompanyTemplateCompany(_TemplateModel):
    name: str = Field(min_length=1, max_length=256)
    mission: str = Field(default="", max_length=4000)

    @field_validator("name", "mission")
    @classmethod
    def _safe_text(cls, value: str) -> str:
        return _portable_text(value)


class CompanyTemplateGoal(_TemplateModel):
    local_key: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=512)
    description: str = Field(default="", max_length=20_000)
    parent_key: str | None = Field(default=None, max_length=64)
    owner_role_key: str | None = Field(default=None, max_length=64)

    @field_validator("local_key", "title", "description", "parent_key", "owner_role_key")
    @classmethod
    def _safe_text(cls, value: str | None) -> str | None:
        return _portable_text(value) if value is not None else None


class CompanyTemplateRole(_TemplateModel):
    local_key: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=256)
    role: str = Field(min_length=1, max_length=128)
    title: str = Field(default="", max_length=256)
    responsibilities: list[str] = Field(default_factory=list, max_length=100)
    permissions: list[str] = Field(default_factory=list, max_length=50)
    skill_references: list[str] = Field(default_factory=list, max_length=100)
    reports_to_key: str | None = Field(default=None, max_length=64)
    budget_key: str | None = Field(default=None, max_length=64)

    @field_validator("local_key", "display_name", "role", "title", "reports_to_key", "budget_key")
    @classmethod
    def _safe_text(cls, value: str | None) -> str | None:
        return _portable_text(value) if value is not None else None

    @field_validator("responsibilities", "permissions", "skill_references")
    @classmethod
    def _safe_strings(cls, values: list[str]) -> list[str]:
        return [_portable_text(value) for value in values]


class CompanyTemplatePlaybookStep(_TemplateModel):
    role_key: str = Field(min_length=1, max_length=64)
    action: str = Field(min_length=1, max_length=2000)

    @field_validator("role_key", "action")
    @classmethod
    def _safe_text(cls, value: str) -> str:
        return _portable_text(value)


class CompanyTemplateBudget(_TemplateModel):
    local_key: str = Field(min_length=1, max_length=64)
    scope: Literal["company", "goal", "agent"]
    scope_key: str | None = Field(default=None, max_length=64)
    period: Literal["daily", "monthly", "quarterly", "total"]
    ceiling_usd: float = Field(gt=0)
    warning_ratio: float = Field(default=0.8, gt=0, le=1)
    model_allowlist: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("local_key", "scope_key")
    @classmethod
    def _safe_keys(cls, value: str | None) -> str | None:
        return _portable_text(value) if value is not None else None

    @field_validator("ceiling_usd", "warning_ratio")
    @classmethod
    def _finite_number(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("portable_budget_numeric_value_must_be_finite")
        return value

    @field_validator("model_allowlist")
    @classmethod
    def _safe_model_names(cls, values: list[str]) -> list[str]:
        return [_portable_text(value) for value in values]


class CompanyTemplatePlaybook(_TemplateModel):
    key: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=256)
    steps: list[CompanyTemplatePlaybookStep] = Field(default_factory=list, max_length=100)

    @field_validator("key", "title")
    @classmethod
    def _safe_text(cls, value: str) -> str:
        return _portable_text(value)


class CompanyTemplate(_TemplateModel):
    schema_version: Literal["1.0"] = "1.0"
    company: CompanyTemplateCompany
    goals: list[CompanyTemplateGoal] = Field(default_factory=list, max_length=500)
    roles: list[CompanyTemplateRole] = Field(default_factory=list, max_length=200)
    budgets: list[CompanyTemplateBudget] = Field(default_factory=list, max_length=500)
    playbooks: list[CompanyTemplatePlaybook] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _validate_references(self) -> CompanyTemplate:
        goal_keys = [goal.local_key for goal in self.goals]
        role_keys = [role.local_key for role in self.roles]
        budget_keys = [budget.local_key for budget in self.budgets]
        playbook_keys = [playbook.key for playbook in self.playbooks]
        _require_unique(goal_keys, "duplicate_goal_local_key")
        _require_unique(role_keys, "duplicate_role_local_key")
        _require_unique(budget_keys, "duplicate_budget_local_key")
        _require_unique(playbook_keys, "duplicate_playbook_key")

        goals_by_key = {goal.local_key: goal for goal in self.goals}
        for goal in self.goals:
            if goal.parent_key is not None and goal.parent_key not in goals_by_key:
                raise ValueError("dangling_goal_parent_reference")
            seen: set[str] = set()
            cursor: str | None = goal.local_key
            while cursor is not None:
                if cursor in seen:
                    raise ValueError("goal_parent_cycle")
                seen.add(cursor)
                parent = goals_by_key.get(cursor)
                cursor = parent.parent_key if parent else None

        role_key_set = set(role_keys)
        budget_key_set = set(budget_keys)
        budgets_by_key = {budget.local_key: budget for budget in self.budgets}
        for goal in self.goals:
            if goal.owner_role_key is not None and goal.owner_role_key not in role_key_set:
                raise ValueError("dangling_goal_owner_role_reference")

        roles_by_key = {role.local_key: role for role in self.roles}
        for role in self.roles:
            if role.reports_to_key is not None and role.reports_to_key not in roles_by_key:
                raise ValueError("dangling_role_reports_to_reference")
            if role.budget_key is not None and role.budget_key not in budget_key_set:
                raise ValueError("dangling_role_budget_reference")
            linked_budget = budgets_by_key.get(role.budget_key) if role.budget_key else None
            if (
                linked_budget is not None
                and linked_budget.scope == "agent"
                and linked_budget.scope_key != role.local_key
            ):
                raise ValueError("role_budget_scope_mismatch")
            role_seen: set[str] = set()
            role_cursor: str | None = role.local_key
            while role_cursor is not None:
                if role_cursor in role_seen:
                    raise ValueError("role_reporting_cycle")
                role_seen.add(role_cursor)
                manager = roles_by_key.get(role_cursor)
                role_cursor = manager.reports_to_key if manager else None

        goals_key_set = set(goal_keys)
        for budget in self.budgets:
            if budget.scope == "company" and budget.scope_key is not None:
                raise ValueError("company_budget_must_not_have_scope_key")
            if budget.scope == "goal" and budget.scope_key not in goals_key_set:
                raise ValueError("dangling_budget_goal_scope_reference")
            if budget.scope == "agent" and budget.scope_key not in role_key_set:
                raise ValueError("dangling_budget_role_scope_reference")
        for playbook in self.playbooks:
            for step in playbook.steps:
                if step.role_key not in role_key_set:
                    raise ValueError("dangling_playbook_role_reference")
        return self


def _require_unique(values: list[str], error: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(error)


def validate_company_template(value: CompanyTemplate | Mapping[str, Any]) -> CompanyTemplate:
    """Parse and validate an import payload without creating runtime state."""
    try:
        if isinstance(value, CompanyTemplate):
            # Revalidate even an existing DTO in case it came from an unchecked copy.
            return CompanyTemplate.model_validate(value.model_dump(mode="python"))
        return CompanyTemplate.model_validate(value)
    except (ValidationError, ValueError, TypeError) as exc:
        # Keep source values out of API/log-facing error text.
        raise CompanyTemplateError("invalid_company_template") from exc


def export_company_template(
    company: Any,
    goals: Iterable[Any],
    roles: Iterable[Any],
    playbooks: Iterable[CompanyTemplatePlaybook | Mapping[str, Any]] | None = None,
    budgets: Iterable[Any] | None = None,
) -> CompanyTemplate:
    """Export only the portable allowlisted fields from domain records."""
    try:
        return _export_company_template(company, goals, roles, playbooks, budgets)
    except CompanyTemplateError:
        raise
    except (ValidationError, ValueError, TypeError) as exc:
        # Validation errors can include the rejected input; never surface it.
        raise CompanyTemplateError("invalid_company_template") from exc


def _export_company_template(
    company: Any,
    goals: Iterable[Any],
    roles: Iterable[Any],
    playbooks: Iterable[CompanyTemplatePlaybook | Mapping[str, Any]] | None,
    budgets: Iterable[Any] | None,
) -> CompanyTemplate:
    goal_records = list(goals)
    role_records = list(roles)
    all_budget_records = list(budgets or ())
    company_id = _attribute(company, "company_id")
    if any(
        _attribute(record, "company_id") != company_id
        for record in [*goal_records, *role_records, *all_budget_records]
    ):
        raise CompanyTemplateError("company_template_records_must_share_company")
    budget_records = [
        budget for budget in all_budget_records if _attribute(budget, "scope") != "work_item"
    ]

    goal_ids = [_attribute(goal, "goal_id") for goal in goal_records]
    role_ids = [_attribute(role, "agent_id") for role in role_records]
    _unique_ids(goal_ids, "duplicate_goal_source_id")
    _unique_ids(role_ids, "duplicate_role_source_id")
    goal_keys = _portable_goal_keys(goal_records, goal_ids)
    playbook_records = list(playbooks or [])
    role_keys = _portable_role_keys(role_records, role_ids, has_playbooks=bool(playbook_records))
    role_key_by_id = {identifier: key for identifier, key in role_keys.items()}
    budget_ids = [_attribute(budget, "budget_id") for budget in budget_records]
    _unique_ids(budget_ids, "duplicate_budget_source_id")
    budget_keys = _portable_budget_keys(budget_records, budget_ids)
    budget_key_by_id = {identifier: key for identifier, key in budget_keys.items()}

    dto_goals = []
    for record, identifier in zip(goal_records, goal_ids, strict=True):
        parent_id = _attribute(record, "parent_goal_id", default=None)
        if parent_id is not None and parent_id not in goal_keys:
            raise CompanyTemplateError("dangling_goal_parent_reference")
        owner_id = _attribute(record, "owner_agent_id", default=None)
        if owner_id is not None and owner_id not in role_key_by_id:
            raise CompanyTemplateError("dangling_goal_owner_role_reference")
        dto_goals.append(
            CompanyTemplateGoal(
                local_key=goal_keys[identifier],
                title=_attribute(record, "title"),
                description=_attribute(record, "description", default=""),
                parent_key=goal_keys.get(parent_id),
                owner_role_key=role_key_by_id.get(owner_id),
            )
        )

    dto_roles = []
    for record, identifier in zip(role_records, role_ids, strict=True):
        manager_id = _attribute(record, "reports_to_agent_id", default=None)
        if manager_id is not None and manager_id not in role_key_by_id:
            raise CompanyTemplateError("dangling_role_reports_to_reference")
        budget_id = _attribute(record, "budget_policy_id", default=None)
        dto_roles.append(
            CompanyTemplateRole(
                local_key=role_keys[identifier],
                display_name=_attribute(record, "display_name"),
                role=_attribute(record, "role"),
                title=_attribute(record, "title", default=""),
                responsibilities=list(_attribute(record, "responsibilities", default=[]) or []),
                permissions=list(_attribute(record, "permissions", default=[]) or []),
                skill_references=list(_attribute(record, "skill_references", default=[]) or []),
                reports_to_key=role_key_by_id.get(manager_id),
                budget_key=budget_key_by_id.get(budget_id),
            )
        )

    goal_key_by_id = {identifier: key for identifier, key in goal_keys.items()}
    dto_budgets = []
    for record, identifier in zip(budget_records, budget_ids, strict=True):
        scope = _attribute(record, "scope")
        scope_id = _attribute(record, "scope_id", default=None)
        if scope == "company":
            scope_key = None
        elif scope == "goal":
            if scope_id not in goal_key_by_id:
                raise CompanyTemplateError("dangling_budget_goal_scope_reference")
            scope_key = goal_key_by_id[scope_id]
        elif scope == "agent":
            if scope_id not in role_key_by_id:
                raise CompanyTemplateError("dangling_budget_role_scope_reference")
            scope_key = role_key_by_id[scope_id]
        else:
            raise CompanyTemplateError("unsupported_portable_budget_scope")
        dto_budgets.append(
            CompanyTemplateBudget(
                local_key=budget_keys[identifier],
                scope=scope,
                scope_key=scope_key,
                period=_attribute(record, "period"),
                ceiling_usd=_attribute(record, "limit_usd"),
                warning_ratio=_attribute(record, "warning_threshold", default=0.8),
                model_allowlist=list(_attribute(record, "model_allowlist", default=[]) or []),
            )
        )

    dto_playbooks: list[CompanyTemplatePlaybook] = []
    for playbook in playbook_records:
        if isinstance(playbook, CompanyTemplatePlaybook):
            dto_playbooks.append(playbook)
        elif isinstance(playbook, Mapping):
            dto_playbooks.append(CompanyTemplatePlaybook.model_validate(playbook))
        else:
            raise CompanyTemplateError("invalid_company_template_playbook")

    try:
        return CompanyTemplate(
            company=CompanyTemplateCompany(
                name=_attribute(company, "name"),
                mission=_attribute(company, "mission", default=""),
            ),
            goals=sorted(dto_goals, key=lambda item: item.local_key),
            roles=sorted(dto_roles, key=lambda item: item.local_key),
            budgets=sorted(dto_budgets, key=lambda item: item.local_key),
            playbooks=dto_playbooks,
        )
    except (ValidationError, ValueError, TypeError) as exc:
        raise CompanyTemplateError("invalid_company_template") from exc


def _unique_ids(values: list[str], error: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values) or len(
        values
    ) != len(set(values)):
        raise CompanyTemplateError(error)


def _portable_role_keys(
    role_records: list[Any],
    role_ids: list[str],
    *,
    has_playbooks: bool,
) -> dict[str, str]:
    """Preserve imported role keys; retain the legacy stable mapping when absent."""
    persistent: dict[str, str] = {}
    for record, role_id in zip(role_records, role_ids, strict=True):
        local_key = _attribute(record, "template_local_key", default=None)
        if local_key is None:
            continue
        if not isinstance(local_key, str) or not local_key.strip():
            raise CompanyTemplateError("invalid_persistent_role_local_key")
        local_key = local_key.strip()
        environment_ids = {
            _attribute(record, field, default=None)
            for field in ("agent_id", "role_id", "company_id")
        }
        if local_key in environment_ids:
            raise CompanyTemplateError("invalid_persistent_role_local_key")
        persistent[role_id] = local_key

    if persistent and len(persistent) != len(role_ids) and has_playbooks:
        # A partial runtime↔portable mapping cannot safely distinguish a stale key
        # from a reference to a role that has no persisted identity.
        raise CompanyTemplateError("ambiguous_playbook_role_mapping")
    if len(set(persistent.values())) != len(persistent):
        raise CompanyTemplateError("duplicate_persistent_role_local_key")
    if len(persistent) == len(role_ids):
        return persistent
    if not persistent:
        return {
            identifier: f"role-{index:03d}" for index, identifier in enumerate(sorted(role_ids), 1)
        }

    # Partial mappings are safe when no playbooks need resolution. Give unmapped
    # roles deterministic portable keys that cannot collide with preserved keys.
    result = dict(persistent)
    used = set(persistent.values())
    next_index = 1
    for identifier in sorted(set(role_ids) - set(persistent)):
        while f"role-{next_index:03d}" in used:
            next_index += 1
        key = f"role-{next_index:03d}"
        result[identifier] = key
        used.add(key)
        next_index += 1
    return result


def _portable_budget_keys(budget_records: list[Any], budget_ids: list[str]) -> dict[str, str]:
    persistent: dict[str, str] = {}
    for record, budget_id in zip(budget_records, budget_ids, strict=True):
        metadata = _attribute(record, "metadata", default={}) or {}
        imported = metadata.get("template_import", {}) if isinstance(metadata, Mapping) else {}
        local_key = imported.get("local_key") if isinstance(imported, Mapping) else None
        if local_key is None:
            continue
        if not isinstance(local_key, str) or not local_key.strip():
            raise CompanyTemplateError("invalid_persistent_budget_local_key")
        local_key = local_key.strip()
        if local_key in {budget_id, _attribute(record, "company_id")}:
            raise CompanyTemplateError("invalid_persistent_budget_local_key")
        persistent[budget_id] = local_key
    if len(set(persistent.values())) != len(persistent):
        raise CompanyTemplateError("duplicate_persistent_budget_local_key")
    if len(persistent) == len(budget_ids):
        return persistent
    result = dict(persistent)
    used = set(persistent.values())
    index = 1
    for budget_id in sorted(set(budget_ids) - set(persistent)):
        while f"budget-{index:03d}" in used:
            index += 1
        key = f"budget-{index:03d}"
        result[budget_id] = key
        used.add(key)
        index += 1
    return result


def _portable_goal_keys(goal_records: list[Any], goal_ids: list[str]) -> dict[str, str]:
    persistent: dict[str, str] = {}
    for record, goal_id in zip(goal_records, goal_ids, strict=True):
        metadata = _attribute(record, "metadata", default={}) or {}
        imported = metadata.get("template_import", {}) if isinstance(metadata, Mapping) else {}
        local_key = imported.get("local_key") if isinstance(imported, Mapping) else None
        if local_key is None:
            continue
        if not isinstance(local_key, str) or not local_key.strip():
            raise CompanyTemplateError("invalid_persistent_goal_local_key")
        local_key = local_key.strip()
        if local_key in {goal_id, _attribute(record, "company_id")}:
            raise CompanyTemplateError("invalid_persistent_goal_local_key")
        persistent[goal_id] = local_key
    if len(set(persistent.values())) != len(persistent):
        raise CompanyTemplateError("duplicate_persistent_goal_local_key")
    if len(persistent) == len(goal_ids):
        return persistent
    result = dict(persistent)
    used = set(persistent.values())
    index = 1
    for goal_id in sorted(set(goal_ids) - set(persistent)):
        while f"goal-{index:03d}" in used:
            index += 1
        result[goal_id] = f"goal-{index:03d}"
        used.add(f"goal-{index:03d}")
        index += 1
    return result


def _attribute(record: Any, name: str, *, default: Any = ...) -> Any:
    if isinstance(record, Mapping):
        if name in record:
            return record[name]
    elif hasattr(record, name):
        return getattr(record, name)
    if default is not ...:
        return default
    raise CompanyTemplateError("company_template_record_missing_field")


__all__ = [
    "CompanyTemplate",
    "CompanyTemplateCompany",
    "CompanyTemplateBudget",
    "CompanyTemplateError",
    "CompanyTemplateGoal",
    "CompanyTemplatePlaybook",
    "CompanyTemplatePlaybookStep",
    "CompanyTemplateRole",
    "export_company_template",
    "validate_company_template",
]
