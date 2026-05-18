"""Application use cases for requirement analysis."""

from typing import Protocol

from .analyzer import AnalysisResult


class RequirementAnalysisRepository(Protocol):
    async def get_by_id(self, requirement_id: str) -> object | None:
        """Return one requirement by ID."""


class RequirementAnalyzerPort(Protocol):
    async def analyze(
        self,
        title: str,
        description: str,
        source_quote: str | None = None,
        existing_requirements: list[dict] | None = None,
    ) -> AnalysisResult:
        """Analyze requirement text without an LLM."""

    async def analyze_with_llm(
        self,
        title: str,
        description: str,
        source_quote: str | None = None,
        context: str | None = None,
    ) -> AnalysisResult:
        """Analyze requirement text with an LLM."""


class RequirementAnalysisUseCase:
    """Application use case for requirement analysis workflows."""

    def __init__(
        self,
        requirement_repository: RequirementAnalysisRepository,
        analyzer: RequirementAnalyzerPort,
    ):
        self._requirements = requirement_repository
        self._analyzer = analyzer

    async def analyze_requirement(
        self,
        requirement_id: str,
        *,
        use_llm: bool = False,
    ) -> AnalysisResult | None:
        requirement = await self._requirements.get_by_id(requirement_id)
        if requirement is None:
            return None

        return await self.analyze_text(
            title=requirement.title,
            description=requirement.description or "",
            source_quote=requirement.source_quote,
            use_llm=use_llm,
        )

    async def analyze_text(
        self,
        *,
        title: str,
        description: str,
        source_quote: str | None = None,
        use_llm: bool = False,
    ) -> AnalysisResult:
        if use_llm:
            return await self._analyzer.analyze_with_llm(
                title=title,
                description=description,
                source_quote=source_quote,
            )
        return await self._analyzer.analyze(
            title=title,
            description=description,
            source_quote=source_quote,
        )
