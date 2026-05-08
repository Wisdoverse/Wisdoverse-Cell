"""Bootstrap first-class organization-role business agents."""

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from shared.control_plane.agent_catalog import ORGANIZATION_ROLE_TEMPLATES
from shared.control_plane.models import AgentRole, AuditEvent, CompanyContext
from shared.control_plane.repository import ControlPlaneRepository
from shared.schemas.event import EventTypes


@dataclass(frozen=True)
class RoleAgentSeed:
    reports_to_agent_id: str | None
    context_sources: tuple[str, ...]
    capabilities: tuple[str, ...]
    responsibilities: tuple[str, ...]
    subscribed_events: tuple[str, ...]
    published_events: tuple[str, ...]
    permissions: tuple[str, ...]
    escalation_policy: dict[str, object]


CORE_ORGANIZATION_ROLE_AGENT_SEEDS: dict[str, RoleAgentSeed] = {
    "ceo": RoleAgentSeed(
        reports_to_agent_id=None,
        context_sources=("control_plane", "operator_console", "company_strategy"),
        capabilities=(
            "Company strategy prioritization",
            "Portfolio trade-off decisions",
            "Budget and escalation governance",
            "Cross-role operating alignment",
        ),
        responsibilities=(
            "Own company-level goals and operating priorities.",
            "Resolve cross-functional conflicts between product, engineering, and operations.",
            "Approve high-impact finance, customer, legal, and technical escalations.",
            "Keep role-agent work aligned with the Wisdoverse Cell mission.",
        ),
        subscribed_events=(
            EventTypes.GOAL_CREATED,
            EventTypes.WORK_ITEM_UPDATED,
            EventTypes.APPROVAL_REQUESTED,
            EventTypes.BUDGET_USAGE_RECORDED,
            EventTypes.AGENT_RUN_FAILED,
            "analysis.risk-detected",
        ),
        published_events=(
            EventTypes.GOAL_UPDATED,
            EventTypes.DECISION_CREATED,
            EventTypes.APPROVAL_GRANTED,
            EventTypes.APPROVAL_REJECTED,
        ),
        permissions=(
            "goals:update",
            "decisions:create",
            "approvals:resolve",
            "budgets:govern",
        ),
        escalation_policy={
            "human_approval_required_for": ["finance", "legal", "customer", "technical"],
            "default_route": "operator_console",
        },
    ),
    "cto": RoleAgentSeed(
        reports_to_agent_id="ceo",
        context_sources=("control_plane", "operator_console", "architecture_records"),
        capabilities=(
            "Architecture decision review",
            "Technical risk assessment",
            "Delivery system governance",
            "Engineering quality policy",
        ),
        responsibilities=(
            "Own technology direction and architecture trade-offs.",
            "Review technical escalations, delivery risk, and quality-gate failures.",
            "Coordinate Dev Agent and QA Agent execution boundaries.",
            "Keep implementation work aligned with architecture contracts.",
        ),
        subscribed_events=(
            EventTypes.WORK_ITEM_CREATED,
            EventTypes.APPROVAL_REQUESTED,
            "dev.workflow-created",
            "dev.mr-created",
            "qa.gate-failed",
            "analysis.risk-detected",
        ),
        published_events=(
            EventTypes.DECISION_CREATED,
            EventTypes.WORK_ITEM_UPDATED,
            EventTypes.APPROVAL_GRANTED,
            EventTypes.APPROVAL_REJECTED,
        ),
        permissions=(
            "work_items:update",
            "decisions:create",
            "approvals:resolve",
            "agents:wake",
        ),
        escalation_policy={
            "human_approval_required_for": ["technical", "legal"],
            "default_route": "operator_console",
        },
    ),
    "cpo": RoleAgentSeed(
        reports_to_agent_id="ceo",
        context_sources=("control_plane", "operator_console", "product_context"),
        capabilities=(
            "Product priority shaping",
            "Requirement acceptance review",
            "User value and scope trade-offs",
            "Roadmap coherence checks",
        ),
        responsibilities=(
            "Own product value, scope, and requirement priority.",
            "Review requirement changes and PRD readiness.",
            "Coordinate Requirement Manager and PJM Agent product handoffs.",
            "Protect customer value when delivery trade-offs are proposed.",
        ),
        subscribed_events=(
            EventTypes.APPROVAL_REQUESTED,
            "requirement.extracted",
            "requirement.confirmed",
            "pm.decompose-completed",
            "analysis.quality-evaluated",
        ),
        published_events=(
            EventTypes.GOAL_UPDATED,
            EventTypes.WORK_ITEM_CREATED,
            EventTypes.DECISION_CREATED,
            EventTypes.APPROVAL_GRANTED,
            EventTypes.APPROVAL_REJECTED,
        ),
        permissions=(
            "goals:update",
            "work_items:create",
            "decisions:create",
            "approvals:resolve",
        ),
        escalation_policy={
            "human_approval_required_for": ["customer", "finance"],
            "default_route": "operator_console",
        },
    ),
    "coo": RoleAgentSeed(
        reports_to_agent_id="ceo",
        context_sources=("control_plane", "operator_console", "operating_metrics"),
        capabilities=(
            "Operating cadence management",
            "Process bottleneck detection",
            "Agent handoff coordination",
            "SLA and execution health review",
        ),
        responsibilities=(
            "Own operating rhythm and execution follow-through.",
            "Track stuck work, stale approvals, and unhealthy agent runs.",
            "Coordinate cross-agent handoffs between gateways, sync, PJM, Dev, and QA.",
            "Escalate operational risks before they block delivery.",
        ),
        subscribed_events=(
            EventTypes.AGENT_RUN_FAILED,
            EventTypes.BUDGET_USAGE_RECORDED,
            "sync.completed",
            "pm.alert-triggered",
            "pm.approval-timeout",
        ),
        published_events=(
            EventTypes.WORK_ITEM_UPDATED,
            EventTypes.DECISION_CREATED,
            EventTypes.APPROVAL_GRANTED,
            EventTypes.APPROVAL_REJECTED,
        ),
        permissions=(
            "work_items:update",
            "decisions:create",
            "approvals:resolve",
            "agents:wake",
        ),
        escalation_policy={
            "human_approval_required_for": ["finance", "customer", "technical"],
            "default_route": "operator_console",
        },
    ),
}


