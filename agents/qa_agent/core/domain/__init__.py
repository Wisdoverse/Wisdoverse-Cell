"""QA agent domain layer.

Holds entities, value objects, aggregates, invariants, and verdict
policies. Must not import from infrastructure (`agents.qa_agent.db`,
`agents.qa_agent.adapters`, `shared.infra.*`, `shared.integrations.*`)
or from interfaces (`agents.qa_agent.api`, `agents.qa_agent.app`).

See docs/architecture/architecture-principles.md §1.
"""
