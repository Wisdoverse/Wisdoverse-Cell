"""Adapter composing existing persistence stores for company templates."""

from __future__ import annotations

from shared.core.identifiers import CompanyId

from .agent_registry_ports import ControlPlaneAgentRegistryStore
from .budget_ports import ControlPlaneBudgetStore
from .company_ports import ControlPlaneCompanyStore
from .company_template_ports import ControlPlaneCompanyTemplateStore
from .goal_ports import ControlPlaneGoalStore
from .models import AgentRole, BudgetPolicy, CompanyContext, Goal


class ExistingStoresCompanyTemplateAdapter(ControlPlaneCompanyTemplateStore):
    """Delegate template reads/writes to existing stores in one session."""

    def __init__(
        self,
        companies: ControlPlaneCompanyStore,
        goals: ControlPlaneGoalStore,
        roles: ControlPlaneAgentRegistryStore,
        budgets: ControlPlaneBudgetStore | None = None,
    ) -> None:
        self._companies = companies
        self._goals = goals
        self._roles = roles
        self._budgets: ControlPlaneBudgetStore | None = budgets

    async def get_company(self, company_id: CompanyId) -> CompanyContext | None:
        return await self._companies.get_company(company_id)

    async def list_companies(self, *, search: str, limit: int) -> list[CompanyContext]:
        return await self._companies.list_companies(search=search, limit=limit)

    async def list_goals(self, *, company_id: CompanyId, limit: int) -> list[Goal]:
        return await self._goals.list_goals(company_id=company_id, limit=limit)

    async def list_agent_roles(self, *, company_id: CompanyId, limit: int) -> list[AgentRole]:
        return await self._roles.list_agent_roles(company_id=company_id, limit=limit)

    async def list_budget_policies(
        self, *, company_id: CompanyId, limit: int
    ) -> list[BudgetPolicy]:
        if self._budgets is None:
            return []
        return await self._budgets.list_budget_policies(company_id=company_id, limit=limit)

    async def create_company(self, company: CompanyContext) -> CompanyContext:
        return await self._companies.create_company(company)

    async def create_goal(self, goal: Goal) -> Goal:
        return await self._goals.create_goal(goal)

    async def create_agent_role(self, role: AgentRole) -> AgentRole:
        return await self._roles.create_agent_role(role)

    async def create_budget_policy(self, budget: BudgetPolicy) -> BudgetPolicy:
        if self._budgets is None:
            raise RuntimeError("company_template_budget_store_unavailable")
        return await self._budgets.create_budget_policy(budget)


__all__ = ["ExistingStoresCompanyTemplateAdapter"]
