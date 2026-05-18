"""Shared API error helpers.

The first compatibility contract keeps FastAPI's existing ``detail`` string
shape while adding a stable machine-readable error code header.
"""

import re
from enum import StrEnum
from typing import NoReturn

from fastapi import HTTPException

ERROR_CODE_HEADER = "X-Error-Code"
_ERROR_CODE_FRAGMENT_RE = re.compile(r"[^a-z0-9_.-]+")


class ApiErrorCode(StrEnum):
    """Stable API error codes for HTTP clients and operators."""

    A2A_NOT_ENABLED = "a2a.not_enabled"
    A2A_AUTH_INVALID_TOKEN = "a2a.auth.invalid_token"
    A2A_AUTH_MISSING_OR_INVALID = "a2a.auth.missing_or_invalid"
    A2A_AUTH_TOKEN_EXPIRED = "a2a.auth.token_expired"
    A2A_MISSING_REQUIRED_SCOPE = "a2a.auth.missing_required_scope"
    A2A_RATE_LIMIT_EXCEEDED = "a2a.rate_limit_exceeded"
    A2A_TASK_NOT_FOUND = "a2a.task_not_found"
    AGENT_NOT_FOUND = "agent.not_found"
    ANALYSIS_DAILY_REPORT_FAILED = "analysis.daily_report_failed"
    ANALYSIS_RISK_CHECK_FAILED = "analysis.risk_check_failed"
    ANALYSIS_WEEKLY_REPORT_FAILED = "analysis.weekly_report_failed"
    DEV_AGENT_NOT_READY = "dev.agent_not_ready"
    DSAR_APPROVAL_REQUIRED = "dsar.approval_required"
    FEISHU_INVALID_JSON = "feishu.invalid_json"
    FEISHU_INVALID_SIGNATURE = "feishu.invalid_signature"
    FEISHU_SIGNATURE_KEY_NOT_CONFIGURED = "feishu.signature_key_not_configured"
    INTERNAL_AUTH_NOT_CONFIGURED = "internal_auth.not_configured"
    INTERNAL_AUTH_UNAUTHORIZED = "internal_auth.unauthorized"
    MCP_INVALID_JSON = "mcp.invalid_json"
    MCP_PROMPT_NOT_FOUND = "mcp.prompt_not_found"
    MCP_RESOURCE_NOT_FOUND = "mcp.resource_not_found"
    MCP_TOOL_EXECUTION_FAILED = "mcp.tool_execution_failed"
    MCP_TOOL_NAME_REQUIRED = "mcp.tool_name_required"
    MCP_TOOL_NOT_FOUND = "mcp.tool_not_found"
    OUTBOUND_ADAPTER_NOT_FOUND = "outbound.adapter_not_found"
    WECOM_CORP_ID_MISMATCH = "wecom.corp_id_mismatch"
    WECOM_INVALID_CIPHERTEXT = "wecom.invalid_ciphertext"
    WECOM_INVALID_ENCODING_AES_KEY = "wecom.invalid_encoding_aes_key"
    WECOM_INVALID_ENCODING_AES_KEY_LENGTH = "wecom.invalid_encoding_aes_key_length"
    WECOM_INVALID_MESSAGE_LENGTH = "wecom.invalid_message_length"
    WECOM_INVALID_PADDING = "wecom.invalid_padding"
    WECOM_INVALID_PAYLOAD = "wecom.invalid_payload"
    WECOM_INVALID_SIGNATURE = "wecom.invalid_signature"
    WECOM_INVALID_XML_PAYLOAD = "wecom.invalid_xml_payload"
    WECOM_MISSING_ENCRYPTED_PAYLOAD = "wecom.missing_encrypted_payload"
    WECOM_MISSING_MESSAGE_TYPE = "wecom.missing_message_type"
    WECOM_SECURITY_NOT_CONFIGURED = "wecom.security_not_configured"
    PM_ALERTS_FAILED = "pm.alerts_failed"
    PM_CONFIG_FAILED = "pm.config_failed"
    PM_CONFIG_REFRESH_FAILED = "pm.config_refresh_failed"
    PM_DAILY_REPORT_FAILED = "pm.daily_report_failed"
    PM_DECOMPOSITION_FORBIDDEN = "pm.decomposition_forbidden"
    PM_DECOMPOSITION_NOT_FOUND = "pm.decomposition_not_found"
    PM_DECOMPOSITION_RETRY_FAILED = "pm.decomposition_retry_failed"
    PM_DECOMPOSITION_UNAVAILABLE = "pm.decomposition_unavailable"
    PM_WEEKLY_REPORT_FAILED = "pm.weekly_report_failed"
    QA_RUN_DETAIL_FAILED = "qa.run_detail_failed"
    QA_RUN_FAILED = "qa.run_failed"
    QA_RUN_LIST_FAILED = "qa.run_list_failed"
    QA_RUN_NOT_FOUND = "qa.run_not_found"
    QA_RUN_TIMEOUT = "qa.run_timeout"
    QA_STATS_FAILED = "qa.stats_failed"
    REQUIREMENT_NOT_FOUND = "requirement.not_found"
    QUESTION_NOT_FOUND = "question.not_found"
    SESSION_NOT_FOUND = "session.not_found"


