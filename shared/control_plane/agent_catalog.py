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
    role: str
    title: str
    domain: str
    description: str
    runtime_boundary: str
    reports_to_agent_id: str | None = None
    adapter_type: str = "builtin"
    context_sources: tuple[str, ...] = ("control_plane",)
    capabilities: tuple[str, ...] = ()
    responsibilities: tuple[str, ...] = ()
    subscribed_events: tuple[str, ...] = ()
    published_events: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    implemented: bool = True
    business_agent: bool = False
    frontend_managed: bool = True

    def to_agent_role(
        self,
        *,
        company_id: str,
        created_by: str = "system",
    ) -> AgentRole:
        """Create a durable control-plane AgentRole for this runtime module."""

        capabilities = self.capabilities or (self.description,)
        responsibilities = self.responsibilities or (self.description,)
        return AgentRole(
            company_id=company_id,
            agent_id=self.agent_id,
            display_name=self.display_name,
            agent_kind=self.agent_kind,
            interaction_mode=self.interaction_mode,
            role=self.role,
            title=self.title,
            domain=self.domain,
            reports_to_agent_id=self.reports_to_agent_id,
            adapter_type=self.adapter_type,
            adapter_config={
                "execution_mode": "runtime_module",
                "managed_by": "control_plane",
                "package_path": self.package_path,
                "runtime_boundary": self.runtime_boundary,
            },
            context_sources=list(self.context_sources),
            capabilities=list(capabilities),
            responsibilities=list(responsibilities),
            subscribed_events=list(self.subscribed_events),
            published_events=list(self.published_events),
            permissions=list(self.permissions),
            created_by=created_by,
            metadata={
                "seeded": True,
                "seed_source": "core_runtime_modules",
                "runtime_boundary": self.runtime_boundary,
                "package_path": self.package_path,
                "business_agent": self.business_agent,
                "frontend_managed": self.frontend_managed,
            },
        )


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
        role="reception",
        title="User Interaction Gateway",
        domain="operations",
        description="User interaction and Feishu webhook gateway.",
        runtime_boundary="gateway",
        context_sources=("feishu", "control_plane"),
        capabilities=(
            "User message intake",
            "Feishu webhook routing",
            "Operator-facing chat handoff",
        ),
        responsibilities=(
            "Receive user-facing messages and normalize them for backend agents.",
            "Route operator requests into the coordinator or business agents.",
            "Return agent responses to the active user interaction channel.",
        ),
        subscribed_events=("chat.pm-response", "coordinator.response"),
        published_events=("chat.pm-query", "coordinator.command", "sync.trigger"),
    ),
    RuntimeModule(
        agent_id="channel-gateway",
        package_path="services.gateways.channel",
        display_name="Channel Gateway",
        agent_kind=AgentKind.INTEGRATION_GATEWAY,
        interaction_mode=AgentInteractionMode.DIRECT,
        role="channel-gateway",
        title="Channel Integration Gateway",
        domain="operations",
        description="Multi-channel messaging gateway runtime.",
        runtime_boundary="gateway",
        context_sources=("feishu", "wecom", "control_plane"),
        capabilities=(
            "Multi-channel inbound messaging",
            "Outbound delivery tracking",
            "Channel adapter status reporting",
        ),
        responsibilities=(
            "Normalize messages from supported external channels.",
            "Deliver outbound messages through the correct channel adapter.",
            "Publish channel delivery and adapter health events.",
        ),
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
        role="orchestrator",
        title="Coordination Engine",
        domain="operations",
        description="Cross-module event orchestration worker.",
        runtime_boundary="orchestration",
        reports_to_agent_id="coo",
        context_sources=("event_bus", "scratchpad", "control_plane"),
        capabilities=(
            "Cross-agent routing",
            "Decision synthesis",
            "Event-driven workflow coordination",
        ),
        responsibilities=(
            "Route cross-module events to the correct runtime boundary.",
            "Coordinate handoffs between product, delivery, QA, and support modules.",
            "Keep orchestration decisions traceable through the control plane.",
        ),
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
        role="requirement-agent",
        title="Requirement Manager Agent",
        domain="product",
        description="Requirement extraction, confirmation, PRD, and local Feishu flow.",
        runtime_boundary="root_agent",
        reports_to_agent_id="cpo",
        context_sources=("feishu", "manual_upload", "control_plane"),
        capabilities=(
            "Requirement extraction",
            "Requirement confirmation workflow",
            "PRD generation",
            "Local Feishu intake flow",
        ),
        responsibilities=(
            "Extract structured requirements from meetings, documents, and manual input.",
            "Manage requirement confirmation, rejection, and deletion workflows.",
            "Generate PRD-ready product context for downstream planning.",
        ),
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
        role="sync-capability",
        title="Context Sync Capability",
        domain="operations",
        description=(
            "Compatibility sync runtime for separate OpenProject and "
            "Feishu Bitable sync capabilities."
        ),
        runtime_boundary="capability",
        reports_to_agent_id="coo",
        context_sources=("openproject", "feishu", "control_plane"),
        capabilities=(
            "OpenProject synchronization",
            "Feishu Bitable synchronization",
            "Sync failure reporting",
        ),
        responsibilities=(
            "Keep OpenProject task data and Feishu Bitable data synchronized.",
            "Preserve separate bounded capability behavior for each external system.",
            "Publish sync completion, failure, and task-decomposition trigger events.",
        ),
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
        role="analysis-capability",
        title="Analysis Capability",
        domain="data-ai",
        description="Risk detection and operating analytics capability.",
        runtime_boundary="capability",
        reports_to_agent_id="coo",
        context_sources=("openproject", "control_plane"),
        capabilities=(
            "Risk detection",
            "Operating analytics",
            "Quality signal evaluation",
        ),
        responsibilities=(
            "Analyze synchronized delivery data for risk and quality signals.",
            "Generate operating reports for role agents and operators.",
            "Publish risk and quality events without owning business execution.",
        ),
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
        role="project-management-agent",
        title="Project Management Agent",
        domain="product",
        description="Task decomposition, approval preparation, alerts, and reports.",
        runtime_boundary="root_agent",
        reports_to_agent_id="cpo",
        context_sources=("openproject", "feishu", "control_plane"),
        capabilities=(
            "Task decomposition",
            "Approval preparation",
            "Delivery alerting",
            "Progress reporting",
        ),
        responsibilities=(
            "Break approved product context into executable work items.",
            "Prepare approval packets and delivery alerts for role agents.",
            "Report delivery progress and decomposition failures through events.",
        ),
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
        role="quality-agent",
        title="QA Agent",
        domain="quality",
        description="QA acceptance and quality verification agent.",
        runtime_boundary="root_agent",
        reports_to_agent_id="cto",
        context_sources=("gitlab", "control_plane"),
        capabilities=(
            "Acceptance verification",
            "Quality gate evaluation",
            "Regression evidence review",
        ),
        responsibilities=(
            "Run acceptance checks for delivered work.",
            "Publish QA success or gate-failure events with enough evidence to act.",
            "Coordinate quality feedback with Dev Agent and CTO role agent.",
        ),
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
        role="development-agent",
        title="Development Agent",
        domain="engineering",
        description="AgentForge-backed software delivery execution agent.",
        runtime_boundary="root_agent",
        reports_to_agent_id="cto",
        context_sources=("agentforge", "gitlab", "control_plane"),
        capabilities=(
            "AgentForge delivery execution",
            "Merge request creation",
            "Implementation task completion",
        ),
        responsibilities=(
            "Execute approved delivery work through the AgentForge workflow.",
            "Create merge requests and publish delivery progress events.",
            "Request QA verification when implementation work is ready.",
        ),
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
        role="evolution-capability",
        title="Evolution Capability",
        domain="data-ai",
        description="Self-evolution analysis and recommendation capability.",
        runtime_boundary="capability",
        reports_to_agent_id="cto",
        context_sources=("traces", "control_plane"),
        capabilities=(
            "Self-evolution analysis",
            "Skill improvement proposals",
            "Collaboration pattern recommendations",
        ),
        responsibilities=(
            "Analyze runtime evidence for L1, L2, and L3 improvement opportunities.",
            "Propose skill and collaboration changes for human review.",
            "Keep evolution proposals separate from direct production changes.",
        ),
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
