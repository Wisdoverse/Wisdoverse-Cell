from unittest.mock import patch

from shared.infra.audit_log import AuditAction, audit_log


def test_audit_log_emits_structured_log():
    with patch("shared.infra.audit_log.logger") as mock_logger:
        audit_log(
            action=AuditAction.LLM_CALL,
            agent_id="requirement-manager",
            detail={"model": "claude-sonnet-4-20250514", "tokens": 1500},
        )
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert call_args[0][0] == "audit"


def test_audit_log_includes_all_fields():
    with patch("shared.infra.audit_log.logger") as mock_logger:
        audit_log(
            action=AuditAction.EVENT_HANDLED,
            agent_id="chat-agent",
            detail={"event_type": "chat.pm-query"},
            trace_id="trace-abc",
        )
        kwargs = mock_logger.info.call_args[1]
        assert kwargs["action"] == "event_handled"
        assert kwargs["agent_id"] == "chat-agent"
        assert kwargs["trace_id"] == "trace-abc"


def test_audit_log_handles_no_detail():
    with patch("shared.infra.audit_log.logger") as mock_logger:
        audit_log(
            action=AuditAction.RATE_LIMITED,
            agent_id="sync-module",
        )
        mock_logger.info.assert_called_once()
        kwargs = mock_logger.info.call_args[1]
        assert kwargs["action"] == "rate_limited"
        assert kwargs["trace_id"] == ""
