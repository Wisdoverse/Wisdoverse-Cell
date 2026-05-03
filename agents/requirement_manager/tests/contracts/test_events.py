"""
Contract tests for event format.

Ensures events published by the Agent match the Pydantic model definitions so
other Agents can parse them correctly when subscribed.
"""
import sys
from pathlib import Path

# Ensure the project root is on the Python path.
_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from shared.schemas.event import EventTypes
from shared.schemas.event_payloads import (
    EVENT_PAYLOAD_MODELS,
    RequirementConfirmedPayload,
    RequirementDeletedPayload,
    RequirementExtractedPayload,
    RequirementRejectedPayload,
    RequirementSummary,
    validate_event_payload,
)


class TestEventPayloadModels:
    """Event payload model tests."""

    def test_requirement_extracted_payload_valid(self):
        """Validate requirement.extracted payload model."""
        payload = RequirementExtractedPayload(
            meeting_id="mtg_123",
            requirement_ids=["req_1", "req_2"],
            count=2,
            requirements=[
                RequirementSummary(
                    id="req_1",
                    title="离线录音",
                    priority="HIGH",
                    category="功能"
                ),
                RequirementSummary(
                    id="req_2",
                    title="多格式支持",
                    priority="MEDIUM",
                    category="功能"
                )
            ]
        )

        assert payload.meeting_id == "mtg_123"
        assert payload.count == 2
        assert len(payload.requirements) == 2

    def test_requirement_extracted_payload_invalid_count(self):
        """Require count to be at least 1."""
        with pytest.raises(ValidationError):
            RequirementExtractedPayload(
                meeting_id="mtg_123",
                requirement_ids=[],
                count=0,  # Invalid
                requirements=[]
            )

    def test_requirement_confirmed_payload_valid(self):
        """Validate requirement.confirmed payload model."""
        payload = RequirementConfirmedPayload(
            requirement_id="req_123",
            title="离线录音功能",
            priority="HIGH",
            category="功能",
            confirmed_by="张三",
            confirmed_at="2026-01-21T10:00:00Z"
        )

        assert payload.requirement_id == "req_123"
        assert payload.confirmed_by == "张三"

    def test_requirement_confirmed_payload_missing_field(self):
        """Validate required fields."""
        with pytest.raises(ValidationError):
            RequirementConfirmedPayload(
                requirement_id="req_123",
                title="离线录音功能",
                # Missing priority, category, confirmed_by, and confirmed_at.
            )

    def test_requirement_rejected_payload_valid(self):
        """Validate requirement.rejected payload model."""
        payload = RequirementRejectedPayload(
            requirement_id="req_123",
            title="某需求",
            reason="不符合产品方向",
            rejected_at="2026-01-21T10:00:00Z"
        )

        assert payload.reason == "不符合产品方向"

    def test_requirement_deleted_payload_valid(self):
        """Validate requirement.deleted payload model."""
        payload = RequirementDeletedPayload(
            requirement_id="req_123",
            title="被删除的需求",
            deleted_by="管理员",
            deleted_at="2026-01-22T10:00:00Z"
        )

        assert payload.requirement_id == "req_123"
        assert payload.deleted_by == "管理员"

    def test_requirement_deleted_payload_missing_field(self):
        """Validate required fields for deleted payload."""
        with pytest.raises(ValidationError):
            RequirementDeletedPayload(
                requirement_id="req_123",
                title="测试",
                # Missing deleted_by and deleted_at.
            )


class TestValidateEventPayload:
    """validate_event_payload function tests."""

    def test_validate_known_event_type(self):
        """Validate a known event type."""
        payload = {
            "requirement_id": "req_123",
            "title": "测试",
            "priority": "HIGH",
            "category": "功能",
            "confirmed_by": "用户",
            "confirmed_at": "2026-01-21T10:00:00Z"
        }

        result = validate_event_payload(
            EventTypes.REQUIREMENT_CONFIRMED,
            payload
        )

        assert isinstance(result, RequirementConfirmedPayload)

    def test_validate_unknown_event_type(self):
        """Raise for an unknown event type."""
        with pytest.raises(KeyError):
            validate_event_payload("unknown.event", {})

    def test_validate_invalid_payload(self):
        """Raise for an invalid payload."""
        with pytest.raises(ValidationError):
            validate_event_payload(
                EventTypes.REQUIREMENT_CONFIRMED,
                {"invalid": "data"}
            )