def raise_api_error(
    *,
    status_code: int,
    code: ApiErrorCode | str,
    message: str,
    headers: dict[str, str] | None = None,
) -> NoReturn:
    """Raise a FastAPI HTTPException with a stable error-code header."""
    response_headers = dict(headers or {})
    response_headers[ERROR_CODE_HEADER] = code.value if isinstance(code, ApiErrorCode) else code
    raise HTTPException(
        status_code=status_code,
        detail=message,
        headers=response_headers,
    )


def _control_plane_error_code(detail: str) -> str:
    normalized = _ERROR_CODE_FRAGMENT_RE.sub("_", detail.strip().lower()).strip("_.-")
    return f"control_plane.{normalized or 'operation_failed'}"


def raise_control_plane_api_error(*, status_code: int, detail: str) -> NoReturn:
    """Raise a control-plane API error with a stable namespaced error code."""
    raise_api_error(
        status_code=status_code,
        code=_control_plane_error_code(detail),
        message=detail,
    )


def raise_requirement_not_found() -> NoReturn:
    """Raise the canonical Requirement not-found error."""
    raise_api_error(
        status_code=404,
        code=ApiErrorCode.REQUIREMENT_NOT_FOUND,
        message="Requirement not found",
    )


def raise_a2a_not_enabled() -> NoReturn:
    """Raise the canonical A2A disabled error."""
    raise_api_error(
        status_code=501,
        code=ApiErrorCode.A2A_NOT_ENABLED,
        message="A2A protocol not enabled for this agent",
    )


def raise_a2a_auth_token_expired() -> NoReturn:
    """Raise the canonical A2A expired-token error."""
    raise_api_error(
        status_code=401,
        code=ApiErrorCode.A2A_AUTH_TOKEN_EXPIRED,
        message="Token has expired",
        headers={"WWW-Authenticate": "Bearer"},
    )


def raise_a2a_auth_invalid_token(message: str) -> NoReturn:
    """Raise the canonical A2A invalid-token error."""
    raise_api_error(
        status_code=401,
        code=ApiErrorCode.A2A_AUTH_INVALID_TOKEN,
        message=f"Invalid token: {message}",
        headers={"WWW-Authenticate": "Bearer"},
    )


def raise_a2a_auth_missing_or_invalid() -> NoReturn:
    """Raise the canonical A2A missing-or-invalid auth error."""
    raise_api_error(
        status_code=401,
        code=ApiErrorCode.A2A_AUTH_MISSING_OR_INVALID,
        message="Missing or invalid authentication",
        headers={"WWW-Authenticate": "Bearer"},
    )


def raise_a2a_missing_required_scope(required_scope: str) -> NoReturn:
    """Raise the canonical A2A missing required scope error."""
    raise_api_error(
        status_code=403,
        code=ApiErrorCode.A2A_MISSING_REQUIRED_SCOPE,
        message=f"Missing required scope: {required_scope}",
    )


def raise_a2a_rate_limit_exceeded(retry_after: int) -> NoReturn:
    """Raise the canonical A2A rate-limit error."""
    raise_api_error(
        status_code=429,
        code=ApiErrorCode.A2A_RATE_LIMIT_EXCEEDED,
        message="Rate limit exceeded",
        headers={"Retry-After": str(retry_after)},
    )


def raise_a2a_task_not_found(task_id: str) -> NoReturn:
    """Raise the canonical A2A task not-found error."""
    raise_api_error(
        status_code=404,
        code=ApiErrorCode.A2A_TASK_NOT_FOUND,
        message=f"Task not found: {task_id}",
    )


def raise_question_not_found() -> NoReturn:
    """Raise the canonical open-question not-found error."""
    raise_api_error(
        status_code=404,
        code=ApiErrorCode.QUESTION_NOT_FOUND,
        message="Question not found",
    )


