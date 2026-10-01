"""Tests for portable company-template serialization and import validation."""

from types import SimpleNamespace

import pytest

from shared.control_plane.company_template_use_cases import (
    export_company_template_for_company,
    import_company_template,
)
from shared.control_plane.domain.company_template import (
    CompanyTemplateError,
    export_company_template,
    validate_company_template,
)
from shared.control_plane.models import (
    AgentRole,
    BudgetPeriod,
    BudgetPolicy,
    BudgetScope,
    CompanyContext,
    Goal,
)


def test_company_template_round_trip_contains_only_portable_fields() -> None:
    company = CompanyContext(
        company_id="cmp_private_source",
        name="Example Cell",
        mission="Deliver reliable operations",
        metadata={"private": "excluded"},
    )
    goals = [
        Goal(
            goal_id="goal_child_domain_id",
            company_id=company.company_id,
            title="Deliver report",
            description="Produce a reviewed report",
            parent_goal_id="goal_root_domain_id",
            owner_agent_id="agent-private",
        ),
        Goal(
            goal_id="goal_root_domain_id",
            company_id=company.company_id,
            title="Operate well",
        ),
    ]
    roles = [
        AgentRole(
            role_id="role-private",
            company_id=company.company_id,
            agent_id="agent-private",
            display_name="Operations role",
            role="operator",
            title="Operations",
            responsibilities=["Review reports"],
            permissions=["reports:read"],
            adapter_type="http",
            adapter_config={"base_url": "http://10.0.0.8/internal"},
            metadata={"provider_account": "excluded"},
        )
    ]

    exported = export_company_template(company, goals, roles)
    payload = exported.model_dump(mode="json")
    validated = validate_company_template(payload)

    assert validated == exported
    assert payload["schema_version"] == "1.0"
    assert payload["goals"][0]["local_key"] == "goal-001"
    assert payload["goals"][0]["parent_key"] == "goal-002"
    assert payload["goals"][1]["parent_key"] is None
    assert payload["roles"][0]["local_key"] == "role-001"
    assert payload["roles"][0]["permissions"] == ["reports:read"]
    serialized = str(payload)
    for private_value in (
        "cmp_private_source",
        "goal_root_domain_id",
        "agent-private",
        "10.0.0.8",
        "provider_account",
    ):
        assert private_value not in serialized


def test_import_rejects_extra_environment_or_execution_fields_without_echoing() -> None:
    payload = {
        "schema_version": "1.0",
        "company": {"name": "Example", "mission": ""},
        "goals": [],
        "roles": [],
        "playbooks": [],
        "provider_account_id": "acct-private-123",
    }
    with pytest.raises(CompanyTemplateError) as error:
        validate_company_template(payload)
    assert "acct-private-123" not in str(error.value)

    secret_role_payload = {
        "schema_version": "1.0",
        "company": {"name": "Example", "mission": ""},
        "goals": [],
        "roles": [
            {
                "local_key": "role-001",
                "display_name": "Operations",
                "role": "operator",
                "title": "",
                "responsibilities": ["Use api_key=super-secret-value"],
                "permissions": [],
                "skill_references": [],
            }
        ],
        "playbooks": [],
    }
    with pytest.raises(CompanyTemplateError) as error:
        validate_company_template(secret_role_payload)
    assert "super-secret-value" not in str(error.value)


def test_export_rejects_private_environment_urls_with_redacted_error() -> None:
    company = CompanyContext(company_id="cmp_secret", name="Example")
    role = AgentRole(
        company_id=company.company_id,
        agent_id="agent-secret",
        display_name="Operations",
        responsibilities=["Call http://service.internal/private"],
    )
    with pytest.raises(CompanyTemplateError) as error:
        export_company_template(company, [], [role])
    assert "service.internal" not in str(error.value)


@pytest.mark.parametrize(
    ("goals", "roles", "playbooks", "message"),
    [
        ([{"local_key": "g1", "title": "One", "parent_key": "missing"}], [], [], "dangling_goal"),
        (
            [
                {"local_key": "g1", "title": "One", "parent_key": "g2"},
                {"local_key": "g2", "title": "Two", "parent_key": "g1"},
            ],
            [],
            [],
            "goal_parent_cycle",
        ),
        (
            [{"local_key": "g1", "title": "One"}, {"local_key": "g1", "title": "Two"}],
            [],
            [],
            "duplicate_goal_local_key",
        ),
        (
            [],
            [{"local_key": "r1", "display_name": "Role", "role": "worker"}],
            [
                {
                    "key": "p1",
                    "title": "Flow",
                    "steps": [{"role_key": "missing", "action": "Review"}],
                }
            ],
            "dangling_playbook_role_reference",
        ),
        (
            [],
            [
                {
                    "local_key": "r1",
                    "display_name": "One",
                    "role": "worker",
                    "reports_to_key": "r2",
                },
                {
                    "local_key": "r2",
                    "display_name": "Two",
                    "role": "worker",
                    "reports_to_key": "r1",
                },
            ],
            [],
            "role_reporting_cycle",
        ),
        (
            [],
            [
                {
                    "local_key": "r1",
                    "display_name": "Role",
                    "role": "worker",
                    "budget_key": "missing",
                }
            ],
            [],
            "dangling_role_budget_reference",
        ),
    ],
)
def test_import_rejects_dangling_cyclic_and_colliding_references(
    goals: list[dict],
    roles: list[dict],
    playbooks: list[dict],
    message: str,
) -> None:
    payload = {
        "schema_version": "1.0",
        "company": {"name": "Example", "mission": ""},
        "goals": goals,
        "roles": roles,
        "playbooks": playbooks,
    }
    with pytest.raises(CompanyTemplateError, match="invalid_company_template"):
        validate_company_template(payload)


