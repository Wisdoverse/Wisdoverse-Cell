"""PJM agent domain layer.

Holds entities, value objects, aggregates, invariants, and lifecycle
policies. Must not import from infrastructure (`agents.pjm_agent.db`,
`agents.pjm_agent.adapters`, `shared.infra.*`, `shared.integrations.*`) or
from interfaces (`agents.pjm_agent.api`, `agents.pjm_agent.app`).

See docs/architecture/architecture-principles.md §1.
"""