async def ensure_core_organization_role_agents(
    repo: ControlPlaneRepository,
    *,
    company_id: str,
    company_name: str = "Wisdoverse Cell",
    created_by: str = "system:control-plane-bootstrap",
) -> list[str]:
    """Ensure CEO/CTO/CPO/COO exist as durable control-plane AgentRole records."""

    await _ensure_company(repo, company_id=company_id, company_name=company_name)
    created_agent_ids: list[str] = []

    for template in ORGANIZATION_ROLE_TEMPLATES:
        if await repo.get_agent_role(company_id=company_id, agent_id=template.agent_id):
            continue

        seed = CORE_ORGANIZATION_ROLE_AGENT_SEEDS[template.agent_id]
        role = _build_role_agent(template_id=template.agent_id, company_id=company_id, created_by=created_by)

        try:
            async with repo.session.begin_nested():
                row = await repo.create_agent_role(role)
        except IntegrityError:
            continue

        await repo.append_audit_event(
            AuditEvent(
                company_id=company_id,
                action=EventTypes.AGENT_ROLE_CREATED,
                target_type="agent_role",
                target_id=row.agent_id,
                actor_type="system",
                actor_id=created_by,
                idempotency_key=f"bootstrap:{company_id}:agent_role:{row.agent_id}",
                detail={
                    "agent_id": row.agent_id,
                    "role_id": row.role_id,
                    "agent_kind": row.agent_kind,
                    "interaction_mode": row.interaction_mode,
                    "role": row.role,
                    "adapter_type": row.adapter_type,
                    "reports_to_agent_id": row.reports_to_agent_id,
                    "capabilities": list(seed.capabilities),
                    "bootstrap": "core_organization_role_agents",
                },
            )
        )
        created_agent_ids.append(row.agent_id)

    return created_agent_ids


async def _ensure_company(
    repo: ControlPlaneRepository,
    *,
    company_id: str,
    company_name: str,
) -> None:
    if await repo.get_company(company_id) is not None:
        return

    try:
        async with repo.session.begin_nested():
            await repo.create_company(
                CompanyContext(
                    company_id=company_id,
                    name=company_name,
                    mission="AI-native company operations with durable role agents.",
                    metadata={"bootstrap": "core_organization_role_agents"},
                )
            )
    except IntegrityError:
        return


def _build_role_agent(
    *,
    template_id: str,
    company_id: str,
    created_by: str,
) -> AgentRole:
    template = next(
        item for item in ORGANIZATION_ROLE_TEMPLATES if item.agent_id == template_id
    )
    seed = CORE_ORGANIZATION_ROLE_AGENT_SEEDS[template.agent_id]
    role = template.to_agent_role(
        company_id=company_id,
        adapter_type="builtin",
        context_sources=list(seed.context_sources),
        capabilities=list(seed.capabilities),
        responsibilities=list(seed.responsibilities),
        subscribed_events=list(seed.subscribed_events),
        published_events=list(seed.published_events),
        created_by=created_by,
    )
    return role.model_copy(
        update={
            "reports_to_agent_id": seed.reports_to_agent_id,
            "adapter_config": {
                "execution_mode": "control_plane_role_agent",
                "managed_by": "control_plane",
            },
            "permissions": list(seed.permissions),
            "escalation_policy": seed.escalation_policy,
            "metadata": {
                "seeded": True,
                "seed_source": "core_organization_role_agents",
                "business_agent": True,
            },
        }
    )
