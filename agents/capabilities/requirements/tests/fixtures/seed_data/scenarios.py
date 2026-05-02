"""
E2E Test Scenarios

Defines complete end-to-end test scenarios combining meetings,
requirements, and expected outcomes for comprehensive testing.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from httpx import AsyncClient

from .meetings import MeetingData, MeetingFactory


@dataclass
class E2EScenario:
    """Complete E2E test scenario definition"""
    name: str
    description: str
    meeting_factory: Callable[[], MeetingData]
    expected_flow: list[str]
    assertions: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


class E2EScenarios:
    """Pre-defined E2E test scenarios"""

    HAPPY_PATH_SINGLE = E2EScenario(
        name="happy_path_single",
        description="Upload meeting -> Extract 1 requirement -> Confirm -> Export PRD",
        meeting_factory=MeetingFactory.simple_product_meeting,
        expected_flow=["upload", "wait_extraction", "list_pending", "confirm_all", "export_prd"],
        assertions={
            "requirements_extracted_min": 1,
            "final_status": "CONFIRMED",
            "prd_generated": True,
        },
        tags=["smoke", "happy_path"],
    )

    HAPPY_PATH_MULTI = E2EScenario(
        name="happy_path_multi",
        description="Upload complex meeting -> Extract multiple -> Partial confirm/reject",
        meeting_factory=MeetingFactory.complex_requirements_meeting,
        expected_flow=["upload", "wait_extraction", "list_pending", "confirm_first", "reject_second", "export_prd"],
        assertions={
            "requirements_extracted_min": 3,
            "confirmed_count_min": 1,
            "rejected_count_min": 1,
        },
        tags=["full_e2e", "happy_path"],
    )

    FEISHU_INTEGRATION = E2EScenario(
        name="feishu_integration",
        description="Feishu webhook -> Extract -> Confirm",
        meeting_factory=MeetingFactory.feishu_webhook_meeting,
        expected_flow=["feishu_upload", "wait_extraction", "list_pending", "confirm_all"],
        assertions={
            "source": "feishu",
            "requirements_extracted_min": 1,
        },
        tags=["integration", "feishu"],
    )

    WECOM_INTEGRATION = E2EScenario(
        name="wecom_integration",
        description="WeCom message -> Extract -> Confirm",
        meeting_factory=MeetingFactory.wecom_meeting,
        expected_flow=["wecom_upload", "wait_extraction", "list_pending", "confirm_all"],
        assertions={
            "source": "wecom",
            "requirements_extracted_min": 1,
        },
        tags=["integration", "wecom"],
    )

    EDGE_EMPTY_CONTENT = E2EScenario(
        name="edge_empty_content",
        description="Upload meeting with no requirements",
        meeting_factory=MeetingFactory.empty_content_meeting,
        expected_flow=["upload", "wait_extraction", "verify_empty"],
        assertions={
            "requirements_extracted": 0,
        },
        tags=["edge_case"],
    )

    EDGE_UNICODE = E2EScenario(
        name="edge_unicode",
        description="Upload meeting with unicode and special characters",
        meeting_factory=MeetingFactory.unicode_and_special_chars,
        expected_flow=["upload", "wait_extraction", "list_pending", "verify_content"],
        assertions={
            "requirements_extracted_min": 1,
            "no_encoding_errors": True,
        },
        tags=["edge_case", "unicode"],
    )

    CONFLICT_DETECTION = E2EScenario(
        name="conflict_detection",
        description="Upload similar requirements -> Detect conflicts",
        meeting_factory=MeetingFactory.conflicting_requirements,
        expected_flow=["upload", "wait_extraction", "check_conflicts"],
        assertions={
            "conflicts_detected": True,
        },
        tags=["conflict", "advanced"],
    )


class ScenarioRunner:
    """Helper class to execute E2E scenarios"""

    def __init__(self, client: AsyncClient, mock_llm: Optional[Any] = None):
        self.client = client
        self.mock_llm = mock_llm
        self.results: dict[str, Any] = {}
        self._meeting_id: Optional[str] = None
        self._requirement_ids: list[str] = []

    async def run(self, scenario: E2EScenario) -> dict[str, Any]:
        """Execute a complete scenario and return results"""
        self.results = {
            "scenario": scenario.name,
            "description": scenario.description,
            "steps": [],
            "success": True,
            "errors": [],
        }

        meeting = scenario.meeting_factory()

        for step in scenario.expected_flow:
            try:
                step_result = await self._execute_step(step, meeting)
                self.results["steps"].append({
                    "step": step,
                    "success": True,
                    "result": step_result,
                })
            except Exception as e:
                self.results["steps"].append({
                    "step": step,
                    "success": False,
                    "error": str(e),
                })
                self.results["success"] = False
                self.results["errors"].append(f"{step}: {e}")
                break

        return self.results

    async def _execute_step(self, step: str, meeting: MeetingData) -> dict[str, Any]:
        """Execute a single scenario step"""
        step_handlers = {
            "upload": lambda: self._step_upload(meeting),
            "feishu_upload": lambda: self._step_feishu_upload(meeting),
            "wecom_upload": lambda: self._step_wecom_upload(meeting),
            "wait_extraction": self._step_wait_extraction,
            "list_pending": lambda: self._step_list_requirements("PENDING"),
            "confirm_all": self._step_confirm_all,
            "confirm_first": self._step_confirm_first,
            "reject_second": self._step_reject_second,
            "export_prd": self._step_export_prd,
            "verify_empty": self._step_verify_empty,
            "verify_content": self._step_verify_content,
            "check_conflicts": self._step_check_conflicts,
        }

        handler = step_handlers.get(step)
        if handler is None:
            raise ValueError(f"Unknown step: {step}")
        return await handler()

    async def _step_upload(self, meeting: MeetingData) -> dict:
        """Upload a meeting"""
        resp = await self.client.post("/api/ingest/upload", json={
            "content": meeting.content,
            "source": meeting.source,
            "title": meeting.title,
        })
        resp.raise_for_status()
        data = resp.json()
        self._meeting_id = data.get("meeting_id")
        self._requirement_ids = data.get("requirement_ids", [])
        return {
            "meeting_id": self._meeting_id,
            "requirements_extracted": data.get("requirements_extracted", 0),
        }

    async def _step_feishu_upload(self, meeting: MeetingData) -> dict:
        """Upload via Feishu webhook"""
        resp = await self.client.post("/api/ingest/feishu", json={
            "event_type": "meeting.ended",
            "meeting_id": meeting.source_id or "feishu_test_001",
            "topic": meeting.title,
            "summary": meeting.content,
            "participants": meeting.participants,
        })
        resp.raise_for_status()
        data = resp.json()
        self._meeting_id = data.get("meeting_id")
        self._requirement_ids = data.get("requirement_ids", [])
        return data

    async def _step_wecom_upload(self, meeting: MeetingData) -> dict:
        """Upload via WeCom"""
        resp = await self.client.post("/api/ingest/upload", json={
            "content": meeting.content,
            "source": "wecom",
            "title": meeting.title,
        })
        resp.raise_for_status()
        data = resp.json()
        self._meeting_id = data.get("meeting_id")
        self._requirement_ids = data.get("requirement_ids", [])
        return data

    async def _step_wait_extraction(self) -> dict:
        """Wait for async extraction to complete (if needed)"""
        import asyncio
        await asyncio.sleep(0.5)
        return {"waited": True}

    async def _step_list_requirements(self, status: str) -> dict:
        """List requirements by status"""
        resp = await self.client.get("/api/requirements", params={"status": status})
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        self._requirement_ids = [r["id"] for r in items]
        return {
            "count": len(items),
            "requirement_ids": self._requirement_ids,
        }

    async def _step_confirm_all(self) -> dict:
        """Confirm all pending requirements"""
        confirmed = 0
        for req_id in self._requirement_ids:
            resp = await self.client.put(f"/api/requirements/{req_id}/confirm", json={
                "confirmed_by": "test_user"
            })
            if resp.status_code == 200:
                confirmed += 1
        return {"confirmed": confirmed}

    async def _step_confirm_first(self) -> dict:
        """Confirm only the first requirement"""
        if not self._requirement_ids:
            return {"confirmed": 0}
        req_id = self._requirement_ids[0]
        resp = await self.client.put(f"/api/requirements/{req_id}/confirm", json={
            "confirmed_by": "test_user"
        })
        return {"confirmed": 1 if resp.status_code == 200 else 0}

    async def _step_reject_second(self) -> dict:
        """Reject the second requirement"""
        if len(self._requirement_ids) < 2:
            return {"rejected": 0}
        req_id = self._requirement_ids[1]
        resp = await self.client.put(f"/api/requirements/{req_id}/reject", json={
            "reason": "不在本版本范围内",
            "rejected_by": "test_user"
        })
        return {"rejected": 1 if resp.status_code == 200 else 0}

    async def _step_export_prd(self) -> dict:
        """Export PRD document"""
        resp = await self.client.get("/api/export/prd")
        return {
            "success": resp.status_code == 200,
            "content_length": len(resp.text) if resp.status_code == 200 else 0,
        }

    async def _step_verify_empty(self) -> dict:
        """Verify no requirements were extracted"""
        resp = await self.client.get("/api/requirements")
        data = resp.json()
        count = data.get("total", len(data.get("items", [])))
        return {
            "is_empty": count == 0,
            "count": count,
        }

    async def _step_verify_content(self) -> dict:
        """Verify content was processed correctly"""
        if not self._requirement_ids:
            return {"verified": False}
        req_id = self._requirement_ids[0]
        resp = await self.client.get(f"/api/requirements/{req_id}")
        if resp.status_code != 200:
            return {"verified": False}
        data = resp.json()
        return {
            "verified": True,
            "title": data.get("title"),
            "has_description": bool(data.get("description")),
        }

    async def _step_check_conflicts(self) -> dict:
        """Check for conflicts with existing requirements"""
        if not self._requirement_ids:
            return {"conflicts_found": False}
        req_id = self._requirement_ids[0]
        resp = await self.client.get(f"/api/requirements/{req_id}/similar")
        if resp.status_code != 200:
            return {"conflicts_found": False}
        data = resp.json()
        similar = data.get("similar", [])
        return {
            "conflicts_found": len(similar) > 0,
            "similar_count": len(similar),
        }


# Scenario groups for different test runs
SMOKE_SCENARIOS = [
    E2EScenarios.HAPPY_PATH_SINGLE,
]

FULL_E2E_SCENARIOS = [
    E2EScenarios.HAPPY_PATH_SINGLE,
    E2EScenarios.HAPPY_PATH_MULTI,
    E2EScenarios.EDGE_EMPTY_CONTENT,
]

INTEGRATION_SCENARIOS = [
    E2EScenarios.FEISHU_INTEGRATION,
    E2EScenarios.WECOM_INTEGRATION,
]

EDGE_CASE_SCENARIOS = [
    E2EScenarios.EDGE_EMPTY_CONTENT,
    E2EScenarios.EDGE_UNICODE,
    E2EScenarios.CONFLICT_DETECTION,
]