def raise_session_not_found() -> NoReturn:
    """Raise the canonical message-session not-found error."""
    raise_api_error(
        status_code=404,
        code=ApiErrorCode.SESSION_NOT_FOUND,
        message="Session not found or has no messages",
    )


def raise_analysis_daily_report_failed() -> NoReturn:
    """Raise the canonical Analysis daily-report failure error."""
    raise_api_error(
        status_code=500,
        code=ApiErrorCode.ANALYSIS_DAILY_REPORT_FAILED,
        message="Daily report generation failed. Please retry later.",
    )


def raise_analysis_weekly_report_failed() -> NoReturn:
    """Raise the canonical Analysis weekly-report failure error."""
    raise_api_error(
        status_code=500,
        code=ApiErrorCode.ANALYSIS_WEEKLY_REPORT_FAILED,
        message="Weekly report generation failed. Please retry later.",
    )


def raise_analysis_risk_check_failed() -> NoReturn:
    """Raise the canonical Analysis risk-check failure error."""
    raise_api_error(
        status_code=500,
        code=ApiErrorCode.ANALYSIS_RISK_CHECK_FAILED,
        message="Risk check failed. Please retry later.",
    )


def raise_agent_not_found() -> NoReturn:
    """Raise the canonical agent not-found error."""
    raise_api_error(
        status_code=404,
        code=ApiErrorCode.AGENT_NOT_FOUND,
        message="agent_not_found",
    )


def raise_dev_agent_not_ready() -> NoReturn:
    """Raise the canonical Dev agent runtime-not-ready error."""
    raise_api_error(
        status_code=503,
        code=ApiErrorCode.DEV_AGENT_NOT_READY,
        message="Agent not ready",
    )


def raise_dsar_approval_required(message: str) -> NoReturn:
    """Raise the canonical DSAR delete approval-required error."""
    raise_api_error(
        status_code=403,
        code=ApiErrorCode.DSAR_APPROVAL_REQUIRED,
        message=message,
    )


def raise_feishu_signature_key_not_configured() -> NoReturn:
    """Raise the canonical Feishu signature-key configuration error."""
    raise_api_error(
        status_code=401,
        code=ApiErrorCode.FEISHU_SIGNATURE_KEY_NOT_CONFIGURED,
        message="Signature verification key is not configured",
    )


def raise_feishu_invalid_signature() -> NoReturn:
    """Raise the canonical Feishu invalid-signature error."""
    raise_api_error(
        status_code=401,
        code=ApiErrorCode.FEISHU_INVALID_SIGNATURE,
        message="Invalid signature",
    )


def raise_feishu_invalid_json() -> NoReturn:
    """Raise the canonical Feishu invalid-JSON error."""
    raise_api_error(
        status_code=400,
        code=ApiErrorCode.FEISHU_INVALID_JSON,
        message="Invalid JSON",
    )


def raise_internal_auth_not_configured() -> NoReturn:
    """Raise the canonical internal-auth configuration error."""
    raise_api_error(
        status_code=503,
        code=ApiErrorCode.INTERNAL_AUTH_NOT_CONFIGURED,
        message="Internal service authentication is not configured",
    )


def raise_internal_auth_unauthorized() -> NoReturn:
    """Raise the canonical internal-auth unauthorized error."""
    raise_api_error(
        status_code=401,
        code=ApiErrorCode.INTERNAL_AUTH_UNAUTHORIZED,
        message="Unauthorized",
    )


def raise_mcp_invalid_json() -> NoReturn:
    """Raise the canonical MCP invalid-JSON error."""
    raise_api_error(
        status_code=400,
        code=ApiErrorCode.MCP_INVALID_JSON,
        message="Invalid JSON",
    )


def raise_mcp_tool_name_required() -> NoReturn:
    """Raise the canonical MCP missing tool name error."""
    raise_api_error(
        status_code=400,
        code=ApiErrorCode.MCP_TOOL_NAME_REQUIRED,
        message="Tool name is required",
    )


def raise_mcp_tool_not_found() -> NoReturn:
    """Raise the canonical MCP tool not-found error."""
    raise_api_error(
        status_code=404,
        code=ApiErrorCode.MCP_TOOL_NOT_FOUND,
        message="Tool not found",
    )


def raise_mcp_tool_execution_failed() -> NoReturn:
    """Raise the canonical MCP tool execution failure error."""
    raise_api_error(
        status_code=500,
        code=ApiErrorCode.MCP_TOOL_EXECUTION_FAILED,
        message="Tool execution failed",
    )