def test_export_rejects_duplicate_source_id_collision() -> None:
    company = CompanyContext(company_id="cmp_collision", name="Example")
    duplicate_goal = SimpleNamespace(
        goal_id="goal-same",
        company_id=company.company_id,
        title="A goal",
        description="",
        parent_goal_id=None,
    )
    with pytest.raises(CompanyTemplateError, match="duplicate_goal_source_id"):
        export_company_template(company, [duplicate_goal, duplicate_goal], [])


@pytest.mark.parametrize("ceiling", [float("nan"), float("inf"), -float("inf")])
def test_template_rejects_non_finite_budget_ceiling(ceiling: float) -> None:
    payload = {
        "schema_version": "1.0",
        "company": {"name": "Example", "mission": ""},
        "budgets": [
            {
                "local_key": "budget-1",
                "scope": "company",
                "period": "monthly",
                "ceiling_usd": ceiling,
            }
        ],
    }
    with pytest.raises(CompanyTemplateError, match="invalid_company_template"):
        validate_company_template(payload)


def test_template_rejects_unknown_budget_scope_key() -> None:
    payload = {
        "schema_version": "1.0",
        "company": {"name": "Example", "mission": ""},
        "roles": [{"local_key": "role-1", "display_name": "Worker", "role": "worker"}],
        "budgets": [
            {
                "local_key": "budget-1",
                "scope": "agent",
                "scope_key": "unknown-role",
                "period": "monthly",
                "ceiling_usd": 1.0,
            }
        ],
    }
    with pytest.raises(CompanyTemplateError, match="invalid_company_template"):
        validate_company_template(payload)


def test_template_round_trip_preserves_reporting_goal_ownership_and_budget_scopes() -> None:
    company = CompanyContext(company_id="cmp_structure_source", name="Structure Source")
    goals = [
        Goal(
            goal_id="goal_delivery",
            company_id=company.company_id,
            title="Deliver",
            owner_agent_id="agent_worker",
        )
    ]
    roles = [
        AgentRole(
            company_id=company.company_id,
            agent_id="agent_manager",
            display_name="Manager",
            role="manager",
        ),
        AgentRole(
            company_id=company.company_id,
            agent_id="agent_worker",
            display_name="Worker",
            role="worker",
            reports_to_agent_id="agent_manager",
            budget_policy_id="budget_worker",
        ),
    ]
    budgets = [
        BudgetPolicy(
            budget_id="budget_company",
            company_id=company.company_id,
            scope=BudgetScope.COMPANY,
            period=BudgetPeriod.MONTHLY,
            limit_usd=100.0,
            warning_threshold=0.7,
            model_allowlist=["model-sample"],
        ),
        BudgetPolicy(
            budget_id="budget_goal",
            company_id=company.company_id,
            scope=BudgetScope.GOAL,
            scope_id="goal_delivery",
            period=BudgetPeriod.QUARTERLY,
            limit_usd=200.0,
        ),
        BudgetPolicy(
            budget_id="budget_worker",
            company_id=company.company_id,
            scope=BudgetScope.AGENT,
            scope_id="agent_worker",
            period=BudgetPeriod.DAILY,
            limit_usd=10.0,
        ),
        BudgetPolicy(
            budget_id="budget_runtime_workitem",
            company_id=company.company_id,
            scope=BudgetScope.WORK_ITEM,
            scope_id="work_private",
            period=BudgetPeriod.DAILY,
            limit_usd=1.0,
        ),
    ]

    exported = export_company_template(company, goals, roles, budgets=budgets)
    validated = validate_company_template(exported.model_dump(mode="json"))

    assert validated == exported
    assert len(exported.budgets) == 3
    role_by_name = {role.display_name: role for role in exported.roles}
    assert role_by_name["Worker"].reports_to_key == role_by_name["Manager"].local_key
    assert exported.goals[0].owner_role_key == role_by_name["Worker"].local_key
    worker_budget = next(budget for budget in exported.budgets if budget.local_key == "budget-003")
    assert worker_budget.scope == "agent"
    assert worker_budget.scope_key == role_by_name["Worker"].local_key
    assert role_by_name["Worker"].budget_key == worker_budget.local_key
    assert (
        next(budget for budget in exported.budgets if budget.scope == "goal").scope_key
        == exported.goals[0].local_key
    )
    payload_text = str(exported.model_dump(mode="json"))
    for private_value in (
        company.company_id,
        "agent_manager",
        "agent_worker",
        "goal_delivery",
        "work_private",
        "budget_runtime_workitem",
    ):
        assert private_value not in payload_text


