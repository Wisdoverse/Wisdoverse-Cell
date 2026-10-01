"""Application use cases for portable company-template workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shared.core.identifiers import CompanyId
from shared.core.ids import IDPrefix, generate_id

from .company_template_ports import ControlPlaneCompanyTemplateStore
from .domain.company_template import (
    CompanyTemplate,
    CompanyTemplateError,
    export_company_template,
    validate_company_template,
)
from .models import (
    AgentRole,
    BudgetPeriod,
    BudgetPolicy,
    BudgetScope,
    CompanyContext,
    Goal,
    GoalStatus,
)


class CompanyTemplateCompanyNotFoundError(LookupError):
    """Raised when exporting a missing company."""


class CompanyTemplateNameCollisionError(ValueError):
    """Raised when an import would reuse an existing company name."""


class CompanyTemplatePermissionsReviewRequiredError(PermissionError):
    """Raised until an operator confirms review of requested permissions."""


@dataclass(frozen=True, slots=True)
class CompanyTemplateImportResult:
    company_id: str
    goal_ids: dict[str, str]
    role_ids: dict[str, str]
    budget_ids: dict[str, str]


async def export_company_template_for_company(
    store: ControlPlaneCompanyTemplateStore,
    *,
    company_id: str,
) -> CompanyTemplate:
    company = await store.get_company(CompanyId(company_id))
    if company is None:
        raise CompanyTemplateCompanyNotFoundError(company_id)
    goals = await store.list_goals(company_id=CompanyId(company_id), limit=500)
    roles = await store.list_agent_roles(company_id=CompanyId(company_id), limit=200)
    budgets = await store.list_budget_policies(company_id=CompanyId(company_id), limit=500)
    portable_roles = [
        {
            "company_id": role.company_id,
            "agent_id": role.agent_id,
            "template_local_key": ((role.metadata or {}).get("template_import") or {}).get(
                "local_key"
            ),
            "display_name": role.display_name,
            "role": role.role,
            "title": role.title,
            "responsibilities": role.responsibilities,
            "permissions": (
                ((role.metadata or {}).get("template_import") or {}).get("requested_permissions")
                or role.permissions
            ),
            "skill_references": (role.metadata or {}).get("skill_references")
            or (((role.metadata or {}).get("template_import") or {}).get("skill_references", [])),
            "reports_to_agent_id": role.reports_to_agent_id,
            "budget_policy_id": role.budget_policy_id,
        }
        for role in roles
    ]
    playbooks = (company.metadata or {}).get("playbooks", [])
    return export_company_template(company, goals, portable_roles, playbooks, budgets)


async def import_company_template(
    store: ControlPlaneCompanyTemplateStore,
    payload: CompanyTemplate | dict[str, Any],
    *,
    permissions_reviewed: bool,
) -> CompanyTemplateImportResult:
    template = validate_company_template(payload)
    if not permissions_reviewed:
        raise CompanyTemplatePermissionsReviewRequiredError(
            "company_template_permissions_review_required"
        )

    possible_collisions = await store.list_companies(search=template.company.name, limit=500)
    normalized_name = template.company.name.casefold()
    if any(company.name.casefold() == normalized_name for company in possible_collisions):
        raise CompanyTemplateNameCollisionError("company_template_name_collision")

    company_id = generate_id(IDPrefix.COMPANY)
    imported_playbooks = [playbook.model_dump(mode="json") for playbook in template.playbooks]
    company = await store.create_company(
        CompanyContext(
            company_id=company_id,
            name=template.company.name,
            mission=template.company.mission,
            metadata={"playbooks": imported_playbooks, "template_import": True},
        )
    )

    agent_id_map = {
        portable_role.local_key: generate_id("agent") for portable_role in template.roles
    }
    goal_id_map = {
        portable_goal.local_key: generate_id(IDPrefix.GOAL) for portable_goal in template.goals
    }
    pending_goals = {goal.local_key: goal for goal in template.goals}

    budget_id_map: dict[str, str] = {}
    for portable_budget in template.budgets:
        if portable_budget.scope == "company":
            scope = BudgetScope.COMPANY
            scope_id = None
        elif portable_budget.scope == "goal":
            assert portable_budget.scope_key is not None
            scope = BudgetScope.GOAL
            scope_id = goal_id_map[portable_budget.scope_key]
        else:
            assert portable_budget.scope_key is not None
            scope = BudgetScope.AGENT
            scope_id = agent_id_map[portable_budget.scope_key]
        budget = await store.create_budget_policy(
            BudgetPolicy(
                company_id=company.company_id,
                scope=scope,
                scope_id=scope_id,
                period=BudgetPeriod(portable_budget.period),
                limit_usd=portable_budget.ceiling_usd,
                warning_threshold=portable_budget.warning_ratio,
                status="paused",
                model_allowlist=list(portable_budget.model_allowlist),
                metadata={
                    "template_import": {
                        "local_key": portable_budget.local_key,
                        "paused_for_operator_review": True,
                    }
                },
            )
        )
        budget_id_map[portable_budget.local_key] = budget.budget_id

    role_id_map: dict[str, str] = {}
    pending_roles = {role.local_key: role for role in template.roles}
    while pending_roles:
        ready_roles = [
            role
            for role in pending_roles.values()
            if role.reports_to_key is None or role.reports_to_key in role_id_map
        ]
        if not ready_roles:
            raise CompanyTemplateError("role_reporting_cycle")
        for portable_role in ready_roles:
            role = await store.create_agent_role(
                AgentRole(
                    company_id=company.company_id,
                    agent_id=agent_id_map[portable_role.local_key],
                    display_name=portable_role.display_name,
                    role=portable_role.role,
                    title=portable_role.title,
                    reports_to_agent_id=(
                        agent_id_map[portable_role.reports_to_key]
                        if portable_role.reports_to_key
                        else None
                    ),
                    responsibilities=list(portable_role.responsibilities),
                    permissions=[],
                    budget_policy_id=(
                        budget_id_map[portable_role.budget_key]
                        if portable_role.budget_key
                        else None
                    ),
                    adapter_type="builtin",
                    adapter_config={},
                    status="paused",
                    created_by="company_template_import",
                    metadata={
                        "template_import": {
                            "local_key": portable_role.local_key,
                            "permissions_reviewed": True,
                            "requested_permissions": list(portable_role.permissions),
                            "skill_references": list(portable_role.skill_references),
                        }
                    },
                )
            )
            role_id_map[portable_role.local_key] = role.role_id
            del pending_roles[portable_role.local_key]

    while pending_goals:
        ready_goals = [
            goal
            for goal in pending_goals.values()
            if goal.parent_key is None or goal.parent_key not in pending_goals
        ]
        if not ready_goals:
            raise CompanyTemplateError("goal_parent_cycle")
        for portable_goal in ready_goals:
            await store.create_goal(
                Goal(
                    goal_id=goal_id_map[portable_goal.local_key],
                    company_id=company.company_id,
                    title=portable_goal.title,
                    description=portable_goal.description,
                    status=GoalStatus.DRAFT,
                    parent_goal_id=(
                        goal_id_map[portable_goal.parent_key] if portable_goal.parent_key else None
                    ),
                    owner_agent_id=(
                        agent_id_map[portable_goal.owner_role_key]
                        if portable_goal.owner_role_key
                        else None
                    ),
                    metadata={"template_import": {"local_key": portable_goal.local_key}},
                )
            )
            del pending_goals[portable_goal.local_key]

    return CompanyTemplateImportResult(
        company_id=company.company_id,
        goal_ids=goal_id_map,
        role_ids=role_id_map,
        budget_ids=budget_id_map,
    )


__all__ = [
    "CompanyTemplateCompanyNotFoundError",
    "CompanyTemplateImportResult",
    "CompanyTemplateNameCollisionError",
    "CompanyTemplatePermissionsReviewRequiredError",
    "export_company_template_for_company",
    "import_company_template",
]