def raise_mcp_resource_not_found() -> NoReturn:
    """Raise the canonical MCP resource not-found error."""
    raise_api_error(
        status_code=404,
        code=ApiErrorCode.MCP_RESOURCE_NOT_FOUND,
        message="Resource not found",
    )


def raise_mcp_prompt_not_found() -> NoReturn:
    """Raise the canonical MCP prompt not-found error."""
    raise_api_error(
        status_code=404,
        code=ApiErrorCode.MCP_PROMPT_NOT_FOUND,
        message="Prompt not found",
    )


def raise_outbound_adapter_not_found() -> NoReturn:
    """Raise the canonical outbound adapter not-found error."""
    raise_api_error(
        status_code=404,
        code=ApiErrorCode.OUTBOUND_ADAPTER_NOT_FOUND,
        message="Adapter not found",
    )


def raise_wecom_security_not_configured(missing: list[str]) -> NoReturn:
    """Raise the canonical WeCom missing webhook security configuration error."""
    raise_api_error(
        status_code=503,
        code=ApiErrorCode.WECOM_SECURITY_NOT_CONFIGURED,
        message=f"WeCom webhook security is not configured: {', '.join(missing)}",
    )


def raise_wecom_invalid_encoding_aes_key_length() -> NoReturn:
    """Raise the canonical WeCom EncodingAESKey length error."""
    raise_api_error(
        status_code=503,
        code=ApiErrorCode.WECOM_INVALID_ENCODING_AES_KEY_LENGTH,
        message="Invalid WeCom EncodingAESKey length",
    )


def raise_wecom_invalid_encoding_aes_key() -> NoReturn:
    """Raise the canonical WeCom EncodingAESKey decode error."""
    raise_api_error(
        status_code=503,
        code=ApiErrorCode.WECOM_INVALID_ENCODING_AES_KEY,
        message="Invalid WeCom EncodingAESKey",
    )


def raise_wecom_invalid_ciphertext() -> NoReturn:
    """Raise the canonical WeCom ciphertext error."""
    raise_api_error(
        status_code=403,
        code=ApiErrorCode.WECOM_INVALID_CIPHERTEXT,
        message="Invalid WeCom ciphertext",
    )


def raise_wecom_invalid_padding() -> NoReturn:
    """Raise the canonical WeCom padding error."""
    raise_api_error(
        status_code=403,
        code=ApiErrorCode.WECOM_INVALID_PADDING,
        message="Invalid WeCom padding",
    )


def raise_wecom_invalid_payload() -> NoReturn:
    """Raise the canonical WeCom payload shape error."""
    raise_api_error(
        status_code=403,
        code=ApiErrorCode.WECOM_INVALID_PAYLOAD,
        message="Invalid WeCom payload",
    )


def raise_wecom_invalid_message_length() -> NoReturn:
    """Raise the canonical WeCom message-length error."""
    raise_api_error(
        status_code=403,
        code=ApiErrorCode.WECOM_INVALID_MESSAGE_LENGTH,
        message="Invalid WeCom message length",
    )


def raise_wecom_corp_id_mismatch() -> NoReturn:
    """Raise the canonical WeCom corp_id mismatch error."""
    raise_api_error(
        status_code=403,
        code=ApiErrorCode.WECOM_CORP_ID_MISMATCH,
        message="WeCom corp_id mismatch",
    )


def raise_wecom_invalid_signature() -> NoReturn:
    """Raise the canonical WeCom invalid-signature error."""
    raise_api_error(
        status_code=403,
        code=ApiErrorCode.WECOM_INVALID_SIGNATURE,
        message="Invalid WeCom signature",
    )


def raise_wecom_missing_encrypted_payload() -> NoReturn:
    """Raise the canonical WeCom missing encrypted payload error."""
    raise_api_error(
        status_code=400,
        code=ApiErrorCode.WECOM_MISSING_ENCRYPTED_PAYLOAD,
        message="Missing encrypted WeCom payload",
    )


def raise_wecom_missing_message_type() -> NoReturn:
    """Raise the canonical WeCom missing message type error."""
    raise_api_error(
        status_code=400,
        code=ApiErrorCode.WECOM_MISSING_MESSAGE_TYPE,
        message="Missing WeCom message type",
    )


def raise_wecom_invalid_xml_payload() -> NoReturn:
    """Raise the canonical WeCom invalid XML payload error."""
    raise_api_error(
        status_code=400,
        code=ApiErrorCode.WECOM_INVALID_XML_PAYLOAD,
        message="Invalid WeCom XML payload",
    )


