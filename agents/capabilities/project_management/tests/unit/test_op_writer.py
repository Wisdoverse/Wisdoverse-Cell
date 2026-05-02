"""
Unit Tests - OPWriterService

Tests for writing WBS results to OpenProject as work packages.
"""

from unittest.mock import AsyncMock

import pytest

from agents.capabilities.project_management.core.op_writer import OPWriterService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def op_client():
    client = AsyncMock()
    # Default: create_work_package returns an id
    _counter = {"n": 100}

    async def _create_wp(project_id, data):
        _counter["n"] += 1
        return {"id": _counter["n"], "subject": data.get("subject", "")}

    client.create_work_package = AsyncMock(side_effect=_create_wp)
    return client


@pytest.fixture
def writer(op_client):
    return OPWriterService(op_client=op_client)


# ---------------------------------------------------------------------------
# write_wbs tests
# ---------------------------------------------------------------------------


class TestWriteWbs:
    @pytest.mark.asyncio
    async def test_nested_structure(self, writer, op_client):
        """write_wbs creates user stories and their child tasks."""
        wbs = {
            "subtasks": [
                {
                    "subject": "US-1 Authentication",
                    "estimated_days": 3,
                    "children": [
                        {"subject": "Task-1 Login form", "estimated_hours": 4},
                        {"subject": "Task-2 OAuth integration", "estimated_hours": 8},
                    ],
                },
                {
                    "subject": "US-2 Dashboard",
                    "estimated_days": 2,
                    "children": [
                        {"subject": "Task-3 Layout", "estimated_hours": 6},
                    ],
                },
            ]
        }

        result = await writer.write_wbs(parent_wp_id=1, project_id=10, wbs_result=wbs)

        assert result["stories_created"] == 2
        assert result["tasks_created"] == 3
        assert result["errors"] == []
        # 2 user stories + 3 tasks = 5 calls
        assert op_client.create_work_package.await_count == 5

    @pytest.mark.asyncio
    async def test_assignee_passed(self, writer, op_client):
        """When assignee_id is provided, user story gets assignee link."""
        wbs = {
            "subtasks": [
                {
                    "subject": "US with assignee",
                    "estimated_days": 1,
                    "children": [
                        {"subject": "Task under US", "estimated_hours": 2},
                    ],
                }
            ]
        }

        await writer.write_wbs(parent_wp_id=1, project_id=10, wbs_result=wbs, assignee_id=42)

        # First call creates the user story
        first_call_data = op_client.create_work_package.call_args_list[0][0][1]
        assert first_call_data["_links"]["assignee"]["href"] == "/api/v3/users/42"

    @pytest.mark.asyncio
    async def test_assignee_not_passed(self, writer, op_client):
        """When assignee_id is None, user story has no assignee link."""
        wbs = {
            "subtasks": [
                {
                    "subject": "US without assignee",
                    "estimated_days": 1,
                    "children": [
                        {"subject": "Task", "estimated_hours": 2},
                    ],
                }
            ]
        }

        await writer.write_wbs(parent_wp_id=1, project_id=10, wbs_result=wbs, assignee_id=None)

        first_call_data = op_client.create_work_package.call_args_list[0][0][1]
        assert "assignee" not in first_call_data["_links"]

    @pytest.mark.asyncio
    async def test_child_task_failure_doesnt_block_others(self, writer, op_client):
        """If one child task creation fails, sibling tasks and other stories still proceed."""
        call_count = {"n": 0}

        async def _create_wp_with_failure(project_id, data):
            call_count["n"] += 1
            # Fail on the second child task (3rd call overall: 1 US + 1st task ok + 2nd task fails)
            if call_count["n"] == 3:
                raise RuntimeError("API error")
            return {"id": call_count["n"], "subject": data.get("subject", "")}

        op_client.create_work_package = AsyncMock(side_effect=_create_wp_with_failure)

        wbs = {
            "subtasks": [
                {
                    "subject": "US-1",
                    "estimated_days": 1,
                    "children": [
                        {"subject": "Task-OK", "estimated_hours": 2},
                        {"subject": "Task-FAIL", "estimated_hours": 2},
                        {"subject": "Task-OK-2", "estimated_hours": 2},
                    ],
                }
            ]
        }

        result = await writer.write_wbs(parent_wp_id=1, project_id=10, wbs_result=wbs)

        assert result["stories_created"] == 1
        assert result["tasks_created"] == 2  # 2 succeeded, 1 failed
        assert len(result["errors"]) == 1
        assert "Task-FAIL" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_user_story_failure_skips_children(self, writer, op_client):
        """If user story creation fails, its children are not attempted."""
        call_count = {"n": 0}

        async def _fail_first_us(project_id, data):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("US creation failed")
            return {"id": call_count["n"], "subject": data.get("subject", "")}

        op_client.create_work_package = AsyncMock(side_effect=_fail_first_us)

        wbs = {
            "subtasks": [
                {
                    "subject": "US-FAIL",
                    "estimated_days": 1,
                    "children": [
                        {"subject": "Task-never-created", "estimated_hours": 2},
                    ],
                },
                {
                    "subject": "US-OK",
                    "estimated_days": 1,
                    "children": [
                        {"subject": "Task-created", "estimated_hours": 2},
                    ],
                },
            ]
        }

        result = await writer.write_wbs(parent_wp_id=1, project_id=10, wbs_result=wbs)

        assert result["stories_created"] == 1
        assert result["tasks_created"] == 1
        assert len(result["errors"]) == 1
        assert "US-FAIL" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_estimated_time_format(self, writer, op_client):
        """Estimated time is formatted as ISO 8601 duration."""
        wbs = {
            "subtasks": [
                {
                    "subject": "Story",
                    "estimated_days": 3,
                    "children": [
                        {"subject": "Task", "estimated_hours": 6},
                    ],
                }
            ]
        }

        await writer.write_wbs(parent_wp_id=1, project_id=10, wbs_result=wbs)

        # User story: 3 days * 8 hours = PT24H
        us_data = op_client.create_work_package.call_args_list[0][0][1]
        assert us_data["estimatedTime"] == "PT24H"

        # Task: 6 hours = PT6H
        task_data = op_client.create_work_package.call_args_list[1][0][1]
        assert task_data["estimatedTime"] == "PT6H"
