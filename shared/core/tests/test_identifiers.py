"""Tests for the typed identifier seed module (DDD-007)."""

from __future__ import annotations

from shared.core.identifiers import (
    GoalId,
    WorkItemId,
    new_company_id,
    new_goal_id,
    new_work_item_id,
)


def test_factory_returns_prefixed_id() -> None:
    work_item_id = new_work_item_id()
    assert isinstance(work_item_id, str)
    assert work_item_id.startswith("work_")


def test_factories_generate_distinct_values() -> None:
    a = new_company_id()
    b = new_company_id()
    assert a != b


def test_newtype_constructor_wraps_string() -> None:
    raw = "work_01hq3k4n5m6p7q8r9s0t"
    wrapped = WorkItemId(raw)
    # NewType is a passthrough at runtime; type checker treats it distinctly.
    assert wrapped == raw
    assert isinstance(wrapped, str)


def test_newtypes_are_distinct_types_to_a_type_checker() -> None:
    """NewTypes are str at runtime but distinct to static analysis.

    mypy / pyright would reject ``goal_id: GoalId = work_id`` even
    though the runtime value compares equal. This regression test
    pins the runtime-equality contract; type-distinctness is enforced
    by the type-check job, not pytest.
    """
    goal_id: GoalId = GoalId("goal_abc")
    work_item_id: WorkItemId = WorkItemId("work_abc")
    assert goal_id == "goal_abc"
    assert work_item_id == "work_abc"
    assert goal_id != work_item_id


def test_all_factories_match_id_prefix_contract() -> None:
    from shared.core.ids import IDPrefix

    cases = [
        (new_company_id, IDPrefix.COMPANY),
        (new_goal_id, IDPrefix.GOAL),
        (new_work_item_id, IDPrefix.WORK_ITEM),
    ]
    for factory, expected_prefix in cases:
        generated = factory()
        assert generated.startswith(f"{expected_prefix}_"), (
            f"{factory.__name__} → {generated} expected prefix {expected_prefix!r}"
        )
