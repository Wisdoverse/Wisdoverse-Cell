import pytest

from shared.infra.tool_validator import ToolValidationError, ToolValidator


@pytest.fixture
def validator():
    tools = [
        {
            "name": "search",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
            },
        },
        {
            "name": "calculate",
            "input_schema": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
            },
        },
    ]
    return ToolValidator(registered_tools=tools)


class TestToolValidation:
    def test_rejects_unknown_tool(self, validator):
        tool_use = {"type": "tool_use", "name": "hack_system", "input": {}}
        with pytest.raises(ToolValidationError, match="unknown_tool"):
            validator.validate_tool_use(tool_use)

    def test_accepts_known_tool(self, validator):
        tool_use = {"type": "tool_use", "name": "search", "input": {"query": "test"}}
        validator.validate_tool_use(tool_use)

    def test_rejects_oversized_input(self, validator):
        tool_use = {"type": "tool_use", "name": "search", "input": {"query": "x" * 200_000}}
        with pytest.raises(ToolValidationError, match="tool_input_too_large"):
            validator.validate_tool_use(tool_use)

    def test_accepts_empty_input(self, validator):
        tool_use = {"type": "tool_use", "name": "search", "input": {}}
        validator.validate_tool_use(tool_use)
