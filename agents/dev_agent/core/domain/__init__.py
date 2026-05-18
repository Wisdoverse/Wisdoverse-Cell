"""Dev agent domain layer.

Holds entities, value objects, aggregates, invariants, and lifecycle
policies. Must not import from infrastructure (`agents.dev_agent.db`,
`agents.dev_agent.adapters`, `shared.infra.*`, `shared.integrations.*`) or
from interfaces (`agents.dev_agent.api`, `agents.dev_agent.app`).

See docs/architecture/architecture-principles.md §1.
"""