@pytest.mark.asyncio
async def test_export_preserves_persisted_role_keys_and_playbook_semantics() -> None:
    class Store:
        def __init__(self):
            self.company = None
            self.roles = []
            self.budgets = []

        async def list_companies(self, **_kwargs):
            return []

        async def create_company(self, company):
            self.company = company
            return company

        async def get_company(self, _company_id):
            return self.company

        async def create_agent_role(self, role):
            # Reproduce independently generated runtime IDs whose order disagrees
            # with the template's portable keys.
            local_key = role.metadata["template_import"]["local_key"]
            generated_id = {
                "portable-author": "agent_zz_random_generated_id",
                "portable-reviewer": "agent_aa_random_generated_id",
            }[local_key]
            created = role.model_copy(update={"agent_id": generated_id})
            self.roles.append(created)
            return created

        async def list_goals(self, **_kwargs):
            return []

        async def list_agent_roles(self, **_kwargs):
            # Deliberately reverse creation order too.
            return list(reversed(self.roles))

        async def list_budget_policies(self, **_kwargs):
            return list(self.budgets)

        async def create_budget_policy(self, budget):
            budget = budget.model_copy(update={"budget_id": f"bud_new_{len(self.budgets) + 1}"})
            self.budgets.append(budget)
            return budget

    store = Store()
    imported = await import_company_template(
        store,
        {
            "schema_version": "1.0",
            "company": {"name": "Example Cell", "mission": ""},
            "goals": [],
            "roles": [
                {"local_key": "portable-author", "display_name": "Author", "role": "writer"},
                {"local_key": "portable-reviewer", "display_name": "Reviewer", "role": "reviewer"},
            ],
            "playbooks": [
                {
                    "key": "handoff",
                    "title": "Handoff",
                    "steps": [
                        {"role_key": "portable-author", "action": "Draft the report"},
                        {"role_key": "portable-reviewer", "action": "Review the report"},
                    ],
                }
            ],
        },
        permissions_reviewed=True,
    )
    author, reviewer = store.roles
    exported = await export_company_template_for_company(store, company_id=imported.company_id)
    role_names = {role.local_key: role.display_name for role in exported.roles}
    steps = exported.playbooks[0].steps

    assert role_names == {
        "portable-author": "Author",
        "portable-reviewer": "Reviewer",
    }
    assert [(role_names[step.role_key], step.action) for step in steps] == [
        ("Author", "Draft the report"),
        ("Reviewer", "Review the report"),
    ]
    serialized = str(exported.model_dump(mode="json"))
    for environment_id in (
        store.company.company_id,
        author.role_id,
        reviewer.role_id,
        author.agent_id,
        reviewer.agent_id,
    ):
        assert environment_id not in serialized


def test_legacy_role_key_mapping_remains_stable_and_partial_mapping_with_playbooks_is_rejected() -> (
    None
):
    company = CompanyContext(company_id="cmp_legacy", name="Legacy Cell")
    legacy_roles = [
        SimpleNamespace(
            company_id=company.company_id, agent_id="agent_z", display_name="Second", role="worker"
        ),
        SimpleNamespace(
            company_id=company.company_id, agent_id="agent_a", display_name="First", role="worker"
        ),
    ]
    playbook = {
        "key": "legacy-flow",
        "title": "Legacy flow",
        "steps": [
            {"role_key": "role-001", "action": "First action"},
            {"role_key": "role-002", "action": "Second action"},
        ],
    }

    exported = export_company_template(company, [], legacy_roles, [playbook])
    assert [(role.local_key, role.display_name) for role in exported.roles] == [
        ("role-001", "First"),
        ("role-002", "Second"),
    ]
    assert [step.role_key for step in exported.playbooks[0].steps] == ["role-001", "role-002"]

    partial_roles = [
        SimpleNamespace(
            company_id=company.company_id,
            agent_id="agent_a",
            display_name="First",
            role="worker",
            template_local_key="portable-first",
        ),
        SimpleNamespace(
            company_id=company.company_id, agent_id="agent_z", display_name="Second", role="worker"
        ),
    ]
    with pytest.raises(CompanyTemplateError, match="ambiguous_playbook_role_mapping"):
        export_company_template(company, [], partial_roles, [playbook])
