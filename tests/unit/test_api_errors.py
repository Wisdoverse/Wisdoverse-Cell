"""Shared API error contract tests."""
import pytest
from fastapi import HTTPException

from shared.api import (
    ERROR_CODE_HEADER,
    ApiErrorCode,
    raise_a2a_auth_invalid_token,
    raise_a2a_auth_missing_or_invalid,
    raise_a2a_auth_token_expired,
    raise_a2a_missing_required_scope,
    raise_a2a_not_enabled,
    raise_a2a_rate_limit_exceeded,
    raise_a2a_task_not_found,
    raise_agent_not_found,
    raise_analysis_daily_report_failed,
    raise_analysis_risk_check_failed,
    raise_analysis_weekly_report_failed,
    raise_control_plane_api_error,
    raise_dev_agent_not_ready,
    raise_dsar_approval_required,
    raise_feishu_invalid_json,
    raise_feishu_invalid_signature,
    raise_feishu_signature_key_not_configured,
    raise_internal_auth_not_configured,
    raise_internal_auth_unauthorized,
    raise_mcp_invalid_json,
    raise_mcp_prompt_not_found,
    raise_mcp_resource_not_found,
    raise_mcp_tool_execution_failed,
    raise_mcp_tool_name_required,
    raise_mcp_tool_not_found,
    raise_outbound_adapter_not_found,
    raise_pm_alerts_failed,
    raise_pm_config_failed,
    raise_pm_config_refresh_failed,
    raise_pm_daily_report_failed,
    raise_pm_decomposition_forbidden,
    raise_pm_decomposition_not_found,
    raise_pm_decomposition_retry_failed,
    raise_pm_decomposition_unavailable,
    raise_pm_weekly_report_failed,
    raise_qa_run_detail_failed,
    raise_qa_run_failed,
    raise_qa_run_list_failed,
    raise_qa_run_not_found,
    raise_qa_run_timeout,
    raise_qa_stats_failed,
    raise_question_not_found,
    raise_requirement_not_found,
    raise_session_not_found,
    raise_wecom_corp_id_mismatch,
    raise_wecom_invalid_ciphertext,
    raise_wecom_invalid_encoding_aes_key,
    raise_wecom_invalid_encoding_aes_key_length,
    raise_wecom_invalid_message_length,
    raise_wecom_invalid_padding,
    raise_wecom_invalid_payload,
    raise_wecom_invalid_signature,
    raise_wecom_invalid_xml_payload,
    raise_wecom_missing_encrypted_payload,
    raise_wecom_missing_message_type,
    raise_wecom_security_not_configured,
)


def test_requirement_not_found_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_requirement_not_found()

    exc = exc_info.value
    assert exc.status_code == 404
    assert exc.detail == "Requirement not found"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.REQUIREMENT_NOT_FOUND.value


def test_control_plane_error_preserves_detail_and_sets_namespaced_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_control_plane_api_error(status_code=409, detail="company_already_exists")

    exc = exc_info.value
    assert exc.status_code == 409
    assert exc.detail == "company_already_exists"
    assert exc.headers[ERROR_CODE_HEADER] == "control_plane.company_already_exists"


def test_control_plane_error_sanitizes_dynamic_detail_for_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_control_plane_api_error(status_code=404, detail="Agent not found")

    exc = exc_info.value
    assert exc.status_code == 404
    assert exc.detail == "Agent not found"
    assert exc.headers[ERROR_CODE_HEADER] == "control_plane.agent_not_found"


def test_a2a_not_enabled_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_a2a_not_enabled()

    exc = exc_info.value
    assert exc.status_code == 501
    assert exc.detail == "A2A protocol not enabled for this agent"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.A2A_NOT_ENABLED.value


def test_a2a_task_not_found_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_a2a_task_not_found("task-123")

    exc = exc_info.value
    assert exc.status_code == 404
    assert exc.detail == "Task not found: task-123"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.A2A_TASK_NOT_FOUND.value


def test_a2a_auth_token_expired_preserves_headers_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_a2a_auth_token_expired()

    exc = exc_info.value
    assert exc.status_code == 401
    assert exc.detail == "Token has expired"
    assert exc.headers["WWW-Authenticate"] == "Bearer"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.A2A_AUTH_TOKEN_EXPIRED.value


