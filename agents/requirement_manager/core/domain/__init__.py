"""Requirement manager domain layer.

Holds entities, value objects, aggregates, invariants, and lifecycle
policies. Must not import from infrastructure
(`agents.requirement_manager.db`, `agents.requirement_manager.adapters`,
`shared.infra.*`, `shared.integrations.*`) or from interfaces
(`agents.requirement_manager.api`, `agents.requirement_manager.app`).

See docs/architecture/architecture-principles.md §1.
"""