def raise_qa_run_not_found() -> NoReturn:
    """Raise the canonical QA run not-found error."""
    raise_api_error(
        status_code=404,
        code=ApiErrorCode.QA_RUN_NOT_FOUND,
        message="QA acceptance run not found",
    )


def raise_qa_run_timeout() -> NoReturn:
    """Raise the canonical QA run timeout error."""
    raise_api_error(
        status_code=504,
        code=ApiErrorCode.QA_RUN_TIMEOUT,
        message="QA acceptance run timed out",
    )


def raise_qa_run_failed(message: str) -> NoReturn:
    """Raise the canonical QA run execution failure error."""
    raise_api_error(
        status_code=500,
        code=ApiErrorCode.QA_RUN_FAILED,
        message=message,
    )


def raise_qa_run_list_failed() -> NoReturn:
    """Raise the canonical QA run list failure error."""
    raise_api_error(
        status_code=500,
        code=ApiErrorCode.QA_RUN_LIST_FAILED,
        message="Failed to list QA acceptance runs",
    )


def raise_qa_run_detail_failed() -> NoReturn:
    """Raise the canonical QA run detail failure error."""
    raise_api_error(
        status_code=500,
        code=ApiErrorCode.QA_RUN_DETAIL_FAILED,
        message="Failed to get QA acceptance run details",
    )


def raise_qa_stats_failed() -> NoReturn:
    """Raise the canonical QA stats failure error."""
    raise_api_error(
        status_code=500,
        code=ApiErrorCode.QA_STATS_FAILED,
        message="Failed to get QA acceptance statistics",
    )


def raise_pm_decomposition_not_found() -> NoReturn:
    """Raise the canonical PM decomposition not-found error."""
    raise_api_error(
        status_code=404,
        code=ApiErrorCode.PM_DECOMPOSITION_NOT_FOUND,
        message="Record not found",
    )


def raise_pm_config_failed() -> NoReturn:
    """Raise the canonical PM config read failure error."""
    raise_api_error(
        status_code=500,
        code=ApiErrorCode.PM_CONFIG_FAILED,
        message="Failed to get PM configuration. Please retry later.",
    )


def raise_pm_config_refresh_failed() -> NoReturn:
    """Raise the canonical PM config refresh failure error."""
    raise_api_error(
        status_code=500,
        code=ApiErrorCode.PM_CONFIG_REFRESH_FAILED,
        message="Failed to refresh PM configuration. Please retry later.",
    )


def raise_pm_alerts_failed() -> NoReturn:
    """Raise the canonical PM alert-list failure error."""
    raise_api_error(
        status_code=500,
        code=ApiErrorCode.PM_ALERTS_FAILED,
        message="Failed to get PM alerts. Please retry later.",
    )


def raise_pm_daily_report_failed() -> NoReturn:
    """Raise the canonical PM daily-report failure error."""
    raise_api_error(
        status_code=500,
        code=ApiErrorCode.PM_DAILY_REPORT_FAILED,
        message="Failed to generate daily report. Please retry later.",
    )


def raise_pm_weekly_report_failed() -> NoReturn:
    """Raise the canonical PM weekly-report failure error."""
    raise_api_error(
        status_code=500,
        code=ApiErrorCode.PM_WEEKLY_REPORT_FAILED,
        message="Failed to generate weekly report. Please retry later.",
    )


def raise_pm_decomposition_retry_failed(
    *,
    status_code: int = 400,
    message: str = "Failed to retry decomposition. Please retry later.",
) -> NoReturn:
    """Raise the canonical PM decomposition retry failure error."""
    raise_api_error(
        status_code=status_code,
        code=ApiErrorCode.PM_DECOMPOSITION_RETRY_FAILED,
        message=message,
    )


def raise_pm_decomposition_forbidden(message: str) -> NoReturn:
    """Raise the canonical PM decomposition forbidden-state error."""
    raise_api_error(
        status_code=403,
        code=ApiErrorCode.PM_DECOMPOSITION_FORBIDDEN,
        message=message,
    )


def raise_pm_decomposition_unavailable(*, status_code: int = 404) -> NoReturn:
    """Raise the canonical PM decomposition unavailable-state error."""
    raise_api_error(
        status_code=status_code,
        code=ApiErrorCode.PM_DECOMPOSITION_UNAVAILABLE,
        message="Record not found or status is not pending",
    )
