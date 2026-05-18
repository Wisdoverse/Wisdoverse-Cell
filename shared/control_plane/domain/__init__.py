"""Control plane domain layer.

Holds entities, value objects, aggregates, invariants, and lifecycle
policies for the control plane ledger. Must not import from infrastructure
(e.g. SQLAlchemy table modules, repository.py session helpers) outside of
the ports it consumes.

See docs/architecture/architecture-principles.md §1.
"""
