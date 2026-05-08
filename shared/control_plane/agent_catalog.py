"""Canonical catalog for runtime agents, services, and role-agent seeds.

Real business runtime agents live as root packages under ``agents/``. Gateway
and orchestration services live under ``services/``. Shared support
capabilities live under ``shared.capabilities``. Organization-role business
agents are durable control-plane records seeded from these templates, not
Python packages.
"""

from dataclasses import dataclass

from shared.control_plane.models import AgentInteractionMode, AgentKind, AgentRole


@dataclass(frozen=True)
class RuntimeModule:
    """A deployable runtime boundary known to the control plane."""

    agent_id: str
    package_path: str
    display_name: str
    agent_kind: AgentKind
    interaction_mode: AgentInteractionMode
    description: str
    runtime_boundary: str
    subscribed_events: tuple[str, ...] = ()
    published_events: tuple[str, ...] = ()
    implemented: bool = True
    business_agent: bool = False
    frontend_managed: bool = True


@dataclass(frozen=True)
class OrganizationRoleTemplate:
    """Seed data for a durable control-plane managed role agent."""

    agent_id: str
    display_name: str
    role: str
    title: str
    domain: str
    interaction_mode: AgentInteractionMode = AgentInteractionMode.ROUTED
    agent_kind: AgentKind = AgentKind.ORGANIZATION_ROLE
    frontend_managed: bool = True
    root_catalog_managed: bool = True

    def to_agent_role(
        self,
        *,
        company_id: str,
        adapter_type: str = "builtin",
        context_sources: list[str] | None = None,
        capabilities: list[str] | None = None,
        responsibilities: list[str] | None = None,
        subscribed_events: list[str] | None = None,
        published_events: list[str] | None = None,
        created_by: str = "system",
    ) -> AgentRole:
        """Create a durable control-plane AgentRole from this template."""

        return AgentRole(
            company_id=company_id,
            agent_id=self.agent_id,
            display_name=self.display_name,
            agent_kind=self.agent_kind,
            interaction_mode=self.interaction_mode,
            role=self.role,
            title=self.title,
            domain=self.domain,
            adapter_type=adapter_type,
            context_sources=context_sources or ["control_plane"],
            capabilities=capabilities or [],
            responsibilities=responsibilities or [],
            subscribed_events=subscribed_events or [],
            published_events=published_events or [],
            created_by=created_by,
        )


@dataclass(frozen=True)
class AgentCatalogEntry:
    """Frontend/control-plane catalog view across role seeds and runtimes."""

    agent_id: str
    display_name: str
    agent_kind: AgentKind
    interaction_mode: AgentInteractionMode
    catalog_group: str
    description: str
    package_path: str | None
    runtime_boundary: str | None
    subscribed_events: tuple[str, ...]
    published_events: tuple[str, ...]
    implemented: bool
    business_agent: bool
    frontend_managed: bool
    root_catalog_managed: bool