class TestAgentEventContracts:
    """Agent event contract tests."""

    def test_create_event_sets_source_agent(self, test_agent):
        """create_event sets the correct source_agent."""
        event = test_agent.create_event(
            event_type=EventTypes.REQUIREMENT_CONFIRMED,
            payload={"test": "data"}
        )

        assert event.source_agent == "requirement-manager"
        assert event.event_type == EventTypes.REQUIREMENT_CONFIRMED

    def test_create_event_generates_valid_id(self, test_agent):
        """create_event generates a valid event_id."""
        event = test_agent.create_event(
            event_type=EventTypes.REQUIREMENT_CONFIRMED,
            payload={}
        )

        assert event.event_id.startswith("evt_")

    @pytest.mark.asyncio
    async def test_confirm_publishes_valid_event(
        self,
        test_agent,
        mock_dependencies,
        captured_events
    ):
        """Confirming a requirement publishes a contract-compliant event."""
        from agents.requirement_manager.db.repository import RequirementRepository
        from agents.requirement_manager.models import Requirement

        # Mock requirement
        mock_requirement = MagicMock(spec=Requirement)
        mock_requirement.id = "req_123"
        mock_requirement.title = "测试需求"
        mock_requirement.priority = "HIGH"
        mock_requirement.category = "功能"

        # Mock repository
        mock_session = MagicMock()
        mock_repo = MagicMock(spec=RequirementRepository)
        mock_repo.confirm = AsyncMock(return_value=mock_requirement)

        with patch(
            "agents.requirement_manager.service.agent.RequirementRepository",
            return_value=mock_repo
        ):
            await test_agent.confirm_requirement(
                requirement_id="req_123",
                confirmed_by="测试用户",
                session=mock_session
            )

        # Validate event.
        assert len(captured_events) == 1
        event = captured_events[0]

        assert event.event_type == EventTypes.REQUIREMENT_CONFIRMED

        # Validate payload contract.
        payload = RequirementConfirmedPayload.model_validate(event.payload)
        assert payload.requirement_id == "req_123"
        assert payload.confirmed_by == "测试用户"
        assert payload.title == "测试需求"

    @pytest.mark.asyncio
    async def test_reject_publishes_valid_event(
        self,
        test_agent,
        mock_dependencies,
        captured_events
    ):
        """Rejecting a requirement publishes a contract-compliant event."""
        from agents.requirement_manager.db.repository import RequirementRepository
        from agents.requirement_manager.models import Requirement

        # Mock requirement
        mock_requirement = MagicMock(spec=Requirement)
        mock_requirement.id = "req_456"
        mock_requirement.title = "被拒绝的需求"

        mock_session = MagicMock()
        mock_repo = MagicMock(spec=RequirementRepository)
        mock_repo.reject = AsyncMock(return_value=mock_requirement)

        with patch(
            "agents.requirement_manager.service.agent.RequirementRepository",
            return_value=mock_repo
        ):
            await test_agent.reject_requirement(
                requirement_id="req_456",
                reason="不符合产品方向",
                rejected_by="产品经理",
                session=mock_session
            )

        # Validate event.
        assert len(captured_events) == 1
        event = captured_events[0]

        assert event.event_type == EventTypes.REQUIREMENT_REJECTED

        # Validate payload contract.
        payload = RequirementRejectedPayload.model_validate(event.payload)
        assert payload.requirement_id == "req_456"
        assert payload.reason == "不符合产品方向"

    @pytest.mark.asyncio
    async def test_delete_publishes_valid_event(
        self,
        test_agent,
        mock_dependencies,
        captured_events
    ):
        """Deleting a requirement publishes a contract-compliant event."""
        from agents.requirement_manager.db.repository import RequirementRepository
        from agents.requirement_manager.models import Requirement

        # Mock requirement
        mock_requirement = MagicMock(spec=Requirement)
        mock_requirement.id = "req_789"
        mock_requirement.title = "被删除的需求"

        mock_session = MagicMock()
        mock_repo = MagicMock(spec=RequirementRepository)
        mock_repo.delete = AsyncMock(return_value=mock_requirement)

        with patch(
            "agents.requirement_manager.service.agent.RequirementRepository",
            return_value=mock_repo
        ):
            await test_agent.delete_requirement(
                requirement_id="req_789",
                deleted_by="管理员",
                session=mock_session
            )

        # Validate event.
        assert len(captured_events) == 1
        event = captured_events[0]

        assert event.event_type == EventTypes.REQUIREMENT_DELETED

        # Validate payload contract.
        payload = RequirementDeletedPayload.model_validate(event.payload)
        assert payload.requirement_id == "req_789"
        assert payload.deleted_by == "管理员"
        assert payload.title == "被删除的需求"


class TestEventPayloadCoverage:
    """Ensure every published event type has a contract."""

    def test_all_published_events_have_contracts(self, test_agent):
        """Each declared published event has a corresponding payload model."""
        for event_type in test_agent.published_events:
            assert event_type in EVENT_PAYLOAD_MODELS, \
                f"Event type '{event_type}' has no payload model defined"
