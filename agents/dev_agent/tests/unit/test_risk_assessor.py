import pytest

from agents.dev_agent.core.risk_assessor import TaskRiskAssessor
from agents.dev_agent.models.schemas import RiskLevel, SanitizedTask


@pytest.fixture
def assessor():
    return TaskRiskAssessor()


def test_docs_is_low(assessor):
    task = SanitizedTask(title="Update README", description="Fix typo in docs", estimated_hours=1)
    assert assessor.assess(task) == RiskLevel.LOW


def test_test_is_low(assessor):
    task = SanitizedTask(
        title="Add unit tests",
        description="Add tests for parser",
        estimated_hours=4,
    )
    assert assessor.assess(task) == RiskLevel.LOW


def test_feature_is_medium(assessor):
    task = SanitizedTask(
        title="Add login page",
        description="Implement user login",
        estimated_hours=8,
    )
    assert assessor.assess(task) == RiskLevel.MEDIUM


def test_shared_is_high(assessor):
    task = SanitizedTask(
        title="Update schema",
        description="Add field",
        estimated_hours=4,
        related_files=["shared/schemas/event.py"],
    )
    assert assessor.assess(task) == RiskLevel.HIGH


def test_migration_is_critical(assessor):
    task = SanitizedTask(
        title="Add migration", description="Database migration for new table", estimated_hours=2
    )
    assert assessor.assess(task) == RiskLevel.CRITICAL


def test_infra_is_critical(assessor):
    task = SanitizedTask(
        title="Update docker", description="Modify infrastructure config", estimated_hours=1
    )
    assert assessor.assess(task) == RiskLevel.CRITICAL