RUNTIME_MODULES: tuple[RuntimeModule, ...] = (
    RuntimeModule(
        agent_id="chat-agent",
        package_path="services.gateways.user_interaction",
        display_name="User Gateway",
        agent_kind=AgentKind.INTEGRATION_GATEWAY,
        interaction_mode=AgentInteractionMode.DIRECT,
        description="User interaction and Feishu webhook gateway.",
        runtime_boundary="gateway",
        subscribed_events=("chat.pm-response", "coordinator.response"),
        published_events=("chat.pm-query", "coordinator.command", "sync.trigger"),
    ),
    RuntimeModule(
        agent_id="channel-gateway",
        package_path="services.gateways.channel",
        display_name="Channel Gateway",
        agent_kind=AgentKind.INTEGRATION_GATEWAY,
        interaction_mode=AgentInteractionMode.DIRECT,
        description="Multi-channel messaging gateway runtime.",
        runtime_boundary="gateway",
        subscribed_events=("channel.message.outbound",),
        published_events=(
            "channel.message.inbound",
            "channel.message.delivered",
            "channel.adapter.status",
        ),
    ),
    RuntimeModule(
        agent_id="coordinator",
        package_path="services.orchestration.coordinator",
        display_name="Coordinator Worker",
        agent_kind=AgentKind.SYSTEM_WORKER,
        interaction_mode=AgentInteractionMode.ROUTED,
        description="Cross-module event orchestration worker.",
        runtime_boundary="orchestration",
        subscribed_events=(
            "coordinator.command",
            "task.notification",
            "task.progress",
            "pm.prd-ready",
            "pm.decompose-completed",
            "pm.decomposition-failed",
            "analysis.risk-detected",
        ),
        published_events=(
            "coordinator.response",
            "coordinator.dispatch",
            "pm.tasks-ready-for-dev",
            "qa.run-requested",
        ),
    ),
    RuntimeModule(
        agent_id="requirement-manager",
        package_path="agents.requirement_manager",
        display_name="Requirement Manager",
        agent_kind=AgentKind.BUSINESS_RUNTIME_AGENT,
        interaction_mode=AgentInteractionMode.INTERNAL,
        description="Requirement extraction, confirmation, PRD, and local Feishu flow.",
        runtime_boundary="root_agent",
        subscribed_events=(
            "project.created",
            "project.updated",
            "sprint.started",
            "sprint.completed",
            "meeting.uploaded",
            "coordinator.dispatch",
        ),
        published_events=(
            "requirement.extracted",
            "requirement.confirmed",
            "requirement.rejected",
            "requirement.deleted",
        ),
        business_agent=True,
    ),
    RuntimeModule(
        agent_id="sync-module",
        package_path="shared.capabilities.sync",
        display_name="Sync Module",
        agent_kind=AgentKind.CAPABILITY_MODULE,
        interaction_mode=AgentInteractionMode.INTERNAL,
        description=(
            "Compatibility sync runtime for separate OpenProject and "
            "Feishu Bitable sync capabilities."
        ),
        runtime_boundary="capability",
        subscribed_events=("sync.trigger",),
        published_events=(
            "sync.started",
            "sync.completed",
            "sync.failed",
            "sync.task-needs-decompose",
        ),
    ),
    RuntimeModule(
        agent_id="analysis-module",
        package_path="shared.capabilities.analysis",
        display_name="Analysis Module",
        agent_kind=AgentKind.CAPABILITY_MODULE,
        interaction_mode=AgentInteractionMode.INTERNAL,
        description="Risk detection and operating analytics capability.",
        runtime_boundary="capability",
        subscribed_events=("sync.completed",),
        published_events=(
            "report.daily-generated",
            "report.weekly-generated",
            "analysis.risk-detected",
            "analysis.quality-evaluated",
        ),
    ),
    RuntimeModule(
        agent_id="pjm-agent",
        package_path="agents.pjm_agent",
        display_name="PJM Agent",
        agent_kind=AgentKind.BUSINESS_RUNTIME_AGENT,
        interaction_mode=AgentInteractionMode.INTERNAL,
        description="Task decomposition, approval preparation, alerts, and reports.",
        runtime_boundary="root_agent",
        subscribed_events=(
            "sync.completed",
            "analysis.risk-detected",
            "chat.pm-query",
            "sync.task-needs-decompose",
            "coordinator.dispatch",
        ),
        published_events=(
            "pm.alert-triggered",
            "chat.pm-response",
            "pm.decompose-completed",
            "pm.decomposition-failed",
            "pm.approval-timeout",
            "pm.tasks-ready-for-dev",
            "sync.task-needs-decompose",
        ),
        business_agent=True,
    ),
    RuntimeModule(
        agent_id="qa-agent",
        package_path="agents.qa_agent",
        display_name="QA Agent",
        agent_kind=AgentKind.BUSINESS_RUNTIME_AGENT,
        interaction_mode=AgentInteractionMode.INTERNAL,
        description="QA acceptance and quality verification agent.",
        runtime_boundary="root_agent",
        subscribed_events=("code.committed", "qa.run-requested"),
        published_events=("qa.acceptance-completed", "qa.gate-failed"),
        business_agent=True,
    ),
    RuntimeModule(
        agent_id="dev-agent",
        package_path="agents.dev_agent",
        display_name="Dev Agent",
        agent_kind=AgentKind.BUSINESS_RUNTIME_AGENT,
        interaction_mode=AgentInteractionMode.INTERNAL,
        description="AgentForge-backed software delivery execution agent.",
        runtime_boundary="root_agent",
        subscribed_events=("pm.tasks-ready-for-dev", "qa.acceptance-completed"),
        published_events=(
            "dev.workflow-created",
            "dev.mr-created",
            "dev.task-completed",
            "dev.task-failed",
            "qa.run-requested",
        ),
        business_agent=True,
    ),
    RuntimeModule(
        agent_id="evolution-module",
        package_path="shared.capabilities.evolution",
        display_name="Evolution Module",
        agent_kind=AgentKind.CAPABILITY_MODULE,
        interaction_mode=AgentInteractionMode.INTERNAL,
        description="Self-evolution analysis and recommendation capability.",
        runtime_boundary="capability",
        subscribed_events=(
            "evolution.cycle-triggered",
            "evolution.human-feedback",
            "evolution.pattern-approved",
        ),
        published_events=("evolution.skill-proposed", "evolution.pattern-proposed"),
    ),
)


