from shared.core import (
    UNKNOWN_ACTION_ERROR_CODE,
    request_error,
    unknown_action_error,
)


def test_request_error_keeps_message_code_and_extra_context():
    result = request_error(
        "invalid request",
        "invalid_request",
        request_id="req_123",
        ignored=None,
    )

    assert result == {
        "error": "invalid request",
        "error_code": "invalid_request",
        "request_id": "req_123",
    }


def test_unknown_action_error_keeps_extra_context():
    assert unknown_action_error(action="invalid") == {
        "error": "unknown action",
        "error_code": UNKNOWN_ACTION_ERROR_CODE,
        "action": "invalid",
    }
