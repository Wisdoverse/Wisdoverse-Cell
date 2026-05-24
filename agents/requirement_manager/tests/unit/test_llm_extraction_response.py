"""Unit tests for the Requirement LLM extraction response ACL."""

from __future__ import annotations

import pytest

from agents.requirement_manager.core.llm_extraction_response import (
    LLMExtractionResponse,
)


def test_llm_extraction_response_translates_markdown_json_to_local_vocabulary() -> None:
    response = LLMExtractionResponse.from_text(
        """
        ```json
        {
          "requirements": [
            {
              "title": "Offline recording",
              "description": "Import offline recordings",
              "category": "feature",
              "priority": "高",
              "source_quote": "Need offline recording"
            }
          ],
          "decisions": [{"content": "Ship MVP", "decided_by": "PM"}],
          "open_questions": [{"question": "Which file format?", "context": "Import"}]
        }
        ```
        """
    )

    assert response.requirements[0].title == "Offline recording"
    assert response.requirements[0].category == "功能"
    assert response.requirements[0].priority == "high"
    assert response.decisions[0].content == "Ship MVP"
    assert response.open_questions[0].question == "Which file format?"


def test_llm_extraction_response_ignores_non_mapping_items() -> None:
    response = LLMExtractionResponse.from_text(
        """
        {
          "requirements": ["bad", {"title": "Security", "category": "security"}],
          "decisions": {},
          "open_questions": null
        }
        """
    )

    assert len(response.requirements) == 1
    assert response.requirements[0].title == "Security"
    assert response.requirements[0].description == ""
    assert response.requirements[0].category == "安全"
    assert response.decisions == ()
    assert response.open_questions == ()


def test_llm_extraction_response_raises_for_invalid_json() -> None:
    with pytest.raises(ValueError):
        LLMExtractionResponse.from_text("not json")