ORGANIZATION_ROLE_TEMPLATES: tuple[OrganizationRoleTemplate, ...] = (
    OrganizationRoleTemplate(
        agent_id="ceo",
        display_name="CEO",
        role="ceo",
        title="Chief Executive Officer",
        domain="business",
    ),
    OrganizationRoleTemplate(
        agent_id="cto",
        display_name="CTO",
        role="cto",
        title="Chief Technology Officer",
        domain="engineering",
    ),
    OrganizationRoleTemplate(
        agent_id="cpo",
        display_name="CPO",
        role="cpo",
        title="Chief Product Officer",
        domain="product",
    ),
    OrganizationRoleTemplate(
        agent_id="coo",
        display_name="COO",
        role="coo",
        title="Chief Operating Officer",
        domain="operations",
    ),
)


RUNTIME_MODULE_BY_ID = {module.agent_id: module for module in RUNTIME_MODULES}
LEGACY_RUNTIME_MODULE_ID_ALIASES = {
    "sync-agent": "sync-module",
    "analysis-agent": "analysis-module",
    "evolution-agent": "evolution-module",
}
ORGANIZATION_ROLE_TEMPLATE_BY_ID = {
    template.agent_id: template for template in ORGANIZATION_ROLE_TEMPLATES
}


def _runtime_module_to_catalog_entry(module: RuntimeModule) -> AgentCatalogEntry:
    return AgentCatalogEntry(
        agent_id=module.agent_id,
        display_name=module.display_name,
        agent_kind=module.agent_kind,
        interaction_mode=module.interaction_mode,
        catalog_group="runtime_module",
        description=module.description,
        package_path=module.package_path,
        runtime_boundary=module.runtime_boundary,
        subscribed_events=module.subscribed_events,
        published_events=module.published_events,
        implemented=module.implemented,
        business_agent=module.business_agent,
        frontend_managed=module.frontend_managed,
        root_catalog_managed=False,
    )


def _role_template_to_catalog_entry(
    template: OrganizationRoleTemplate,
) -> AgentCatalogEntry:
    return AgentCatalogEntry(
        agent_id=template.agent_id,
        display_name=template.display_name,
        agent_kind=template.agent_kind,
        interaction_mode=template.interaction_mode,
        catalog_group="organization_role_template",
        description=f"{template.title} role agent template for {template.domain}.",
        package_path=None,
        runtime_boundary=None,
        subscribed_events=(),
        published_events=(),
        implemented=False,
        business_agent=True,
        frontend_managed=template.frontend_managed,
        root_catalog_managed=template.root_catalog_managed,
    )


def get_managed_agent_catalog() -> tuple[AgentCatalogEntry, ...]:
    """Return every agent-like thing visible to the frontend/control plane.

    Organization-role agents are bootstrapped as durable `AgentRole` records.
    Runtime modules remain in their service-boundary packages and are exposed
    here only as metadata.
    """

    return tuple(
        [_role_template_to_catalog_entry(template) for template in ORGANIZATION_ROLE_TEMPLATES]
        + [_runtime_module_to_catalog_entry(module) for module in RUNTIME_MODULES]
    )


def get_business_runtime_agents() -> tuple[RuntimeModule, ...]:
    """Return implemented runtime modules that own business work outcomes."""

    return tuple(
        module
        for module in RUNTIME_MODULES
        if module.implemented and module.business_agent
    )


def get_runtime_module(agent_id: str) -> RuntimeModule | None:
    """Return the deployed runtime module for an existing compatibility id."""

    canonical_id = LEGACY_RUNTIME_MODULE_ID_ALIASES.get(agent_id, agent_id)
    return RUNTIME_MODULE_BY_ID.get(canonical_id)


def get_organization_role_template(agent_id: str) -> OrganizationRoleTemplate | None:
    """Return the control-plane role template for a managed role agent id."""

    return ORGANIZATION_ROLE_TEMPLATE_BY_ID.get(agent_id)


def create_organization_role(
    agent_id: str,
    *,
    company_id: str,
    adapter_type: str = "builtin",
    context_sources: list[str] | None = None,
    capabilities: list[str] | None = None,
    responsibilities: list[str] | None = None,
    subscribed_events: list[str] | None = None,
    published_events: list[str] | None = None,
    created_by: str = "system",
) -> AgentRole:
    """Create a control-plane AgentRole for a known organization-role agent."""

    template = get_organization_role_template(agent_id)
    if template is None:
        raise KeyError(f"Unknown organization role agent: {agent_id}")
    return template.to_agent_role(
        company_id=company_id,
        adapter_type=adapter_type,
        context_sources=context_sources,
        capabilities=capabilities,
        responsibilities=responsibilities,
        subscribed_events=subscribed_events,
        published_events=published_events,
        created_by=created_by,
    )


def is_runtime_module(agent_id: str) -> bool:
    return agent_id in RUNTIME_MODULE_BY_ID or agent_id in LEGACY_RUNTIME_MODULE_ID_ALIASES


def is_organization_role_template(agent_id: str) -> bool:
    return agent_id in ORGANIZATION_ROLE_TEMPLATE_BY_ID