def test_a2a_auth_invalid_token_preserves_headers_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_a2a_auth_invalid_token("Not enough segments")

    exc = exc_info.value
    assert exc.status_code == 401
    assert exc.detail == "Invalid token: Not enough segments"
    assert exc.headers["WWW-Authenticate"] == "Bearer"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.A2A_AUTH_INVALID_TOKEN.value


def test_a2a_auth_missing_or_invalid_preserves_headers_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_a2a_auth_missing_or_invalid()

    exc = exc_info.value
    assert exc.status_code == 401
    assert exc.detail == "Missing or invalid authentication"
    assert exc.headers["WWW-Authenticate"] == "Bearer"
    assert (
        exc.headers[ERROR_CODE_HEADER]
        == ApiErrorCode.A2A_AUTH_MISSING_OR_INVALID.value
    )


def test_a2a_missing_required_scope_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_a2a_missing_required_scope("a2a:write")

    exc = exc_info.value
    assert exc.status_code == 403
    assert exc.detail == "Missing required scope: a2a:write"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.A2A_MISSING_REQUIRED_SCOPE.value


def test_a2a_rate_limit_exceeded_preserves_retry_after_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_a2a_rate_limit_exceeded(9)

    exc = exc_info.value
    assert exc.status_code == 429
    assert exc.detail == "Rate limit exceeded"
    assert exc.headers["Retry-After"] == "9"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.A2A_RATE_LIMIT_EXCEEDED.value


def test_question_not_found_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_question_not_found()

    exc = exc_info.value
    assert exc.status_code == 404
    assert exc.detail == "Question not found"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.QUESTION_NOT_FOUND.value


def test_session_not_found_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_session_not_found()

    exc = exc_info.value
    assert exc.status_code == 404
    assert exc.detail == "Session not found or has no messages"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.SESSION_NOT_FOUND.value


def test_agent_not_found_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_agent_not_found()

    exc = exc_info.value
    assert exc.status_code == 404
    assert exc.detail == "agent_not_found"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.AGENT_NOT_FOUND.value


def test_analysis_daily_report_failed_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_analysis_daily_report_failed()

    exc = exc_info.value
    assert exc.status_code == 500
    assert exc.detail == "Daily report generation failed. Please retry later."
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.ANALYSIS_DAILY_REPORT_FAILED.value


def test_analysis_weekly_report_failed_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_analysis_weekly_report_failed()

    exc = exc_info.value
    assert exc.status_code == 500
    assert exc.detail == "Weekly report generation failed. Please retry later."
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.ANALYSIS_WEEKLY_REPORT_FAILED.value


def test_analysis_risk_check_failed_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_analysis_risk_check_failed()

    exc = exc_info.value
    assert exc.status_code == 500
    assert exc.detail == "Risk check failed. Please retry later."
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.ANALYSIS_RISK_CHECK_FAILED.value


def test_dev_agent_not_ready_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_dev_agent_not_ready()

    exc = exc_info.value
    assert exc.status_code == 503
    assert exc.detail == "Agent not ready"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.DEV_AGENT_NOT_READY.value


def test_dsar_approval_required_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_dsar_approval_required("control_plane_approval_required")

    exc = exc_info.value
    assert exc.status_code == 403
    assert exc.detail == "control_plane_approval_required"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.DSAR_APPROVAL_REQUIRED.value


def test_feishu_signature_key_not_configured_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_feishu_signature_key_not_configured()

    exc = exc_info.value
    assert exc.status_code == 401
    assert exc.detail == "Signature verification key is not configured"
    assert (
        exc.headers[ERROR_CODE_HEADER]
        == ApiErrorCode.FEISHU_SIGNATURE_KEY_NOT_CONFIGURED.value
    )


def test_feishu_invalid_signature_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_feishu_invalid_signature()

    exc = exc_info.value
    assert exc.status_code == 401
    assert exc.detail == "Invalid signature"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.FEISHU_INVALID_SIGNATURE.value


def test_feishu_invalid_json_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_feishu_invalid_json()

    exc = exc_info.value
    assert exc.status_code == 400
    assert exc.detail == "Invalid JSON"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.FEISHU_INVALID_JSON.value


def test_internal_auth_not_configured_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_internal_auth_not_configured()

    exc = exc_info.value
    assert exc.status_code == 503
    assert exc.detail == "Internal service authentication is not configured"
    assert (
        exc.headers[ERROR_CODE_HEADER]
        == ApiErrorCode.INTERNAL_AUTH_NOT_CONFIGURED.value
    )


