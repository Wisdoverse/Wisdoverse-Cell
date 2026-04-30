"""Tests for shared.integrations.feishu.errors — FeishuAPIError, handle_feishu_response, feishu_error_handler."""

import pytest

from shared.integrations.feishu.errors import (
    FeishuAPIError,
    feishu_error_handler,
    handle_feishu_response,
)


class TestFeishuAPIError:
    """Unit tests for FeishuAPIError exception class."""

    def test_construct__with_all_fields__formats_message(self):
        error = FeishuAPIError(code=99991, message="Token expired", details={"extra": "info"})

        assert error.code == 99991
        assert error.message == "Token expired"
        assert error.details == {"extra": "info"}
        assert str(error) == "FeishuAPIError [99991]: Token expired"

    def test_construct__defaults__code_zero_empty_message(self):
        error = FeishuAPIError()

        assert error.code == 0
        assert error.message == ""
        assert error.details == {}
        assert str(error) == "FeishuAPIError [0]: "

    def test_format_message__includes_code_and_message(self):
        error = FeishuAPIError(code=40003, message="Invalid app_id")

        assert error._format_message() == "FeishuAPIError [40003]: Invalid app_id"

    def test_from_response__with_msg_key(self):
        response_data = {"code": 99992, "msg": "Rate limited"}
        error = FeishuAPIError.from_response(response_data)

        assert error.code == 99992
        assert error.message == "Rate limited"
        assert error.details == response_data

    def test_from_response__with_message_key__fallback(self):
        response_data = {"code": 50001, "message": "Internal server error"}
        error = FeishuAPIError.from_response(response_data)

        assert error.code == 50001
        assert error.message == "Internal server error"
        assert error.details == response_data

    def test_from_response__missing_keys__defaults(self):
        response_data = {}
        error = FeishuAPIError.from_response(response_data)

        assert error.code == 0
        assert error.message == "Unknown error"
        assert error.details == {}

    @pytest.mark.parametrize(
        ("code", "expected"),
        [
            pytest.param(99991663, True, id="token_expired"),
            pytest.param(99991664, True, id="token_invalid"),
            pytest.param(99991668, True, id="rate_limited"),
            pytest.param(12345, False, id="arbitrary_non_retryable"),
            pytest.param(0, False, id="success_code"),
        ],
    )
    def test_is_retryable__parametrized(self, code: int, expected: bool):
        error = FeishuAPIError(code=code)

        assert error.is_retryable is expected


class TestHandleFeishuResponse:
    """Unit tests for handle_feishu_response utility."""

    def test_success__returns_data(self):
        response_data = {"code": 0, "data": {"message_id": "msg_abc123"}}

        result = handle_feishu_response(response_data)

        assert result == {"message_id": "msg_abc123"}

    def test_error__raises_feishu_api_error(self):
        response_data = {"code": 99991, "msg": "Invalid token"}

        with pytest.raises(FeishuAPIError) as exc_info:
            handle_feishu_response(response_data)

        assert exc_info.value.code == 99991
        assert exc_info.value.message == "Invalid token"
        assert exc_info.value.details == response_data


class TestFeishuErrorHandler:
    """Unit tests for feishu_error_handler decorator."""

    @pytest.mark.asyncio
    async def test_success__passthrough(self):
        @feishu_error_handler("send_message")
        async def successful_op():
            return {"message_id": "msg_ok"}

        result = await successful_op()

        assert result == {"message_id": "msg_ok"}

    @pytest.mark.asyncio
    async def test_feishu_api_error__propagated_directly(self):
        original_error = FeishuAPIError(code=500, message="Server error")

        @feishu_error_handler("send_message")
        async def failing_op():
            raise original_error

        with pytest.raises(FeishuAPIError) as exc_info:
            await failing_op()

        assert exc_info.value is original_error
        assert exc_info.value.code == 500
        assert exc_info.value.message == "Server error"

    @pytest.mark.asyncio
    async def test_generic_exception__wrapped_as_feishu_api_error(self):
        @feishu_error_handler("create_doc")
        async def failing_op():
            raise ValueError("connection reset")

        with pytest.raises(FeishuAPIError) as exc_info:
            await failing_op()

        assert exc_info.value.code == -1
        assert "connection reset" in exc_info.value.message
        assert isinstance(exc_info.value.__cause__, ValueError)

    @pytest.mark.asyncio
    async def test_operation_name__preserved_in_wrapped_error(self):
        @feishu_error_handler("upload_image")
        async def failing_op():
            raise RuntimeError("disk full")

        with pytest.raises(FeishuAPIError) as exc_info:
            await failing_op()

        assert exc_info.value.message == "upload_image failed: disk full"
