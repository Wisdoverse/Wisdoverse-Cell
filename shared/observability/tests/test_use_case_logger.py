"""Tests for shared.observability.use_case_logger."""

from __future__ import annotations

import logging
from typing import Any

import pytest
import structlog

from shared.observability.use_case_logger import log_use_case


@pytest.fixture(autouse=True)
def _capture_structlog(caplog):
    """Route structlog records into pytest's caplog buffer."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
    yield
    structlog.reset_defaults()


def _parse(records: list[Any]) -> list[dict]:
    """Best-effort parse of structlog JSON records captured by pytest."""
    import json

    out: list[dict] = []
    for rec in records:
        try:
            out.append(json.loads(rec.message))
        except (json.JSONDecodeError, TypeError):
            continue
    return out


@pytest.mark.asyncio
async def test_log_use_case_emits_start_and_complete(capsys):
    """Happy path: start + complete events with bound business IDs."""
    async with log_use_case(
        "qa.acceptance_execute",
        agent_id="qa-agent",
        run_id="run_01",
        work_item_id="wi_42",
    ):
        pass

    captured = capsys.readouterr().out.splitlines()
    assert any("use_case.started" in line for line in captured), captured
    assert any("use_case.completed" in line for line in captured), captured
    # Business IDs should appear on at least one emitted line.
    joined = "\n".join(captured)
    assert "qa-agent" in joined
    assert "run_01" in joined
    assert "wi_42" in joined
    # Duration should be reported on completion.
    assert "duration_ms" in joined


@pytest.mark.asyncio
async def test_log_use_case_emits_failed_on_exception(capsys):
    """Exception path: fail event emitted, original exception re-raised."""

    class BoomError(RuntimeError):
        pass

    with pytest.raises(BoomError):
        async with log_use_case(
            "qa.acceptance_execute",
            agent_id="qa-agent",
            run_id="run_02",
        ):
            raise BoomError("explode")

    captured = capsys.readouterr().out.splitlines()
    assert any("use_case.started" in line for line in captured), captured
    assert any("use_case.failed" in line for line in captured), captured
    joined = "\n".join(captured)
    assert "BoomError" in joined
    assert "run_02" in joined


@pytest.mark.asyncio
async def test_log_use_case_unrecognized_kwargs_go_under_ctx_prefix(capsys):
    """Unrecognized kwargs do not collide with reserved structlog names."""
    async with log_use_case(
        "evolution.proposal_score",
        agent_id="evolution-module",
        proposal_id="prop_99",
        custom_score=0.83,
    ):
        pass

    out = capsys.readouterr().out
    assert "ctx.proposal_id" in out
    assert "ctx.custom_score" in out


@pytest.mark.asyncio
async def test_log_use_case_unbinds_contextvars_on_exit():
    """Context vars added by the helper must be removed after exit."""
    async with log_use_case("pjm.decompose", agent_id="pjm-agent"):
        ctx = structlog.contextvars.get_contextvars()
        assert ctx.get("use_case") == "pjm.decompose"
        assert ctx.get("agent_id") == "pjm-agent"

    ctx = structlog.contextvars.get_contextvars()
    assert "use_case" not in ctx
    assert "agent_id" not in ctx


@pytest.mark.asyncio
async def test_log_use_case_unbinds_contextvars_on_exception():
    """Context vars must be removed even when the block raises."""
    with pytest.raises(ValueError):
        async with log_use_case("pjm.decompose", agent_id="pjm-agent"):
            raise ValueError("bang")

    ctx = structlog.contextvars.get_contextvars()
    assert "use_case" not in ctx
    assert "agent_id" not in ctx