def test_internal_auth_unauthorized_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_internal_auth_unauthorized()

    exc = exc_info.value
    assert exc.status_code == 401
    assert exc.detail == "Unauthorized"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.INTERNAL_AUTH_UNAUTHORIZED.value


@pytest.mark.parametrize(
    ("raise_func", "status_code", "detail", "code"),
    [
        (
            raise_mcp_invalid_json,
            400,
            "Invalid JSON",
            ApiErrorCode.MCP_INVALID_JSON,
        ),
        (
            raise_mcp_tool_name_required,
            400,
            "Tool name is required",
            ApiErrorCode.MCP_TOOL_NAME_REQUIRED,
        ),
        (
            raise_mcp_tool_not_found,
            404,
            "Tool not found",
            ApiErrorCode.MCP_TOOL_NOT_FOUND,
        ),
        (
            raise_mcp_tool_execution_failed,
            500,
            "Tool execution failed",
            ApiErrorCode.MCP_TOOL_EXECUTION_FAILED,
        ),
        (
            raise_mcp_resource_not_found,
            404,
            "Resource not found",
            ApiErrorCode.MCP_RESOURCE_NOT_FOUND,
        ),
        (
            raise_mcp_prompt_not_found,
            404,
            "Prompt not found",
            ApiErrorCode.MCP_PROMPT_NOT_FOUND,
        ),
    ],
)
def test_mcp_errors_preserve_detail_and_set_error_code(
    raise_func,
    status_code,
    detail,
    code,
):
    with pytest.raises(HTTPException) as exc_info:
        raise_func()

    exc = exc_info.value
    assert exc.status_code == status_code
    assert exc.detail == detail
    assert exc.headers[ERROR_CODE_HEADER] == code.value


def test_outbound_adapter_not_found_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_outbound_adapter_not_found()

    exc = exc_info.value
    assert exc.status_code == 404
    assert exc.detail == "Adapter not found"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.OUTBOUND_ADAPTER_NOT_FOUND.value


@pytest.mark.parametrize(
    ("raise_func", "status_code", "detail", "code"),
    [
        (
            raise_wecom_invalid_encoding_aes_key_length,
            503,
            "Invalid WeCom EncodingAESKey length",
            ApiErrorCode.WECOM_INVALID_ENCODING_AES_KEY_LENGTH,
        ),
        (
            raise_wecom_invalid_encoding_aes_key,
            503,
            "Invalid WeCom EncodingAESKey",
            ApiErrorCode.WECOM_INVALID_ENCODING_AES_KEY,
        ),
        (
            raise_wecom_invalid_ciphertext,
            403,
            "Invalid WeCom ciphertext",
            ApiErrorCode.WECOM_INVALID_CIPHERTEXT,
        ),
        (
            raise_wecom_invalid_padding,
            403,
            "Invalid WeCom padding",
            ApiErrorCode.WECOM_INVALID_PADDING,
        ),
        (
            raise_wecom_invalid_payload,
            403,
            "Invalid WeCom payload",
            ApiErrorCode.WECOM_INVALID_PAYLOAD,
        ),
        (
            raise_wecom_invalid_message_length,
            403,
            "Invalid WeCom message length",
            ApiErrorCode.WECOM_INVALID_MESSAGE_LENGTH,
        ),
        (
            raise_wecom_corp_id_mismatch,
            403,
            "WeCom corp_id mismatch",
            ApiErrorCode.WECOM_CORP_ID_MISMATCH,
        ),
        (
            raise_wecom_invalid_signature,
            403,
            "Invalid WeCom signature",
            ApiErrorCode.WECOM_INVALID_SIGNATURE,
        ),
        (
            raise_wecom_missing_encrypted_payload,
            400,
            "Missing encrypted WeCom payload",
            ApiErrorCode.WECOM_MISSING_ENCRYPTED_PAYLOAD,
        ),
        (
            raise_wecom_missing_message_type,
            400,
            "Missing WeCom message type",
            ApiErrorCode.WECOM_MISSING_MESSAGE_TYPE,
        ),
        (
            raise_wecom_invalid_xml_payload,
            400,
            "Invalid WeCom XML payload",
            ApiErrorCode.WECOM_INVALID_XML_PAYLOAD,
        ),
    ],
)
def test_wecom_static_errors_preserve_detail_and_set_error_code(
    raise_func,
    status_code,
    detail,
    code,
):
    with pytest.raises(HTTPException) as exc_info:
        raise_func()

    exc = exc_info.value
    assert exc.status_code == status_code
    assert exc.detail == detail
    assert exc.headers[ERROR_CODE_HEADER] == code.value


