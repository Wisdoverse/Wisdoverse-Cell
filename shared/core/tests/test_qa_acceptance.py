from shared.core.qa_acceptance import (
    QA_API_STATUS_ERROR,
    QA_API_STATUS_FAILED,
    QA_API_STATUS_PASSED,
    QA_FINDING_FAIL,
    QA_FINDING_INFO,
    QA_FINDING_LEVEL_L0,
    QA_FINDING_LEVEL_L1,
    QA_FINDING_LEVEL_L2,
    QA_FINDING_WARN,
    QA_GATE_ERROR,
    QA_GATE_FAIL,
    QA_GATE_PASS,
    is_qa_acceptance_failed,
    is_qa_acceptance_passed,
    is_qa_blocking_finding,
    is_qa_gate_failing,
    is_qa_gate_passing,
    is_qa_informational_finding,
    is_qa_warning_finding,
    qa_api_status_from_l0_gate,
    qa_l0_gate_from_summary,
)


def test_qa_gate_helpers_classify_published_summary() -> None:
    assert qa_l0_gate_from_summary({"l0_gate": QA_GATE_PASS}) == QA_GATE_PASS
    assert qa_l0_gate_from_summary({}) == QA_GATE_ERROR
    assert is_qa_acceptance_passed({"l0_gate": QA_GATE_PASS})
    assert not is_qa_acceptance_passed({"l0_gate": QA_GATE_FAIL})
    assert is_qa_acceptance_failed({"l0_gate": QA_GATE_FAIL})
    assert not is_qa_acceptance_failed({"l0_gate": QA_GATE_ERROR})


def test_qa_gate_helpers_classify_gate_value() -> None:
    assert is_qa_gate_passing(QA_GATE_PASS)
    assert not is_qa_gate_passing(QA_GATE_ERROR)
    assert is_qa_gate_failing(QA_GATE_FAIL)
    assert not is_qa_gate_failing(QA_GATE_PASS)


def test_qa_api_status_uses_published_gate_vocabulary() -> None:
    assert qa_api_status_from_l0_gate(QA_GATE_PASS) == QA_API_STATUS_PASSED
    assert qa_api_status_from_l0_gate(QA_GATE_FAIL) == QA_API_STATUS_FAILED
    assert qa_api_status_from_l0_gate(QA_GATE_ERROR) == QA_API_STATUS_ERROR
    assert qa_api_status_from_l0_gate("UNKNOWN") == QA_API_STATUS_ERROR


def test_qa_finding_helpers_classify_published_findings() -> None:
    assert is_qa_blocking_finding(
        level=QA_FINDING_LEVEL_L0,
        status=QA_FINDING_FAIL,
    )
    assert not is_qa_blocking_finding(
        level=QA_FINDING_LEVEL_L1,
        status=QA_FINDING_FAIL,
    )
    assert is_qa_warning_finding(
        level=QA_FINDING_LEVEL_L1,
        status=QA_FINDING_WARN,
    )
    assert is_qa_informational_finding(
        level=QA_FINDING_LEVEL_L2,
        status=QA_FINDING_INFO,
    )
