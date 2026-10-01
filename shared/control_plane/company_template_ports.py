"""Persistence port for company-template import and export use cases."""

from __future__ import annotations

from typing import Protocol

from shared.core.identifiers import CompanyId

from .models import AgentRole, BudgetPolicy, CompanyContext, Goal


class ControlPlaneCompanyTemplateStore(Protocol):
    """Composition of existing stores needed by template operations."""

    async def get_company(self, company_id: CompanyId) -> CompanyContext | None: ...

    async def list_companies(self, *, search: str, limit: int) -> list[CompanyContext]: ...

    async def list_goals(self, *, company_id: CompanyId, limit: int) -> list[Goal]: ...

    async def list_agent_roles(self, *, company_id: CompanyId, limit: int) -> list[AgentRole]: ...

    async def list_budget_policies(
        self, *, company_id: CompanyId, limit: int
    ) -> list[BudgetPolicy]: ...

    async def create_company(self, company: CompanyContext) -> CompanyContext: ...

    async def create_goal(self, goal: Goal) -> Goal: ...

    async def create_agent_role(self, role: AgentRole) -> AgentRole: ...

    async def create_budget_policy(self, budget: BudgetPolicy) -> BudgetPolicy: ...


__all__ = ["ControlPlaneCompanyTemplateStore"]