def test_wecom_security_not_configured_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_wecom_security_not_configured(["WECOM_TOKEN", "WECOM_CORP_ID"])

    exc = exc_info.value
    assert exc.status_code == 503
    assert (
        exc.detail
        == "WeCom webhook security is not configured: WECOM_TOKEN, WECOM_CORP_ID"
    )
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.WECOM_SECURITY_NOT_CONFIGURED.value


def test_qa_run_not_found_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_qa_run_not_found()

    exc = exc_info.value
    assert exc.status_code == 404
    assert exc.detail == "QA acceptance run not found"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.QA_RUN_NOT_FOUND.value


def test_qa_run_timeout_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_qa_run_timeout()

    exc = exc_info.value
    assert exc.status_code == 504
    assert exc.detail == "QA acceptance run timed out"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.QA_RUN_TIMEOUT.value


def test_qa_run_failed_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_qa_run_failed("QA acceptance run failed: runner crashed")

    exc = exc_info.value
    assert exc.status_code == 500
    assert exc.detail == "QA acceptance run failed: runner crashed"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.QA_RUN_FAILED.value


def test_qa_run_list_failed_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_qa_run_list_failed()

    exc = exc_info.value
    assert exc.status_code == 500
    assert exc.detail == "Failed to list QA acceptance runs"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.QA_RUN_LIST_FAILED.value


def test_qa_run_detail_failed_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_qa_run_detail_failed()

    exc = exc_info.value
    assert exc.status_code == 500
    assert exc.detail == "Failed to get QA acceptance run details"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.QA_RUN_DETAIL_FAILED.value


def test_qa_stats_failed_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_qa_stats_failed()

    exc = exc_info.value
    assert exc.status_code == 500
    assert exc.detail == "Failed to get QA acceptance statistics"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.QA_STATS_FAILED.value


def test_pm_decomposition_not_found_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_pm_decomposition_not_found()

    exc = exc_info.value
    assert exc.status_code == 404
    assert exc.detail == "Record not found"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.PM_DECOMPOSITION_NOT_FOUND.value


def test_pm_config_failed_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_pm_config_failed()

    exc = exc_info.value
    assert exc.status_code == 500
    assert exc.detail == "Failed to get PM configuration. Please retry later."
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.PM_CONFIG_FAILED.value


def test_pm_config_refresh_failed_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_pm_config_refresh_failed()

    exc = exc_info.value
    assert exc.status_code == 500
    assert exc.detail == "Failed to refresh PM configuration. Please retry later."
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.PM_CONFIG_REFRESH_FAILED.value


def test_pm_alerts_failed_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_pm_alerts_failed()

    exc = exc_info.value
    assert exc.status_code == 500
    assert exc.detail == "Failed to get PM alerts. Please retry later."
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.PM_ALERTS_FAILED.value


def test_pm_daily_report_failed_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_pm_daily_report_failed()

    exc = exc_info.value
    assert exc.status_code == 500
    assert exc.detail == "Failed to generate daily report. Please retry later."
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.PM_DAILY_REPORT_FAILED.value


def test_pm_weekly_report_failed_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_pm_weekly_report_failed()

    exc = exc_info.value
    assert exc.status_code == 500
    assert exc.detail == "Failed to generate weekly report. Please retry later."
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.PM_WEEKLY_REPORT_FAILED.value


def test_pm_decomposition_retry_failed_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_pm_decomposition_retry_failed(status_code=404, message="Retry failed")

    exc = exc_info.value
    assert exc.status_code == 404
    assert exc.detail == "Retry failed"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.PM_DECOMPOSITION_RETRY_FAILED.value


def test_pm_decomposition_forbidden_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_pm_decomposition_forbidden("approved_by required")

    exc = exc_info.value
    assert exc.status_code == 403
    assert exc.detail == "approved_by required"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.PM_DECOMPOSITION_FORBIDDEN.value


def test_pm_decomposition_unavailable_preserves_detail_and_sets_error_code():
    with pytest.raises(HTTPException) as exc_info:
        raise_pm_decomposition_unavailable(status_code=400)

    exc = exc_info.value
    assert exc.status_code == 400
    assert exc.detail == "Record not found or status is not pending"
    assert exc.headers[ERROR_CODE_HEADER] == ApiErrorCode.PM_DECOMPOSITION_UNAVAILABLE.value
