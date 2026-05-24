"""Requirement-local ACL for LLM extraction responses."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class LLMExtractedRequirement:
    """Domain-friendly requirement fields parsed from an LLM response."""

    title: str
    description: str
    category: str
    priority: str
    source_quote: str | None


@dataclass(frozen=True, slots=True)
class LLMExtractedDecision:
    """Domain-friendly decision fields parsed from an LLM response."""

    content: str
    decided_by: str | None


@dataclass(frozen=True, slots=True)
class LLMExtractedQuestion:
    """Domain-friendly open-question fields parsed from an LLM response."""

    question: str
    context: str | None


@dataclass(frozen=True, slots=True)
class LLMExtractionResponse:
    """Translated Requirement extraction response from the LLM Gateway."""

    requirements: tuple[LLMExtractedRequirement, ...]
    decisions: tuple[LLMExtractedDecision, ...]
    open_questions: tuple[LLMExtractedQuestion, ...]

    @classmethod
    def from_text(cls, response: str) -> "LLMExtractionResponse":
        """Parse a raw LLM response into local Requirement vocabulary."""
        cleaned = _strip_markdown_json_fence(response)
        data = json.loads(cleaned)
        if not isinstance(data, Mapping):
            return cls.empty()

        return cls(
            requirements=tuple(
                _requirement_from_mapping(requirement)
                for requirement in _mapping_items(data.get("requirements"))
            ),
            decisions=tuple(
                _decision_from_mapping(decision)
                for decision in _mapping_items(data.get("decisions"))
            ),
            open_questions=tuple(
                _question_from_mapping(question)
                for question in _mapping_items(data.get("open_questions"))
            ),
        )

    @classmethod
    def empty(cls) -> "LLMExtractionResponse":
        """Return an empty translated response."""
        return cls(requirements=(), decisions=(), open_questions=())


def _strip_markdown_json_fence(response: str) -> str:
    cleaned = response.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def _mapping_items(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _requirement_from_mapping(
    requirement: Mapping[str, Any],
) -> LLMExtractedRequirement:
    return LLMExtractedRequirement(
        title=_text(requirement.get("title")),
        description=_text(requirement.get("description")),
        category=_normalize_category(_text(requirement.get("category"), default="功能")),
        priority=_normalize_priority(_text(requirement.get("priority"), default="medium")),
        source_quote=_optional_text(requirement.get("source_quote")),
    )


def _decision_from_mapping(decision: Mapping[str, Any]) -> LLMExtractedDecision:
    return LLMExtractedDecision(
        content=_text(decision.get("content")),
        decided_by=_optional_text(decision.get("decided_by")),
    )


def _question_from_mapping(question: Mapping[str, Any]) -> LLMExtractedQuestion:
    return LLMExtractedQuestion(
        question=_text(question.get("question")),
        context=_optional_text(question.get("context")),
    )


def _normalize_category(category: str) -> str:
    normalized = category.lower()
    category_map = {
        "功能": "功能",
        "feature": "功能",
        "性能": "性能",
        "performance": "性能",
        "硬件": "硬件",
        "hardware": "硬件",
        "集成": "集成",
        "integration": "集成",
        "ui": "UI",
        "UI": "UI",
        "用户界面": "UI",
        "安全": "安全",
        "security": "安全",
    }
    return category_map.get(category, category_map.get(normalized, "其他"))


def _normalize_priority(priority: str) -> str:
    priority_map = {
        "high": "high",
        "高": "high",
        "medium": "medium",
        "中": "medium",
        "low": "low",
        "低": "low",
    }
    return priority_map.get(priority.lower(), "medium")


def _text(value: Any, *, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _optional_text(value: Any | None) -> str | None:
    if value is None:
        return None
    return str(value)


__all__ = [
    "LLMExtractedDecision",
    "LLMExtractedQuestion",
    "LLMExtractedRequirement",
    "LLMExtractionResponse",
]
